"""Complete a certificate chain the server forgot to send, without turning verification off.

`srv.cnpb.ro` — the București chamber's own file server, and the only place its studies are
published — serves a valid certificate and omits the intermediate that signs it. The leaf is
genuine: `O=CAMERA NOTARILOR PUBLICI BUCUREȘTI`, issued by DigiCert's GeoTrust TLS RSA CA G1.
The server simply does not send that CA, so a client that has the root but not the intermediate
cannot build a path and fails with *unable to get local issuer certificate*.

The tempting fix is `verify=False`, and it is the wrong one. These documents become published
numbers; fetching them over a connection nobody authenticated means a proxy could rewrite the
price of every square metre in Bucharest and nothing would notice.

The right fix is the one browsers already do. An X.509 certificate carries an **Authority
Information Access** extension naming the URL of its own issuer, so a client that is missing an
intermediate can go and get it. Python's ssl module does not do this by itself. This does:

1. connect once with verification off, **only to read the certificate the server presents** —
   nothing is trusted on that connection and no content is fetched over it;
2. read the AIA `CA Issuers` URL out of that certificate;
3. fetch the intermediate from it and add it to a context that still has the system roots;
4. reconnect **with verification on** and the chain now complete.

Step 4 is the load-bearing one. If the presented certificate is not in fact signed by a
trusted root — self-signed, expired, wrong host — the retry fails exactly as it should. All
this does is supply a link the server should have supplied, and hardcodes no CA of its own, so
it keeps working when DigiCert rotates that intermediate.
"""

from __future__ import annotations

import re
import ssl
import subprocess
import urllib.request
from functools import lru_cache
from urllib.parse import urlparse

UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"


def _presented_certificate(host: str, port: int) -> str:
    """The leaf the server sends, in PEM, read over an unverified connection.

    Unverified on purpose and harmless: nothing here is trusted and no study is downloaded
    over it. The certificate read is the thing about to be *checked*, not something relied on.
    """
    context = ssl._create_unverified_context()  # noqa: S323
    import socket  # noqa: PLC0415

    with socket.create_connection((host, port), timeout=60) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    return ssl.DER_cert_to_PEM_cert(der)


def _issuer_url(pem: str) -> str | None:
    """The AIA "CA Issuers" URL, read with openssl because the stdlib does not expose it."""
    done = subprocess.run(  # noqa: S603
        ["openssl", "x509", "-noout", "-text"],
        input=pem, capture_output=True, text=True, check=False,
    )
    found = re.search(r"CA Issuers - URI:(\S+)", done.stdout)
    return found.group(1) if found else None


def _as_pem(body: bytes) -> str:
    if body.lstrip().startswith(b"-----BEGIN"):
        return body.decode("ascii")
    done = subprocess.run(  # noqa: S603
        ["openssl", "x509", "-inform", "DER"], input=body, capture_output=True, check=False,
    )
    return done.stdout.decode("ascii")


@lru_cache(maxsize=8)
def context_for(host: str, port: int = 443) -> ssl.SSLContext | None:
    """A verifying context that can validate `host`, or None if the default already can.

    Cached per host: the handshake and the intermediate fetch are the same answer every time,
    and a study import asks for the same host once per document.
    """
    default = ssl.create_default_context()
    import socket  # noqa: PLC0415

    try:
        with socket.create_connection((host, port), timeout=60) as raw:
            with default.wrap_socket(raw, server_hostname=host):
                return None
    except ssl.SSLCertVerificationError:
        pass

    url = _issuer_url(_presented_certificate(host, port))
    if not url:
        raise SystemExit(
            f"{host} presents a certificate that does not verify and names no issuer URL. "
            "Not fetching over an unauthenticated connection."
        )
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        intermediate = _as_pem(response.read())
    if not intermediate.strip():
        raise SystemExit(f"{host}: could not read the intermediate certificate from {url}")

    context = ssl.create_default_context()
    context.load_verify_locations(cadata=intermediate)
    # Proof, before anything is downloaded: the chain now validates with verification ON.
    with socket.create_connection((host, port), timeout=60) as raw:
        with context.wrap_socket(raw, server_hostname=host):
            pass
    print(f"  completed {host}'s certificate chain from its own AIA pointer ({url})")
    return context


def opener_for(url: str):
    """A urllib opener that can verify this URL's host, completing the chain if it must."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return urllib.request.build_opener()
    context = context_for(parsed.hostname, parsed.port or 443)
    if context is None:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

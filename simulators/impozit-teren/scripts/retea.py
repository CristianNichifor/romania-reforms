"""Talking to INS TEMPO, which is up most of the time.

Three importers here read from `statistici.insse.ro:8077`, each with its own copy of the same
twenty lines, and each opening a single connection with `urlopen` and no second chance. That
is fine on a laptop, where a failed run is retyped, and it is not fine in CI: a merge to main
failed on

    File ".../import_lemn_recoltat.py", line 68, in metadata
        with urllib.request.urlopen(request, timeout=120) as response:
    urllib.error.URLError: <urlopen error timed out>

which is not a defect in the import, in the data, or in the change being merged. The service
was slow for two minutes. Nothing downstream had been touched.

**The failure modes are not all exceptions.** Over its cell budget TEMPO answers *200 with an
empty body* rather than an error, so "the request returned" is not the same as "the request
worked" — a check for a body is part of the retry, not a separate validation. The same shape
of silent-success is why the land register's importer counts localities before it writes.

**Retried here rather than around the script.** `import_fond_funciar.py --all` already retries
whole counties by re-running itself as a subprocess, which works but can only retry work that
was split into counties in the first place: the matrix definition every one of those counties
needs is fetched once, before the split, and a failure there fails all forty-two. So the retry
belongs on the request.

**Cheaper than retrying: not asking.** The matrix definitions are committed under `sources/`,
so a CI run reads them off disk and never calls this at all. Retrying is what happens on a
fresh definition, a new matrix, or `--refresh` — the paths where a network call is genuinely
unavoidable.

`read` is not about TEMPO and is used from `build_valoare_teren.py` for the ECB reference
rates, which are the opposite case: they change daily, so they cannot be committed, so that
one is fetched on every run and has nothing but the retry between it and a failed build.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
TEMPO = "http://statistici.insse.ro:8077/tempo-ins"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"

# Three tries, not ten. The failure this exists for lasts seconds to a couple of minutes; a
# service that is genuinely down should fail the build in a few minutes rather than hold a
# runner for an hour, and the waits are long enough to be waits rather than a fast loop that
# only asks the same overloaded server three times in a row.
ATTEMPTS = 3
BACKOFF = (5.0, 20.0)


class TempoUnavailable(RuntimeError):
    """TEMPO did not answer usefully, after every attempt."""


def read(
    request: urllib.request.Request,
    *,
    timeout: float,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    opener: Callable[..., object] = urllib.request.urlopen,
    log: Callable[[str], None] = print,
) -> bytes:
    """One request, up to `attempts` times, returning the body once there is one.

    An empty body counts as a failure: it is how TEMPO reports being over its cell budget,
    and a caller that accepted it would go on to parse zero rows and write an empty file —
    which is the one outcome worse than the build stopping here.
    """
    last = ""
    for attempt in range(attempts):
        try:
            with opener(request, timeout=timeout) as response:  # noqa: S310
                body = response.read()
            if body:
                if attempt:
                    log(f"  {request.full_url}: ok la încercarea {attempt + 1}")
                return body
            last = "răspuns gol (TEMPO peste bugetul de celule)"
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = str(error)
        if attempt < attempts - 1:
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            log(f"  {request.full_url}: {last}; reîncercare în {wait:.0f}s")
            sleep(wait)
    raise TempoUnavailable(f"{request.full_url}: {last} (după {attempts} încercări)")


def tempo_metadata(matrix: str, *, timeout: float = 120, **kwargs: object) -> dict:
    """The matrix definition — from `sources/` if it is there, from TEMPO if it is not.

    Cached on disk and committed, because it is a vocabulary rather than an observation: it
    changes when INS restructures a matrix, which is rare and which changes the import
    anyway. The daily-moving file next to it — the ECB rates — is deliberately not committed
    for the opposite reason.

    Stored gzipped, like the consolidated Fiscal Code beside it: the three definitions are
    516 KB of pretty-printed JSON and 103 KB compressed, and the repository has under two
    megabytes of headroom against its own size ceiling. A plain `.json` is still read if one
    is lying there, which is what a hand-run `--refresh` or an older checkout leaves.
    """
    stem = ROOT / "sources" / f"ins-{matrix.lower()}-metadata.json"
    packed = stem.with_suffix(".json.gz")
    if packed.exists():
        with gzip.open(packed, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    if not stem.exists():
        print(f"downloading {TEMPO}/matrix/{matrix} ...")
        request = urllib.request.Request(f"{TEMPO}/matrix/{matrix}", headers={"User-Agent": UA})
        body = read(request, timeout=timeout, **kwargs)  # type: ignore[arg-type]
        packed.parent.mkdir(parents=True, exist_ok=True)
        # mtime pinned, so re-fetching an unchanged definition produces an identical file
        # rather than a diff made entirely of the moment it was downloaded.
        with gzip.GzipFile(packed, "wb", mtime=0) as handle:
            handle.write(body)
        return json.loads(body)
    return json.loads(stem.read_text(encoding="utf-8"))


def tempo_table(matrix: str, meta: dict, arr: list, *, timeout: float = 300, **kwargs: object) -> str:
    """One query's answer, as the HTML table TEMPO replies with.

    The options are posted back verbatim rather than as their ids: the endpoint deserialises
    each entry into a typed object and rejects a bare number, which is why every caller reads
    the metadata before it can ask a question.
    """
    body = json.dumps(
        {
            "language": "ro",
            "arr": arr,
            "matrixName": meta["matrixName"],
            "matrixDetails": meta["details"],
        }
    ).encode()
    request = urllib.request.Request(
        f"{TEMPO}/matrix/{matrix}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    return json.loads(read(request, timeout=timeout, **kwargs))["resultTable"]  # type: ignore[arg-type]

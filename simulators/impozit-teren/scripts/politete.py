"""A crawler that cannot be rude, because the rudeness is what the code refuses to do.

Every importer in this directory so far reads an API, a statistical office or a PDF that
somebody published in order to be read. This one is different: it reads a commercial listing
site, which published its pages for humans and merely tolerates machines. The difference is
not legal boilerplate — it is that the site can say no, in several ways, and a crawler that
does not listen is the reason sites stop publishing.

So the politeness is not a convention this file follows. It is the only thing it offers.

**robots.txt is a hard gate, not advice.** `allowed()` parses the host's file and `get()`
raises on a disallowed path rather than logging and continuing. There is no override flag. A
crawler with an override flag is a crawler that will be run with the override flag.

**One request at a time, per host, with a floor under the gap.** No threads, no connection
pool, no concurrency parameter. The delay honours `Crawl-delay` when the host states one and
otherwise sits at `DEFAULT_DELAY`, jittered — a metronome is a signature, and a burst is the
thing that gets a range blocked.

**A refusal ends the run.** 429 and 503 are the polite forms of "not now": the first two get a
long backoff, the third aborts. 403 aborts immediately, because it is not a transient failure,
it is an answer. Nothing here retries its way past a block, and there is deliberately no code
for rotating a user agent, using a proxy, or carrying a browser's cookies — those exist only to
defeat a decision the site already made.

**It says who it is.** One user agent, never varied, carrying a URL where the project can be
read and its author contacted. If somebody at the other end wonders what this traffic is, the
answer is one click away. That is also the pragmatic move: identified research traffic that
behaves gets left alone, and disguised traffic that behaves gets blocked with everything else.

**Every response is kept, so the same page is never asked for twice.** The cache is the whole
reason a slow crawler is affordable: a second run costs nothing, a parse that has to change
costs nothing, and the site pays exactly once for each page no matter how many times the
importer is debugged. Cached bodies are gzipped under `sources/<host>/`, which is not committed
— that would be a mirror of somebody else's site, which is a different thing from a dataset of
statistics derived from it.

**And there is a ceiling on the whole run.** `budget` is the number of live requests a single
invocation may make. A bug in a paging loop is otherwise indistinguishable from an attack.

Usage:
    fetcher = Politete(cache=ROOT / "sources" / "storia", delay=5.0, budget=200)
    body = fetcher.get("https://www.storia.ro/ro/rezultate/vanzare/teren/bihor/alesd")
    print(fetcher.report())
"""

from __future__ import annotations

import gzip
import hashlib
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

# Who this is. One string, never varied, with somewhere to look it up.
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"

# Seconds between live requests to one host when the host does not state a Crawl-delay.
# Five is not derived from anything the site publishes; it is slow enough that a full pass over
# a national listing site is an overnight job rather than a spike, which is the point.
DEFAULT_DELAY = 5.0

# How long to wait after the host says "not now", and how many times to accept that answer
# before stopping. The second number is the important one: a crawler that retries indefinitely
# through a rate limit is a crawler that has stopped taking no for an answer.
BACKOFF = (60.0, 300.0)
MAX_REFUSALS = 3

TIMEOUT = 60.0


class Blocked(Exception):
    """The host said no. Not a transient failure, and not something to retry through."""


class Disallowed(Exception):
    """robots.txt forbids this path. Raised rather than warned about, and not overridable."""


class BudgetSpent(Exception):
    """This run has made as many live requests as it was allowed."""


class Politete:
    def __init__(
        self,
        cache: Path,
        *,
        delay: float = DEFAULT_DELAY,
        budget: int = 500,
        user_agent: str = UA,
        log=lambda message: print(message, file=sys.stderr),
    ) -> None:
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.budget = budget
        self.user_agent = user_agent
        self.log = log
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last: dict[str, float] = {}
        self.fetched = 0
        self.from_cache = 0
        self.refusals = 0

    # ---- robots ---------------------------------------------------------------------

    def _rules(self, url: str) -> urllib.robotparser.RobotFileParser:
        """The host's robots.txt, fetched once and remembered for the run.

        Fetched with `urlopen` directly and not through `get`: the gate cannot ask itself for
        permission. It is the one request this class makes without consulting anything, and it
        is the request that makes every other one legitimate.
        """
        host = urllib.parse.urlsplit(url).netloc
        if host not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            robots = f"{urllib.parse.urlsplit(url).scheme}://{host}/robots.txt"
            request = urllib.request.Request(robots, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
                    parser.parse(response.read().decode("utf-8", "replace").splitlines())
                self.log(f"  robots.txt read for {host}")
            except urllib.error.HTTPError as error:
                # RFC 9309 §2.3.1 says what each answer means, and the three cases are
                # genuinely different rather than three flavours of failure.
                #
                # 401 and 403 are the host refusing to show its rules, which is refusing. An
                # earlier version of this method treated *every* failure that way, which is
                # conservative in the direction that sounds safe and is simply wrong: most of
                # the web has no robots.txt at all, and e-licitatie.ro — a public procurement
                # portal that publishes an API called `api-pub` — answers 404. Refusing it
                # would have been the crawler inventing a prohibition nobody stated.
                if error.code in (401, 403):
                    raise Blocked(f"{robots} answered {error.code}; the host declines") from error
                if 400 <= error.code < 500:
                    self.log(f"  no robots.txt for {host} ({error.code}) — nothing is forbidden")
                    parser.parse([])
                    parser.allow_all = True
                else:
                    # 5xx is the server being broken, not the site being open. Trying again
                    # later is the polite reading; assuming consent is not.
                    raise Blocked(
                        f"{robots} answered {error.code}; not assuming consent"
                    ) from error
            except urllib.error.URLError as error:
                raise Blocked(f"cannot reach {robots}: {error}") from error
            self._robots[host] = parser
        return self._robots[host]

    def allowed(self, url: str) -> bool:
        return self._rules(url).can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float:
        """The host's own figure when it states one, never below this run's floor."""
        stated = self._rules(url).crawl_delay(self.user_agent)
        return max(self.delay, float(stated)) if stated else self.delay

    # ---- cache ----------------------------------------------------------------------

    def _path(self, url: str) -> Path:
        host = urllib.parse.urlsplit(url).netloc
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.cache / host / f"{digest}.gz"

    def cached(self, url: str) -> str | None:
        raw = self.cached_bytes(url)
        return None if raw is None else raw.decode("utf-8", "replace")

    def cached_bytes(self, url: str) -> bytes | None:
        path = self._path(url)
        if not path.exists():
            return None
        with gzip.open(path, "rb") as handle:
            return handle.read()

    def _store(self, url: str, body: bytes) -> None:
        path = self._path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        # mtime pinned so a re-fetch of unchanged content produces an identical file, the same
        # way the INS metadata caches are written.
        with gzip.GzipFile(path, "wb", mtime=0) as raw:
            raw.write(body)

    # ---- the one method that touches the network ------------------------------------

    def get(self, url: str, *, refresh: bool = False) -> str:
        """The page as text. Most sources are HTML or XML; spreadsheets want `get_bytes`."""
        return self.get_bytes(url, refresh=refresh).decode("utf-8", "replace")

    def get_bytes(self, url: str, *, refresh: bool = False) -> bytes:
        """The response, from disk if it is there and from the host at most once if it is not.

        Bytes rather than text is the honest primitive: half of what a public body publishes is
        a spreadsheet, and the ANCPI sales files arrive as XLSX beside CSVs written in
        windows-1250. Decoding at the door would corrupt the first and guess wrong at the
        second, so the caller decides what the payload is.
        """
        if not refresh:
            body = self.cached_bytes(url)
            if body is not None:
                self.from_cache += 1
                return body

        if not self.allowed(url):
            raise Disallowed(f"robots.txt forbids {url}")
        if self.fetched >= self.budget:
            raise BudgetSpent(f"{self.fetched} live requests made, which was the budget")

        host = urllib.parse.urlsplit(url).netloc
        wait = self.crawl_delay(url)
        since = time.monotonic() - self._last.get(host, 0.0)
        if since < wait:
            # Jittered. A request exactly every five seconds is a signature; a request every
            # five to seven is traffic.
            time.sleep(wait - since + random.uniform(0, wait * 0.4))

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ro,en;q=0.8",
            },
        )
        for attempt in range(len(BACKOFF) + 1):
            self._last[host] = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
                    body = response.read()
                self.fetched += 1
                self._store(url, body)
                return body
            except urllib.error.HTTPError as error:
                if error.code in (403, 401):
                    # An answer, not a hiccup. Nothing in this file tries to get around it.
                    raise Blocked(f"{error.code} for {url}; the host has declined") from error
                if error.code in (429, 503) and attempt < len(BACKOFF):
                    self.refusals += 1
                    if self.refusals >= MAX_REFUSALS:
                        raise Blocked(
                            f"{self.refusals} rate-limit responses; stopping rather than "
                            "pressing on"
                        ) from error
                    pause = BACKOFF[attempt]
                    self.log(f"  {error.code} — waiting {pause:.0f}s ({url})")
                    time.sleep(pause)
                    continue
                if error.code == 404:
                    raise
                raise Blocked(f"HTTP {error.code} for {url}") from error
            except urllib.error.URLError as error:
                if attempt < len(BACKOFF):
                    self.log(f"  {error} — waiting {BACKOFF[attempt]:.0f}s")
                    time.sleep(BACKOFF[attempt])
                    continue
                raise
        raise Blocked(f"gave up on {url}")

    def report(self) -> str:
        return (
            f"{self.fetched} live requests, {self.from_cache} from cache, "
            f"{self.refusals} rate-limit answers, budget {self.budget}"
        )

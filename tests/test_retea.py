"""The network layer under the INS importers, and the caches that keep it from being used.

A merge to main failed on `urllib.error.URLError: <urlopen error timed out>` inside
`import_lemn_recoltat.metadata`, on a change that touched neither the importer nor its data.
Nothing was wrong with the build; INS TEMPO was slow for two minutes. These are the two
things that stop it happening again — the request is retried, and the file it asks for is
committed so that CI does not ask at all — and they are tested separately because either one
can be undone without the other noticing.

No test here touches the network. The opener is injected, which is the only way to assert
what happens on a timeout without waiting for one.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "simulators" / "impozit-teren" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import retea  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def opener_for(*answers: object):
    """An opener that hands back one answer per call, raising the ones that are exceptions."""
    remaining = list(answers)

    def opener(request: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        answer = remaining.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)

    return opener


@pytest.fixture()
def request_() -> urllib.request.Request:
    return urllib.request.Request("http://statistici.insse.ro:8077/tempo-ins/matrix/AGR306A")


def test_a_timeout_is_not_the_answer(request_):
    """The exact failure that failed the merge: first attempt times out, second works."""
    waited: list[float] = []
    body = retea.read(
        request_,
        timeout=1,
        opener=opener_for(urllib.error.URLError("timed out"), b"{}"),
        sleep=waited.append,
        log=lambda _: None,
    )
    assert body == b"{}"
    assert waited, "a retry that does not wait is three requests to the same busy server"


def test_an_empty_body_is_a_failure_and_not_a_result(request_):
    """TEMPO answers 200 with nothing when it is over its cell budget.

    A caller that accepted that would parse zero rows and write an empty file, which is worse
    than the build stopping — so the empty answer has to be retried like an error, not
    returned like data.
    """
    body = retea.read(
        request_,
        timeout=1,
        opener=opener_for(b"", b"<table>"),
        sleep=lambda _: None,
        log=lambda _: None,
    )
    assert body == b"<table>"


def test_a_service_that_is_really_down_still_fails_the_build(request_):
    """Retrying must not turn an outage into a silent success or an empty dataset."""
    with pytest.raises(retea.TempoUnavailable):
        retea.read(
            request_,
            timeout=1,
            attempts=2,
            opener=opener_for(TimeoutError("timed out"), TimeoutError("timed out")),
            sleep=lambda _: None,
            log=lambda _: None,
        )


def test_nothing_is_retried_when_nothing_failed(request_):
    """One attempt on the happy path. A retry loop that always sleeps is a slower build."""
    waited: list[float] = []
    retea.read(
        request_,
        timeout=1,
        opener=opener_for(b"{}"),
        sleep=waited.append,
        log=lambda _: None,
    )
    assert waited == []


def test_the_matrix_definitions_are_in_the_repository():
    """The cheaper half of the fix: a CI run must not need TEMPO to be up to read these.

    They are vocabularies, not observations — they change when INS restructures a matrix,
    which changes the importer too. The rates file beside them is deliberately *not*
    committed, because it moves daily, and that asymmetry is the whole point.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "simulators/impozit-teren/sources"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    names = {Path(p).name for p in tracked}
    for matrix in ("agr101b", "agr306a", "pop107d"):
        assert f"ins-{matrix}-metadata.json.gz" in names, (
            f"ins-{matrix}-metadata.json.gz is not committed, so every CI run downloads it "
            "from a service that times out"
        )
    assert not [n for n in names if n.startswith("ecb-")], (
        "the ECB rates change daily and must not be committed"
    )


def test_an_outage_and_a_regression_are_different_exit_codes():
    """The narrow claim `retea.UNREACHABLE` makes, and the wide one it must never make.

    A statistics server in Bucharest going down should not fail a pull request that changes
    four TypeScript files — that is what this exists for. But the moment it starts covering
    anything else it becomes a way of ignoring failures, so the four cases are pinned here:
    only "nothing imported, everything failed the same way, and that way was the host" is an
    outage. A partial import is a failure precisely because the roster on disk is then half
    old and half new.
    """
    import sys
    from pathlib import Path

    sys.path.insert(
        0, str(Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "scripts")
    )
    import import_fond_funciar as importer
    import retea as network

    gone = network.UNREACHABLE
    broke = 1

    everything = [("AB", 0, "ok"), ("AR", 0, "ok")]
    assert importer.outcome(everything) == 0

    nothing = [("AB", gone, "TEMPO nu a răspuns"), ("AR", gone, "TEMPO nu a răspuns")]
    assert importer.outcome(nothing) == network.UNREACHABLE

    # Half the country imported and half did not. Not an outage — the data is now mixed.
    partial = [("AB", 0, "ok"), ("AR", gone, "TEMPO nu a răspuns")]
    assert importer.outcome(partial) == 1

    # Everything failed, but not all for the same reason. Something else is wrong.
    mixed = [("AB", gone, "TEMPO nu a răspuns"), ("AR", broke, "AGR101B categories changed")]
    assert importer.outcome(mixed) == 1

    # The decision is on exit codes, never on the wording of a message. A version of this that
    # grepped stderr for "TempoUnavailable" passed its tests and failed in CI the moment the
    # exception started being caught and reported as a sentence instead of a traceback.
    worded_differently = [("AB", gone, "anything at all"), ("AR", gone, "")]
    assert importer.outcome(worded_differently) == network.UNREACHABLE


def test_the_guard_only_swallows_the_one_exception():
    """Anything that is not an unreachable TEMPO keeps its traceback."""
    import sys
    from pathlib import Path

    sys.path.insert(
        0, str(Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "scripts")
    )
    import retea as network

    assert network.guarded(lambda: 0) == 0
    assert network.guarded(lambda: 7) == 7

    def gone():
        raise network.TempoUnavailable("nobody home")

    assert network.guarded(gone) == network.UNREACHABLE

    def broken():
        raise ValueError("a real bug")

    with pytest.raises(ValueError):
        network.guarded(broken)

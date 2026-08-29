"""Tests for the court-map importer.

Reading a table out of a PDF fails silently: a row that does not match simply is not there,
and the output still looks like a court map. Each of these pins a way that actually
happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "simulators/justitie/data/instante-2023.json"


@pytest.fixture(scope="module")
def courts() -> list[dict]:
    if not DATA.exists():
        pytest.skip("court map not imported yet")
    return json.loads(DATA.read_text(encoding="utf-8"))["courts"]


def by_tier(courts: list[dict], tier: str) -> list[dict]:
    return [c for c in courts if c["tier"] == tier]


def test_every_tier_is_present(courts):
    """The highest court went missing once, to a diacritic.

    Romanian is written with two encodings of the same letters — comma-below (ș ț) and
    cedilla (ş ţ) — and the report mixes them inside one line. A character class listing
    only one silently fails, and the Înalta Curte vanished from its own court map.
    """
    assert len(by_tier(courts, "iccj")) == 1
    assert len(by_tier(courts, "curte-de-apel")) == 15
    assert len(by_tier(courts, "judecatorie")) == 175
    assert len(by_tier(courts, "tribunal")) >= 42


def test_the_bucharest_sector_courts_are_there(courts):
    """All six were dropped by a name pattern that stopped at the first digit.

    "Judecatoria SECTORUL 1 BUCUREŞTI" has a digit inside its name. They are among the
    largest courts in the country, so losing them would have left the map arguing that
    small courts are the problem while missing the biggest urban ones.
    """
    sectors = [c for c in courts if "SECTORUL" in c["name"]]
    assert len(sectors) == 6
    biggest = max(sectors, key=lambda c: c["volume"])
    tribunals = by_tier(courts, "tribunal")
    bigger = [t for t in tribunals if t["volume"] > biggest["volume"]]
    assert len(bigger) == 1, "only Tribunalul București should out-carry Sector 1"


def test_derived_headcounts_reproduce_the_printed_ratios(courts):
    """judges = volume / loadPerJudge, within the precision the source itself has.

    The tolerance is relative, not absolute. The ratio is printed to one decimal, so on a
    court with two judges a single unit in the last place moves the recomputed ratio by
    more than ten cases — that is the source's precision, not a parsing error.
    """
    for court in courts:
        if not court.get("judges"):
            continue
        recomputed = court["volume"] / court["judges"]
        assert abs(recomputed - court["loadPerJudge"]) / court["loadPerJudge"] < 0.01, court["name"]


def test_the_establishment_almost_always_exceeds_the_sitting_judges(courts):
    """Posts include vacancies, so posts > judges nearly everywhere — but not always.

    Exactly one court of 241 inverts: Judecătoria Târnăveni sits 4,5 judges against 4
    established posts, which happens when delegated judges cover more than the approved
    establishment. Asserting the inequality universally was wrong; asserting that the
    exception stays rare is what actually detects a misread column.
    """
    inverted = [
        c for c in courts
        if c.get("judges") and c.get("posts") and c["posts"] < c["judges"] - 0.05
    ]
    assert len(inverted) <= 3, [c["name"] for c in inverted]


def test_resolved_never_exceeds_volume(courts):
    """A court cannot dispose of more cases than it had. Columns swapped would show it."""
    for court in courts:
        assert court["resolved"] <= court["volume"], court["name"]


def test_nothing_claims_to_be_more_certain_than_it_is(courts):
    """Derived figures are marked as such in the note, and nothing is `assumed`."""
    for court in courts:
        assert court["provenance"]["confidence"] in {"verbatim", "derived"}


def test_the_small_courts_the_proposal_targets_actually_exist(courts):
    """The paper's case rests on courts too small to be viable.

    If the data did not contain a long tail of small courts, the proposal would have
    nothing to act on and the simulator nothing to model.
    """
    judecatorii = sorted(by_tier(courts, "judecatorie"), key=lambda c: c["volume"])
    assert judecatorii[0]["volume"] < 3_000
    assert sum(1 for c in judecatorii if c["volume"] < 5_000) > 20

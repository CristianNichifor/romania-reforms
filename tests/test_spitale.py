"""Tests for the hospital register and the co-location figure drawn from it.

The number this file produces — every court seat has a hospital — is the kind that gets quoted
without its caveat. It is true of 36 counties and unknown for six, and the register's own gaps
are what make the difference. So the completeness check is a test, not a footnote: if the
missing counties ever silently become "counties without hospitals", the figure turns into a
claim the source cannot support.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPITALE = ROOT / "simulators/justitie/data/spitale-2026.json"
COURTS = ROOT / "simulators/justitie/data/court-distance.json"


@pytest.fixture(scope="module")
def spitale() -> dict:
    if not SPITALE.exists():
        pytest.skip("the hospital register is not imported")
    return json.loads(SPITALE.read_text(encoding="utf-8"))


def test_the_register_is_declared_incomplete(spitale):
    """The gap is the headline, and it must stay blocking.

    Six counties are absent entirely — including Galati and Mures, which plainly have county
    hospitals. Any national statement from this file would be wrong in the flattering
    direction: it would read absence of data as absence of hospitals.
    """
    blocking = {x["id"] for x in spitale["limitations"] if x["severity"] == "blocking"}
    assert "registrul-e-incomplet" in blocking
    missing = spitale["summary"]["countiesMissing"]
    assert len(missing) > 0
    assert spitale["summary"]["countiesCovered"] + len(missing) == spitale["summary"]["countiesTotal"]


def test_the_colocation_figure_only_speaks_for_covered_counties(spitale):
    """It must be reported over what the register reaches, never over all 42."""
    summary = spitale["summary"]
    assert summary["courtSeatsCheckable"] == summary["countiesCovered"]
    assert summary["courtSeatsCheckable"] < summary["countiesTotal"]
    assert summary["courtSeatsWithHospital"] <= summary["courtSeatsCheckable"]


def test_every_checkable_court_seat_has_a_hospital(spitale):
    """The finding itself, recomputed from the rows rather than read off the summary."""
    if not COURTS.exists():
        pytest.skip("court seats not built")
    seats = {c["county"]: c["siruta"] for c in json.loads(COURTS.read_text(encoding="utf-8"))["courts"]}
    located = [h for h in spitale["hospitals"] if h["county"]]
    covered = {h["county"] for h in located}
    hosting = {h["siruta"] for h in located}
    checkable = [county for county in seats if county in covered]
    without = [county for county in checkable if seats[county] not in hosting]
    assert without == [], without
    assert len(checkable) == spitale["summary"]["courtSeatsCheckable"]


def test_the_summary_matches_its_own_rows(spitale):
    rows = spitale["hospitals"]
    located = [h for h in rows if h["county"]]
    assert spitale["summary"]["hospitals"] == len(rows)
    assert spitale["summary"]["located"] == len(located)
    assert spitale["summary"]["countiesCovered"] == len({h["county"] for h in located})


def test_unplaced_markers_are_kept_and_excluded(spitale):
    """Kept so the count stays honest, excluded so the shares do."""
    unplaced = [h for h in spitale["hospitals"] if h["county"] is None]
    assert spitale["summary"]["located"] == len(spitale["hospitals"]) - len(unplaced)
    for row in unplaced:
        assert row["siruta"] is None and row["uat"] is None


def test_the_coordinates_are_inside_romania(spitale):
    """A marker outside the country is a source error, not a hospital somewhere surprising."""
    for row in spitale["hospitals"]:
        assert 43.5 < row["lat"] < 48.5, row["name"]
        assert 20.0 < row["lng"] < 30.0, row["name"]


def test_most_hospitals_are_not_in_a_court_seat_town(spitale):
    """The counterweight to the headline.

    Every seat having a hospital is not the same as the seats being where the hospitals are:
    about two thirds sit elsewhere, which is what consolidating services into 42 towns would
    move away from.
    """
    summary = spitale["summary"]
    assert summary["hospitalsInCourtSeatTowns"] < summary["located"] / 2


def test_hospitals_are_not_claimed_to_be_prosecutors(spitale):
    """The paper's argument is about courts, prosecutors and police sharing a town. Hospitals
    are a proxy for a county service centre and the file must say so."""
    assert "spitalele-nu-sunt-parchete" in {x["id"] for x in spitale["limitations"]}

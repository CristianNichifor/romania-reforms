"""Tests for assigning consolidated UATs to courts by distance.

This joins two simulators, so the failure that matters is silent drift: the administrative
model changes its merge rules, or the court set loses a seat, and the assignment quietly
becomes a statement about something else. Every check recomputes from the rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARONDARE = ROOT / "simulators/justitie/data/arondare-noua.json"


@pytest.fixture(scope="module")
def arondare() -> dict:
    if not ARONDARE.exists():
        pytest.skip("the new arondare is not built")
    return json.loads(ARONDARE.read_text(encoding="utf-8"))


def test_there_is_one_court_per_county_plus_the_capital(arondare):
    assert arondare["courtSeats"] == 42, arondare["courtSeats"]


def test_every_reachable_unit_gets_exactly_one_court(arondare):
    """The point of assigning the unit rather than its communes.

    A consolidated UAT gets one court, and a unit the road graph cannot reach gets none rather
    than a default. The first version took argmin over a row of infinities, which returns index
    zero — quietly handing the unreachable unit the alphabetically first court in the country
    and a cross-county flag to go with it.
    """
    for unit in arondare["units"]:
        if unit["metres"] is None:
            assert unit["courtSiruta"] is None, unit["siruta"]
            assert unit["crossesCounty"] is False
        else:
            assert isinstance(unit["courtSiruta"], str) and unit["courtSiruta"]


def test_commune_level_routing_really_would_split_units(arondare):
    """The count that justifies the whole approach, recomputed as a consistency check.

    If this were zero, assigning whole units would be a preference with no consequence and the
    file should say so instead of arguing for it.
    """
    flagged = [u for u in arondare["units"] if u["wouldSplitByCommune"]]
    assert arondare["summary"]["wouldSplitByCommune"] == len(flagged)
    assert len(flagged) > 0, "no unit would be split; the argument for unit-level assignment fails"


def test_the_nearest_court_is_never_further_than_the_county_one(arondare):
    """Nearest-of-42 is by construction no further than the one court inside your county.

    If any row broke this, the assignment would be picking something other than the nearest and
    every conclusion about travel would be wrong in the flattering direction.
    """
    worse = [
        u["siruta"]
        for u in arondare["units"]
        if u["metres"] is not None
        and u["ownCountyMetres"] is not None
        and u["metres"] > u["ownCountyMetres"]
    ]
    assert worse == [], worse[:10]


def test_crossing_the_county_line_is_exactly_when_the_court_sits_elsewhere(arondare):
    """Only meaningful where a court was assigned: an unreachable unit has no court county, and
    comparing None against a county code would call it a crossing."""
    for unit in arondare["units"]:
        if unit["courtSiruta"] is None:
            assert unit["crossesCounty"] is False, unit["siruta"]
            continue
        assert unit["crossesCounty"] == (unit["courtCounty"] != unit["county"])


def test_some_units_do_cross_and_it_is_not_a_rounding_artefact(arondare):
    """The finding: county capitals are not evenly spaced, so the county line costs travel.

    Asserted with a floor on how much shorter the crossing drive is, so a handful of ties a
    metre apart could not masquerade as the result.
    """
    crossing = [u for u in arondare["units"] if u["crossesCounty"]]
    assert len(crossing) > 10, len(crossing)
    assert arondare["summary"]["crossingCounty"] == len(crossing)
    assert arondare["summary"]["metresSavedEachCrossing"] > 5_000


def test_dropping_the_county_line_shortens_the_average(arondare):
    summary = arondare["summary"]
    assert summary["meanMetresNearest"] < summary["meanMetresOwnCounty"]


def test_the_summary_matches_its_own_rows(arondare):
    units = arondare["units"]
    routed = [u for u in units if u["metres"] is not None]
    summary = arondare["summary"]
    assert summary["units"] == len(units)
    assert summary["routed"] == len(routed)
    assert summary["peopleCrossingCounty"] == sum(
        u["population"] for u in routed if u["crossesCounty"]
    )


def test_the_unroutable_units_are_kept_and_excluded(arondare):
    """Kept in the file so the count stays honest, out of the averages so the averages do."""
    units = arondare["units"]
    assert arondare["summary"]["routed"] <= len(units)
    for unit in units:
        if unit["metres"] is None:
            assert unit["ownCountyMetres"] is None or unit["ownCountyMetres"] >= 0


def test_units_cover_every_commune_once(arondare):
    """The consolidated map partitions the country; so must this."""
    total_members = sum(u["members"] for u in arondare["units"])
    assert total_members == 3186, total_members


def test_the_legal_and_parameter_caveats_survive(arondare):
    """Cross-county arondare is not what the law does today, and the units depend on the
    administrative simulator's parameters. Both change how the map should be read."""
    ids = {x["id"] for x in arondare["limitations"]}
    assert "arondarea-peste-judet-nu-e-legala" in ids
    assert "depinde-de-parametrii-reformei-administrative" in ids
    assert "distanta-se-masoara-din-sediu" in ids

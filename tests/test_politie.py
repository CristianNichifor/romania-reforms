"""Tests for the police stations, and the one claim crowd-sourced data can carry.

OpenStreetMap has no completeness guarantee and no register to check it against — four other
sources were tried and none publishes the list. So the tests here separate the claim that
survives patchy mapping from the claims that do not, and pin the difference.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
POLITIE = ROOT / "simulators/justitie/data/politie-osm.json"
COURTS = ROOT / "simulators/justitie/data/court-distance.json"


@pytest.fixture(scope="module")
def politie() -> dict:
    if not POLITIE.exists():
        pytest.skip("police stations not imported")
    return json.loads(POLITIE.read_text(encoding="utf-8"))


def test_coverage_is_national(politie):
    """The test that failed for the hospital map. Police pass it, which is why they can carry a
    national statement where hospitals cannot."""
    summary = politie["summary"]
    assert summary["countiesCovered"] == summary["countiesTotal"] == 42


def test_every_court_seat_has_a_station(politie):
    """The existence claim, recomputed from the rows.

    This is the one that survives under-coverage: unmapped stations make a seat harder to
    match, never easier, so 42 of 42 cannot be an artefact of over-mapping.
    """
    if not COURTS.exists():
        pytest.skip("court seats not built")
    seats = {c["county"]: c["siruta"] for c in json.loads(COURTS.read_text(encoding="utf-8"))["courts"]}
    towns = {s["siruta"] for s in politie["stations"] if s["siruta"]}
    without = sorted(county for county, siruta in seats.items() if siruta not in towns)
    assert without == [], without
    assert politie["summary"]["courtSeatsWithStation"] == len(seats)


def test_the_stations_are_a_minority_of_uats(politie):
    """Presence everywhere would make the co-location finding vacuous."""
    summary = politie["summary"]
    assert summary["uatsWithStation"] < summary["uatsTotal"] / 2


def test_the_summary_matches_its_own_rows(politie):
    rows = politie["stations"]
    located = [s for s in rows if s["county"]]
    summary = politie["summary"]
    assert summary["stations"] == len(rows)
    assert summary["located"] == len(located)
    assert summary["uatsWithStation"] == len({s["siruta"] for s in located})
    assert summary["countiesCovered"] == len({s["county"] for s in located})
    assert summary["unnamed"] == sum(1 for s in rows if not s["name"])


def test_unnamed_stations_are_kept(politie):
    """An unnamed feature is still a station; dropping them would understate coverage."""
    assert politie["summary"]["unnamed"] > 0
    assert politie["summary"]["unnamed"] < politie["summary"]["stations"]


def test_coordinates_are_inside_romania(politie):
    for station in politie["stations"]:
        assert 43.5 < station["lat"] < 48.5, station["osm"]
        assert 20.0 < station["lng"] < 30.0, station["osm"]


def test_the_source_and_its_limits_are_declared(politie):
    """Crowd-sourced, unverifiable, and silent about rank. All three change how it reads."""
    ids = {x["id"] for x in politie["limitations"]}
    assert "osm-nu-e-registru" in ids
    assert "prezenta-nu-e-rang" in ids
    assert "distantele-sunt-limite-de-sus" in ids
    assert politie["provenance"]["source"] == "openstreetmap"
    assert politie["provenance"]["confidence"] != "verbatim"

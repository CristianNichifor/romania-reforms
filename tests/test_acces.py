"""Tests for the travel-to-court figures.

This is the one part of the reform the paper asserts and cannot show, so it is the part most
worth being suspicious of. Every check here recomputes something from the row data rather
than trusting the summary, because a summary that disagrees with its own rows would still
read as an answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ACCES = ROOT / "simulators/justitie/data/acces-2025.json"
ARONDARE = ROOT / "simulators/justitie/data/arondare-2023.json"


@pytest.fixture(scope="module")
def acces() -> dict:
    if not ACCES.exists():
        pytest.skip("access figures not built")
    return json.loads(ACCES.read_text(encoding="utf-8"))


def test_it_covers_every_commune_the_arondare_places(acces):
    """Anything short of the arondare is a hole, and a hole flatters the proposal.

    A commune missing from this file is a commune whose extra travel nobody counted, so the
    cost of consolidation comes out lower than it is.
    """
    if not ARONDARE.exists():
        pytest.skip("arondare not imported")
    arondare = json.loads(ARONDARE.read_text(encoding="utf-8"))
    placed = {s for court in arondare["courts"] for s in court["localities"]}
    covered = {row["siruta"] for row in acces["communes"]}
    assert covered == placed, sorted(placed - covered)[:10]


def test_the_summary_matches_its_own_rows(acces):
    rows = acces["communes"]
    on_road = [r for r in rows if r["byRoad"]]
    summary = acces["summary"]
    assert summary["communes"] == len(rows)
    assert summary["people"] == sum(r["population"] for r in on_road)
    for km, counts in summary["beyond"].items():
        metres = int(km) * 1000
        for key, value in counts.items():
            assert value == sum(
                r["population"] for r in on_road if r[key] > metres
            ), f"{km} km, {key}"


def test_consolidation_never_shortens_the_journey_on_average(acces):
    """A merge that closes courts cannot reduce mean travel, so if it appears to, the
    computation is wrong rather than the reform miraculous."""
    mean = acces["summary"]["mean"]
    assert mean["metresByCounty"] >= mean["metresToday"]
    assert mean["metresNearest"] >= mean["metresToday"]


def test_dropping_the_county_line_never_costs_anyone(acces):
    """Nearest-of-42 is by construction no further than that county's court, commune by
    commune. If it were, the routing would be picking something other than the nearest."""
    worse = [
        r["siruta"]
        for r in acces["communes"]
        if r["byRoad"] and r["metresNearest"] > r["metresByCounty"]
    ]
    assert worse == [], worse[:10]


def test_the_roadless_communes_are_kept_and_excluded(acces):
    """Eight of the eleven are the Delta, reached by water whatever any reform says.

    Kept in the file so the count stays honest, and out of every average so the averages do.
    """
    without = [r for r in acces["communes"] if not r["byRoad"]]
    assert len(without) == acces["summary"]["communesWithoutRoad"] == 11
    assert all(r["metresToday"] is None for r in without)
    delta = {r["siruta"] for r in without if r["county"] == "TL"}
    assert len(delta) == 8, sorted(delta)


def test_some_communes_are_unaffected(acces):
    """The ones already served from their county's tribunal town do not move.

    If this were zero, every commune would have been reassigned, which would mean the
    proposed court was not being seated where a court already is.
    """
    rows = [r for r in acces["communes"] if r["byRoad"]]
    same = [r for r in rows if r["metresByCounty"] <= r["metresToday"]]
    assert len(same) > 500, len(same)


def test_distances_are_plausible(acces):
    """Romania is about 700 km across, so anything past 300 km is the graph, not geography."""
    on_road = [r for r in acces["communes"] if r["byRoad"]]
    assert max(r["metresNearest"] for r in on_road) < 300_000
    assert all(
        r["metresToday"] >= 0 and r["metresByCounty"] >= 0 and r["metresNearest"] >= 0
        for r in on_road
    )


def test_bucharest_is_not_given_a_commute(acces):
    """Its sectors and its courts are all inside one city; a road distance between them is not
    what access means here, and leaving it in would put a fake number on two million people."""
    rows = [r for r in acces["communes"] if r["county"] == "B"]
    assert rows, "Bucharest is missing entirely"
    assert all(
        r["metresToday"] == 0 and r["metresByCounty"] == 0 and r["metresNearest"] == 0
        for r in rows
    )


def test_the_weighting_caveat_is_declared(acces):
    ids = {x["id"] for x in acces["limitations"]}
    assert "populatia-nu-e-numarul-de-justitiabili" in ids
    assert "distanta-nu-e-timp" in ids
    assert "delta-nu-are-drum" in ids
    assert "arondarea-peste-judet-nu-e-legala-azi" in ids


def test_balancing_costs_travel_and_buys_evenness(acces):
    """The trade the ceiling makes, asserted in the direction it must go.

    A load ceiling can only push communes away from their nearest court, so mean travel under
    any ceiling is at least the unconstrained figure. If it came out lower, the assignment
    would be finding journeys the nearest-court routing missed, which is impossible.
    """
    scenarios = acces["summary"]["balanced"]
    assert scenarios, "no ceiling scenarios were computed"
    floor = acces["summary"]["mean"]["metresNearest"]
    for name, scenario in scenarios.items():
        assert scenario["meanMetres"] >= floor, (name, scenario["meanMetres"], floor)


def test_a_tighter_ceiling_never_travels_less(acces):
    """Ordered by ceiling, travel must not fall as the constraint tightens.

    This is what caught the first version: the fallback sent full-court communes to the
    *farthest* court in the country, and a 1,2x ceiling came out both more even and vastly
    more expensive than 1,5x — a shape no correct assignment produces.
    """
    scenarios = sorted(
        acces["summary"]["balanced"].values(), key=lambda s: s["ceilingMultiplier"]
    )
    travel = [s["meanMetres"] for s in scenarios]
    assert travel == sorted(travel, reverse=True), travel


def test_bucharest_cannot_be_balanced_away(acces):
    """Its sectors carry 5,7x the average court and cannot move, so no ceiling reaches them.

    Recomputed from the rows: if this ever came out under about 3x, the capital would have
    become balanceable by moving communes, which would mean the attribution changed rather
    than the country.
    """
    rows = [r for r in acces["communes"] if r["byRoad"]]
    total = sum(r["cases"] for r in rows)
    bucharest = sum(r["cases"] for r in rows if r["county"] == "B")
    mean = total / 42
    assert bucharest / mean > 3, bucharest / mean

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
    summary = acces["summary"]
    assert summary["communes"] == len(rows)
    assert summary["people"] == sum(r["population"] for r in rows)
    for km, counts in summary["beyond"].items():
        metres = int(km) * 1000
        assert counts["todayPeople"] == sum(
            r["population"] for r in rows if r["metresToday"] > metres
        ), km
        assert counts["proposedPeople"] == sum(
            r["population"] for r in rows if r["metresProposed"] > metres
        ), km


def test_consolidation_never_shortens_the_journey_on_average(acces):
    """A merge that closes courts cannot reduce mean travel, so if it appears to, the
    computation is wrong rather than the reform miraculous."""
    summary = acces["summary"]
    assert summary["meanProposedM"] >= summary["meanTodayM"]
    assert summary["medianProposedM"] >= summary["medianTodayM"]


def test_some_communes_are_unaffected(acces):
    """The ones already served from their county's tribunal town do not move.

    If this were zero, every commune would have been reassigned, which would mean the
    proposed court was not being seated where a court already is.
    """
    rows = acces["communes"]
    same = [r for r in rows if r["metresProposed"] <= r["metresToday"]]
    assert len(same) > 500, len(same)
    assert acces["summary"]["unchanged"] == len(same)


def test_distances_are_plausible(acces):
    """Romania is about 700 km across and no county is; a county-scoped road distance beyond
    300 km means the graph, not the geography."""
    worst = max(r["metresProposed"] for r in acces["communes"])
    assert worst < 300_000, worst
    assert all(r["metresToday"] >= 0 and r["metresProposed"] >= 0 for r in acces["communes"])


def test_bucharest_is_not_given_a_commute(acces):
    """Its sectors and its courts are all inside one city; a road distance between them is not
    what access means here, and leaving it in would put a fake number on two million people."""
    rows = [r for r in acces["communes"] if r["county"] == "B"]
    assert rows, "Bucharest is missing entirely"
    assert all(r["metresToday"] == 0 and r["metresProposed"] == 0 for r in rows)


def test_the_weighting_caveat_is_declared(acces):
    ids = {x["id"] for x in acces["limitations"]}
    assert "populatia-nu-e-numarul-de-justitiabili" in ids
    assert "distanta-nu-e-timp" in ids

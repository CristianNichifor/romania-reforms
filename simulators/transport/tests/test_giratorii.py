"""Tests for the junction count.

The measurement is easy and the interpretation is not, so these tests mostly guard the
interpretation: that the number stays labelled as an upper bound, and that the traffic split
survives as the thing separating a candidate list from a programme.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "data" / "giratorii.json"


@pytest.fixture(scope="module")
def built() -> dict:
    if not BUILT.exists():
        pytest.skip("junctions not built")
    return json.loads(BUILT.read_text(encoding="utf-8"))


def test_clustering_reduces_the_raw_points(built):
    """A dual carriageway crossing another road makes two points and a staggered crossroads
    three. Without clustering the count is of nodes, not junctions."""
    j = built["junctions"]
    assert j["distinct"] <= j["rawPoints"]
    assert j["distinct"] > 0


def test_the_remaining_are_what_is_left_after_the_converted(built):
    j = built["junctions"]
    assert j["remaining"] == j["distinct"] - j["alreadyRoundabout"]
    assert j["onMeasuredTraffic"] <= j["remaining"]


def test_the_already_converted_count_is_small_for_a_known_reason(built):
    """Not a data problem. A roundabout is its own loop, so the two roads stop touching each
    other and the junction leaves the intersection set entirely. If this ever became large,
    the geometry handling changed and the whole count needs rereading."""
    j = built["junctions"]
    assert j["alreadyRoundabout"] < j["remaining"] / 10
    assert j["existingRoundaboutWays"] > j["alreadyRoundabout"]


def test_the_busy_subset_is_a_small_fraction(built):
    """The point of the split. If most junctions were on measured roads the traffic filter
    would not be separating anything, and the candidate list would still be a wish list."""
    j = built["junctions"]
    assert 0 < j["onMeasuredTraffic"] < j["remaining"] / 2


def test_cost_follows_the_counts(built):
    cost, j = built["cost"], built["junctions"]
    assert cost["allRemainingRon"] == pytest.approx(j["remaining"] * cost["leiEach"], rel=1e-6)
    assert cost["onMeasuredTrafficRon"] == pytest.approx(
        j["onMeasuredTraffic"] * cost["leiEach"], rel=1e-6
    )
    assert cost["onMeasuredTrafficRon"] < cost["allRemainingRon"]


def test_it_refuses_to_call_itself_a_programme(built):
    """Blocking on purpose. Some of these want signals, some grade separation, some nothing at
    all, and nothing here tells them apart."""
    by_id = {limitation["id"]: limitation for limitation in built["limitations"]}
    assert by_id["candidati-nu-program"]["severity"] == "blocking"
    assert "pretul-unitar-variaza-de-zece-ori" in by_id
    assert "intersectia-geometrica-nu-e-intersectie-rutiera" in by_id

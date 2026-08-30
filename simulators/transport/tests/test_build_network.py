"""Tests for the national feeder network.

The check this layer lives or dies by is coverage: every UAT is served, is a hub, or is named
unroutable. A UAT that were none of those is a place nobody counted, and an uncounted place
flatters every figure built on top of it — the failure that once cost administrativ eight
courts, including all six Bucharest sector courts, and was caught by a structural check rather
than a tolerance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "data" / "network.json"


@pytest.fixture(scope="module")
def network() -> dict:
    if not NETWORK.exists():
        pytest.skip("network not built")
    return json.loads(NETWORK.read_text(encoding="utf-8"))


def served_uats(network: dict) -> list[str]:
    return [uat for route in network["routes"] for uat in route["serves"]]


def test_every_uat_is_served_or_a_hub_or_named_unroutable(network):
    """No fourth outcome. This is the whole point of the layer."""
    served = set(served_uats(network))
    named = {row["siruta"] for row in network["unroutable"]}
    hubs = set(network["summary"]["hubSirutas"])
    assert len(served | named | hubs) == network["summary"]["uatsTotal"] == 3186


def test_no_uat_is_served_twice(network):
    """A UAT on two branches belongs to exactly one route, or it is costed twice and the
    network comes out more expensive than it is."""
    served = served_uats(network)
    assert len(served) == len(set(served))


def test_a_hub_is_never_served_by_a_feeder(network):
    """A hub does not need a bus to itself; counting one would inflate every region."""
    hubs = set(network["summary"]["hubSirutas"])
    assert not (set(served_uats(network)) & hubs)


def test_the_unroutable_are_named_not_counted(network):
    """A number is not accountability. Each carries its name, county and hub so the hole can
    be looked at — and looked at, it turns out to be the Danube Delta."""
    assert network["unroutable"], "expected the delta communes to be listed"
    for row in network["unroutable"]:
        assert row["siruta"] and row["name"] and row["county"] and row["hub"]


def test_the_unroutable_are_where_the_roads_genuinely_are_not(network):
    """Validation by geography rather than by arithmetic: almost all of them are Tulcea
    (Danube Delta) or Brăila (river islands), reachable only by water. If this ever fills up
    with ordinary inland communes, the graph broke rather than the country changing."""
    counties = [row["county"] for row in network["unroutable"]]
    water = sum(1 for c in counties if c in ("TL", "BR"))
    assert water >= len(counties) / 2, counties


def test_the_tree_actually_merges(network):
    """Around 1 537 routes for 2 923 served UATs. If routes approach UATs, the tree is not
    collapsing branches and every village has its own bus — which is the upper bound this
    layer exists to beat."""
    summary = network["summary"]
    assert summary["routes"] < summary["uatsServed"] * 0.75


def test_every_route_ends_at_its_hub(network):
    for route in network["routes"]:
        assert route["stops"][-1] == route["hub"]
        assert route["stops"][0] == route["leaf"]


def test_a_route_serves_only_places_it_stops_at(network):
    """A route cannot be responsible for a UAT it never passes."""
    for route in network["routes"]:
        assert set(route["serves"]) <= set(route["stops"]), route["leaf"]


def test_route_lengths_are_measured_not_assumed(network):
    """A route whose kilometres could not be measured is null, never zero. Zero would price
    a real journey as free."""
    for route in network["routes"]:
        assert route["oneWayKm"] is None or route["oneWayKm"] > 0


def test_long_routes_are_flagged_consistently(network):
    flagged = sum(1 for route in network["routes"] if route["isLong"])
    assert flagged == network["summary"]["longRoutes"]
    for route in network["routes"]:
        assert route["isLong"] == (route["oneWayMin"] > 60.0)


def test_the_summary_matches_its_own_routes(network):
    summary = network["summary"]
    assert summary["routes"] == len(network["routes"])
    assert summary["uatsServed"] == len(set(served_uats(network)))
    assert summary["uatsUnroutable"] == len(network["unroutable"])


def test_the_holes_are_declared(network):
    ids = {limitation["id"] for limitation in network["limitations"]}
    assert "uat-uri-fara-drum" in ids

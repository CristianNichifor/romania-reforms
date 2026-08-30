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
    """Only the feeders. A trunk route serves centres, which their own feeder already covers."""
    return [u for route in network["routes"] if route["tier"] == "T3" for u in route["serves"]]


def summary_of(network: dict) -> dict:
    return network["summary"]


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


def test_the_feeder_tree_actually_merges(network):
    """Around 1 537 feeder routes for 2 923 served UATs. If routes approach UATs, the tree is
    not collapsing branches and every village has its own bus — the upper bound this layer
    exists to beat."""
    summary = network["summary"]
    assert summary["feeder"]["routes"] < summary["uatsServed"] * 0.75


def test_the_trunk_reaches_every_centre_it_can(network):
    """Only Sulina has no road to its county seat, and it is in the Delta. If this grows, a
    county's centres have been cut off from their seat and nobody would see it in a cost."""
    assert summary_of(network)["hubsWithoutTrunk"] <= 1
    for row in network["hubsWithoutTrunk"]:
        assert row["siruta"] and row["name"] and row["county"]


def test_the_trunk_leg_is_the_longer_half(network):
    """The finding that made this tier necessary: a feeder reaches a centre in a median 27,6
    minutes, and the trunk from that centre to the county seat is a median 60,6. Costing
    feeders alone described a network connecting nobody to their county town."""
    summary = network["summary"]
    assert summary["trunk"]["oneWayMinMedian"] > summary["feeder"]["oneWayMinMedian"]


def test_a_trunk_route_serves_centres_not_villages(network):
    """A trunk route drives through the villages between two centres without being
    responsible for them — their own feeder is, and counting them twice would inflate the
    network."""
    hubs = set(network["summary"]["hubSirutas"])
    seats = {r["hub"] for r in network["routes"] if r["tier"] == "T2"}
    for route in network["routes"]:
        if route["tier"] != "T2":
            continue
        assert set(route["serves"]) <= hubs | seats, route["leaf"]


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
    for tier, key in (("T3", "feeder"), ("T2", "trunk")):
        flagged = sum(1 for r in network["routes"] if r["tier"] == tier and r["isLong"])
        assert flagged == network["summary"][key]["longRoutes"], tier
    for route in network["routes"]:
        assert route["isLong"] == (route["oneWayMin"] > 60.0)


def test_the_summary_matches_its_own_routes(network):
    summary = network["summary"]
    assert summary["routes"] == len(network["routes"])
    for tier, key in (("T3", "feeder"), ("T2", "trunk")):
        assert summary[key]["routes"] == sum(1 for r in network["routes"] if r["tier"] == tier)
    assert summary["uatsServed"] == len(set(served_uats(network)))
    assert summary["uatsUnroutable"] == len(network["unroutable"])


def test_the_holes_are_declared(network):
    ids = {limitation["id"] for limitation in network["limitations"]}
    assert "uat-uri-fara-drum" in ids

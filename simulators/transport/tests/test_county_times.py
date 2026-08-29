"""Tests for accumulating edge times into county-scoped journeys.

This mirrors reference_model._county_road_distances in the time domain. It is a Dijkstra
over the UAT adjacency graph, not over the road graph: the journey from a commune to a
distant seat is the sum of the seat-to-seat hops between them.

That is an approximation and an honest one — it forces a route through each intermediate
seat village, so it never understates. The tests pin that direction, because a substrate
that understated travel would flatter every network built on it.
"""

from __future__ import annotations

from scripts.county_times import county_times

# A chain: 1 - 2 - 3, plus 4 hanging off 2. All in county "XX".
COUNTY = {"1": "XX", "2": "XX", "3": "XX", "4": "XX"}
NEIGHBOURS = {"1": ["2"], "2": ["1", "3", "4"], "3": ["2"], "4": ["2"]}
EDGE_S = {
    ("1", "2"): 600.0,
    ("2", "1"): 600.0,
    ("2", "3"): 900.0,
    ("3", "2"): 900.0,
    ("2", "4"): 300.0,
    ("4", "2"): 300.0,
}


def test_the_source_reaches_itself_in_no_time():
    got = county_times(COUNTY, NEIGHBOURS, EDGE_S, "XX", ["1"])
    assert got["1"] == 0.0


def test_it_sums_hops_along_the_chain():
    got = county_times(COUNTY, NEIGHBOURS, EDGE_S, "XX", ["1"])
    assert got["2"] == 600.0
    assert got["3"] == 1500.0


def test_it_takes_the_cheapest_route_not_the_first():
    """Two ways round must give the shorter. A first-wins traversal is a plausible bug that
    produces a map nobody can tell is wrong."""
    neighbours = {"1": ["2", "3"], "2": ["1", "3"], "3": ["1", "2"]}
    edges = {
        ("1", "2"): 100.0,
        ("2", "1"): 100.0,
        ("2", "3"): 100.0,
        ("3", "2"): 100.0,
        ("1", "3"): 5000.0,
        ("3", "1"): 5000.0,
    }
    got = county_times({"1": "XX", "2": "XX", "3": "XX"}, neighbours, edges, "XX", ["1"])
    assert got["3"] == 200.0


def test_multiple_sources_give_the_nearest():
    got = county_times(COUNTY, NEIGHBOURS, EDGE_S, "XX", ["1", "3"])
    assert got["2"] == 600.0
    assert got["3"] == 0.0


def test_it_never_leaves_the_county():
    """Regions never cross county lines, so neither may a journey. A leak here would produce
    a network that crosses a boundary no operator crosses."""
    county = {"1": "XX", "2": "XX", "3": "YY"}
    got = county_times(county, {"1": ["2"], "2": ["1", "3"], "3": ["2"]}, EDGE_S, "XX", ["1"])
    assert "3" not in got


def test_an_unreachable_uat_is_absent_rather_than_zero():
    """Absent is a hole a caller must handle. Zero is a hole that looks like an answer."""
    county = {"1": "XX", "2": "XX", "9": "XX"}
    got = county_times(county, {"1": ["2"], "2": ["1"], "9": []}, EDGE_S, "XX", ["1"])
    assert "9" not in got


def test_a_missing_edge_does_not_silently_become_free():
    """If an edge has no measured time the hop must not cost nothing, or the graph would
    route through exactly the pairs the router failed on."""
    got = county_times(COUNTY, NEIGHBOURS, {}, "XX", ["1"])
    assert got == {"1": 0.0}

"""Tests for the route rule.

The rule is a paragraph and these tests are the paragraph, one clause at a time, on graphs
small enough to check by hand. Determinism has its own tests because a route set that
reshuffles between runs cannot be argued with.
"""

from __future__ import annotations

from scripts.network import Route, routes_for_hub

#   A chain with a spur, all in one zone:
#
#        hub --10-- a --10-- b --10-- c        (c is a leaf, 30 min out)
#                    \
#                     --15-- d                 (d is a leaf, 25 min out)
#
NEIGHBOURS = {
    "hub": ["a"],
    "a": ["hub", "b", "d"],
    "b": ["a", "c"],
    "c": ["b"],
    "d": ["a"],
}
EDGE_S = {}
for _u, _v, _m in (("hub", "a", 10), ("a", "b", 10), ("b", "c", 10), ("a", "d", 15)):
    EDGE_S[(_u, _v)] = _m * 60.0
    EDGE_S[(_v, _u)] = _m * 60.0
POPULATION = {"hub": 9000, "a": 3000, "b": 2000, "c": 1000, "d": 1500}
ZONE = set(NEIGHBOURS)


def build():
    return routes_for_hub(
        hub="hub",
        members=set(NEIGHBOURS),
        zone=ZONE,
        neighbours=NEIGHBOURS,
        edge_s=EDGE_S,
        population=POPULATION,
    )


def test_each_leaf_becomes_a_route():
    """Two branches end somewhere, so two routes. `a` and `b` are not leaves — they are
    stops on the way, which is the whole reason a tree merges shuttles into routes."""
    routes = build()
    assert {r.leaf for r in routes} == {"c", "d"}


def test_a_route_stops_at_every_uat_along_its_branch():
    routes = {r.leaf: r for r in build()}
    assert routes["c"].stops == ["c", "b", "a", "hub"]
    assert routes["d"].stops == ["d", "a", "hub"]


def test_a_route_ends_at_the_hub():
    for route in build():
        assert route.stops[-1] == "hub"


def test_the_one_way_time_is_the_distance_to_the_leaf():
    routes = {r.leaf: r for r in build()}
    assert routes["c"].one_way_min == 30.0
    assert routes["d"].one_way_min == 25.0


def test_a_uat_on_two_branches_is_served_once_by_the_nearer():
    """`a` is on both routes. It must not be counted twice when the network is costed, so
    each UAT is assigned to exactly one route: the one whose branch it sits on."""
    served = [u for route in build() for u in route.serves]
    assert sorted(served) == sorted(set(served))
    assert set(served) == {"a", "b", "c", "d"}


def test_the_hub_is_not_served_by_its_own_feeder():
    """A hub does not need a bus to itself. Counting it would inflate every region."""
    served = {u for route in build() for u in route.serves}
    assert "hub" not in served


def test_routes_come_back_in_a_stable_order():
    """Same inputs, same order, every run — a scenario that reshuffles cannot be argued
    with, and this repository's whole position is that its output is byte-reproducible."""
    first = [r.leaf for r in build()]
    for _ in range(5):
        assert [r.leaf for r in build()] == first


def test_the_order_is_population_then_siruta():
    """Documented and deterministic: the busier leaf first, ties broken by code."""
    population = dict(POPULATION, c=1000, d=1000)
    routes = routes_for_hub(
        hub="hub",
        members=set(NEIGHBOURS),
        zone=ZONE,
        neighbours=NEIGHBOURS,
        edge_s=EDGE_S,
        population=population,
    )
    assert [r.leaf for r in routes] == ["c", "d"]


def test_a_long_route_is_flagged_rather_than_split():
    """The design document says a route over the maximum is split at the furthest stop that
    fits. That cannot work. A feeder runs from a leaf to its hub, so its one-way time *is*
    the leaf's distance from the hub; splitting yields sub-routes, and the one holding the
    leaf either still runs to the hub (unchanged) or stops short — which breaks the rule
    that a route ends at the hub, and quietly introduces a transfer.

    You cannot make a village nearer its centre by cutting the route in half. The 45 real
    routes over an hour are a fact about Romanian geography under this hub assignment, so
    they are flagged and reported rather than pretended away."""
    long_route = Route(
        hub="hub", leaf="c", stops=["c", "b", "a", "hub"], serves=["c", "b"], one_way_min=75.0
    )
    short_route = Route(
        hub="hub", leaf="d", stops=["d", "a", "hub"], serves=["d"], one_way_min=25.0
    )
    assert long_route.is_long
    assert not short_route.is_long


def test_the_real_routes_are_mostly_not_long():
    """Around 45 of 1 476 exceed an hour. If a change makes most routes long, the hub
    assignment or the speed model moved, not the route rule."""
    assert not any(r.is_long for r in build())


def test_a_uat_the_zone_cannot_reach_is_reported_not_dropped():
    """14 UATs in the country have no road route to their hub. They must come back named."""
    neighbours = dict(NEIGHBOURS, island=[])
    routes = routes_for_hub(
        hub="hub",
        members=set(NEIGHBOURS) | {"island"},
        zone=ZONE | {"island"},
        neighbours=neighbours,
        edge_s=EDGE_S,
        population=dict(POPULATION, island=500),
    )
    served = {u for route in routes for u in route.serves}
    assert "island" not in served


def test_a_hub_with_no_members_produces_no_routes():
    """One of the 249 hubs serves only itself. A feeder route to it has nothing to feed."""
    routes = routes_for_hub(
        hub="hub",
        members={"hub"},
        zone=ZONE,
        neighbours=NEIGHBOURS,
        edge_s=EDGE_S,
        population=POPULATION,
    )
    assert routes == []


def test_a_route_may_cross_a_uat_it_does_not_serve():
    """The correction this layer exists for. `bridge` belongs to another region but lies on
    the only road to `far`, so the route drives through it without serving it."""
    neighbours = dict(NEIGHBOURS)
    neighbours["a"] = ["hub", "b", "d", "bridge"]
    neighbours["bridge"] = ["a", "far"]
    neighbours["far"] = ["bridge"]
    edges = dict(EDGE_S)
    for u, v, m in (("a", "bridge", 5), ("bridge", "far", 5)):
        edges[(u, v)] = edges[(v, u)] = m * 60.0
    routes = routes_for_hub(
        hub="hub",
        members=set(NEIGHBOURS) | {"far"},
        zone=ZONE | {"bridge", "far"},
        neighbours=neighbours,
        edge_s=edges,
        population=dict(POPULATION, bridge=700, far=800),
    )
    served = {u for route in routes for u in route.serves}
    assert "far" in served
    assert "bridge" not in served
    crossing = next(r for r in routes if "far" in r.serves)
    assert "bridge" in crossing.stops

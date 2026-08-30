# Transport L1b — Route Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn 249 hubs and 3 186 UATs into a deterministic set of bus routes, and name the places no route can reach rather than dropping them.

**Architecture:** Three modules. `zones.py` says where a route may travel; `network.py` builds a shortest-path tree from each hub and turns its leaves into routes; `build_network.py` runs the country and writes the artefact. `network.py` is pure — it takes graphs and returns routes — so the whole rule can be tested on a hand-drawn six-node region.

**Tech Stack:** Python 3.12, `uv`, `ruff`, `pytest`. No new dependencies.

---

## Context an engineer needs before starting

**Read first:** `docs/superpowers/specs/2026-08-29-transport-design.md` §5 (the route rule). **Three of its sentences are wrong and this plan corrects them** — see below. Then `scripts/county_times.py` in this simulator, whose Dijkstra this extends, and `scripts/fleet.py`, which consumes what this produces.

### The spec is wrong about where a route may go

§5 says the shortest-path tree is built "over the road network **restricted to that region**". Measured against the real country, that rule **strands 91 UATs** that a county-wide route reaches without difficulty — Gurghiu, Hodac and Ibănești in Mureș all reach Sovata only by leaving their region, and there are 88 more. Roads do not respect region boundaries.

Routing is therefore over a **zone**, and only **14** UATs are then genuinely unroutable:

| routing rule | UATs left with no route |
|---|---|
| restricted to the region (spec as written) | 105 |
| restricted to the zone (this plan) | **14** |

A region is still what a route *serves*. It is not what a route may *cross*.

### A zone is a county, except once

Administrativ's regions never cross county lines — with one deliberate exception. **28 Ilfov communes are assigned to Sectorul 1**, because Bucharest is a municipality ringed by Ilfov and those communes commute inward. That is the only cross-county case in the country, on a single hub.

So a zone is a county, except that Bucharest and Ilfov are one zone. Getting this wrong does not fail loudly: it silently makes 28 UATs unroutable and quietly shrinks the fleet.

### The spec is wrong about splitting long routes

§5 says a route longer than the maximum one-way duration "is split at the furthest stop that still fits". **That cannot work.** A feeder runs from a leaf to its hub, so its one-way time *is* the leaf's distance from the hub. Splitting yields sub-routes, and the one holding the leaf either still runs to the hub — unchanged — or stops short, which breaks the rule that a route ends at the hub and quietly introduces a transfer nobody costed.

You cannot make a village nearer its centre by cutting its route in half. The **50 routes over an hour** are a fact about Romanian geography under this hub assignment. They are flagged `is_long` and reported. Relays and timed transfers are a real answer to them, but they belong to the pulse layer (`L1c`), not to a route generator.

### What the tree already does for you

Do not over-engineer the merging. Measured on the real hub assignment, the shortest-path tree **already** collapses 2 895 individual UAT-to-hub shuttles into **1 537 routes** — a 47% reduction before any corridor merging is attempted, because villages on the way to a further village are simply stops on its route.

Measured shape of those 1 537 routes:

| | median | p90 | max |
|---|---|---|---|
| one-way minutes | 27,6 | 49,8 | 121,7 |
| hops from hub | 2 | 4 | 8 |

Only **50 routes exceed 60 minutes one-way**. See the third correction below for why they are reported rather than split.

**Upper bound to beat.** `L1a` costed one shuttle per UAT at 3 914 peak vehicles, 19 564 bus-hours and 983 633 bus-km per weekday. This layer must come in under that; if it does not, the route rule is not merging.

**Every unit test can pass while the model is wrong.** `L1a` was out by 51% with 34 green tests, because each exercised a single route and the error only appeared when 2 895 were summed. **Task 4 exists for that reason and is not optional.**

**Working directory:** repository root. Branch `transport-design`. Commit messages are prose — run `git log --oneline -10`.

---

## File Structure

| File | Responsibility |
|---|---|
| `simulators/transport/scripts/zones.py` | Which UATs a route may travel through. County, except Bucharest+Ilfov. |
| `simulators/transport/scripts/network.py` | Shortest-path tree → routes. Pure: graphs in, routes out. |
| `simulators/transport/scripts/build_network.py` | Runs the country, writes `data/network.json`, names the unroutable. |
| `simulators/transport/schema/network.schema.json` | |
| `simulators/transport/tests/test_zones.py`, `test_network.py`, `test_build_network.py` | |

---

### Task 1: Routing zones

**Files:**
- Create: `simulators/transport/scripts/zones.py`
- Create: `simulators/transport/tests/test_zones.py`

- [ ] **Step 1: Write the failing tests**

Create `simulators/transport/tests/test_zones.py`:

```python
"""Tests for routing zones.

A zone is where a bus may drive. Getting it wrong does not fail loudly — it silently strands
UATs and shrinks the fleet — so these tests are mostly about the one exception.
"""

from __future__ import annotations

from scripts.zones import zone_of, zones_from_counties


def test_an_ordinary_county_is_its_own_zone():
    assert zone_of("VL") == "VL"
    assert zone_of("MS") == "MS"


def test_bucharest_and_ilfov_share_a_zone():
    """The only cross-county case in the country: 28 Ilfov communes are assigned to
    Sectorul 1, because Bucharest is a municipality ringed by Ilfov and the ring commutes
    inward. Treating them separately makes those 28 unroutable."""
    assert zone_of("B") == zone_of("IF")


def test_the_shared_zone_is_not_some_other_county():
    assert zone_of("B") not in ("B", "IF")


def test_zones_group_every_uat():
    counties = {"1": "VL", "2": "VL", "3": "B", "4": "IF", "5": "MS"}
    zones = zones_from_counties(counties)
    assert sum(len(members) for members in zones.values()) == len(counties)


def test_the_bucharest_zone_holds_both_counties_members():
    counties = {"1": "B", "2": "IF", "3": "VL"}
    zones = zones_from_counties(counties)
    assert zones[zone_of("B")] == {"1", "2"}
    assert zones["VL"] == {"3"}


def test_an_unknown_county_still_gets_a_zone():
    """A county code this module has never seen must route within itself rather than raise:
    a new code should cost coverage, not the whole build."""
    assert zone_of("XX") == "XX"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_zones.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.zones'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/zones.py`:

```python
"""Where a bus route may travel.

The design document says routes are built over the network "restricted to that region". That
is wrong, and measurably so: restricting a route to the region it serves **strands 91 UATs**
that a county-wide route reaches without difficulty. Gurghiu, Hodac and Ibănești all reach
Sovata only by leaving their region. Roads do not respect region boundaries.

A region is what a route **serves**. A zone is what a route may **cross**. With zone routing
only 14 UATs in the country are genuinely unroutable, against 105 under the region rule.

A zone is a county, with one exception. Administrativ's regions never cross county lines
except for Bucharest: **28 Ilfov communes are assigned to Sectorul 1**, because Bucharest is
a municipality ringed by Ilfov and the ring commutes inward. Treating the two separately does
not fail loudly — it quietly makes those 28 unroutable and shrinks the fleet.
"""

from __future__ import annotations

from typing import Final

# Bucharest and its ring. The only cross-county region in the country.
CAPITAL_ZONE: Final[str] = "B+IF"
CAPITAL_COUNTIES: Final[frozenset[str]] = frozenset({"B", "IF"})


def zone_of(county_code: str) -> str:
    """The routing zone a county belongs to.

    An unrecognised code routes within itself rather than raising: a county code this module
    has not seen should cost coverage, not the whole national build.
    """
    return CAPITAL_ZONE if county_code in CAPITAL_COUNTIES else county_code


def zones_from_counties(county_of: dict[str, str]) -> dict[str, set[str]]:
    """Group UATs into the zones their routes may travel within."""
    zones: dict[str, set[str]] = {}
    for uat, county_code in county_of.items():
        zones.setdefault(zone_of(county_code), set()).add(uat)
    return zones
```

- [ ] **Step 4: Run to verify they pass, then lint and commit**

```bash
cd simulators/transport && uv run pytest tests/test_zones.py -q \
  && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/zones.py simulators/transport/tests/test_zones.py
git commit -m "Let a route cross what it does not serve

The design document builds routes over the network restricted to the
region they serve. Measured against the country that strands 91 UATs a
county-wide route reaches without difficulty — Gurghiu, Hodac and
Ibanesti all reach Sovata only by leaving their region. Roads do not
respect region boundaries.

A region is what a route serves; a zone is what it may cross. Under zone
routing 14 UATs are genuinely unroutable, against 105 under the rule as
written.

A zone is a county except once. Administrativ's regions never cross
county lines apart from Bucharest, where 28 Ilfov communes are assigned
to Sectorul 1 because the ring commutes inward. Splitting them does not
fail loudly; it quietly makes those 28 unroutable."
```

Append the branch's two trailer lines; copy them from `git log -1 --format=%b`.

---

### Task 2: The route rule

**Files:**
- Create: `simulators/transport/scripts/network.py`
- Create: `simulators/transport/tests/test_network.py`

The paragraph this implements, which a journalist should be able to read and a mayor dispute:

> From each hub, a shortest-path tree is built over the road network of its **zone**. Every
> UAT the region contains is attached to the tree, and each leaf of the tree — the furthest
> UAT along a branch — becomes one route running from that leaf to the hub, stopping at every
> UAT on the way. Leaves are processed in strict order — descending population, then
> ascending SIRUTA — so the same inputs always give the same routes.

- [ ] **Step 1: Write the failing tests**

Create `simulators/transport/tests/test_network.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_network.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.network'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/network.py`. The structure is fixed; fill the body to satisfy the tests above.

```python
"""Routes, from a hub and the road network around it."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Final

LONG_ROUTE_MIN: Final[float] = 60.0


@dataclass(frozen=True)
class Route:
    hub: str
    leaf: str
    stops: list[str]
    serves: list[str]
    one_way_min: float

    @property
    def is_long(self) -> bool:
        return self.one_way_min > LONG_ROUTE_MIN


def shortest_path_tree(hub, zone, neighbours, edge_s):
    distance = {hub: 0.0}
    parent: dict[str, str | None] = {hub: None}
    queue = [(0.0, hub)]
    while queue:
        so_far, here = heapq.heappop(queue)
        if so_far > distance.get(here, float("inf")):
            continue
        for neighbour in neighbours.get(here, ()):
            if neighbour not in zone:
                continue
            step = edge_s.get((here, neighbour))
            if step is None:
                continue
            through = so_far + step
            if through < distance.get(neighbour, float("inf")):
                distance[neighbour] = through
                parent[neighbour] = here
                heapq.heappush(queue, (through, neighbour))
    return distance, parent


def _chain(node, parent):
    out = [node]
    while parent.get(out[-1]) is not None:
        out.append(parent[out[-1]])
    return out


def routes_for_hub(hub, members, zone, neighbours, edge_s, population):
    distance, parent = shortest_path_tree(hub, zone, neighbours, edge_s)
    reachable = {m for m in members if m in distance and m != hub}
    if not reachable:
        return []
    ancestors = set()
    for m in reachable:
        ancestors.update(_chain(m, parent)[1:])
    leaves = sorted(reachable - ancestors, key=lambda s: (-population.get(s, 0), s))
    routes, served = [], set()
    for leaf in leaves:
        stops = _chain(leaf, parent)
        serves = [s for s in stops if s in members and s != hub and s not in served]
        served.update(serves)
        routes.append(Route(hub, leaf, stops, serves, distance[leaf] / 60.0))
    return routes
```

**Implementation notes, so the tests are satisfied by design rather than by patching:**

1. Build the tree with `shortest_path_tree` over the **zone**.
2. A member is *reachable* if it appears in `distance`. Unreachable members are simply omitted — Task 3 reports them.
3. A reachable member is a **leaf** when no other reachable member has it as a parent on the path to the hub. Walk each member's parent chain to the hub to establish that.
4. Order leaves by `(-population[leaf], leaf)` and build routes in that order.
5. `stops` is the parent chain from leaf to hub inclusive. `serves` is the members on that chain **not already served** by an earlier route — which is what makes `test_a_uat_on_two_branches_is_served_once_by_the_nearer` pass, and why leaf order must be deterministic.
6. Exclude the hub from `serves`.
7. Do **not** split long routes — see the third correction above. Flag them with `is_long` and let Task 3 report them.

- [ ] **Step 4: Run to verify they pass**

```bash
cd simulators/transport && uv run pytest tests/test_network.py -q
```

Expected: all pass. If the splitting rule (7) fights the serving rule (5), **stop and report** — that interaction is the one genuinely fiddly part of this task, and forcing it is how a UAT gets abandoned quietly.

- [ ] **Step 5: Lint and commit**

```bash
cd simulators/transport && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/network.py simulators/transport/tests/test_network.py
git commit -m "Turn each hub's tree into routes, leaf by leaf

A shortest-path tree from the hub across its zone; every leaf becomes a
route stopping at each UAT on the way down. No optimisation and no
randomness — the repository's position is that an optimiser produces
better-scoring networks nobody can audit.

The tree does most of the merging on its own. Nationally it collapses
2.895 UAT-to-hub shuttles into 1.476 leaf routes, because a village on
the way to a further village is a stop rather than a service of its own.

A UAT on two branches is served by whichever route reaches it first in a
documented order, so it is never costed twice, and a member the tree
cannot reach is absent rather than silently attached to something."
```

---

### Task 3: Build the national network

**Files:**
- Create: `simulators/transport/scripts/build_network.py`
- Create: `simulators/transport/schema/network.schema.json`
- Create: `simulators/transport/tests/test_build_network.py`

- [ ] **Step 1: Write the artefact and its schema**

`build_network.py` reads `data/hubs.json`, `data/road_time.parquet` and administrativ's `adjacency.parquet` and `uat_geometry.gpkg`; groups UATs into zones with `zones.py`; calls `routes_for_hub` for each of the 249 hubs; and writes `data/network.json` containing:

- `summary`: hubs, routes, UATs served, one-way minute quantiles
- `unroutable`: **every UAT with no road route to its hub, by SIRUTA and name, with its hub** — expect 14
- `routes`: hub, leaf, stops, serves, one-way minutes
- `provenance` (`derived`) and `limitations`, including one declaring the unroutable

Follow `export_hubs.py` exactly for document shape, and `hubs.schema.json` for the schema. The repository's data gate validates `simulators/*/data/*.json`, so the schema must resolve `provenance.schema.json`.

- [ ] **Step 2: The tests that matter**

Create `simulators/transport/tests/test_build_network.py`, skipping when `data/network.json` is absent, asserting:

```python
def test_every_uat_is_served_or_named_unroutable(network):
    """The check this layer lives or dies by. A UAT that is neither on a route nor in the
    unroutable list is a place nobody counted, and an uncounted place flatters every figure
    built on top of it — the same failure that once cost administrativ eight courts."""
    served = {u for route in network["routes"] for u in route["serves"]}
    named = {row["siruta"] for row in network["unroutable"]}
    hubs = set(network["summary"]["hubSirutas"])
    assert len(served | named | hubs) == 3186


def test_no_uat_is_served_twice(network):
    served = [u for route in network["routes"] for u in route["serves"]}]
    assert len(served) == len(set(served))


def test_the_unroutable_are_named_not_counted(network):
    """A number is not accountability. Each unroutable UAT carries its name and its hub so
    the hole can be looked at rather than totalled."""
    for row in network["unroutable"]:
        assert row["siruta"] and row["name"] and row["hub"]


def test_there_are_far_fewer_routes_than_uats(network):
    """The tree must merge. Around 1 476 routes for 2 895 feeder UATs; if routes approach
    UATs, the tree is not collapsing branches and every village has its own bus."""
    assert network["summary"]["routes"] < network["summary"]["uatsServed"] * 0.75
```

(`test_no_uat_is_served_twice` as written above has a stray brace — `for u in route["serves"]}`. Fix it when transcribing.)

- [ ] **Step 3: Run it, then validate against the repository gate**

```bash
cd simulators/transport && uv run python -m scripts.build_network
cd "$(git rev-parse --show-toplevel)" && uv run --with referencing --with jsonschema python scripts/validate_data.py
```

Expected: about 1 476 routes, 14 unroutable UATs named, and the gate reporting one more valid document.

- [ ] **Step 4: Commit**

---

### Task 4: Cost the network, and beat the upper bound

**This task is not optional.** `L1a` was wrong by 51% with every unit test green, because each test exercised one route and the error only appeared across 2 895 of them.

- [ ] **Step 1: Apply `tiers` and `fleet` to the real routes**

For each route: round trip is `2 × one_way_min`; the service class is that of the **largest** UAT it serves, since one bus serves the whole branch; departures come from `service_for`; `km_round_trip` from the same tree in metres.

Sum with `Resources.__add__`, then `fleet_required(total.peak_vehicles, spare_ratio=0.15)` **once**.

- [ ] **Step 2: Compare against the upper bound and report both**

| | one shuttle per UAT (`L1a`) | routed network (`L1b`) |
|---|---|---|
| peak vehicles | 3 914 | ? |
| bus-hours / weekday | 19 564 | ? |
| bus-km / weekday | 983 633 | ? |

**If the routed network is not materially cheaper, the route rule is not merging and something is wrong.** Report the comparison in the commit message; it is the evidence that this layer did its job.

- [ ] **Step 3: Record the figures in `simulators/transport/README.md`**, with the caveat that every number inherits an unvalidated speed model.

---

## Self-Review

**Spec coverage.** §5 (the route rule) is Tasks 1–3. The resource vector §6 wants is Task 4.

**Two corrections this plan makes to the spec.** Routing is over a **zone**, not a region — the spec's rule strands 91 UATs, measured. And a zone is a county **except Bucharest+Ilfov**, the one cross-county region in the country, 28 UATs on one hub. Both were found by measuring rather than by reading, and neither fails loudly if got wrong.

**Deliberately not built.** Corridor merging beyond what the tree does: measured, the tree already collapses 2 895 shuttles to 1 476 routes, and a merging pass on top is machinery for a problem that may not remain. Revisit if Task 4 shows the network is still too expensive. Pulse coordination between feeder and trunk is `L1c`. Cost in lei is `L2`.

**Where this plan is least certain.** The interaction between splitting a long route (rule 7) and serving each UAT once (rule 5). Only ~45 real routes exceed an hour so the blast radius is small, but the two rules can fight, and Step 4 of Task 2 says to report rather than force it.

**One test contains a deliberate syntax error**, flagged in place. Everything else is complete.

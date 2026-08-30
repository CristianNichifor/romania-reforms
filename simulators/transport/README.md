# transport — Romanian public transport simulator

What it costs per year to connect every one of Romania's 3 186 UATs to public transport at a
declared standard, and who can actually get where.

Design: [`docs/superpowers/specs/2026-08-29-transport-design.md`](../../docs/superpowers/specs/2026-08-29-transport-design.md).
Plan for this layer: [`docs/superpowers/plans/2026-08-29-transport-l0-travel-time.md`](../../docs/superpowers/plans/2026-08-29-transport-l0-travel-time.md).

## Status

**`L0` built and run at national scale. Derived throughout, and validated against nothing.**

The travel-time substrate exists, its inputs are measured, and its machinery is checked. What
does not exist anywhere in this repository is an observation of a real Romanian journey — so
the model is defensible part by part and unverified as a whole. That is a declared limitation
carried in provenance, not a footnote; every number built on `L0` inherits it.

First full run over the OSM Romania extract:

```
road_graph                 511.650 road features -> 5.710.662 junctions
seat_snapping              median 19 m, max 749 m; 0 beyond 5.000 m
routed_pairs               9.235 of 9.281 adjacent pairs; 46 unreachable
travel_time_distribution   median 16,0 min, p90 35,0 min, max 178,5 min
implied_speed              median 50,0 km/h over 9.086 pairs; 0 above 110
```

## L1: the network, and what it costs in vehicles

**Two tiers built: T3 feeders and T2 trunk. T1, county seat to county seat, is not built.**

Every UAT gets a **fixed, published** timetable. What population changes is how many
departures a place receives and where they sit in the day; what it never changes is whether
they can be relied on. Nothing here is booked in advance.

| class | UATs | people | departures/day | seats |
|---|---|---|---|---|
| basic | 887 | 1 247 536 | 4, all on the peaks | 20 |
| feeder | 1 587 | 4 967 997 | 9 | 40 |
| trunk | 712 | 12 838 282 | 16, across the day | 50 |

Routes come from a shortest-path tree out of each of the 249 hubs; every leaf becomes a route
stopping at each UAT down its branch. That alone collapses **2 895 UAT-to-hub shuttles into
1 537 routes**, because a village on the way to a further village is a stop rather than a
service of its own.

The network has two tiers, both from the same tree. **T3 feeders** take every UAT to its
centre; **T2 trunk** routes take every centre to its county seat. `members` decides what a
route serves and `zone` what it may cross, so a trunk route drives through the villages
between two centres without being responsible for them — their own feeder is.

```
             routes   one-way min: median   p90    max   over an hour
T3 feeder     1.537                  27,6  49,8  121,7             50
T2 trunk        171                  60,6 105,4  146,3             87

UATs served   2.923    unroutable 14    centres with no trunk route 1
accounted for 3.186 of 3.186
```

**The trunk leg is the longer half.** A feeder reaches a centre in a median 27,6 minutes; from
there to the county seat is a median 60,6. A full journey is therefore around 88 minutes one
way *before* any wait at the transfer, which is not yet modelled. Costing feeders alone would
have described a network that connects nobody to their county town.

### What the network costs

```
                        T3 feeder    T2 trunk     network
peak vehicles               2.351         477       2.828
bus-hours / weekday        14.295       5.805      20.100
bus-km / weekday          718.859     299.485   1.018.344
fleet incl. 15% spare                                3.253

annualised: 5,03 M bus-hours, 254,6 M bus-km
```

Two things that only show up once the tiers are separated.

**Merging works on the feeders.** Against the one-bus-per-village upper bound of 3 914 peak
vehicles, the routed feeders need 2 351 — down 40% — while driving falls only 27%, because
merging four villages onto one route removes three *concurrent* buses over similar ground.
Keeping the peak and the hours apart is the whole reason `fleet.py` exists.

**The trunk tier is cheap in fleet and expensive in hours.** It adds 20% more vehicles but
41% more bus-hours, from a tenth of the routes — long journeys run frequently, where feeders
are short journeys run rarely. That is the opposite shape to the feeders, and it is where the
operating cost will land when `L2` prices it.

**Spares are a depot float, applied once to the network.** Applying the ratio route by route
and rounding up buys a spare for every single-bus service — `ceil(1 × 1,15)` is 2, a 100%
margin from 15%. Measured, that was 6 809 buses against 4 502.

### The 14 places with no road

`data/network.json` names them rather than counting them, and named they validate the model:
Chilia Veche, Crișan, C.A. Rosetti, Maliuc, Pardina and Ceatalchioi in the Danube Delta,
Frecăței and Mărașu on the Brăila river islands. Reachable only by water, found without being
told they exist. Every cost figure here therefore describes the country **minus** those places.

## What L0 is

`simulators/administrativ` measures the road **distance** between the seats of adjacent UATs.
This measures the **time**, over the same OSM network, the same junction graph and the same
seat snapping — the only difference is that each segment is divided by a speed before the
search.

It is not only for this simulator. `justitie` already maps what court consolidation costs in
travel and carries an explicit caveat against its own figures: *kilometres are not hours;
forty in the mountains can cost more than eighty on the plain.* That caveat is a limitation of
the unit, and this is what retires it.

| file | what it holds |
|---|---|
| `scripts/measure_limits.py` | Measures signed limits per road class from OSM → `data/road-limits.json`. |
| `scripts/speeds.py` | Derives effective speed from those limits plus kinematics. |
| `scripts/build_road_time.py` | Drives administrativ's graph with a time weight → `data/road_time.parquet`. |
| `scripts/county_times.py` | Accumulates one-hop times into journeys, within one county. |
| `scripts/check_gate.py` | Comparison harness for recorded drive times. Currently uncalibrated. |

## Where the speeds come from

An earlier version of `speeds.py` was a column of judgement calls — `trunk: 75.0` and a
paragraph arguing that Romanian national roads do not deliver their legal 90. The argument was
right and the number was not, and nothing in the file could tell you which. It is now three
separable parts, so a critic can attack one without having to accept the others.

**1. Measured limits** (`derived`). From 505 456 OSM features, length-weighted. The finding
that shapes everything: below motorway, the *open-road* limit is essentially the national 90 on
every class. Trunk, primary, secondary and tertiary are not signed differently out in the
country. What separates them is how much of their length runs **inside a locality** at 50:

| class | inside a locality | open-road limit | coverage |
|---|---|---|---|
| motorway | 0% | 126,7 | 96% |
| trunk | 32% | 94,1 | 84% |
| primary | 51% | 88,0 | 88% |
| secondary | 59% | 89,2 | 74% |
| tertiary | 79% | 89,4 | 56% |
| unclassified | 95% | 88,6 | 41% |
| residential | 100% | 85,5 | 38% |

A DN is not slow because it is a worse road. It is slow because a third of it threads through
the villages it connects — a fact about settlement geography, not asphalt. Below 30% coverage a
class is marked unusable and takes the pessimistic fallback rather than pretending.

**2. Kinematics** (computed). Leaving a 90 zone for a 50 zone costs braking and re-acceleration
against cruising, from the speed change and the vehicle's rates. It is smaller than intuition
suggests — about five seconds per village for a bus — which is itself the point: a village
costs a minute of crawling and a few seconds of braking, so the crawl is what matters.

**3. Efficiency per class** (`assumed`). Curves, junctions, surface, traffic, and nobody driving
at the limit continuously. The one genuinely assumed term, per class because a motorway has no
junctions and a village lane is all junction. **This is where a dispute about these numbers
should land.**

Resulting effective speeds, km/h:

| class | car | bus |
|---|---|---|
| motorway | 119,9 | 94,8 |
| trunk | 60,9 | 57,1 |
| primary | 54,4 | 52,3 |
| secondary | 50,4 | 48,7 |
| tertiary | 44,3 | 43,5 |
| residential | 37,1 | 36,8 |

**A bus and a car converge below trunk.** Those roads are bound by their own geometry, not by
the vehicle, so on the rural network that carries most UAT-to-UAT travel, vehicle choice is not
a lever on journey time. The bus penalty is real only on motorway and trunk — which is where
the inter-county and trunk layers run, and nowhere else.

L0 uses the **car** profile: it is a road travel-time substrate, and `justitie` reads the same
graph to ask how far a citizen is from a courthouse. The bus profile belongs in the timetable
layer above, together with dwell time, which is not a property of a road.

## The change to administrativ is verified beyond what CI can show

`L0` gave `pipeline.build_graph` an optional speed argument, so administrativ's every region
boundary now flows through a function this simulator edited. CI cannot prove that safe: it
skips administrativ's reference-model and parity tests for want of the built artefacts.

With the artefacts present locally the full suite is **114 passed, 0 skipped** — where it is 64
passed and 50 skipped in CI. Those 50 include the parity fixtures, which compare the Python
reference model against the TypeScript port by hash across all 3 186 UATs. Every region
assignment is unchanged.

## What the run settled

**153 pairs administrativ cannot reach do have road routes** — 149 under the current model.
Administrativ bounds its search at 60 km of distance and records 195 adjacent pairs as
unreachable. Bounding by *time* reaches further along fast roads and routes most of them, 55 to
159 minutes. No pair goes the other way.

This matters outside this simulator: `reference_model._county_road_distances` substitutes a
straight-line estimate for an edge it has no measured distance for, so those pairs currently
carry a Euclidean guess in `justitie`'s published access map where the real drive is over an
hour.

**The search bound is not tight in practice.** `SEARCH_LIMIT_S` is derived from the table's
slowest road so that nothing administrativ can reach is truncated, which on paper clears the
worst case by two seconds. The longest hop actually routed is 99 minutes against a 180-minute
limit — the theoretical worst case, 60 km entirely at 20 km/h, does not occur.

## The gate, and what it is not

`scripts/check_gate.py` compares modelled times against drive times recorded by a human, in one
county — Vâlcea, because it has both the Olt gorge and real mountain roads, so the assumption
that a road class implies a speed is exercised rather than flattered.

Its reference set is split, because `L0` has two errors pointing opposite ways. The speed model
may be optimistic; `county_times` is deliberately pessimistic, since it routes through every
intermediate seat village rather than past it. Compared only as whole journeys the two partly
cancel and the gate would pass with both components wrong. So `adjacent` drives are checked
against the raw one-hop edge, where the accumulation cannot reach them, and bias is reported per
kind:

| adjacent | journey | what it means |
|---|---|---|
| biased | biased | the speed model is wrong |
| clean | biased | speeds are fine; the detour through intermediate seats is the cost |
| biased | clean | the two errors are cancelling — the dangerous case, now visible |

**It has not been run, and no drive times exist for it.** `sources/reference-drive-times-vl.csv`
holds twelve pairs chosen from the graph — six genuinely adjacent, six six-hops apart, spread
across gorge, hill and plain — with the times left as placeholders. The pairs are the part that
could be derived; the times are the part that could not.

So this is a **calibration harness that has not been calibrated**, and the layer's honest status
is *unvalidated* rather than *verified*. That state lives in `speeds.SPEED_PROVENANCE` and in the
limitations of `data/road-limits.json`, both checked by the repository's data gate, rather than
in a build that is red forever and learned to be ignored.

## Running it

```sh
# In simulators/administrativ, once. The OSM extract is 312 MB; end to end about twenty minutes.
uv run python -m pipeline.fetch --with-roads
uv run python -m pipeline.build_geometry
uv run python -m pipeline.build_seats
uv run python -m pipeline.build_adjacency
uv run python -m pipeline.build_road_distance
# check_gate reads administrativ's full model, not only its road graph:
uv run python -m pipeline.build_candidacy
uv run python -m pipeline.build_finance

# Then here:
uv run python -m scripts.measure_limits    # writes data/road-limits.json (committed)
uv run python -m scripts.build_road_time   # writes data/road_time.parquet (not committed)
uv run python -m scripts.export_hubs       # writes data/hubs.json (committed)
uv run python -m scripts.build_network     # writes data/network.json (committed)
uv run python -m scripts.cost_network      # vehicles, hours and km against the upper bound
uv run python -m scripts.check_gate        # the harness; needs recorded times to say anything
```

`data/road-limits.json` is committed — it is small, and it is the measurement the speed model
rests on. `data/road_time.parquet` is not: it is reproducible from the commands above.

# transport — Romanian public transport simulator

What it would cost per year to connect every one of Romania's 3 186 UATs to a **fixed, published**
public transport service, who could actually get where, and what a minute of journey time costs
to buy — by bus or by rail.

Design: [`docs/superpowers/specs/2026-08-29-transport-design.md`](../../docs/superpowers/specs/2026-08-29-transport-design.md).

## Status

**Built end to end and published.** Measured road limits → derived speeds → hubs → routes →
fleet → cost in lei → journey times → consolidation scenarios → rail track, rail cost, and the
comparison between them, on a map.

**Nothing here is validated against a recorded Romanian journey.** No such observation exists in
this repository. The model is defensible part by part and unverified as a whole; that is a
declared limitation carried in provenance, and every number inherits it. Rail is the exception in
one direction only — its speed model is anchored at both ends, to a measurement and to a
published national average.

## The headline

```
network      249 centres   1.708 routes   4.057 buses   1,80 mld lei/an
journey      median 98 min uncoordinated, 73 min pulsed (population-weighted)
rail         12.516 km of passenger line, 1.993 stations
             45,0 km/h as the track stands, 74,3 km/h rehabilitated
a minute     356 lei per passenger-hour by rehabilitating track
             0 lei per passenger-hour by coordinating the buses that already run
```

## What the model found

Three findings, each of which contradicted something in the design document or in my own
reasoning, and each of which is reproducible from the committed data.

### 1. Consolidating harder makes journeys *shorter*

The project was designed around a trade: fewer centres save administrative money and cost
travel time. The sweep says the trade runs the other way.

| scenario | centres | fleet | cost/yr | median journey | admin saving |
|---|---|---|---|---|---|
| default | 249 | 4 058 | 1,80 md | 73 min | 8,73 md |

| higher absorber bar | 233 | 4 009 | 1,79 md | 70 min | 8,81 md |
| smaller radii | 255 | 4 017 | 1,78 md | 75 min | 8,69 md |
| no population target | 347 | 4 028 | 1,79 md | 73 min | 8,20 md |
| **one centre per county** | **41** | **4 799** | **2,38 md** | **52 min** | — |

At one centre per county the journey is **28% shorter** and transport **33% dearer**. Removing
the hub removes the transfer, and the transfer was the expensive part. Between 233 and 347
centres almost nothing moves at all — under 1% on cost, under 5% on journey time — so the
parameter the reform argues about is not the parameter that matters.

The default row reads 4 058 against `data/cost.json`'s 4 057, because the sweep recomputes hub
assignment in memory while `build_cost` reads the committed `network.json`, and one tie breaks
differently. It is 0,003% of cost and one bus in four thousand — left alone, but held by
`test_the_sweep_default_agrees_with_the_costed_network` so that it cannot widen unnoticed.

### 2. Coordination beats capital, twice

Pulsing the timetable — same buses, same kilometres, same drivers, only the departure times
move — takes the median journey from 98 to 73 minutes. Population within 90 minutes goes from
46,9% to 57,5%. It costs nothing: `ceil(cycle / headway)` is unchanged by padding, so the
rounding does not buy a single extra vehicle.

Rail says the same thing from the other side. Rehabilitating track buys an hour of passenger
time for 356 lei. Buying the 7,0 m passenger-hours that pulsing gives away free would cost
**2,50 md lei a year — more than the entire bus network costs to run.**

These are unit prices, not two ways of serving the same people; rail passengers and bus
passengers are different people on different routes. What survives is the ordering: the
organisational fix goes first because it is nearly free, not because renewal is pointless.

### 3. Romania loses 39% of the speed its own alignment already permits

| | |
|---|---|
| measured line speed | **88,0 km/h** — OSM `maxspeed`, 8 485 main/branch segments |
| physics ceiling | **74,3 km/h** — kinematics at 10 km stop spacing |
| observed commercial | **45,0 km/h** — published national average |
| condition residual | **0,606** — *derived, not assumed* |

The gap is not geometry: the curves are where they are in both numbers. It is slow orders over
worn rail, single-track crossing waits, and the 65% of track and 85% of catenary CFR's own
renewal figures describe as life-expired. So the model does not assume a condition penalty; it
measures one as the residual between what the alignment permits and what the network delivers.

A perverse property falls out of CFR's tariff: it bands lines by permitted speed **including
permanent restrictions**, and charges 3,45 lei/train-km on the best band against 1,48 on the
worst. A worn line is cheaper to run on and slower. Renewal is partly self-taxing, and the model
charges it for that.

## The layers

| file | what it holds |
|---|---|
| `scripts/measure_limits.py` | Signed limits per road class from OSM → `data/road-limits.json`. |
| `scripts/speeds.py` | Effective road speed: measured limits + kinematics + one assumed efficiency. |
| `scripts/build_road_time.py` | Drives administrativ's graph with a time weight → `data/road_time.parquet`. |
| `scripts/county_times.py` | Dijkstra over UAT adjacency, within a routing zone. |
| `scripts/network.py` `tiers.py` | Routes from shortest-path trees; three fixed service classes. |
| `scripts/fleet.py` `costs.py` | Peak vehicles vs bus-hours; unit prices into lei. |
| `scripts/build_access.py` | Feeder + wait + trunk → `data/access.json`. |
| `scripts/sweep_scenarios.py` | Five consolidation scenarios → `data/scenarios.json`. |
| `scripts/rail_speeds.py` | Commercial speed by track condition class, calibrated at both ends. |
| `scripts/build_railnet.py` | Rail graph, station↔UAT join, county-seat times, map geometry. |
| `scripts/rail_costs.py` `build_rail_cost.py` | TUI, energy, crew, rolling stock, rehabilitation. |
| `app/` | MapLibre map. No basemap, no runtime calls, everything client-side. |

## Where the road speeds come from

Three separable parts, so a critic can attack one without accepting the others.

**1. Measured limits** (`derived`). Length-weighted over 505 456 OSM features. The finding that
shapes everything: below motorway the *open-road* limit is essentially the national 90 on every
class. What separates a national road from a communal one is how much of its length runs
**inside a locality** at 50 — 32% for trunk, 59% for secondary, 79% for tertiary. A DN is not
slow because it is a worse road; it is slow because a third of it threads through villages.

**2. Kinematics** (computed). Braking into a locality and accelerating out, from the speed
change and the vehicle's rates. About five seconds per village for a bus — smaller than
intuition suggests, which is itself the point: the crawl through the village is the cost, not
the braking at its edge.

**3. Efficiency per class** (`assumed`). Curves, junctions, surface, traffic. The one genuinely
assumed term, and **where a dispute about these numbers should land.**

| class | car | bus |
|---|---|---|
| motorway | 119,9 | 94,8 |
| trunk | 60,9 | 57,1 |
| primary | 54,4 | 52,3 |
| secondary | 50,4 | 48,7 |
| tertiary | 44,3 | 43,5 |
| residential | 37,1 | 36,8 |

**A bus and a car converge below trunk.** Those roads are bound by their geometry, not by the
vehicle, so on the rural network vehicle choice is not a lever on journey time.

## Where the money comes from

```
driver     0,42 md      running   1,00 md      standing  0,05 md
admin      0,18 md      capital   0,15 md      total     1,80 md
```

Operating cost scales with what the buses do; capital with how many must exist. Fold them
together and the trade between a peaky timetable and a large fleet disappears — which is how a
transit system gets costed wrong in a way nobody can see.

**The rail side is better sourced than the road side**, which was not expected. CFR publishes its
access tariff in the network statement and the procurements are public, so TUI, rolling stock
and rehabilitation are all `verbatim` — including a maintenance figure contracted separately,
the exact split no Romanian bus source would yield.

### Sanity checks

```
driver share of operating     25%    expect ~24%        ok
commercial speed             36,8    expect 25-40 km/h  ok
operating cost per bus-km    6,47    0,92x Buzau at 20 seats
```

Two of these pass only because earlier versions were wrong, and the corrections are the useful
part.

**The Buzău benchmark does not normalise across fleets.** ANRSC divides cost per vehicle-km by
average **seats**, and cost per km does not scale with seats — a 40-seat bus does not cost what
two 20-seat buses cost. An earlier version of this file claimed the model was 2,3× too low
against that benchmark. It was comparing at *our* mean of 41 seats; county programmes specify
capacities in the 20s, where the model sits at 0,92×. That bad comparison sent me chasing
maintenance and utilisation for a gap that was an artefact of the comparison itself.

**Driver share was reported as failing** against a 35–55% band. That band was Western European.
Wage-adjusted, Romania should sit near 22–24%, and the model does.

**Maintenance is derived, not guessed.** A European benchmark of 0,45 EUR/km, split into labour
and parts, with the Romanian wage ratio applied **only to the labour half** — a bearing costs
what a bearing costs. Discounting the whole figure is precisely the driver-share error again.
1,20 → 1,49 lei/km, and the model moved *toward* its benchmark and *upward* in cost.

## Errors worth keeping

Recorded because each was silent, and because the mechanism that caught each one is the
reusable part.

**The fleet was 51% wrong and 34 unit tests passed.** The spare ratio was applied per route, so
`ceil(1 × 1,15) = 2` bought a spare for every single-bus service: 6 809 buses against 4 502.
`Resources` now has no `fleet` field at all, and a test asserts its absence.

**A join matched 0 of 3 186 rows and rendered a plausible map.** `uats.geojson` carries no
properties — administrativ keys it by polygon position. The fatal guard in `copy-data.mjs`
exists because a silently empty join produces a uniform grey map that still renders, which is
worse than one that does not.

**The rail layer was blocked on a rule, not on data.** The spec said rail times must come from
the published *Mersul Trenurilor*. But this simulator models a counterfactual, and that
timetable describes the system being reformed — it would hard-code today's restrictions into an
answer about tomorrow. It was the wrong input, not the missing one. Once inverted, the layer
took one sitting.

**A 1,64× rail detour looked like a bug, so it was tested rather than published.** Sweeping the
junction-snap constant over a tenfold range moves the detour by 7% while halving the node count,
and connectivity stays complete at every setting. It is the Carpathians, not the graph.

**Two limitations went stale as the work landed.** `cost.json` was publishing "no unit price has
a public source" after several had been sourced, and `railnet.json` still declared rail cost
unmodelled after it was built. An artefact that lies about its own limits is worse than one with
no limits section, because it has been believed once already.

## What this cannot support

Seven `blocking` and `material` limitations travel with the data and reach the page. The ones
that would change a conclusion:

- **This is cost, not subsidy.** There is no demand model and no fare revenue anywhere here.
- **Train loading is assumed.** At 96 passengers a passenger-hour costs 356 lei; at half that,
  double. It is the single number that can overturn the rail comparison's order of magnitude.
- **The line class is deduced, not read.** CFR's official section-to-class list was not taken;
  class comes from measured OSM speed using CFR's own thresholds.
- **The station is not the village.** 5 of 42 county seats have their station beyond 2 km and
  need a bus to reach their own railway. Reported, not yet added to journey time.
- **14 UATs have no road route** — the Danube Delta and the Brăila river islands. Every figure
  here describes the country *minus* those places. They are named in `data/network.json` rather
  than counted, and they were found without being told they exist.

## Running it

```sh
# In simulators/administrativ, once. The OSM extract is 312 MB; about twenty minutes end to end.
uv run python -m pipeline.fetch --with-roads
uv run python -m pipeline.build_geometry
uv run python -m pipeline.build_seats
uv run python -m pipeline.build_adjacency
uv run python -m pipeline.build_road_distance
uv run python -m pipeline.build_candidacy
uv run python -m pipeline.build_finance

# Then here:
uv run python -m scripts.measure_limits    # data/road-limits.json      (committed)
uv run python -m scripts.build_road_time   # data/road_time.parquet     (not committed)
uv run python -m scripts.export_hubs       # data/hubs.json             (committed)
uv run python -m scripts.build_network     # data/network.json          (committed)
uv run python -m scripts.build_cost        # data/cost.json             (committed)
uv run python -m scripts.build_access      # data/access.json           (committed)
uv run python -m scripts.sweep_scenarios   # data/scenarios.json        (committed)
uv run python -m scripts.build_railnet     # data/railnet.json + geojson (committed)
uv run python -m scripts.build_rail_cost   # data/rail-cost.json        (committed)

cd app && npm ci && npm run build
```

`data/*.json` and `data/*.geojson` are committed: the first because `scripts/validate_data.py`
globs them into the repository's one data gate, the second because the app build runs in CI and
the pipeline that produces them cannot — it needs the OSM extract. `data/*.parquet` is not
committed; it is reproducible from the commands above.

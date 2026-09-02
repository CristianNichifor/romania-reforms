# transport — Romanian public transport simulator

What it would cost per year to connect every one of Romania's 3 186 UATs to a **fixed, published**
public transport service, who could actually get where, and what a minute of journey time costs
to buy — by bus or by rail.

Design: [`docs/superpowers/specs/2026-08-29-transport-design.md`](../../docs/superpowers/specs/2026-08-29-transport-design.md).

## Status

**Built end to end and published, and coupled live to the administrative reform.** The map reads
whichever consolidation scenario the reader built next door — from the same URL `justitie` reads —
and recomputes centres, routes, journeys, fleet, drivers, capacity and cost for it in the browser.
Measured road limits → derived speeds → hubs → routes → fleet → cost in lei → journey times →
rail track and rail cost, all following the reader's own map.

**Checked at both ends, and the two checks disagree in opposite directions.** The composite
commercial speed is 3,7% *slow* against 552 timetabled county bus runs read out of six county
councils' transport programmes; the road layer alone is ~10% *fast* against twelve routed car
drives in Vâlcea. Neither reference is ground truth and no measurement of Romanian free-flow
speed by class exists, so the errors are bounded and directional rather than resolved — which is
the most that can honestly be claimed, and is carried in provenance so every number inherits it.
Rail is anchored separately, at both ends, to a measurement and to a published national average.

## The headline

These are the **committed pipeline run** at the administrative model's default parameters and
the proposed service level — every figure below is read back out of `data/` by a test, so it
cannot drift. The browser recomputes the whole network live against whatever scenario the
reader builds, so its numbers will differ from these.

```
network      249 centres  1.708 routes  2.923 of 3.186 UATs reached
fleet        4.057 buses  5.552 drivers  6.538 duties a weekday
money        operator 1,75 md/yr  authority 0,20 md/yr  = 1,95 md public
             vehicles annualised 0,28 md  → 2,22 md a year, all in
authority    42 bodies, 22 staff each — 11,3% of operator cost, Movia 15,6%
demand       22% of offered seats, from population
             tickets 0,80 md, subsidy 1,14 md, 68 lei a head, 41% recovery
ledger       transport 2,22 md against an administrative saving of 8,73 md
             buses only — rail is priced separately and NOT added
rail         magistrale 9.839 km, secondary 2.677 km, 1.993 stations
             45,0 km/h as the track stands, 74,3 km/h rehabilitated
```

## What the model found

Three findings, each of which contradicted something in the design document or in my own
reasoning, and each of which is reproducible from the committed data.

### 1. Consolidating harder makes journeys *shorter*

The project was designed around a trade: fewer centres save administrative money and cost
travel time. It runs the other way. Move the administrative sliders towards fewer, larger units
and the median journey **falls** — because removing a hub removes the transfer, and the transfer
was the expensive part.

This is no longer a table of five precomputed scenarios. The page recomputes the whole network
from whatever map the reader arrived with, so the finding is reproducible by moving a slider
rather than by trusting a row. `#pt=100000&n=3`, for instance, gives 216 centres instead of 249.

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
| `scripts/rail_speeds.py` | Commercial speed by track condition class, calibrated at both ends. |
| `scripts/build_railnet.py` | Rail graph, station↔UAT join, county-seat times, map geometry. |
| `scripts/rail_costs.py` `build_rail_cost.py` | TUI, energy, crew, rolling stock, rehabilitation, extra track. |
| `scripts/export_traveltime.py` | The road graph for the browser: endpoints and times, 109 KB. |
| `scripts/export_speed_limits.py` | Signed `maxspeed` per road portion → `data/road-speeds.geojson`. |
| `app/src/consolidare.ts` | Runs the administrative model and routes it, in the browser. |
| `app/src/serviciu.ts` | Service levels, fleet, drivers, traction, capacity, cost, farebox. |
| `app/src/feroviar.ts` | The train judged against the bus, for the reader's own network. |
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

**You can look at the limits instead of taking the averages on trust.** The *Limitele de viteză
semnalizate* toggle draws `maxspeed` itself over 76 653 km of motorway, trunk, primary,
secondary and tertiary road — the same tags these three parts are derived from, unreduced. The
finding above stops being a claim and becomes a picture: **50 km/h on 29 033 km (38%) against
90 km/h on 16 359 km (21%)**, the villages and the open road, with the 90 dropping to 50 at
every settlement the length of the country.

Untagged is its own grey band and is never filled with a default. 21 626 km — 28% — carry no
`maxspeed` in OSM, and the gap is not spread evenly: coverage runs 96% on motorway down to 56%
on tertiary, so it is thinnest exactly where the model leans hardest. A road without a tag
still has a limit; what is missing is a mapper's record of it. Painting those at an assumed 90
would manufacture the very fact the layer exists to show.

The 5,7 MB of geometry is **not committed**. The repository sits at 54 of the 60 MB its own
size gate allows, and that gate's rule is that the fix for a full repository is to stop
committing derived payloads rather than to raise the ceiling. Build it with
`uv run python -m scripts.export_speed_limits` and the layer appears; without it the toggle
disables itself and says why, and the build does not fail — CI has no OSM extract and never
will. That means the published site does not currently carry this layer.

**Both ends are now checked, and they disagree in opposite directions.** At the far end, the
commercial speed this produces is 36,8 km/h against 38,2 measured over 552 timetabled county
bus runs — 3,7% **slow**, inside their interquartile range. On the road layer alone,
`scripts/check_gate.py` compares twelve routed car drives in Vâlcea from OSRM: the table runs
10,9% **fast** on single hops and 9,3% fast on six-hop journeys.

Two things follow. The accumulation through intermediate seats costs about 1,6 points, not the
large pessimism the gate was built to expose — in Vâlcea the seat villages sit near the direct
line. And since the two checks lean opposite ways, the service factor and dwell are absorbing
more than a correct road layer would need, *or* OSRM's rural profile is conservative. Neither
reference is ground truth and no measurement of Romanian free-flow speed by class exists to
settle it. The errors are bounded and their direction is known, which is the most that can
honestly be claimed.

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
driver share of operating     29%    expect ~24%        ok
operating cost per bus-km    6,87    expect ~9,0 RON    ok
commercial speed             36,8    expect 25-40 km/h  ok
km per bus per year         62.752   real range 60-80k  ok
```

All four pass, and two of them only because earlier versions were wrong. The corrections are
the useful part.

**The Buzău benchmark is recorded, not used.** Consiliul Județean Buzău approved 0,35
lei/km/loc in 2025 — the only Romanian operating figure this project found. It cannot be
converted: ANRSC divides cost per vehicle-km by average **seats**, and cost per kilometre does
not scale with seats, so multiplying by a seat count corresponds to nothing. Converting would
need their fleet composition, which is in a scanned PDF.

It was carried as a failing check for most of this project — first as "the model is 2,3× too
low", which was wrong and was withdrawn, then as a band of ratios that still read as a failure.
The checks that *do* convert all pass. An unconvertible number kept beside them gave a
non-result the weight of a problem, so it is now a note.



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

- **Demand is population times a flat rate.** The level is anchored — the county layer is
  13,4% of Romania's measured bus passenger-km — but the rate does not fall with distance, so
  route-level occupancy is wrong in a known direction: long routes to isolated communes are
  emptier than modelled, short periurban ones fuller.
- **The institutional design is checked against nothing.** `INSTITUTIONS.md` argues it from
  the model's own constraints and from Danish practice. Everything else here has a benchmark;
  that document does not, and it does not cost the authorities it proposes.
- **Train loading is assumed.** At 96 passengers a passenger-hour costs 356 lei; at half that,
  double. It is the single number that can overturn the rail comparison's order of magnitude.
- **The line class is deduced, not read.** CFR's official section-to-class list was not taken;
  class comes from measured OSM speed using CFR's own thresholds.
- **The station is not the village.** 5 of 42 county seats have their station beyond 2 km and
  need a bus to reach their own railway. Reported, not yet added to journey time.
- **14 UATs have no road route** — the Danube Delta and the Brăila river islands. Every figure
  here describes the country *minus* those places. They are named in `data/network.json` rather
  than counted, and they were found without being told they exist.

## Who would run it

A cost model without an institutional design is a spreadsheet that assumes someone will sort
this out. [`INSTITUTIONS.md`](INSTITUTIONS.md) names the buyer, the contract and the payer: a
county transport authority constituted as an ADI under Legea 92/2007, buying operations on
gross-cost contracts tendered in lots under Reg. (CE) 1370/2007, owning the vehicles and depots
itself. Its central finding is that **no new primary legislation is required** — the authority,
the contract form and the regulator all exist. What is missing is the network to put in them.

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
uv run python -m scripts.build_railnet     # data/railnet.json + geojson (committed)
uv run python -m scripts.build_rail_cost   # data/rail-cost.json        (committed)

cd app && npm ci && npm run build
```

`data/*.json` and `data/*.geojson` are committed: the first because `scripts/validate_data.py`
globs them into the repository's one data gate, the second because the app build runs in CI and
the pipeline that produces them cannot — it needs the OSM extract. `data/*.parquet` is not
committed; it is reproducible from the commands above.

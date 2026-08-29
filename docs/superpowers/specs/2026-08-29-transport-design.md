# transport — design

**Status:** agreed, not yet built. No code exists.
**Next plan covers `L0` only** — the road travel-time substrate and its verification gate.
Each later layer gets its own plan once the one beneath it has passed.
**Date:** 2026-08-29
**Simulator:** `simulators/transport/`, fourth in the repository.

---

## 1. What it claims

> Connect every one of Romania's 3 186 UATs to public transport at a declared standard.
> What does it cost per year, and who can actually get where.

The reader sets a service standard and a hub structure. The model derives the network, the
vehicles, the staff, the annual cost, and the resulting accessibility. Every threshold is an
input the reader can move and dispute; the rules that consume those thresholds are fixed and
written down.

**Version 1 produces cost and access. It does not produce ridership, revenue, or fares.**

That refusal is the point. Estimating Romanian transit demand means elasticities nobody
publishes, and a cost number contaminated by a demand guess can be dismissed by attacking the
guess. A cost derived from a *declared standard* can only be attacked on the standard itself,
which is exactly the argument worth having. Fares and demand arrive in `L5`, behind explicit
assumption bands, once the cost figure stands on its own.

---

## 2. Scope

**In v1:** all 41 județe plus București — 3 186 UATs. Networks are built inside county
boundaries, matching administrativ's constraint that regions never cross county lines. The
inter-county layer is rail, and arrives with `LR`.

**Deliberately not modelled, v1:** demand, revenue, fare structure; urban networks operating
*inside* a municipality (STB, CTP Cluj and their peers are treated as out of scope, and a
county network terminates at the municipal boundary); school transport, which in Romania runs
on a separate legal and financial track; driver *availability* as a binding constraint, which
is reported but does not limit the model.

**Geographic scope is national, but the verification gate is one county.** A hand-checked
county is the only way to catch a systematic road-speed error before it propagates into every
downstream number. See §14.

---

## 3. Coupling to administrativ

The consolidation simulator already computes, at default settings, **3 186 UATs → 682
regions**, each with an absorber seat. Those absorber seats are this simulator's hubs. The
hierarchy therefore already exists in the repository and does not need inventing:

```
3 186 UATs   →   682 region centres   →   42 county seats
   feeder              trunk                inter-county
```

**The transport engine does not import administrativ's engine.** It consumes a single input
interface:

```
hubOf : SIRUTA → SIRUTA
```

Two providers satisfy it:

- **frozen** — one administrativ scenario exported to a data file. This is v1. There is no
  engine coupling, no shared package, and transport is testable entirely on its own.
- **live** — administrativ's TypeScript model running in the worker alongside this one, so
  moving the *radius slider* moves the *bus fleet*. Later, same engine, different provider.

The staging matters because the repository's stated rule is that a shared package waits for a
second real consumer. Under `frozen` there is no second consumer and nothing to extract.
Under `live` there provably is — and by then the surface to extract will be known rather than
guessed. This is the same discipline the README applies to `packages/ui` and `justitie`.

### What the coupling unlocks

Administrativ already runs `build_finance.py`, which separates operating from development
expenditure per UAT. Consolidation is argued for as an administrative saving. Transport is
its counter-ledger: fewer centres means cheaper administration and longer journeys, therefore
more bus-hours. With rail (`LR`) the ledger becomes three columns:

| administrative saving | added transport cost | cost of using the railway that already exists |
|---|---|---|

Putting those in the same currency on the same page is the reason this simulator belongs in
this repository rather than in a separate one.

---

## 4. The service rule

**Every UAT gets a published timetable.** What varies with population is how many departures a
UAT receives and where they sit in the day. What never varies is whether those departures can
be relied on. Nothing in this simulator is booked in advance.

A UAT's service class follows from its population, through one table the reader edits:

| band | class | vehicle | service |
|---|---|---|---|
| smallest | **basic** | small bus | fixed and published; few departures, placed on the peaks and on the hub pulse |
| middle | **feeder** | small or medium bus | fixed and published; peak-frequent, thinned off-peak |
| largest, or is a hub | **trunk** | full bus | fixed and published; pulse headway across the service day |

Thresholds, vehicle sizes and departure counts are all inputs. The *structure* — three classes
assigned by population band, all of them fixed-route and published — is fixed.

### Predictability is a design constraint, not a service level

An earlier draft made the smallest tier demand-responsive — book-ahead minibuses, on the Danish
**flextrafik** model, which exists because a clockface timetable to a 200-person village is
ruinous. That was rejected, and the reasoning is worth recording because it is a values
decision rather than a technical one.

A public system's first obligation is that it can be relied upon without arrangement. Booking
is a barrier that falls hardest on exactly the population rural Romanian transit exists to
serve: the elderly, people without smartphones or data, people making unplanned trips. A
service you must telephone for is not a public network; it is a subsidised taxi with a
timetable-shaped hole where the timetable should be.

The cost objection that motivated flex is real, but it is answered better by **frequency than by
responsiveness**. A small commune does not need an hourly bus. It needs four departures that
always run, timed to school, work and the hub pulse. That is stable, predictable, and still far
cheaper than clockface headway — and unlike flex, it is a network.

Flex is retained as an optional **comparison scenario** at `L2`, so a reader can price the
alternative and see the trade rather than have it decided for them. It is not the default and
it is not a tier.

**This design costs more than the flex design.** Fixed service to all 3 186 UATs is more
expensive than book-ahead minibuses to the smallest of them. The simulator reports that
difference rather than shaving it.

### The service day

Because departures are placed rather than merely counted, each class declares its departures
across a **day profile**: AM peak, midday, PM peak, evening, and a separate weekend profile.
The profile is an input. It is what allows the model to be sized for peaks rather than for
averages, and it is what makes §6's fleet arithmetic possible at all.

**Why distance is absent from this table.** Distance does not change a UAT's *service class*,
but it fully drives that service's *cost*: a UAT 40 km from its hub generates roughly four
times the bus-km of one at 10 km, a longer cycle, and possibly an additional vehicle to hold
the headway. Remoteness therefore enters through the cost engine (`L2`), not the tier rule
(`L1`). The rule stays one paragraph; the geography still bites. This split was chosen
deliberately over a two-axis population × distance grid, which is more defensible in transport
terms but gives the reader more sliders than they can reason about and cannot be explained in
a paragraph.

---

## 5. The route rule

The paragraph a journalist reads and a mayor disputes — the counterpart to administrativ's
gravitational accretion:

> Each UAT is assigned to its hub. From the hub, a shortest-path tree is built over the road
> network restricted to that region; every leaf-to-hub path is a candidate route; paths sharing
> more than a threshold fraction of their length merge into one corridor. A route exceeding the
> maximum one-way duration splits at the furthest point that still fits. Trunk routes run
> region centre to county seat along the fastest road path. Candidates are processed in strict
> order — descending population, then ascending SIRUTA — so ties resolve identically on every
> run.

No optimisation, no randomness, no annealing. Same inputs, same routes, byte for byte. This is
the repository's stated position: an optimiser produces better-scoring networks that nobody can
audit or argue with, and that trade is refused on purpose.

---

## 6. Pulse timetable, and vehicles

Feeders and trunk meet at the region centre on a repeating clock — all arrive, a short dwell,
all depart. A journey is then *ride plus a short transfer*, not *ride plus half a headway*.
Same fleet, materially better accessibility. It is what makes Danish and Swiss regional
networks usable, and it is the single largest lever on the `L3` numbers.

Vehicles on a route:

```
vehicles = ceil( (round_trip_time + layover) / headway )
```

Under pulse, `round_trip_time + layover` is first rounded **up to a whole multiple of the pulse
interval**. That rounding sometimes buys an extra vehicle, and **the model reports those
vehicles as their own line item.** It is the honest price of a connection that actually
connects, and hiding it inside a total would misrepresent what pulse costs.

### Sizing for the peak

The formula above is evaluated **per period of the day profile**, not once. Two different
numbers fall out of it, and conflating them is the classic way to under-cost a transit system:

- **Peak vehicle requirement (PVR)** — the maximum concurrent vehicles across all periods.
  **This sizes the fleet, and therefore CAPEX.** A bus bought for the 07:00 peak stands in the
  depot at 11:00. That is not waste; it is what being able to serve the peak costs, and a system
  that owns only its average fleet cannot serve a peak at all.
- **Bus-hours** — summed across every period. **This drives OPEX and driver numbers.**

They diverge, and the ratio between them is itself an output worth displaying: a peaky service
carries a high fleet cost per bus-hour, a flat one a low one. A reader flattening the day
profile can watch OPEX rise while CAPEX falls, which is the actual trade a transport authority
faces.

**Spare ratio.** Fleet is `PVR × (1 + spare ratio)`. Vehicles under maintenance or repair cannot
run a published departure, so a system that owns exactly its PVR will cancel service routinely.
The ratio is an explicit input, not an allowance folded into an average — named, it reads as the
cost of the timetable being true; buried, it reads as slack that an opponent will propose
cutting.

The **pulse interval is a slider, not a constant.** Sixty minutes is the Danish default and the
natural clockface; 120 minutes is what a poor county could actually afford. The difference
between them is one of the more interesting things the simulator can show.

**Drivers:** bus-hours × a platform-to-paid ratio (sign-on, breaks, deadhead) gives driver-hours;
EU Regulation 561/2006 on driving times together with Romanian labour law converts those to
FTE. The platform-to-paid ratio is an assumption and is marked as one.

---

## 7. Modes, and the network hierarchy

| tier | link | mode |
|---|---|---|
| **T3** | UAT → region centre | bus — basic, feeder or trunk class by the §4 rule |
| **T2** | region centre → county seat | **rail where track exists and serves, otherwise bus** |
| **T1** | county seat ↔ county seat | **rail** |

The mode-choice rule, applying at T2 only:

> A T2 leg is served by rail when both ends have a station within the walk-or-shuttle radius of
> their seat point, the line is open, a service runs on it, and rail journey time does not
> exceed road journey time by more than the tolerance. Otherwise it is served by bus.

The radius and the tolerance are inputs. T1 is rail by definition; T3 is never rail.

**Pulse inverts at a rail hub.** Danish and Swiss practice is that the train is the spine: its
clockface is the anchor and buses are timed to *it*, never the reverse. At a rail hub the train
timetable is therefore exogenous and the bus cycle constraint solves against it. This is a
simplification of the engine, not a complication.

---

## 8. Rail: infrastructure is given, service is derived

A bus route can be invented with a slider. **A railway cannot.** Rail therefore enters as
*infrastructure input*, and the decision variable is the **service run on it** — trains per day
and stopping pattern — not where the line goes. The one genuine geographic lever is which
closed lines reopen, which is a toggle over a known set rather than a generator.

This splits the rail cost model in the way that matters:

- **Marginal cost on open track** — track access charge (TUI, published by CFR SA as
  infrastructure manager in the network statement), energy, crew, rolling-stock hours. Low,
  because the infrastructure is already paid for.
- **Capital cost to reopen or electrify** — per kilometre, and an order of magnitude higher.

Which is the argument: Romania owns a large railway network running very little service. The
cheapest new transit capacity in the country may be track already lying in the ground. The
simulator should be able to price that claim rather than assert it.

### Two hard problems, accepted up front

**Rail time is not geometry.** Romanian journey times are dominated by speed restrictions, not
by distance; the same 100 km may run in 70 minutes or 180 depending on track condition.
Computing rail time from OSM line geometry multiplied by a design speed would produce numbers
that are plausible and quietly wrong — exactly the failure mode this repository's gates exist to
catch, and the same class of error as administrativ's silently dropped court rows. Therefore:

> **Rail journey times for existing services come from the published timetable, never from the
> map.** Reopened or modernised lines take an assumed design speed, marked `assumed`, and the
> limitation is declared against every output that depends on it.

Geometry is nonetheless free — the Geofabrik Romania extract already downloaded for roads carries
`railway=rail` and station nodes — it is simply not trustworthy for times.

**The station is not the village.** Halte sit two to five kilometres outside the settlement they
are named for, and are frequently named for a different settlement altogether. Station-to-UAT is
a new join of the same class as administrativ's SIRUTA crosswalk, and takes the same rule: an
explicit crosswalk, a documented resolution per mismatch, and a loud failure on unmatched rows
rather than a silent drop. It also means a rail-served UAT may still need a bus to reach its own
halt — an honest and somewhat damning property of Romanian rail that the model shows rather than
hides.

---

## 9. Engine units and their boundaries

Eight units. Each takes explicit inputs, returns plain data, holds no shared mutable state.

| unit | takes | gives |
|---|---|---|
| `traveltime` | seats, roads, road-class speed table | seat-to-seat road minutes, intra-county |
| `railnet` | lines (open/closed/electrified), stations, published timetables | rail graph, station↔UAT join, rail minutes |
| `hubs` | *provider interface* `hubOf` | UAT → hub assignment |
| `tiers` | population, tier table, day profile | service class, vehicle type, departures per period |
| `network` | hubs, tiers, traveltime, railnet | route set, as **legs carrying a mode** |
| `timetable` | routes, pulse interval, train clock, day profile | per-period vehicles, **PVR**, bus-hours, bus-km, train-hours, train-km |
| `cost` | resource vector, per-mode rate table | OPEX, CAPEX, annualised |
| `access` | timetable | isochrones over mixed-mode chains |

The boundary that earns its keep: **`cost` never sees geography, and `timetable` never sees
lei.** A reader disputing the driver wage touches one unit and re-runs arithmetic. A reader
disputing road speeds touches another. Neither can silently move the other.

The road matrix and the rail matrix are **kept separate and never blended into a single
number**, because they have different sources and deserve different trust.

The interface that carries multimodality:

```
Leg = { from, to, mode: 'bus' | 'rail' | 'flex', tier: 'T1' | 'T2' | 'T3', minutes, km }
       // 'flex' never appears in the default scenario — only in the L2 comparison run
```

The resource vector is per-mode: bus-hours, bus-km, train-hours, train-km, and vehicle counts by
type. **Setting the rail line set to empty yields exactly the bus-only simulator.** There is no
branch and no second engine — v1 is the multimodal engine with one input absent.

---

## 10. Data flow and layout

```
sources → scripts/ (Python reference) → data/ artefacts → export.py
        → typed arrays → Web Worker (TypeScript port) → MapLibre
```

Parity suite between the Python reference model and the TypeScript port, as in administrativ.

```
simulators/transport/
  schema/    service-standard · network · costs · railnet
  scripts/   build_traveltime · build_railnet · build_hubs · reference_model · export
  data/      travel-time matrices, hub assignment, cost line items, rail graph
  sources/   INS Tempo pulls, Danish trafikselskab reports, CFR timetables, county programmes
  engine/    TypeScript port
  app/       Vite + MapLibre, model in a Web Worker
```

Matches the repository's stated per-simulator layout. Adding it means the five explicit edits
the README describes: the simulator directory, a CI job, a deploy build step with `VITE_BASE`,
a line in the assembly step and its path check, and a card in `site/index.html`.

---

## 11. Data sources

| layer | source | note |
|---|---|---|
| UAT boundaries, seats, roads, adjacency | reuse administrativ's pipeline | already built and gated |
| Population | INS, Census 2021 | via administrativ |
| Hub assignment | administrativ scenario export | the `frozen` provider |
| Rail geometry, stations | OSM / Geofabrik Romania extract | same extract as roads |
| Rail journey times | published timetable (*Mersul Trenurilor*) | **times come from here, not geometry**; licence to be confirmed at import |
| Track access charge | CFR SA network statement (*documentul de referință al rețelei*) | published and regulated |
| Line status, electrification, reopenings | CFR SA network statement; MPGT and PNRR project lists for the normative set | |
| Driver wages | INS Tempo earnings series | CAEN choice matters: 4931 urban/suburban vs 4939 other land passenger vs 4910 rail — record which, per line item |
| Fuel, energy, maintenance, insurance, depot | line-item sources, each cited individually | |
| Danish benchmark band | trafikselskab annual reports (Midttrafik, Sydtrafik and peers): cost per bus-hour, per flextur trip | outer band only, never a source for a Romanian figure |
| County transport programmes | county councils | `L4`; see §16 |

Importers download their sources on first run and keep them, so a re-import does not depend on a
government website being up. That is already the repository's practice.

---

## 12. Cost model

Bottom-up. Cost per bus-hour and per bus-km is assembled from line items — driver wage,
fuel or energy, maintenance per km, depot, insurance, overhead — **each separately sourced and
each separately disputable**. Rail is assembled the same way over its own line items, with the
marginal/capital split of §8.

The assembled total is then checked against the wage-adjusted Danish cost per bus-hour. **That
band is a sanity check, never a source.** If the bottom-up figure lands far outside it, a line
item is wrong and the build says so. A Romanian number derived from a Danish number by ratio
would not survive contact with a critic, and would not deserve to.

CAPEX covers fleet purchase and renewal, depots, and — for rail — rolling stock and any
reopening or electrification the reader switches on. Annualised over stated asset lives.

**Fleet CAPEX is driven by `PVR × (1 + spare ratio)`, never by average vehicles in service.**
Costing a fleet off average utilisation understates it by whatever the peak-to-average ratio is,
which for a commuter-shaped rural network is substantial.

**Diesel in v1; electric as a scenario toggle at `L2`.** The fork is large in both CAPEX and
OPEX and has live PNRR funding relevance, but it is a toggle over the same engine rather than a
structural question.

---

## 13. Provenance and declared limitations

Per `packages/provenance`:

- `verbatim` — INS Tempo wage tables, published timetable times, published track access charges.
- `derived` — cost per bus-hour, cost per bus-km, vehicle counts, driver FTE.
- `assumed` — layover and platform-to-paid ratios, every tier threshold, the shape of the day
  profile, the spare ratio, road-class speeds, rail times on reopened or modernised lines, asset
  lives.

Declared limitations, each naming the outputs it affects:

- No demand model in v1. Affects nothing v1 publishes, and is declared so that the absence is
  visible rather than inferred.
- Tier thresholds are **normative, not observed** — they describe a standard someone would have
  to choose, not behaviour anyone has measured.
- Road travel times are free-flow estimates from road class, not measured times.
- Rail times on non-operating lines are assumed, and the gate in §14 enforces that they are
  marked.
- Driver availability is reported but not constrained; Romania has a driver shortage that the
  model does not represent.
- Station-to-settlement distance means "rail-served" overstates convenience for some UATs.

---

## 14. Verification gates

Nothing downstream is built until the gate above it passes. This ordering is taken directly from
administrativ, where a wrong road-crossing flag would have produced a map that looked plausible
and was quietly incorrect.

1. **`L0` road travel time — one county, hand-checked.** Roughly a dozen seat-to-seat pairs
   verified against real drive times, with a stated tolerance, failing loudly. National scope,
   county-scale audit. Nothing in `L1` builds until this passes.
2. **Coverage.** Every one of the 3 186 UATs appears on exactly one route, with at least one
   departure in the day profile. No UAT may be served only by a scenario variant. No
   silent drops. Administrativ lost eight courts — including all six Bucharest sector courts —
   to precisely this failure, and it was caught by a structural check rather than a tolerance
   check. The structural check is the one that goes here.
3. **Station↔UAT join.** Fails loudly on unmatched rows, with a documented resolution for each
   mismatch, exactly as the SIRUTA crosswalk does.
4. **Rail time provenance.** Any rail leg whose time is geometry-derived rather than
   timetable-derived **must** be marked `assumed`, or the build fails. This is the automated
   guard against the §8 failure mode.
5. **Determinism.** Same inputs produce a byte-identical resource vector. Note administrativ's
   lesson: GeoPackage embeds a `last_change` timestamp, so a changed `.gpkg` checksum on its own
   means nothing — hash content, not files.
6. **Parity.** Python reference model against the TypeScript port.
7. **Sanity band.** Bottom-up cost per bus-hour lands inside the wage-adjusted Danish band, or
   the build reports the discrepancy out loud.

---

## 15. Performance

Administrativ recomputes in about 15 ms against a 150 ms budget, so slider drags feel
continuous. Transport is heavier: shortest-path trees across some 682 regions.

The split: **the pipeline precomputes travel-time matrices and per-region shortest-path trees;
the browser does tier assignment, corridor merge, cycle arithmetic, and cost arithmetic.** Same
150 ms target. If pulse cycle-solving breaches it, per-region route candidates move into
precomputation as well.

Same two constraints as administrativ, and for the same reasons: entirely client-side, no
backend or solver service; deterministic and explainable, same inputs to identical output.

---

## 16. Build order

```
L0   road travel time              ── gate: one county, hand-checked
L1   network + timetable           (mode-aware; rail line set empty)
L2   cost                          ──► ship map 1 · bus-only annual cost
L3   access                        ──► ship map 2 · isochrones
LR   railnet + station join + timetables
                                   ──► ship map 3 · multimodal + the three-way ledger
L4   the county transport programmes   (independent; may run in parallel at any time)
L5   fare + demand — Rejsekort proper
```

`L2` is the first public artefact, and it deliberately ships before any demand assumption exists.

`L4` is pure import work and the largest import in the repository — 41 counties of heterogeneous
documents. It is independent of every other layer and turns "X lei per year" into "X versus what
is spent today". One caution to resolve at import: the legal framework for county transport
churned around 2022–2023, so the importer must record which regime each programme was issued
under rather than assuming a single format.

`L5` is where fares, revenue, farebox recovery and the Rejsekort account-based ticketing
question live — including the ticketing system's own capital cost, which in Denmark is a
famously cautionary and well-documented figure, and the clearing problem across 42 separate
transport authorities.

---

## 17. Headline outputs

**`L2`:** *Every UAT connected: X lei per year, Z buses, W drivers.* Beside it, administrativ's
operating expenditure per UAT, so the administrative saving and the transport cost sit in the
same currency on the same page.

**`L3`:** the share of population able to reach their county seat within 30, 60 and 90 minutes —
and the same map with pulse switched off, which shows what coordination alone is worth at
constant fleet. This layer also feeds `justitie` directly: how long it takes to reach the court
that would serve you under the consolidated map.

**`LR`:** the three-way ledger — administrative saving, added bus cost, and the cost of running
service on railway that already exists.

---

## 18. Cut from v1

No demand, no revenue, no fares. No urban networks inside municipalities. No school transport.
No live administrativ coupling — `frozen` provider only. Driver supply reported, not constrained.

**Demand-responsive service is not a tier.** Every UAT receives fixed published departures. Flex
survives only as an optional comparison scenario at `L2`, priced against the Danish flextur
figures so the trade is visible rather than assumed.

CFR rail and the inter-county layer are **not** cuts. They are `LR`, and the engine is built
mode-aware from the first commit so that adding them requires no rewrite of `network`,
`timetable`, `cost` or `access`.

---

## 19. Decisions deferred, deliberately

- **Pulse interval default.** A slider from the start; the shipped default waits until `L2` shows
  what 60 versus 120 minutes actually costs.
- **Electric fleet.** A `L2` scenario toggle, not a v1 structural question.
- **County transport contracts from SICAP/SEAP.** Real prices that counties actually pay, and a
  strong validator against the bottom-up model — the gap between what service *should* cost and
  what is *actually* paid could be the most interesting figure in the simulator. Deferred because
  contracts bundle incompatible scopes (gross-cost versus net-cost, vehicles included or not) and
  normalising them is its own project. Lands after v1, alongside or within `L4`.
- **`live` administrativ coupling.** Waits until the transport engine is proven against `frozen`.

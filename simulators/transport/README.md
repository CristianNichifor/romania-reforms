# transport — Romanian public transport simulator

What it costs per year to connect every one of Romania's 3 186 UATs to public transport at a
declared standard, and who can actually get where.

Design: [`docs/superpowers/specs/2026-08-29-transport-design.md`](../../docs/superpowers/specs/2026-08-29-transport-design.md).
Plan for this layer: [`docs/superpowers/plans/2026-08-29-transport-l0-travel-time.md`](../../docs/superpowers/plans/2026-08-29-transport-l0-travel-time.md).

## Status

**`L0` built and run at national scale. Not yet verified.** The substrate exists and its
machinery is sound; the gate that would make its *numbers* trustworthy has not been run,
because it needs drive times a human has to record. Nothing above `L0` may be built until it
passes.

First full run, over the OSM Romania extract:

```
road_graph                 511.650 road features -> 5.710.662 junctions
seat_snapping              median 19 m, max 749 m; 0 beyond 5.000 m
routed_pairs               9.239 of 9.281 adjacent pairs; 42 unreachable
travel_time_distribution   median 14,6 min, p90 31,9 min, max 159,2 min
implied_speed              median 54,5 km/h over 9.086 pairs; 0 above 110
```

### What the run settled, and what it did not

**Settled: 153 pairs administrativ cannot reach do have road routes.** Administrativ bounds
its search at 60 km of distance and records 195 adjacent pairs as unreachable. Bounding by
*time* instead reaches further along fast roads, and finds routes for 153 of them — 55 to 159
minutes, median 81. No pair went the other way. This matters outside this simulator:
`reference_model._county_road_distances` substitutes a straight-line estimate for an edge it
has no measured distance for, so those pairs currently carry a Euclidean guess in `justitie`'s
published access map where the real drive is well over an hour.

**Not settled: whether the speed table is right.** `implied_speed` divides administrativ's
shortest-*distance* by this build's shortest-*time*, and those are two different routes. The
fastest route may be the longer one, so the ratio understates how fast the model actually
drives — the true figure is at or above 54,5 km/h, against perhaps 40–50 for real rural
seat-to-seat driving in Romania.

That is consistent with the table being 10–20% optimistic, which is what `trunk` at 75 km/h
would predict. **It is not grounds to tune it.** Calibrating `EFFECTIVE_KMH` against a hybrid
proxy would fit the table to a number that is not ground truth, which is the failure the gate
exists to prevent. The correction waits for recorded drives.

## What L0 is

`simulators/administrativ` measures the road **distance** between the seats of adjacent UATs.
This measures the **time**, over the same OSM network, the same junction graph and the same
seat snapping — the only difference is that each segment is divided by an assumed speed for
its road class before the search.

It is not only for this simulator. `justitie` already maps what court consolidation costs in
travel, and carries an explicit caveat against its own figures: *kilometres are not hours;
forty in the mountains can cost more than eighty on the plain.* That caveat is a limitation of
the unit, and this is what retires it.

| file | what it holds |
|---|---|
| `scripts/speeds.py` | **Every assumed number in L0.** OSM road class → effective km/h. Deliberately alone in a file with no dependencies, so the whole assumption set reads in one screen. |
| `scripts/build_road_time.py` | Drives administrativ's graph with a time weight. Writes `data/road_time.parquet`. |
| `scripts/county_times.py` | Accumulates one-hop times into journeys, within one county. |
| `scripts/check_gate.py` | The gate. Modelled times against real recorded drives. |

## The gate, and why it is split

`speeds.py` is assumed and nothing in this simulator can make it true. `check_gate.py` is what
makes it *defensible*: a dozen drives in Vâlcea, recorded by hand from a public routing service
and committed with their source. Vâlcea because it has both the Olt valley and real mountain
roads, so the weakest assumption — that a road class implies a speed whatever the terrain — is
exercised rather than flattered.

The reference set is split in two because L0 has two errors pointing opposite ways:

- **`speeds.py` is probably optimistic.** Romanian DNs thread through the villages they
  connect; DJ and DC roads underperform their class. Too-fast segments give too-short journeys.
- **`county_times.py` is deliberately pessimistic.** It routes through every intermediate seat
  village rather than past it, so an accumulated journey is longer than the real drive.

Compare only whole journeys and those two **partially cancel** — the gate passes, both
components are wrong, and the cancellation holds only for the distances Vâlcea happens to
contain. So `adjacent` drives are checked against the raw one-hop edge, where the accumulation
cannot reach them, and bias is reported per kind:

| adjacent | journey | what it means |
|---|---|---|
| biased | biased | the speed table is wrong — fix `EFFECTIVE_KMH` |
| clean | biased | speeds are fine; the detour through intermediate seats is the cost |
| biased | clean | the two errors are cancelling — the dangerous case, now visible |

Three ways to fail: any single drive outside 35%, either kind showing systematic bias beyond
15%, or fewer than three adjacent drives — because a mean over one hop is scatter with the word
bias attached to it.

## Running it

```sh
# In simulators/administrativ, once — L0 reads its road graph.
# The OSM extract is roughly a gigabyte and the graph build is long.
uv run python -m pipeline.fetch --with-roads
uv run python -m pipeline.build_geometry
uv run python -m pipeline.build_seats
uv run python -m pipeline.build_adjacency
uv run python -m pipeline.build_road_distance

# Then here:
uv run python -m scripts.build_road_time   # writes data/road_time.parquet
uv run python -m scripts.check_gate        # the gate; non-zero exit on failure
```

`data/` is not committed. It is reproducible from the commands above.

## Before this layer can be trusted

`sources/reference-drive-times-vl.csv` ships with `REPLACE_ME` placeholders, and
`test_the_reference_file_is_filled_in` **fails until a human replaces them**. That failure is
deliberate. An unfilled gate that passed would read as verification while having checked
nothing, which is worse than having no gate at all.

Needed: at least six `adjacent` drives (the two UATs must genuinely share a border — check
`adjacency.parquet`) and at least six `journey` drives several hops apart, spread across valley,
plateau and mountain, each with the routing service and date it came from.

Expect the first run to fail on systematic bias. The speed table has not been calibrated
against anything yet, and `trunk` at 75 km/h in particular looks optimistic for a Romanian DN.
That first failure is the gate doing its job; adjust `EFFECTIVE_KMH` in the direction the bias
reports, re-run `build_road_time`, and record what changed and why. A speed table tuned to a
gate with no record of the tuning is worse than an untuned one.

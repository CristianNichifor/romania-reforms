# Administrativ — explaining the merge

**Date:** 2026-09-07
**Simulator:** `simulators/administrativ`
**Status:** approved, implementation in five PRs

## The problem

The map shows *what* the model decided. It does not show *why*, and it does not show it on a
phone.

A reader hovering a merged commune is told "absorbed by Topolog, 34% overlap". The distance
that actually decided it was measured along real roads, hop by hop, and none of that is on
screen — the roads layer can be ticked on, but it draws the whole national network rather
than the two roads the number came from. The reader is asked to trust an arithmetic they
cannot see.

Three further gaps: the set of towns that *could* have been centres is computed and thrown
away, so a reader cannot argue with the choice; there is no published map, only whatever the
default sliders happen to produce; and the sidebars are fixed-width on desktop and cover the
map on a phone.

## Scope

Five independent pieces of work, each its own branch and PR, in this order:

1. **PR1 — reading the map.** Resizable sidebars, mobile bottom sheets, touch-correct
   hovercard, per-UAT transparenta.eu links.
2. **PR2 — candidates and overrides.** The absorber-candidate list, and forcing a UAT to be
   an absorber.
3. **PR3 — the reference map.** A published scenario, and reader-saved versions.
4. **PR4 — the roads behind the number.** The accretion chain, drawn on the real road
   geometry.
5. **PR5 — what the new unit means.** Data from the sibling simulators, and the
   representation layer.

PR1 ships first deliberately: every other feature adds content to sidebars that already
truncate their text.

---

## PR1 — Reading the map

### Sidebar width

`.controls` (292 px) and `.detail` (320 px) are fixed. The truncation is a hard width, not an
overflow bug, so widening fixes it outright.

Each sidebar gains a 6 px drag handle on its inner edge. Width is clamped to 260–560 px,
persisted to `localStorage` under `administrativ:width:controls` / `:detail`, and reset by
double-clicking the handle. The handle is keyboard-operable (`role="separator"`,
arrow keys move it 16 px) — a drag-only control is unusable without a mouse.

`.hovercard`'s `max-width: calc(100vw - 360px)` is derived from the old fixed width and
becomes a function of the live sidebar widths.

### Mobile

Below 900 px both sidebars become bottom sheets: a drag handle, a ~44 px peek bar carrying
the panel title, and three snap positions (peek, half, full). The map keeps the whole
viewport until the reader pulls a sheet up. This replaces the current rule, which stacks both
panels over the map and leaves no map to read.

### The hovercard on touch

The hovercard has no dismiss control because a pointer leaving is its dismiss. On a
touchscreen there is no leave event, so it strands.

A close button is the wrong fix — it would make the hovercard a dialog, and there would then
be two dialogs saying overlapping things. Instead: on coarse pointers
(`matchMedia('(pointer: coarse)')`) the hovercard is suppressed entirely, and a tap selects
the commune and opens the detail sheet, which is a real panel with a real close control. One
interaction model per input type, same information in both.

### transparenta.eu links

**Verified 2026-09-07:** transparenta.eu entity pages are `https://www.transparenta.eu/entities/{uat_code}`,
where `uat_code` is the field the pipeline's existing `uats` GraphQL query already
requests — `MUNICIPIUL SIBIU` carries `uat_code` `4270740`, and `/entities/4270740` is Sibiu's
page on the site.

So no crosswalk and no new fetch: `uat_code` is plumbed through `fetch_attributes` →
`export.py` → `attributes.json`, and the detail panel links the unit's seat and every member
row. Links are rendered only where a `uat_code` is present; a missing code renders plain
text rather than a dead link.

---

## PR2 — Candidates and overrides

### The candidate list

`selectSeeds()` already distinguishes every state a candidate can be in, and discards all of
them once `tierOf` is written. It gains a second output, `candidacyOf: Uint8Array`, recording
per UAT:

| State | Meaning |
|---|---|
| `CAPITAL` | county capital — automatic, cannot be refused |
| `THRESHOLD` | population ≥ `x` |
| `PROMOTED` | promoted to fill a county short of `nMin` |
| `STOOD_DOWN` | was a centre, stood down inside a capital's core |
| `ELIGIBLE_UNUSED` | in the promotion pool; the county already had enough centres |
| `REFUSED_SEPARATION` | in the promotion pool; inside `rSep` of an existing centre |
| `FORCED` | forced by the reader |
| `NONE` | not a candidate under any rule |

Recording it changes no assignment, so the parity fixtures are unaffected.

Rendered in the left sidebar as a county-grouped list, each row naming its state and, for
`STOOD_DOWN`, the capital that displaced it. Rows fly the map to the UAT. This is the rules
chart: it shows the choice the model made *and the alternatives it rejected*, which is what
makes the choice disputable.

### Forcing an absorber

A new scenario field `forced: number[]`, encoded in the URL hash beside `pins`.

A forced UAT becomes a centre in its own tier. It waives the two soft rules — the population
threshold and the separation floor. It does not waive the hard ones: it never crosses a
county line, and it does not survive inside a county capital's ring. It then competes for
communes through the ordinary bidding with no advantage.

**This is not a pin.** Pins are applied after the model has run, which is what keeps the
parity fixtures meaningful. A forced seed changes the model's input, so it must exist in
`pipeline/reference_model.py` too, with parity fixtures covering it. Implementing it only in
TypeScript would leave the two implementations silently disagreeing — the one failure mode
this project's whole structure exists to prevent.

The Python port is the bulk of this PR, not the UI.

---

## PR3 — The reference map

### The published scenario

A `REFERENCE_SCENARIO` constant in code: params, forced absorbers, pins, a version string and
a date. A bare URL loads it and badges it `◉ Referință v1 · <date>`. Touching any control
flips the badge to `○ Versiunea ta (nesalvată)` and the URL becomes shareable exactly as it
is today.

The constant's values are supplied by the author: the scenario is tuned in the UI, and the
resulting URL is baked in. The mechanism ships before the values exist, defaulting to
`DEFAULT_PARAMS` until then.

### Reader versions

Named versions in `localStorage`: name, date, full scenario, resulting unit count. A version
exports to a small JSON file and imports back, so it survives a cleared browser and can be
mailed or attached to an argument.

PNG export at display resolution. MapLibre needs `preserveDrawingBuffer` to allow a canvas
read-back, and that carries a memory cost on every frame, so the map is re-created with the
flag set the first time export is pressed rather than running with it always on.

A print stylesheet: map, legend, and the parameter values as a table. A printed map without
its parameters cannot be cited, so the table is not optional.

---

## PR4 — The roads behind the number

### The chain

`grow()` computes `reach = base + neighbourRoadM[e]` and discards which held commune `held`
the winning bid came through. Recording it as `parentOf: Uint16Array` makes the chain
`uat → parent → … → centre` recoverable. Additive; no assignment changes.

**Only accretion produces a chain.** Communes placed by `absorbLeftovers`, `orphanTier`,
`consolidateToTarget`, `equalise`, `rebalance`, `absorbStranded` or a pin were not placed by
an accumulated road distance, and the panel must name the rule that placed them instead of
drawing a road that decided nothing.

### The geometry

`build_road_distance.py` runs Dijkstra per seat and keeps only the scalar distance.
Re-running it with `return_predecessors=True` reconstructs the actual polyline for each of the
9 125 traversable adjacency edges. Simplified, coordinate-rounded, sharded by county into 42
files, published as a release asset beside `roads.geojson` and listed in `data-assets.json`.

Payload size is **estimated** at 200–400 KB gzipped per shard, extrapolated from the existing
road payloads. This is a projection, not a measurement: one county is built and measured
first, and the result reported, before the other 41 are committed to.

The re-run needs `data/raw/romania-latest.osm.pbf` (327 MB, not committed) and its runtime is
unknown.

### The interaction

Hovering a merged unit draws its chain. Following the existing HEAD-probe pattern for
`roads.geojson`:

- Shard already loaded → the true polyline, immediately.
- Not loaded → the chain draws at once as a schematic line labelled with the real per-hop
  road distances, badged *"drumurile se descarcă…"*, and the geometry swaps to the true
  polyline when the shard lands.
- Asset absent from the build → says so, and stays schematic.

The schematic line is drawn dashed and captioned, because a solid line labelled "12,1 km"
that is not 12.1 km long is the exact misreading this feature exists to prevent.

---

## PR5 — What the new unit means

Per-UAT data from the sibling simulators, in the detail panel.

| Source | Artefact | Size | What it adds |
|---|---|---|---|
| `transport` | `road-time.bin` | 111 KB | Drive time along the same chain, in minutes |
| `justitie` | `court-distance.bin` | 267 KB | Which court serves the unit; whether a merge splits members across two |
| `transport` | `access.json` | 1.1 MB | Public-transport time to the **county** seat |
| `impozit-teren` | fond funciar | new build step | Taxable land base beside the administration cost |

`road-time.bin` is aligned edge-for-edge with this project's own `adjacency.parquet`, so the
existing chain is reported in minutes at almost no cost. It makes the 50 km distance cap
legible to a reader who does not think in kilometres.

`access.json` is labelled for what it measures — time to the *county* seat, not to the new
centre. It is suggestive, not exact, and lazy-loaded at 1.1 MB.

The land-tax base needs a new aggregation over per-county fond funciar files. It is the
heaviest item here and splits into its own PR if PR5 grows too wide.

### Representation

Mayors, vice-mayors and councillors, before and after.

Romanian council size is statutory — set by population bracket in the Codul administrativ,
not scraped. **The brackets are not quoted here because they have not yet been read against
the statute.** No figure ships until it names its article, which is this repo's standing rule.

Incumbents' *names* are out of scope: they would need scraping, they change, and they add
nothing to the analysis.

The Danish comparator needs a small new source — council sizes across the 98 kommuner — which
does not yet exist in the repo.

Useful adjacency: `salarizare` already carries mayor and vice-mayor pay by population bracket
in both Romanian regimes. The political layer's *cost* before and after is therefore
computable from the regime already modelled next door, rather than estimated.

---

## Testing

- **PR1** — width clamping and persistence; the coarse-pointer branch; a `uat_code`-absent UAT
  renders text, not a dead link.
- **PR2** — parity fixtures covering forced seeds in both implementations; `candidacyOf`
  asserted not to change any assignment.
- **PR3** — round-trip a version through export and import; the reference badge flips on the
  first control change and not before.
- **PR4** — the chain terminates at the centre for every accretion-placed commune; every
  non-accretion reason names its rule; per-hop distances sum to the model's own total.
- **PR5** — every borrowed artefact's index alignment asserted against `attributes.json`,
  because a silent off-by-one here reads as plausible data rather than as an error.

## Risks

1. **Edge-path payload size is a projection.** Measured on one county before the rest.
2. **PR2's Python port is the real cost**, not its UI.
3. ~~transparenta URL scheme unverified~~ — resolved 2026-09-07, `uat_code` is the entity id.
4. **Council brackets and Danish council sizes both need sourcing** before any number ships.
5. **The `build_road_distance.py` re-run needs the 327 MB OSM extract** and has unknown
   runtime.

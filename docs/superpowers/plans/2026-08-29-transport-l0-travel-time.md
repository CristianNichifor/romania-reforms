# Transport L0 — Road Travel-Time Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce seat-to-seat road **travel times** for every adjacent UAT pair in Romania, verified against real drive times in one hand-checked county, so that every layer above it — and `justitie`'s existing access map — can speak in minutes instead of kilometres.

**Architecture:** `simulators/administrativ` already builds the national road graph from OSM, snaps all 3 186 UAT seats to it, and runs a chunked Dijkstra between adjacent seat pairs to produce `road_distance.parquet`. L0 does **not** rebuild any of that. It adds one thing the graph lacks — a speed per road class — and reuses the identical machinery with a time weight instead of a length weight. One small backward-compatible change upstream in `build_graph`, then a transport-owned script that drives it.

**Tech Stack:** Python 3.12, `uv`, geopandas / pyogrio (OSM PBF reading), scipy.sparse.csgraph (Dijkstra), pandas + pyarrow (Parquet), pytest.

---

## Context an engineer needs before starting

**Read these first. They are the prior art this plan extends, not background reading.**

- `simulators/administrativ/pipeline/build_road_distance.py` — the whole pattern. `load_roads()`, `build_graph()`, `snap_seats()`, and the chunked Dijkstra loop in `main()`. L0 reuses all four.
- `simulators/justitie/scripts/build_acces.py:44` — how one simulator imports another's pipeline (`sys.path.insert` then a function-local import). Copy this pattern exactly; do not invent a new one.
- `docs/superpowers/specs/2026-08-29-transport-design.md` §14 — the verification gates. Gate 1 is what Task 6 builds.

**Two facts that will otherwise waste your afternoon:**

1. **The data is gitignored and not in the repository.** `simulators/administrativ/data/` is reproducible but not committed, and the OSM extract (`data/raw/romania-latest.osm.pbf`) is a large download. Every test in this plan must pass **without** those artefacts. Tests that genuinely need them are marked `skipif`, exactly as `simulators/administrativ/tests/test_reference_model.py:37` does.
2. **Commit messages in this repository are prose, not Conventional Commits.** Look at `git log`. They read `Model the court count as coverage, not population`, not `feat: add court count`. The commit messages in this plan follow the repository. Ignore any template that says otherwise.

**Working directory:** all commands assume the repository root, `romania-reforms-transport/`, unless a step says otherwise.

---

## File Structure

| File | Responsibility |
|---|---|
| `simulators/transport/pyproject.toml` | Transport's own dependency set and pytest config. Mirrors administrativ's; transport needs the same geo stack. |
| `simulators/transport/scripts/__init__.py` | Makes `scripts` importable so the pure units can be unit-tested. Empty. |
| `simulators/transport/scripts/speeds.py` | **The one new idea in L0.** OSM `highway` class → assumed effective speed. Pure, no I/O, no geo dependency. Every `assumed` number in L0 lives here and nowhere else. |
| `simulators/transport/scripts/build_road_time.py` | Drives administrativ's graph with a time weight. Writes `road_time.parquet` and a data-quality report. |
| `simulators/transport/scripts/county_times.py` | Accumulates edge times across the UAT adjacency graph into seat-to-seat minutes within a county. The time-domain counterpart of `reference_model._county_road_distances`. |
| `simulators/transport/scripts/check_gate.py` | Gate 1. Compares modelled minutes against human-recorded real drive times and fails loudly. |
| `simulators/transport/sources/reference-drive-times-vl.csv` | The hand-checked reference times. Committed, human-authored, cited per row. |
| `simulators/transport/tests/` | Transport's pipeline tests. Pure units run always; artefact-dependent ones skip. |
| `simulators/administrativ/pipeline/build_road_distance.py` | **Modified**, one function: `build_graph()` gains an optional speed argument. Default behaviour byte-identical. |

Why `speeds.py` is its own file with no dependencies: it holds the weakest numbers in L0. Keeping them in one dependency-free module means a critic can read the entire assumption set in one screen, and Task 6's gate can calibrate them without touching anything else.

---

### Task 1: Transport package skeleton

**Files:**
- Create: `simulators/transport/pyproject.toml`
- Create: `simulators/transport/scripts/__init__.py`
- Create: `simulators/transport/tests/test_speeds.py`

- [ ] **Step 1: Create the package directories and the empty package marker**

```bash
mkdir -p simulators/transport/scripts simulators/transport/tests simulators/transport/sources simulators/transport/data
touch simulators/transport/scripts/__init__.py
```

- [ ] **Step 2: Write `simulators/transport/pyproject.toml`**

```toml
[project]
name = "transport-simulator-pipeline"
version = "0.1.0"
description = "Travel-time substrate and network model for the Romanian public transport simulator"
requires-python = ">=3.12"
license = { text = "Apache-2.0" }

# The same geo stack as administrativ, because L0 drives administrativ's road graph rather
# than building its own. scipy is declared explicitly here: build_road_distance.py imports it
# but administrativ only receives it transitively through libpysal, which is a dependency
# nobody chose on purpose.
dependencies = [
    "geopandas>=1.0",
    "shapely>=2.0",
    "pyproj>=3.6",
    "pandas>=2.2",
    "numpy>=1.26",
    "pyogrio>=0.9",
    "pyarrow>=25.0.1",
    "scipy>=1.14",
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.6"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
# Determinism is a hard requirement: a test that depends on dict ordering, set iteration
# order or hash seeding is a test that hides a real bug.
addopts = "-p no:randomly --strict-markers"

[tool.uv]
package = false
```

- [ ] **Step 3: Write one trivial test so the harness is proved before anything depends on it**

Create `simulators/transport/tests/test_speeds.py`:

```python
"""Tests for the assumed speed table.

These are the weakest numbers in L0 — every one of them is `assumed` — so the tests here
check the table's shape and internal consistency rather than its truth. Its truth is what
Task 6's one-county gate is for.
"""

from __future__ import annotations


def test_the_test_harness_runs():
    assert True
```

- [ ] **Step 4: Run it and confirm the harness works**

```bash
cd simulators/transport && uv sync --all-groups && uv run pytest -q
```

Expected: `1 passed`. If `uv sync` fails on geopandas wheels, that is an environment problem to solve now, not after five more tasks depend on it.

- [ ] **Step 5: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/pyproject.toml simulators/transport/scripts/__init__.py simulators/transport/tests/test_speeds.py
git commit -m "Start the transport simulator with its own dependency set

It drives administrativ's road graph rather than building one, so it needs
the same geo stack. scipy is declared rather than inherited: administrativ
gets it transitively through libpysal, which is not a dependency anyone
chose."
```

---

### Task 2: The speed table

**Files:**
- Create: `simulators/transport/scripts/speeds.py`
- Modify: `simulators/transport/tests/test_speeds.py`

- [ ] **Step 1: Write the failing tests**

Replace the whole contents of `simulators/transport/tests/test_speeds.py`:

```python
"""Tests for the assumed speed table.

These are the weakest numbers in L0 — every one of them is `assumed` — so the tests here
check the table's shape and internal consistency rather than its truth. Its truth is what
Task 6's one-county gate is for.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.speeds import (
    EFFECTIVE_KMH,
    FALLBACK_KMH,
    ROUTING_CLASSES,
    speeds_for_classes,
)


def test_every_routable_class_has_a_speed():
    """A class the router will traverse but the table does not price gets the fallback
    silently, which is how a whole road category ends up quietly wrong."""
    missing = [c for c in ROUTING_CLASSES if c not in EFFECTIVE_KMH]
    assert missing == [], missing


def test_speeds_are_ordered_by_road_class():
    """A motorway that models slower than a residential street means the table was edited
    without being read."""
    assert EFFECTIVE_KMH["motorway"] > EFFECTIVE_KMH["trunk"]
    assert EFFECTIVE_KMH["trunk"] >= EFFECTIVE_KMH["primary"]
    assert EFFECTIVE_KMH["primary"] > EFFECTIVE_KMH["secondary"]
    assert EFFECTIVE_KMH["secondary"] > EFFECTIVE_KMH["tertiary"]
    assert EFFECTIVE_KMH["tertiary"] > EFFECTIVE_KMH["residential"]


def test_no_speed_exceeds_the_legal_limit():
    """OUG 195/2002 caps cars at 130 km/h on motorways and 90 on other roads outside
    localities. An effective speed above the legal limit is not a modelling choice."""
    assert EFFECTIVE_KMH["motorway"] <= 130
    for name, kmh in EFFECTIVE_KMH.items():
        if name.startswith("motorway"):
            continue
        assert kmh <= 90, (name, kmh)


def test_a_link_is_never_faster_than_the_road_it_serves():
    for base in ("motorway", "trunk", "primary", "secondary", "tertiary"):
        assert EFFECTIVE_KMH[f"{base}_link"] <= EFFECTIVE_KMH[base], base


def test_it_maps_an_array_of_classes_to_speeds():
    got = speeds_for_classes(np.array(["motorway", "residential", "tertiary"]))
    assert got.tolist() == [
        EFFECTIVE_KMH["motorway"],
        EFFECTIVE_KMH["residential"],
        EFFECTIVE_KMH["tertiary"],
    ]


def test_an_unknown_class_falls_back_rather_than_crashing():
    """OSM adds highway values without asking. An unknown class must route slowly, not
    raise — a crash here would fail the whole national build on one odd way."""
    got = speeds_for_classes(np.array(["motorway", "some_new_osm_value"]))
    assert got[1] == FALLBACK_KMH


def test_the_fallback_is_pessimistic():
    """If the fallback were fast, an unrecognised class would silently become a shortcut."""
    assert FALLBACK_KMH <= min(EFFECTIVE_KMH.values())


def test_missing_classes_fall_back_too():
    got = speeds_for_classes(np.array([None, "motorway"], dtype=object))
    assert got[0] == FALLBACK_KMH


def test_it_returns_floats_not_ints():
    """The caller divides by these. Integer division would silently truncate travel time."""
    assert speeds_for_classes(np.array(["motorway"])).dtype == np.float64


def test_it_handles_an_empty_array():
    assert speeds_for_classes(np.array([], dtype=object)).shape == (0,)


def test_every_speed_is_positive():
    """A zero would divide by zero and produce an infinite travel time on a real road."""
    assert all(kmh > 0 for kmh in EFFECTIVE_KMH.values())
    assert FALLBACK_KMH > 0


def test_the_provenance_note_names_the_gate():
    """The table is assumed, and the only thing that makes it defensible is the county
    check. If that sentence goes missing, so does the reason to trust any of this."""
    from scripts.speeds import SPEED_PROVENANCE

    assert SPEED_PROVENANCE["confidence"] == "assumed"
    assert "OUG 195/2002" in SPEED_PROVENANCE["locator"]


@pytest.mark.parametrize("kmh", EFFECTIVE_KMH.values())
def test_no_speed_is_absurdly_low(kmh):
    """Below 15 km/h a road is not a road; that would be a typo, not a slow lane."""
    assert kmh >= 15
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd simulators/transport && uv run pytest -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'scripts.speeds'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/speeds.py`:

```python
"""Assumed effective speed by OSM road class.

This is the weakest thing in L0 and it is deliberately alone in one file, so that the whole
assumption set can be read in one screen and disputed as a unit.

These are **effective** speeds, not legal limits. The legal limits (OUG 195/2002) are 130
km/h on motorways, 100 on expressways and European national roads, 90 on other roads outside
localities and 50 inside them. Nobody averages those over a real journey: junctions, villages
strung along national roads, agricultural traffic and the state of the surface all take their
cut, and a Romanian DN through a string of communes does not deliver 90 km/h over any distance
that matters.

So each figure below is the legal limit discounted toward what a journey actually averages.
That discount is a judgement, and it is the single assumption most likely to be wrong.

**What makes it defensible is not this file.** It is the one-county gate in
`scripts/check_gate.py`, which compares these speeds' output against real recorded drive
times and fails the build when they disagree. Changing a number here without re-running that
gate is how the whole substrate becomes plausible and quietly wrong.

The classes are administrativ's `ROUTING_CLASSES`, repeated here rather than imported: this
module has no dependency on the geo stack and is the poorer for gaining one, and the test
`test_every_routable_class_has_a_speed` fails loudly if the two lists ever drift apart.
"""

from __future__ import annotations

from typing import Final

import numpy as np

# Kept in step with administrativ's pipeline.build_road_distance.ROUTING_CLASSES.
ROUTING_CLASSES: Final[tuple[str, ...]] = (
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "road",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
)

EFFECTIVE_KMH: Final[dict[str, float]] = {
    # Free-flowing and grade-separated; the one class that comes close to its limit.
    "motorway": 110.0,
    # DN-grade. The legal 90 is rarely achieved: these run through the villages they connect.
    "trunk": 75.0,
    "primary": 65.0,
    # DJ-grade county roads, the backbone of everything this simulator models.
    "secondary": 55.0,
    # DC-grade communal roads, frequently unsurfaced in part.
    "tertiary": 45.0,
    # Inside a locality, where the limit is 50 and the achieved speed is lower.
    "unclassified": 35.0,
    "residential": 30.0,
    "living_street": 20.0,
    # OSM's "we know it is a road and no more than that".
    "road": 30.0,
    # Slip roads: short, and taken at the speed of the slower end.
    "motorway_link": 60.0,
    "trunk_link": 50.0,
    "primary_link": 45.0,
    "secondary_link": 40.0,
    "tertiary_link": 35.0,
}

# An OSM value the table does not know. Pessimistic on purpose: an unrecognised class must
# never become a shortcut, because a shortcut is invisible in the output while a slow road
# shows up as an implausible time the gate can catch.
FALLBACK_KMH: Final[float] = 20.0

SPEED_PROVENANCE: Final[dict[str, str]] = {
    "source": "oug-195-2002-plus-judecata",
    "locator": (
        "Limitele legale din OUG 195/2002 art. 49, reduse la viteze efective de parcurs; "
        "calibrate prin verificarea pe județul de control"
    ),
    "confidence": "assumed",
    "note": (
        "Vitezele sunt estimate pe clasa drumului din OSM, nu măsurate. Nu există date "
        "publice de viteză reală pe rețeaua rutieră din România la nivel de segment."
    ),
}


def speeds_for_classes(classes: np.ndarray) -> np.ndarray:
    """Map an array of OSM `highway` values to effective speeds in km/h.

    Unknown or missing values take FALLBACK_KMH rather than raising: OSM gains new highway
    values without notice, and one unrecognised way must not fail a national build.
    """
    out = np.full(len(classes), FALLBACK_KMH, dtype=np.float64)
    for name, kmh in EFFECTIVE_KMH.items():
        out[classes == name] = kmh
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd simulators/transport && uv run pytest -q
```

Expected: `27 passed` (12 named tests plus 14 parametrised cases, minus the one deleted placeholder — the exact count is not the point; zero failures is).

- [ ] **Step 5: Lint**

```bash
cd simulators/transport && uv run ruff check scripts tests && uv run ruff format --check scripts tests
```

Expected: `All checks passed!`. If `ruff format --check` objects, run `uv run ruff format scripts tests` and re-run the tests.

- [ ] **Step 6: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/speeds.py simulators/transport/tests/test_speeds.py
git commit -m "Price each road class, and keep every assumption in one file

Effective speeds, not legal limits: a DN through a string of communes does
not deliver its 90 over any distance that matters, so each figure is the
limit discounted toward what a journey averages. That discount is the
weakest judgement in L0, which is why it lives alone in a file with no
dependencies and can be read as a unit.

An unknown OSM class falls back slowly rather than raising. A fast fallback
would be an invisible shortcut; a slow one shows up as an implausible time
the county gate can catch."
```

---

### Task 3: Let administrativ's graph carry a time weight

This is the only change outside `simulators/transport/`. It is additive and the default path stays byte-identical, so administrativ's parity fixtures are unaffected.

**Files:**
- Modify: `simulators/administrativ/pipeline/build_road_distance.py` (the `build_graph` function, currently at `:100`)
- Create: `simulators/administrativ/tests/test_build_road_distance.py`

- [ ] **Step 1: Write the failing tests**

Create `simulators/administrativ/tests/test_build_road_distance.py`:

```python
"""Tests for the road graph's weighting.

The graph is built from ten million vertices by a hand-rolled hashing trick, so it is not
something to change casually. These tests pin the two things a caller depends on: that the
default weight is still length, and that a supplied speed produces seconds.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

from pipeline.build_geometry import Report
from pipeline.build_road_distance import build_graph
from pipeline.constants import CRS_STEREO70


def two_roads() -> gpd.GeoDataFrame:
    """Two straight 1 000 m segments meeting end to end, in projected metres."""
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "residential"]},
        geometry=[
            LineString([(0.0, 0.0), (1000.0, 0.0)]),
            LineString([(1000.0, 0.0), (2000.0, 0.0)]),
        ],
        crs=CRS_STEREO70,
    )


def test_the_default_weight_is_still_length_in_metres():
    """Administrativ's whole model reads this graph. If the default changed, every region
    boundary in the country would move and the parity fixtures would be the only warning."""
    graph, _, _, _ = build_graph(two_roads(), Report())
    assert graph.sum() == pytest.approx(2 * 2000.0)  # two segments, stored both directions


def test_a_speed_turns_the_weight_into_seconds():
    """1 000 m at 100 km/h is 36 s; 1 000 m at 50 km/h is 72 s."""
    speed = np.array([100.0, 50.0])
    graph, _, _, _ = build_graph(two_roads(), Report(), speed_kmh=speed)
    assert graph.sum() == pytest.approx(2 * (36.0 + 72.0))


def test_the_speed_applies_per_feature_not_globally():
    """The two segments must not share one speed — that would flatten the whole table."""
    speed = np.array([100.0, 50.0])
    graph, _, _, _ = build_graph(two_roads(), Report(), speed_kmh=speed)
    weights = sorted(graph.tocoo().data.tolist())
    assert weights == pytest.approx([36.0, 36.0, 72.0, 72.0])


def test_a_multi_vertex_line_splits_its_time_across_segments():
    """A road digitised as many short segments must total the same time as one long one."""
    roads = gpd.GeoDataFrame(
        {"highway": ["motorway"]},
        geometry=[LineString([(0.0, 0.0), (500.0, 0.0), (1000.0, 0.0)])],
        crs=CRS_STEREO70,
    )
    graph, _, _, _ = build_graph(roads, Report(), speed_kmh=np.array([100.0]))
    assert graph.sum() == pytest.approx(2 * 36.0)


def test_a_wrong_length_speed_array_is_rejected():
    """Passing one speed for the wrong number of features would silently misprice roads
    through numpy broadcasting rather than failing."""
    with pytest.raises(ValueError, match="one speed per road feature"):
        build_graph(two_roads(), Report(), speed_kmh=np.array([100.0]))


def test_zero_length_segments_do_not_become_infinite_time():
    """Snapping collapses near-duplicate vertices; a self-loop must be dropped, not divided."""
    roads = gpd.GeoDataFrame(
        {"highway": ["residential"]},
        geometry=[LineString([(0.0, 0.0), (0.1, 0.0), (1000.0, 0.0)])],
        crs=CRS_STEREO70,
    )
    graph, _, _, _ = build_graph(roads, Report(), speed_kmh=np.array([50.0]))
    assert np.isfinite(graph.tocoo().data).all()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd simulators/administrativ && uv run pytest tests/test_build_road_distance.py -q
```

Expected: failures — `TypeError: build_graph() got an unexpected keyword argument 'speed_kmh'` on every test that passes one, and a pass on `test_the_default_weight_is_still_length_in_metres`.

- [ ] **Step 3: Change `build_graph`**

In `simulators/administrativ/pipeline/build_road_distance.py`, replace the whole `build_graph` function (from `def build_graph(` down to and including `return graph, node_of_vertex, coords, n_nodes`) with:

```python
def build_graph(
    roads: gpd.GeoDataFrame,
    report: Report,
    speed_kmh: np.ndarray | None = None,
):
    """Turn road linestrings into a weighted node graph.

    Every vertex becomes a node and every consecutive pair an undirected edge weighted by
    its length. Vertices are snapped to a 1 m grid first so that ways meeting at a junction
    share a node rather than passing through each other.

    With `speed_kmh` — one effective speed per road feature, in the row order of `roads` —
    each edge is weighted by **travel time in seconds** instead of length in metres. The
    graph is otherwise identical, so a caller wanting minutes and a caller wanting kilometres
    share this construction rather than each maintaining a copy of the vertex hashing below.
    """
    if speed_kmh is not None and len(speed_kmh) != len(roads):
        raise ValueError(
            f"speed_kmh must hold one speed per road feature: "
            f"got {len(speed_kmh)} for {len(roads)} features"
        )

    coords, index = get_coordinates(roads.geometry, return_index=True)
    snapped = np.round(coords / SNAP_GRID_M).astype(np.int64)

    # Identify junctions by hashing the snapped (x, y) into one integer and uniquing that.
    #
    # `np.unique(..., axis=0)` on a ten-million-row array is what killed the first attempt:
    # the row-wise path builds a structured view and lexsorts it, and the peak allocation
    # is several times the input. Packing into a single int64 first turns the same job into
    # an ordinary 1-D sort.
    x0, y0 = snapped[:, 0].min(), snapped[:, 1].min()
    span_y = int(snapped[:, 1].max() - y0) + 1
    key = (snapped[:, 0] - x0) * span_y + (snapped[:, 1] - y0)
    _, node_of_vertex = np.unique(key, return_inverse=True)
    del snapped, key
    n_nodes = int(node_of_vertex.max()) + 1

    # Consecutive vertices belong to the same edge only when they belong to the same line.
    same_line = index[:-1] == index[1:]
    a = node_of_vertex[:-1][same_line]
    b = node_of_vertex[1:][same_line]
    seg = coords[1:][same_line] - coords[:-1][same_line]
    length = np.hypot(seg[:, 0], seg[:, 1])

    if speed_kmh is None:
        weight = length
    else:
        # Which feature each segment came from, so a segment is priced by its own road class
        # rather than by an average over the file.
        segment_speed = speed_kmh[index[:-1][same_line]]
        weight = length / (segment_speed / 3.6)

    # Drop self-loops created by snapping.
    keep = a != b
    a, b, weight = a[keep], b[keep], weight[keep]

    # Built symmetric directly: duplicate entries are summed by coo_matrix, which would
    # double the weight of any segment appearing twice, so `directed=False` is used at
    # query time and each segment is stored once in each direction.
    graph = coo_matrix(
        (np.concatenate([weight, weight]), (np.concatenate([a, b]), np.concatenate([b, a]))),
        shape=(n_nodes, n_nodes),
    ).tocsr()

    report.add(
        Check(
            "road_graph",
            n_nodes > 100_000,
            f"{len(roads):,} road features -> {n_nodes:,} junctions, {len(a):,} segments",
            fatal=n_nodes <= 100_000,
        )
    )
    return graph, node_of_vertex, coords, n_nodes
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
cd simulators/administrativ && uv run pytest tests/test_build_road_distance.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Run administrativ's whole suite to prove nothing moved**

```bash
cd simulators/administrativ && uv run ruff check pipeline tests && uv run ruff format --check pipeline tests && PYTHONHASHSEED=0 uv run pytest -q
```

Expected: all pass. Tests needing built artefacts skip, as they already did. **If any previously-passing test now fails, stop** — the default path was supposed to be byte-identical and is not.

- [ ] **Step 6: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add simulators/administrativ/pipeline/build_road_distance.py simulators/administrativ/tests/test_build_road_distance.py
git commit -m "Let the road graph be weighted by time as well as distance

The graph is built from ten million vertices by a hashing trick with a
documented history of blowing up memory. A second caller wanting minutes
instead of metres should not carry a copy of that; it should pass a speed.

Additive, and the default is unchanged — administrativ's every region
boundary reads this graph, so the tests pin length-in-metres as the
no-argument behaviour rather than trusting the parity fixtures to notice."
```

---

### Task 4: Seat-to-seat travel time for every adjacent pair

**Files:**
- Create: `simulators/transport/scripts/build_road_time.py`
- Create: `simulators/transport/tests/test_build_road_time.py`

- [ ] **Step 1: Write the failing tests**

Create `simulators/transport/tests/test_build_road_time.py`:

```python
"""Tests for the seat-to-seat travel-time build.

The expensive part of this script is administrativ's, already tested over there. What is
tested here is the part L0 owns: that the output is shaped right, that unreachable pairs are
reported rather than dropped, and that the artefact is deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
ADMINISTRATIV = ROOT / "simulators/administrativ"
sys.path.insert(0, str(ADMINISTRATIV))

from scripts.build_road_time import (  # noqa: E402
    SEARCH_LIMIT_S,
    plausibility,
    time_table,
)


def test_it_pairs_every_edge_with_a_time():
    pairs = [("1", "2"), ("2", "3")]
    seconds = np.array([600.0, 1200.0])
    table = time_table(pairs, seconds)
    assert list(table["a_siruta"]) == ["1", "2"]
    assert list(table["road_s"]) == [600.0, 1200.0]


def test_it_is_sorted_so_the_artefact_is_byte_reproducible():
    """Same inputs must give the same file. Parquet is byte-reproducible; dict ordering is
    not, so the sort is what makes the determinism check in CI meaningful."""
    pairs = [("9", "1"), ("2", "3")]
    table = time_table(pairs, np.array([10.0, 20.0]))
    assert list(table["a_siruta"]) == ["2", "9"]


def test_it_carries_minutes_as_well_as_seconds():
    """The whole point of L0 is that a reader thinks in minutes. Rounding once, here, stops
    four consumers rounding differently."""
    table = time_table([("1", "2")], np.array([630.0]))
    assert table["road_min"].iloc[0] == pytest.approx(10.5)


def test_an_unreachable_pair_survives_as_infinity_rather_than_vanishing():
    """A dropped row is a commune with no journey that nobody counted. It must reach the
    report as infinity and be counted there, not disappear between the two."""
    table = time_table([("1", "2")], np.array([np.inf]))
    assert len(table) == 1
    assert np.isinf(table["road_s"].iloc[0])


def test_plausibility_flags_a_time_that_beats_the_motorway():
    """No pair of adjacent commune seats is reachable at 130 km/h door to door. If one is,
    the speed table or the snapping is wrong."""
    fast = plausibility(distance_m=np.array([50_000.0]), seconds=np.array([600.0]))
    assert fast["implausible"] == 1


def test_plausibility_accepts_an_ordinary_pair():
    ok = plausibility(distance_m=np.array([20_000.0]), seconds=np.array([1_500.0]))
    assert ok["implausible"] == 0
    assert ok["median_kmh"] == pytest.approx(48.0)


def test_plausibility_ignores_unreachable_pairs():
    """An infinite time has no implied speed; including it would make the median useless."""
    mixed = plausibility(
        distance_m=np.array([20_000.0, 30_000.0]),
        seconds=np.array([1_500.0, np.inf]),
    )
    assert mixed["implausible"] == 0
    assert mixed["median_kmh"] == pytest.approx(48.0)


def test_the_search_limit_covers_the_distance_limit():
    """Administrativ bounds its search at 60 km. At the slowest class in the table that is
    well over an hour, so a limit shorter than that would silently drop real neighbours."""
    assert SEARCH_LIMIT_S >= 60_000 / (20.0 / 3.6)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_build_road_time.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.build_road_time'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/build_road_time.py`:

```python
"""Road travel time between the seats of every adjacent pair of UATs.

Administrativ measures the same pairs in metres. This measures them in seconds, over the
same OSM network, the same junction graph and the same seat snapping — the only difference
is that each segment is divided by an assumed speed for its road class before the search.

Why the repository needs both. `justitie` already maps what court consolidation costs in
travel and carries an explicit caveat against its own figures: *kilometres are not hours;
forty in the mountains can cost more than eighty on the plain.* That caveat is a limitation
of the unit, not of the graph, and this is the file that retires it.

Output:
    data/road_time.parquet          a_siruta, b_siruta, road_s, road_min
    data/reports/road_time.md

Usage:
    uv run python -m scripts.build_road_time
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"

# The road graph belongs to the administrative simulator. This is the third consumer of it —
# after administrativ itself and justitie's access map — which is the point at which the
# design document says the substrate should move to packages/. It has not yet; see
# docs/superpowers/specs/2026-08-29-transport-design.md §3.
sys.path.insert(0, str(ADMINISTRATIV))

from scripts.speeds import speeds_for_classes  # noqa: E402

OUT_DIR = ROOT / "data"

# Administrativ bounds its search at 60 km because adjacent seats are close and an unbounded
# national search would explore the whole country per source. The same bound in seconds, at
# the slowest speed in the table, so nothing reachable within 60 km is lost to the limit.
SEARCH_LIMIT_S = 60_000 / (20.0 / 3.6)

# Sources per Dijkstra call: each allocates one float64 row per source over every node.
SOURCE_CHUNK = 4

# No pair of adjacent commune seats is reachable door to door at motorway speed. A pair that
# appears to be means the speed table is wrong or a seat snapped to the wrong junction.
IMPLAUSIBLE_KMH = 110.0


def time_table(pairs: list[tuple[str, str]], seconds: np.ndarray) -> pd.DataFrame:
    """Assemble the artefact, sorted so that identical inputs give an identical file.

    Unreachable pairs are kept as infinity rather than dropped: a missing row is a journey
    nobody counted, and an uncounted journey flatters every figure built on top of it.
    """
    return (
        pd.DataFrame(
            {
                "a_siruta": [a for a, _ in pairs],
                "b_siruta": [b for _, b in pairs],
                "road_s": seconds,
                "road_min": np.round(seconds / 60.0, 2),
            }
        )
        .sort_values(["a_siruta", "b_siruta"], ignore_index=True)
    )


def plausibility(distance_m: np.ndarray, seconds: np.ndarray) -> dict:
    """Implied door-to-door speed, and how many pairs imply an impossible one."""
    usable = np.isfinite(seconds) & np.isfinite(distance_m) & (seconds > 0)
    kmh = (distance_m[usable] / 1000.0) / (seconds[usable] / 3600.0)
    return {
        "implausible": int((kmh > IMPLAUSIBLE_KMH).sum()),
        "median_kmh": float(np.median(kmh)) if kmh.size else 0.0,
        "pairs": int(usable.sum()),
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd
    from scipy.sparse.csgraph import dijkstra

    from pipeline.build_geometry import Check, Report, write_report
    from pipeline.build_road_distance import build_graph, load_roads, snap_seats
    from pipeline.paths import PROCESSED_DIR

    report = Report()

    adjacency_path = PROCESSED_DIR / "adjacency.parquet"
    seats_path = PROCESSED_DIR / "uat_seats.gpkg"
    distance_path = PROCESSED_DIR / "road_distance.parquet"
    for path, cmd in (
        (adjacency_path, "build_adjacency"),
        (seats_path, "build_seats"),
        (distance_path, "build_road_distance"),
    ):
        if not path.exists():
            raise SystemExit(
                f"Missing {path}. Run, in simulators/administrativ: "
                f"uv run python -m pipeline.{cmd}"
            )

    print("Loading roads...")
    roads = load_roads()

    print("Pricing each road class...")
    speed = speeds_for_classes(roads["highway"].to_numpy())

    print("Building the timed road graph...")
    graph, node_of_vertex, coords, _ = build_graph(roads, report, speed_kmh=speed)

    seats = gpd.read_file(seats_path, layer="seat").sort_values("siruta", ignore_index=True)
    row_of = {s: i for i, s in enumerate(seats["siruta"])}
    seat_nodes, _ = snap_seats(coords, node_of_vertex, seats, report)

    adjacency = pd.read_parquet(adjacency_path)
    pairs = list(zip(adjacency["a_siruta"], adjacency["b_siruta"], strict=True))

    wanted: dict[int, list[tuple[int, int]]] = {}
    for edge_index, (a, b) in enumerate(pairs):
        wanted.setdefault(row_of[a], []).append((row_of[b], edge_index))

    print(f"Routing between {len(pairs):,} adjacent seat pairs...")
    road_s = np.full(len(pairs), np.inf)
    sources = sorted(wanted)
    for start in range(0, len(sources), SOURCE_CHUNK):
        chunk = sources[start : start + SOURCE_CHUNK]
        times = dijkstra(graph, directed=False, indices=seat_nodes[chunk], limit=SEARCH_LIMIT_S)
        for row, source_row in enumerate(chunk):
            for target_row, edge_index in wanted[source_row]:
                road_s[edge_index] = times[row, seat_nodes[target_row]]
        done = min(start + SOURCE_CHUNK, len(sources))
        print(f"  {done}/{len(sources)} seats", end="\r", flush=True)
    print()

    unreachable = int(np.isinf(road_s).sum())
    report.add(
        Check(
            "routed_pairs",
            unreachable < len(pairs) * 0.05,
            f"{len(pairs) - unreachable:,} of {len(pairs):,} adjacent pairs routed; "
            f"{unreachable} unreachable by road",
            fatal=unreachable >= len(pairs) * 0.05,
        )
    )

    finite = road_s[np.isfinite(road_s)]
    report.add(
        Check(
            "travel_time_distribution",
            True,
            f"seat-to-seat travel time: median {np.median(finite) / 60:,.1f} min, "
            f"p90 {np.quantile(finite, 0.9) / 60:,.1f} min, max {finite.max() / 60:,.1f} min",
        )
    )

    # Cross-check against administrativ's metres for the same pairs. This is the check that
    # catches a speed table applied to the wrong column or a graph built from the wrong file:
    # both produce times that look reasonable alone and absurd beside a distance.
    distance = pd.read_parquet(distance_path).set_index(["a_siruta", "b_siruta"])["road_m"]
    distance_m = np.array([distance.get((a, b), np.nan) for a, b in pairs])
    checked = plausibility(distance_m, road_s)
    report.add(
        Check(
            "implied_speed",
            checked["implausible"] == 0,
            f"implied door-to-door speed over {checked['pairs']:,} pairs: "
            f"median {checked['median_kmh']:.1f} km/h; "
            f"{checked['implausible']} pairs above {IMPLAUSIBLE_KMH:.0f} km/h",
            fatal=checked["implausible"] > 0,
        )
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "road_time.parquet"
    time_table(pairs, road_s).to_parquet(out, index=False)

    reports_dir = OUT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    write_report(report, reports_dir / "road_time.md", reports_dir / "road_time.json")

    if report.failed:
        return 1
    print(f"\nWrote {out} ({len(pairs):,} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd simulators/transport && uv run pytest tests/test_build_road_time.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Lint and commit**

```bash
cd simulators/transport && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/build_road_time.py simulators/transport/tests/test_build_road_time.py
git commit -m "Measure the same adjacent pairs in seconds

Administrativ measures them in metres over this exact graph; the only
difference here is that each segment is divided by its class's speed
before the search. Justitie already carries the caveat this retires —
kilometres are not hours, and forty in the mountains can cost more than
eighty on the plain.

Unreachable pairs stay in the table as infinity. A dropped row is a
journey nobody counted, and an uncounted journey flatters everything
built on top of it.

The implied door-to-door speed is checked against administrativ's metres
for the same pairs and is fatal above 110 km/h. A speed table applied to
the wrong column produces times that look reasonable alone and absurd
beside a distance."
```

---

### Task 5: County-scoped seat-to-seat minutes

**Files:**
- Create: `simulators/transport/scripts/county_times.py`
- Create: `simulators/transport/tests/test_county_times.py`

- [ ] **Step 1: Write the failing tests**

Create `simulators/transport/tests/test_county_times.py`:

```python
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
    ("1", "2"): 600.0, ("2", "1"): 600.0,
    ("2", "3"): 900.0, ("3", "2"): 900.0,
    ("2", "4"): 300.0, ("4", "2"): 300.0,
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
        ("1", "2"): 100.0, ("2", "1"): 100.0,
        ("2", "3"): 100.0, ("3", "2"): 100.0,
        ("1", "3"): 5000.0, ("3", "1"): 5000.0,
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_county_times.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.county_times'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/county_times.py`:

```python
"""Seat-to-seat journey time within one county, accumulated over the adjacency graph.

The time-domain counterpart of `reference_model._county_road_distances`. Like it, this is a
Dijkstra over the **UAT adjacency graph** rather than over the road network: a journey from a
commune to a distant seat is the sum of the seat-to-seat hops between them.

That approximation always overstates, never understates, because it forces the route through
each intermediate seat village rather than past it. Overstating is the safe direction for a
substrate: a network built on times that are slightly too long is conservative, while one
built on times that are too short promises journeys that do not exist.

Journeys never cross a county line, matching administrativ's constraint that regions do not.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable


def county_times(
    county: dict[str, str],
    neighbours: dict[str, list[str]],
    edge_s: dict[tuple[str, str], float],
    county_code: str,
    sources: Iterable[str],
) -> dict[str, float]:
    """Seconds from the nearest source to every reachable UAT in `county_code`.

    A UAT with no route is **absent from the result**, not zero: absent is a hole the caller
    has to handle, and zero is a hole that reads as an answer. An adjacency edge with no
    measured time is likewise not traversable — treating it as free would route journeys
    through precisely the pairs the router failed to measure.
    """
    best: dict[str, float] = {}
    queue: list[tuple[float, str]] = []

    for source in sources:
        if county.get(source) == county_code and source not in best:
            best[source] = 0.0
            heapq.heappush(queue, (0.0, source))

    while queue:
        seconds, uat = heapq.heappop(queue)
        if seconds > best.get(uat, float("inf")):
            continue
        for neighbour in neighbours.get(uat, ()):
            if county.get(neighbour) != county_code:
                continue
            step = edge_s.get((uat, neighbour))
            if step is None:
                continue
            through = seconds + step
            if through < best.get(neighbour, float("inf")):
                best[neighbour] = through
                heapq.heappush(queue, (through, neighbour))

    return best
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd simulators/transport && uv run pytest tests/test_county_times.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Lint and commit**

```bash
cd simulators/transport && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/county_times.py simulators/transport/tests/test_county_times.py
git commit -m "Accumulate hop times into county-scoped journeys

The time counterpart of the model's road-distance accumulation: a Dijkstra
over the UAT adjacency graph, so a distant journey is the sum of the
seat-to-seat hops between.

It overstates and never understates, because it routes through each
intermediate seat village rather than past it. That is the safe direction
for a substrate — times slightly too long are conservative, times too
short promise journeys that do not exist.

An unmeasured edge is impassable rather than free, and an unreachable UAT
is absent rather than zero. Zero is a hole that reads as an answer."
```

---

### Task 6: The gate — one county, hand-checked

This is the task the whole layer exists for. Nothing above L0 may be built until it passes.

**Files:**
- Create: `simulators/transport/sources/reference-drive-times-vl.csv`
- Create: `simulators/transport/scripts/check_gate.py`
- Create: `simulators/transport/tests/test_check_gate.py`

**Why Vâlcea (VL):** the county has both the Olt valley and genuine mountain roads, so the speed table's weakest assumption — that a road class implies a speed regardless of terrain — is exercised rather than flattered. A flat county would pass this gate with a badly wrong table.

- [ ] **Step 1: Create the reference file with real, cited drive times**

This file is **human-authored** and is the only part of L0 that cannot be generated. Record each pair from a public routing service, note which and when, and keep the pairs spread across terrain — valley, plateau and mountain — rather than clustered near Râmnicu Vâlcea.

Create `simulators/transport/sources/reference-drive-times-vl.csv`:

```csv
from_siruta,to_siruta,from_name,to_name,minutes,source,retrieved
# Twelve seat-to-seat drives in Vâlcea, recorded by hand. Replace every REPLACE_ME with a
# real SIRUTA code and a real recorded time before running the gate; the gate refuses to run
# on an unfilled file rather than passing an empty check.
REPLACE_ME,REPLACE_ME,Râmnicu Vâlcea,Băbeni,0,REPLACE_ME,2026-08-29
```

> **Note for the implementer:** the SIRUTA codes come from `simulators/administrativ/data/processed/uat_seats.gpkg`, or from the `attributes.json` already published under `dist/administrativ/data/`. Do not invent them. The gate's `test_the_reference_file_is_filled_in` test fails while any `REPLACE_ME` remains, which is deliberate — an empty gate that passes is worse than no gate.

- [ ] **Step 2: Write the failing tests**

Create `simulators/transport/tests/test_check_gate.py`:

```python
"""Tests for the one-county verification gate.

The gate is the only thing standing between an assumed speed table and every number built on
top of it, so these tests are mostly about the gate failing when it should. A gate that
passes quietly is indistinguishable from no gate at all.
"""

from __future__ import annotations

import pytest

from scripts.check_gate import compare, verdict


def test_a_close_match_passes():
    rows = compare(
        modelled_min={("1", "2"): 30.0},
        reference=[{"from_siruta": "1", "to_siruta": "2", "minutes": 32.0}],
    )
    assert rows[0]["within_tolerance"] is True


def test_a_wild_miss_fails():
    rows = compare(
        modelled_min={("1", "2"): 12.0},
        reference=[{"from_siruta": "1", "to_siruta": "2", "minutes": 45.0}],
    )
    assert rows[0]["within_tolerance"] is False


def test_the_error_is_relative_not_absolute():
    """Ten minutes out on a two-hour drive is fine; ten minutes out on a twelve-minute drive
    is the speed table being wrong."""
    long_drive = compare(
        modelled_min={("1", "2"): 130.0},
        reference=[{"from_siruta": "1", "to_siruta": "2", "minutes": 120.0}],
    )
    short_drive = compare(
        modelled_min={("1", "2"): 22.0},
        reference=[{"from_siruta": "1", "to_siruta": "2", "minutes": 12.0}],
    )
    assert long_drive[0]["within_tolerance"] is True
    assert short_drive[0]["within_tolerance"] is False


def test_a_pair_the_model_cannot_route_is_a_failure_not_a_skip():
    """A missing pair is the graph failing on exactly the journey someone checked by hand."""
    rows = compare(
        modelled_min={},
        reference=[{"from_siruta": "1", "to_siruta": "2", "minutes": 30.0}],
    )
    assert rows[0]["within_tolerance"] is False
    assert rows[0]["modelled_min"] is None


def test_the_verdict_fails_when_any_pair_is_out():
    rows = [{"within_tolerance": True}, {"within_tolerance": False}]
    assert verdict(rows)["passed"] is False


def test_the_verdict_reports_systematic_bias():
    """Every pair 20% slow is a speed table to fix, not twelve separate coincidences. Errors
    that all lean the same way are the signal; scatter is not."""
    rows = [
        {"within_tolerance": True, "error_ratio": 1.18},
        {"within_tolerance": True, "error_ratio": 1.21},
        {"within_tolerance": True, "error_ratio": 1.19},
    ]
    assert verdict(rows)["passed"] is False
    assert "systematic" in verdict(rows)["reason"]


def test_scattered_errors_within_tolerance_pass():
    rows = [
        {"within_tolerance": True, "error_ratio": 1.08},
        {"within_tolerance": True, "error_ratio": 0.94},
        {"within_tolerance": True, "error_ratio": 1.02},
    ]
    assert verdict(rows)["passed"] is True


def test_an_empty_gate_never_passes():
    """The failure mode this whole task exists to prevent."""
    assert verdict([])["passed"] is False


def test_the_reference_file_is_filled_in():
    """Fails until a human has recorded real times. An unfilled gate that passes is worse
    than no gate, because it reads as verification."""
    from pathlib import Path

    csv = Path(__file__).resolve().parents[1] / "sources/reference-drive-times-vl.csv"
    text = csv.read_text(encoding="utf-8")
    assert "REPLACE_ME" not in text, "record real drive times before the gate means anything"
    rows = [line for line in text.splitlines() if line and not line.startswith(("#", "from_"))]
    assert len(rows) >= 12, f"only {len(rows)} reference drives; the gate needs at least 12"


@pytest.mark.parametrize("minutes", [0.0, -5.0])
def test_a_nonsense_reference_time_is_rejected(minutes):
    with pytest.raises(ValueError, match="positive"):
        compare(
            modelled_min={("1", "2"): 30.0},
            reference=[{"from_siruta": "1", "to_siruta": "2", "minutes": minutes}],
        )
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_check_gate.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.check_gate'`.

- [ ] **Step 4: Write the implementation**

Create `simulators/transport/scripts/check_gate.py`:

```python
"""Gate 1: modelled travel times against real drive times, in one county.

The speed table in `speeds.py` is assumed. This is the only thing that makes it defensible,
and it is deliberately small and manual: a dozen seat-to-seat drives in Vâlcea, recorded by a
human from a public routing service and committed with their source.

Vâlcea because it has both the Olt valley and real mountain roads, so the table's weakest
assumption — that a road class implies a speed regardless of terrain — is exercised rather
than flattered. A flat county would pass this gate with a badly wrong table.

Two ways to fail, and the second matters more. Any single pair outside tolerance fails.
But so does a set of pairs that are all inside tolerance and all leaning the same way: twelve
drives each 18% slow is one speed table to fix, not twelve coincidences, and it is exactly
the error a per-pair tolerance is blind to.

Usage:
    uv run python -m scripts.check_gate
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "sources/reference-drive-times-vl.csv"
COUNTY = "VL"

# A modelled time may be this far either side of the recorded one. Wide, because the recorded
# time is itself one routing service's estimate on one day, and narrow enough that a table
# out by a third cannot survive.
TOLERANCE = 0.35

# Mean error beyond this, in a consistent direction, is a systematic bias rather than scatter.
BIAS_LIMIT = 0.15


def compare(modelled_min: dict[tuple[str, str], float], reference: list[dict]) -> list[dict]:
    """One row per reference drive, with the modelled time beside it."""
    rows = []
    for ref in reference:
        recorded = float(ref["minutes"])
        if recorded <= 0:
            raise ValueError(f"reference minutes must be positive, got {recorded}")
        key = (str(ref["from_siruta"]), str(ref["to_siruta"]))
        got = modelled_min.get(key)
        ratio = None if got is None else got / recorded
        rows.append(
            {
                "from_siruta": key[0],
                "to_siruta": key[1],
                "recorded_min": recorded,
                "modelled_min": got,
                "error_ratio": ratio,
                "within_tolerance": ratio is not None and abs(ratio - 1.0) <= TOLERANCE,
            }
        )
    return rows


def verdict(rows: list[dict]) -> dict:
    """Pass or fail, and why. An empty set never passes."""
    if not rows:
        return {"passed": False, "reason": "no reference drives; the gate checked nothing"}

    out = [r for r in rows if not r["within_tolerance"]]
    if out:
        return {"passed": False, "reason": f"{len(out)} of {len(rows)} drives outside tolerance"}

    ratios = [r["error_ratio"] for r in rows if r.get("error_ratio") is not None]
    if ratios:
        bias = statistics.mean(ratios) - 1.0
        if abs(bias) > BIAS_LIMIT:
            direction = "slow" if bias > 0 else "fast"
            return {
                "passed": False,
                "reason": (
                    f"systematic bias: every drive models {abs(bias):.0%} {direction} on "
                    f"average — a speed table to fix, not scatter"
                ),
            }

    return {"passed": True, "reason": f"{len(rows)} drives within {TOLERANCE:.0%}"}


def load_reference(path: Path = REFERENCE) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import pandas as pd

    from scripts.county_times import county_times

    times_path = ROOT / "data/road_time.parquet"
    if not times_path.exists():
        raise SystemExit(f"Missing {times_path}. Run: uv run python -m scripts.build_road_time")

    sys.path.insert(0, str(ROOT.parent / "administrativ"))
    from pipeline.reference_model import load_data  # noqa: PLC0415

    data = load_data()
    table = pd.read_parquet(times_path)
    edge_s: dict[tuple[str, str], float] = {}
    for a, b, seconds in zip(table["a_siruta"], table["b_siruta"], table["road_s"], strict=True):
        edge_s[(a, b)] = seconds
        edge_s[(b, a)] = seconds

    reference = load_reference()
    modelled: dict[tuple[str, str], float] = {}
    for ref in reference:
        source = str(ref["from_siruta"])
        reach = county_times(data.county, data.neighbours, edge_s, COUNTY, [source])
        target = str(ref["to_siruta"])
        if target in reach:
            modelled[(source, target)] = reach[target] / 60.0

    rows = compare(modelled, reference)
    result = verdict(rows)

    print(f"Gate 1 — travel time, {COUNTY}\n")
    print(f"{'from':>9} {'to':>9} {'recorded':>9} {'modelled':>9} {'ratio':>7}")
    for row in rows:
        got = "—" if row["modelled_min"] is None else f"{row['modelled_min']:.0f}"
        ratio = "—" if row["error_ratio"] is None else f"{row['error_ratio']:.2f}"
        mark = " " if row["within_tolerance"] else "✗"
        print(
            f"{row['from_siruta']:>9} {row['to_siruta']:>9} "
            f"{row['recorded_min']:>8.0f}m {got:>8}m {ratio:>7} {mark}"
        )

    print(f"\n{'PASS' if result['passed'] else 'FAIL'}: {result['reason']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

```bash
cd simulators/transport && uv run pytest tests/test_check_gate.py -q
```

Expected: all pass **except** `test_the_reference_file_is_filled_in`, which fails while the CSV still contains `REPLACE_ME`. That failure is the plan working.

- [ ] **Step 6: Fill in the reference file, then re-run**

Record twelve real seat-to-seat drives in Vâlcea, spread across valley, plateau and mountain. Replace the placeholder row entirely. Then:

```bash
cd simulators/transport && uv run pytest tests/test_check_gate.py -q
```

Expected: all pass, including `test_the_reference_file_is_filled_in`.

- [ ] **Step 7: Lint and commit**

```bash
cd simulators/transport && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/check_gate.py simulators/transport/tests/test_check_gate.py simulators/transport/sources/reference-drive-times-vl.csv
git commit -m "Check the modelled times against twelve real drives in Valcea

The speed table is assumed and nothing else makes it defensible. Valcea
because it has both the Olt valley and real mountain roads, so the weakest
assumption — that a road class implies a speed whatever the terrain — is
exercised rather than flattered.

Two ways to fail. Any single drive outside 35% fails. So does a set that
are all within tolerance and all leaning the same way: twelve drives each
18% slow is one table to fix, not twelve coincidences, and it is exactly
what a per-pair tolerance cannot see.

An empty gate never passes, and the tests fail while the reference file
still holds placeholders. A gate that passes without checking anything
reads as verification, which is worse than having none."
```

---

### Task 7: Run the real build, and wire it into CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `simulators/transport/README.md`

- [ ] **Step 1: Build administrativ's artefacts, if they are not already present**

This is a long download and a long run. Do it once.

```bash
cd simulators/administrativ
uv sync --all-groups
uv run python -m pipeline.fetch --with-roads
uv run python -m pipeline.build_geometry
uv run python -m pipeline.build_seats
uv run python -m pipeline.build_adjacency
uv run python -m pipeline.build_road_distance
```

Expected: `data/processed/road_distance.parquet` exists. If `fetch` fails on a government source, that is administrativ's documented behaviour — importers keep what they downloaded, so re-run rather than restart.

- [ ] **Step 2: Run the travel-time build**

```bash
cd simulators/transport && uv run python -m scripts.build_road_time
```

Expected: a report ending in `Wrote .../road_time.parquet` with roughly the same edge count as `road_distance.parquet`, a median seat-to-seat time in the tens of minutes, and `implied_speed` passing. **If `implied_speed` fails, stop and fix the speed table** — that check exists precisely to catch this before the gate does.

- [ ] **Step 3: Run the gate**

```bash
cd simulators/transport && uv run python -m scripts.check_gate
```

Expected: a twelve-row table and `PASS`. If it fails with a systematic bias, adjust `EFFECTIVE_KMH` in `speeds.py` in the direction the bias reports, re-run Step 2, and re-run the gate. Record what you changed and why in the commit — a speed table tuned to a gate with no record of the tuning is worse than an untuned one.

- [ ] **Step 4: Write `simulators/transport/README.md`**

```markdown
# transport — Romanian public transport simulator

What it costs per year to connect every one of Romania's 3 186 UATs to public transport at a
declared standard, and who can actually get where.

Design: [`docs/superpowers/specs/2026-08-29-transport-design.md`](../../docs/superpowers/specs/2026-08-29-transport-design.md).

## Status

`L0` only — the road travel-time substrate. Nothing above it is built.

## What L0 is

Administrativ measures the distance between adjacent UAT seats. This measures the **time**,
over the same OSM network and the same junction graph, by dividing each segment by an assumed
speed for its road class.

That assumption is the weakest thing here, and it is confined to `scripts/speeds.py` so it can
be read as a unit. What makes it defensible is `scripts/check_gate.py`: twelve real drives in
Vâlcea, recorded by hand, which the modelled times must match within 35% individually and
without systematic bias collectively.

## Running it

```sh
# In simulators/administrativ, once — L0 reads its road graph:
uv run python -m pipeline.fetch --with-roads
uv run python -m pipeline.build_road_distance

# Then here:
uv run python -m scripts.build_road_time   # writes data/road_time.parquet
uv run python -m scripts.check_gate        # the gate; non-zero exit on failure
```

`data/` is not committed. It is reproducible from the commands above.
```

- [ ] **Step 5: Add the CI job**

In `.github/workflows/ci.yml`, add this job after the `administrativ` job, at the same indentation as the other jobs:

```yaml
  transport:
    name: transport
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      # The travel-time build needs administrativ's road graph and a 1 GB OSM extract, so
      # it does not run here — the same reason administrativ's own reference-model tests
      # skip in CI. What runs is everything that does not need the artefacts: the speed
      # table, the accumulation, and the gate's own logic including its refusal to pass on
      # an empty or unfilled reference file.
      - name: Pipeline
        working-directory: simulators/transport
        env:
          PYTHONHASHSEED: '0'
        run: |
          uv sync --all-groups
          uv run ruff check scripts tests
          uv run ruff format --check scripts tests
          uv run pytest -q
```

- [ ] **Step 6: Verify the CI job's commands pass locally exactly as written**

```bash
cd simulators/transport && uv sync --all-groups && uv run ruff check scripts tests && uv run ruff format --check scripts tests && PYTHONHASHSEED=0 uv run pytest -q
```

Expected: all pass. This is the same sequence CI runs, so a pass here means the job will pass.

- [ ] **Step 7: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add .github/workflows/ci.yml simulators/transport/README.md
git commit -m "Run the transport pipeline in CI, minus what needs a gigabyte of OSM

The travel-time build reads administrativ's road graph and a 1 GB extract,
so it stays out of CI for the same reason administrativ's reference-model
tests do. What does run is everything that does not need the artefacts —
including the gate's refusal to pass on an unfilled reference file, which
is the check most worth having run on every push."
```

---

## Self-Review

**Spec coverage.** L0 in the spec is the road travel-time substrate (§9 `traveltime` unit) plus Gate 1 (§14.1). Tasks 2–5 build the unit; Task 6 builds the gate; Task 7 runs both. §14.5's determinism requirement is covered by `test_it_is_sorted_so_the_artefact_is_byte_reproducible` and Parquet's byte-reproducibility, which the spec already notes is safe where GeoPackage is not. §13's provenance requirement is covered by `SPEED_PROVENANCE` and its test. Not covered, and correctly so: the rail matrix (§9 `railnet`, layer `LR`), and the TypeScript port and parity suite (§10) — L0 produces a pipeline artefact with no browser consumer yet, so a port would be a port of nothing.

**One deliberate deviation from the spec.** §14.1 says "roughly a dozen seat-to-seat pairs"; Task 6 fixes it at twelve minimum and adds a systematic-bias check the spec does not mention. The bias check earns its place: twelve independent tolerances cannot see the one error most likely to occur, which is the whole table being uniformly wrong.

**Where the plan is smaller than the spec assumed.** The spec treats L0 as building a travel-time substrate from scratch. It is not: `build_road_distance.py` already builds the graph, snaps the seats and runs the chunked Dijkstra. L0 adds a speed table and a weight. Task 3 is the only change outside `simulators/transport/`, it is additive, and its tests pin the existing behaviour as the no-argument default.

**Placeholder scan.** The only `REPLACE_ME` in the plan is inside the reference CSV, deliberately, with a test that fails while it remains — that is a gate, not an unfinished step. Every code step contains complete runnable code.

**Type consistency.** `speeds_for_classes(np.ndarray) -> np.ndarray` is defined in Task 2 and called in Task 4. `build_graph(roads, report, speed_kmh=None)` is defined in Task 3 and called in Task 4 with the keyword. `county_times(county, neighbours, edge_s, county_code, sources)` is defined in Task 5 and called in Task 6 with that argument order. `compare(modelled_min, reference)` and `verdict(rows)` are defined in Task 6 and used only there.

**Verified against the real code.** `Data.neighbours: dict[str, tuple[str, ...]]` exists at `pipeline/reference_model.py:129`, alongside `county: dict[str, str]` and `road_distance: dict[tuple[str, str], float]`. Task 6's call signature is correct as written.

**Two deliberate divergences from `_county_road_distances`.** Both are in `county_times`, both are stricter, and neither is an accident — if an implementer "fixes" them to match administrativ, the substrate gets quietly worse:

1. **Sources are filtered by county.** `_county_road_distances` seeds `best = {s: 0.0 for s in sources}` without checking the source is in the county, so a source outside it enters the result at zero. `county_times` skips such a source. Test: `test_it_never_leaves_the_county`.
2. **A missing edge is impassable, not straight-line.** `_county_road_distances` falls back to `_distance(data, uat, neighbour)` — a Euclidean estimate — when an edge has no measured road distance. There is no honest Euclidean *time*: it would require exactly the speed assumption the gate exists to test, applied where the router already failed. So `county_times` refuses the hop instead. Test: `test_a_missing_edge_does_not_silently_become_free`.

This is why `county_times` takes plain dicts rather than a `Data` object. It does not inherit administrativ's fallbacks, and it can be tested without building a 3 186-row model.

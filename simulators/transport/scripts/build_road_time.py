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

from scripts.speeds import (  # noqa: E402
    DEFAULT_VEHICLE,
    EFFECTIVE_KMH,
    FALLBACK_KMH,
    effective_kmh,
    speeds_for_classes,
)

OUT_DIR = ROOT / "data"

# Administrativ bounds its search at 60 km because adjacent seats are close and an unbounded
# national search would explore the whole country per source. This is the same bound in
# seconds: the time the slowest road in the table would take to cover that distance, so
# nothing administrativ can reach is lost here to the limit.
#
# **Derived, not written down.** The real longest adjacent pair is 60,0 km — administrativ's
# own limit, exactly — which at 20 km/h is 10 798 s against a limit of 10 800. The margin is
# two seconds. A literal here would still read as correct after someone lowered a speed in
# the table, and pairs would begin disappearing from the graph with nothing to say so.
SLOWEST_KMH = min(min(EFFECTIVE_KMH.values()), FALLBACK_KMH)
SEARCH_LIMIT_M = 60_000
SEARCH_LIMIT_S = SEARCH_LIMIT_M / (SLOWEST_KMH / 3.6)

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
    return pd.DataFrame(
        {
            "a_siruta": [a for a, _ in pairs],
            "b_siruta": [b for _, b in pairs],
            "road_s": seconds,
            "road_min": np.round(seconds / 60.0, 2),
        }
    ).sort_values(["a_siruta", "b_siruta"], ignore_index=True)


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
    parser = argparse.ArgumentParser(description=__doc__)
    # A counterfactual network is driven through this same code rather than a copy of it: the
    # bypass programme writes a limits file in which the bypassed settlements no longer hold
    # their class inside a 50 zone, and the two runs are comparable precisely because only the
    # limits differ. See scripts/build_ocoliri.py.
    parser.add_argument("--limits", type=Path, default=None, help="alternate road-limits.json")
    parser.add_argument("--out", type=Path, default=None, help="alternate output parquet")
    args = parser.parse_args(argv)
    table = effective_kmh(DEFAULT_VEHICLE, args.limits) if args.limits else None
    if args.limits:
        print(f"Using {args.limits.name}: trunk {table['trunk']}, primary {table['primary']} km/h")

    import geopandas as gpd
    from pipeline.build_geometry import Check, Report, write_report
    from pipeline.build_road_distance import build_graph, load_roads, snap_seats
    from pipeline.paths import PROCESSED_DIR
    from scipy.sparse.csgraph import dijkstra

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
                f"Missing {path}. Run, in simulators/administrativ: uv run python -m pipeline.{cmd}"
            )

    print("Loading roads...")
    roads = load_roads()

    print("Pricing each road class...")
    speed = speeds_for_classes(roads["highway"].to_numpy(), table)

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
    out = args.out or OUT_DIR / "road_time.parquet"
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

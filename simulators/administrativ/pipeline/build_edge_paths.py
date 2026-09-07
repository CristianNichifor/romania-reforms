"""The actual roads behind each adjacency edge's distance.

`build_road_distance.py` routes between the seats of every adjacent pair of UATs and keeps
one number per edge. The number is what the model accumulates; the route it came from is
thrown away. That makes the map unable to answer the question it is most often asked — *why
is this commune under that town* — with anything but an assertion.

This reconstructs the route. Same graph, same weights, same snapping, but Dijkstra is asked
for predecessors as well as distances, so the sequence of junctions between two seats can be
walked back and written out as a line.

**Every path is checked against the distance already published for that edge.** A
reconstruction that does not reproduce `road_m` is a different route from the one the model
measured, and drawing it would be worse than drawing nothing: the map would show a road that
is not the road the number came from. Mismatches are reported and, past a threshold, fatal.

Output:
    web/public/data/edge-paths/<COUNTY>.geojson   one LineString per adjacency edge
    data/processed/reports/edge_paths.md

Usage:
    uv run python -m pipeline.build_edge_paths --county TL
    uv run python -m pipeline.build_edge_paths --all
"""

from __future__ import annotations

import argparse
import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import LineString

from pipeline.build_geometry import Check, Report, write_report
from pipeline.build_road_distance import (
    ROUTING_CLASSES,
    SEARCH_LIMIT_M,
    build_graph,
    snap_seats,
)
from pipeline.constants import CRS_STEREO70, CRS_WGS84
from pipeline.paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR, WEB_DATA_DIR

# How far outside a county's own seats to load road geometry.
#
# The routing that produced the published distances ran on the whole national network. Working
# county by county keeps the graph small enough to build repeatedly, but a route that leaves
# the county and comes back needs the roads it used to be present or it will be re-routed the
# long way round — and silently disagree with the number it is supposed to illustrate. The
# margin is generous for that reason, and the agreement check below is what actually proves it
# was generous enough.
COUNTY_MARGIN_M = 30_000.0

# A reconstructed route is the same route if it is this close to the published distance.
#
# Chosen from the measured distribution, not tuned until it passed. `road_distance.parquet`
# was built from an OSM extract some days older than the one this reads, and OSM Romania is
# edited daily — so the same road can be a metre or two longer than when it was measured. The
# deviations split cleanly along that line: across the worst counties the median is 0.00 m and
# the p99 is 3-8 m, which is a refined shape, while Timis carries a tail at 113-380 m, which
# on a 15 km route is a different road.
#
# 25 m accepts the first and refuses the second. An edge that fails is left without geometry
# and drawn schematically, which is the honest outcome: the alternative is a line the reader
# would take as evidence for a number it did not produce.
#
# The clean fix is to rebuild road_distance.parquet from this same extract so there is one
# vintage. That changes every distance in the model, and with it the map and the parity
# fixtures, so it is deliberately not bundled into this change.
LENGTH_TOLERANCE_M = 25.0

# Above this share of disagreeing edges the county is not written at all. A handful of
# genuinely re-routed edges is a data note; a systematic disagreement means the margin is too
# small and the whole shard is describing routes nobody measured.
MAX_MISMATCH_SHARE = 0.02

# Simplification, in metres, applied in the projected CRS before writing.
#
# These lines are drawn under a commune fill at national-to-regional zoom, never inspected for
# survey accuracy. 25 m keeps every bend a reader can see at the zoom the chain is shown at.
SIMPLIFY_M = 25.0

# Coordinate decimals in the output. Six is ~10 cm and pointless here; five is ~1 m.
COORD_DECIMALS = 5


def county_of_seats(seats: gpd.GeoDataFrame, county: str) -> gpd.GeoDataFrame:
    return seats[seats["county_code"] == county]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--county", help="two-letter county code, e.g. TL")
    ap.add_argument("--all", action="store_true", help="every county")
    ap.add_argument(
        "--tolerance-m",
        type=float,
        default=LENGTH_TOLERANCE_M,
        help="how far a reconstructed route may differ from its published distance",
    )
    ap.add_argument(
        "--margin-km",
        type=float,
        default=COUNTY_MARGIN_M / 1000,
        help="how far outside the county to load roads; raise it where routes detour widely",
    )
    args = ap.parse_args(argv)
    if not args.county and not args.all:
        raise SystemExit("Pass --county <CODE> or --all")

    report = Report()

    seats_path = PROCESSED_DIR / "uat_seats.gpkg"
    adjacency_path = PROCESSED_DIR / "adjacency.parquet"
    distance_path = PROCESSED_DIR / "road_distance.parquet"
    for path, cmd in (
        (seats_path, "build_seats"),
        (adjacency_path, "build_adjacency"),
        (distance_path, "build_road_distance"),
    ):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run: uv run python -m pipeline.{cmd}")

    pbf = RAW_DIR / "romania-latest.osm.pbf"
    if not pbf.exists():
        raise SystemExit(f"Missing {pbf}. Run: uv run python -m pipeline.fetch --with-roads")

    seats = gpd.read_file(seats_path, layer="seat").sort_values("siruta", ignore_index=True)
    if "county_code" not in seats.columns:
        # The seat layer carries the SIRUTA; the county comes from the geometry layer.
        uats = gpd.read_file(PROCESSED_DIR / "uat_geometry.gpkg", layer="uat")
        seats = seats.merge(uats[["siruta", "county_code"]], on="siruta", how="left")

    adjacency = pd.read_parquet(adjacency_path)
    distances = pd.read_parquet(distance_path)
    published = {
        (a, b): m
        for a, b, m in zip(
            distances["a_siruta"], distances["b_siruta"], distances["road_m"], strict=True
        )
    }

    counties = sorted(seats["county_code"].dropna().unique()) if args.all else [args.county]
    out_dir = WEB_DATA_DIR / "edge-paths"
    out_dir.mkdir(parents=True, exist_ok=True)
    to_wgs84 = Transformer.from_crs(CRS_STEREO70, CRS_WGS84, always_xy=True)
    to_lonlat = to_wgs84

    totals = {"edges": 0, "written": 0, "mismatched": 0, "unreachable": 0}

    for county in counties:
        here = county_of_seats(seats, county)
        if here.empty:
            print(f"[{county}] no seats; skipped")
            continue

        # Edges with both ends in this county. A cross-border edge belongs to neither shard:
        # the model never grows over a county line, so no chain ever uses one.
        in_county = set(here["siruta"])
        edges = [
            (a, b)
            for a, b in zip(adjacency["a_siruta"], adjacency["b_siruta"], strict=True)
            if a in in_county and b in in_county
        ]
        if not edges:
            print(f"[{county}] no intra-county edges; skipped")
            continue

        # The seats are in Stereo70 and the extract is in WGS84. pyogrio filters in the
        # layer's own CRS, so the margin is applied in metres and the box is then converted —
        # passing projected metres to a lon/lat filter would quietly select nothing at all.
        minx, miny, maxx, maxy = here.total_bounds
        margin = args.margin_km * 1000
        west, south = to_lonlat.transform(minx - margin, miny - margin)
        east, north = to_lonlat.transform(maxx + margin, maxy + margin)
        bbox = (west, south, east, north)
        classes = ",".join(f"'{c}'" for c in ROUTING_CLASSES)
        print(f"[{county}] loading roads in bbox…")
        roads = gpd.read_file(
            pbf,
            layer="lines",
            columns=["highway"],
            where=f"highway IN ({classes})",
            bbox=bbox,
            engine="pyogrio",
        )
        if roads.crs is None:
            roads = roads.set_crs(CRS_WGS84)
        roads = roads.to_crs(CRS_STEREO70)

        graph, node_of_vertex, coords, n_nodes = build_graph(roads, Report())

        # One representative coordinate per junction. Vertices snapped to the same node are
        # within a metre of each other by construction, so any of them will do.
        node_xy = np.zeros((n_nodes, 2), dtype=np.float64)
        node_xy[node_of_vertex] = coords

        seat_nodes, _ = snap_seats(coords, node_of_vertex, here, Report())
        node_of_siruta = dict(zip(here["siruta"], seat_nodes, strict=True))

        wanted: dict[str, list[str]] = {}
        for a, b in edges:
            wanted.setdefault(a, []).append(b)

        features = []
        mismatched: list[tuple[str, str, float, float]] = []
        deviations: list[float] = []
        unreachable = 0

        print(f"[{county}] routing {len(edges):,} edges from {len(wanted):,} seats…")
        for source in sorted(wanted):
            dist, predecessors = dijkstra(
                graph,
                directed=False,
                indices=node_of_siruta[source],
                limit=SEARCH_LIMIT_M,
                return_predecessors=True,
            )
            for target in wanted[source]:
                end = node_of_siruta[target]
                if not np.isfinite(dist[end]):
                    unreachable += 1
                    continue

                # Walk the predecessors back from the target to the source.
                path = [end]
                node = end
                while predecessors[node] >= 0:
                    node = predecessors[node]
                    path.append(node)
                path.reverse()
                if len(path) < 2:
                    unreachable += 1
                    continue

                line = LineString(node_xy[path])
                want = published.get((source, target), np.inf)
                if np.isfinite(want):
                    deviations.append(abs(line.length - want))
                # The check that makes this worth drawing: the same route, or not written.
                if abs(line.length - want) > args.tolerance_m:
                    mismatched.append(
                        (source, target, line.length, published.get((source, target), float("nan")))
                    )
                    continue

                simplified = line.simplify(SIMPLIFY_M, preserve_topology=False)
                lon, lat = to_wgs84.transform(*np.asarray(simplified.coords).T)
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"a": source, "b": target},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [round(float(x), COORD_DECIMALS), round(float(y), COORD_DECIMALS)]
                                for x, y in zip(lon, lat, strict=True)
                            ],
                        },
                    }
                )

        share = len(mismatched) / max(len(edges), 1)
        totals["edges"] += len(edges)
        totals["written"] += len(features)
        totals["mismatched"] += len(mismatched)
        totals["unreachable"] += unreachable

        print(
            f"[{county}] {len(features):,} written, {len(mismatched):,} disagreed "
            f"({share:.1%}), {unreachable} unreachable"
        )
        for a, b, got, want in mismatched[:5]:
            print(f"        {a}->{b}: reconstructed {got:,.0f} m, published {want:,.0f} m")
        if deviations:
            d = np.array(deviations)
            print(
                f"[{county}] deviation from published: median {np.median(d):.2f} m, "
                f"p99 {np.quantile(d, 0.99):.1f} m, max {d.max():,.1f} m"
            )

        report.add(
            Check(
                f"edge_paths_{county}",
                share <= MAX_MISMATCH_SHARE,
                f"{county}: {len(features):,} of {len(edges):,} edges reproduced the published "
                f"distance; {len(mismatched):,} disagreed ({share:.1%}), {unreachable} unreachable",
                fatal=share > MAX_MISMATCH_SHARE,
            )
        )
        if share > MAX_MISMATCH_SHARE:
            print(f"[{county}] REFUSING to write: too many routes disagree with their distance")
            continue

        path_out = out_dir / f"{county}.geojson"
        path_out.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"[{county}] wrote {path_out} ({path_out.stat().st_size / 1024:,.0f} KB)")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_report(report, REPORTS_DIR / "edge_paths.md", REPORTS_DIR / "edge_paths.json")
    print(
        f"\nTotal: {totals['written']:,} of {totals['edges']:,} edges written, "
        f"{totals['mismatched']:,} disagreed, {totals['unreachable']:,} unreachable"
    )
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())

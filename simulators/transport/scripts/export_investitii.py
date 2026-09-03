"""The road-investment layers, as one file the map can draw.

Three models produce places rather than totals — the ranked bypass crossings, the measured
traffic corridors, and the junctions that carry real traffic — and until now all three existed
only as numbers in JSON. A number about geography that cannot be pointed at is a number a
reader has to take on trust.

**One file, three kinds.** Everything carries a `kind` and the map filters on it, rather than
three fetches and three sources. The whole set is small — hundreds of features, not the
hundreds of thousands the speed layer holds — because these are the places a programme would
touch, not the network it sits on.

**Only what the models actually ranked.** The bypass crossings here are the 636 with measured
traffic, not all 2 781: the rest have no traffic to rank them by, so drawing them would put
lines on the map the model cannot order. The junctions are the busy subset for the same reason.
Both files say so in their own limitations, and the map says it again in the panel.

Output:
    data/investitii.geojson

Usage:
    uv run python -m scripts.export_investitii
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PBF = ADMINISTRATIV / "data" / "raw" / "romania-latest.osm.pbf"
TRAFFIC = ROOT / "data" / "reports" / "major-roads.gpkg"
OUT = ROOT / "data" / "investitii.geojson"

CLASSES: Final[tuple[str, ...]] = ("trunk", "primary")
JUNCTION_CLASSES: Final[tuple[str, ...]] = ("trunk", "primary", "secondary")
LOCALITY_KMH: Final[int] = 50
MIN_CROSSING_M: Final[float] = 500.0
MATCH_M: Final[float] = 60.0
JUNCTION_MATCH_M: Final[float] = 100.0
CLUSTER_M: Final[float] = 20.0
ROUNDABOUT_M: Final[float] = 60.0
DAYS: Final[int] = 365

# Coarser than the speed layer: these are 900-odd features drawn as an overlay, and nobody
# reads a bypass candidate at ten-metre fidelity.
SIMPLIFY_M: Final[float] = 200.0
DECIMALS: Final[int] = 4
CRS: Final[str] = "EPSG:3844"


def rounded(value):
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (int, float)):
            return [round(float(v), DECIMALS) for v in value]
        return [rounded(v) for v in value]
    return value


def feature(geometry, properties: dict) -> dict:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": geometry.geom_type,
            "coordinates": rounded(geometry.__geo_interface__["coordinates"]),
        },
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    for path, how in (
        (PBF, "administrativ fetch --with-roads"),
        (TRAFFIC, "build_trafic --refetch"),
    ):
        if not path.exists():
            print(f"Missing {path}. Run: {how}", file=sys.stderr)
            return 1

    import geopandas as gpd
    import numpy as np
    from shapely.ops import linemerge, unary_union

    from scripts.build_giratorii import ROUNDABOUT_TAG, junction_points, road_ref
    from scripts.build_prioritate import regime_speeds
    from scripts.measure_limits import parse_maxspeed

    ocoliri = json.loads((ROOT / "data" / "ocoliri-inputs.json").read_text(encoding="utf-8"))[
        "items"
    ]
    lei_per_km = ocoliri["bypassLeiPerKm"]["value"]
    lengthening = ocoliri["bypassLengthFactor"]["value"]
    inside_kmh, open_kmh = regime_speeds()

    end = gpd.read_file(TRAFFIC, layer="MajorRoadSource", engine="pyogrio").to_crs(CRS)
    end["aadt"] = end["annualTrafficFlow"] / DAYS

    features: list[dict] = []

    # --- measured traffic corridors ---------------------------------------------------
    corridors = end.copy()
    corridors["geometry"] = corridors.geometry.simplify(SIMPLIFY_M)
    for row in corridors.to_crs("EPSG:4326").itertuples():
        features.append(
            feature(
                row.geometry,
                {
                    "kind": "trafic",
                    "road": row.roadNationalCode,
                    "aadt": int(row.aadt),
                    "km": round(row.length / 1000, 1),
                },
            )
        )
    print(f"  {len(corridors):,} measured corridors")

    # --- ranked bypass crossings ------------------------------------------------------
    selector = ",".join(f"'{c}'" for c in CLASSES)
    roads = (
        gpd.read_file(
            PBF,
            layer="lines",
            columns=["highway", "other_tags"],
            where=f"highway IN ({selector})",
            engine="pyogrio",
        )
        .set_crs("EPSG:4326")
        .to_crs(CRS)
    )
    limits = np.array([parse_maxspeed(t) for t in roads["other_tags"]])
    merged = linemerge(unary_union(list(roads[limits == LOCALITY_KMH].geometry)))
    parts = merged.geoms if merged.geom_type == "MultiLineString" else [merged]
    parts = [p for p in parts if p.length >= MIN_CROSSING_M]
    crossings = gpd.GeoDataFrame({"m": [p.length for p in parts]}, geometry=list(parts), crs=CRS)
    near = gpd.sjoin_nearest(
        crossings, end[["aadt", "roadNationalCode", "geometry"]], how="left", max_distance=MATCH_M
    )
    near = near.groupby(level=0).agg({"m": "first", "aadt": "max", "roadNationalCode": "first"})
    known = near[near["aadt"].notna()].copy()
    known["km"] = known["m"] / 1000
    known["buildKm"] = known["km"] * lengthening
    known["hours"] = known["km"] / inside_kmh - known["buildKm"] / open_kmh
    known["vehicleHours"] = known["hours"] * known["aadt"] * DAYS
    known["cost"] = known["buildKm"] * lei_per_km
    known = known[known["vehicleHours"] > 0]
    known["perHour"] = known["cost"] / known["vehicleHours"]
    known = known.sort_values("perHour").reset_index()
    geoms = crossings.geometry.simplify(SIMPLIFY_M)
    for rank, row in enumerate(known.itertuples(), start=1):
        features.append(
            feature(
                gpd.GeoSeries([geoms.iloc[row.index]], crs=CRS).to_crs("EPSG:4326").iloc[0],
                {
                    "kind": "ocolire",
                    "rank": rank,
                    "road": row.roadNationalCode,
                    "km": round(row.km, 2),
                    "aadt": int(row.aadt),
                    "costRon": round(row.cost),
                    "ronPerVehicleHour": round(row.perHour, 1),
                },
            )
        )
    print(f"  {len(known):,} ranked crossings")

    # --- busy junction candidates -----------------------------------------------------
    jselector = ",".join(f"'{c}'" for c in JUNCTION_CLASSES)
    jroads = (
        gpd.read_file(
            PBF,
            layer="lines",
            columns=["highway", "other_tags"],
            where=f"highway IN ({jselector})",
            engine="pyogrio",
        )
        .set_crs("EPSG:4326")
        .to_crs(CRS)
    )
    jtags = jroads["other_tags"].fillna("")
    jroads["ref"] = [road_ref(t) for t in jroads["other_tags"]]
    jroads["rb"] = jtags.str.contains(ROUNDABOUT_TAG, regex=False)
    dissolved = jroads[jroads["ref"].notna() & ~jroads["rb"]].dissolve(by="ref", as_index=False)
    index = dissolved.sindex
    points = []
    for row in dissolved.itertuples():
        for other in index.query(row.geometry, predicate="intersects"):
            if dissolved["ref"].iloc[other] <= row.ref:
                continue
            points.extend(
                junction_points(row.geometry.intersection(dissolved.geometry.iloc[other]))
            )
    blobs = gpd.GeoSeries(points, crs=CRS).buffer(CLUSTER_M).union_all()
    clusters = list(blobs.geoms) if blobs.geom_type == "MultiPolygon" else [blobs]
    junctions = gpd.GeoDataFrame(geometry=[c.centroid for c in clusters], crs=CRS)
    converted = junctions.geometry.intersects(
        jroads[jroads["rb"]].geometry.buffer(ROUNDABOUT_M).union_all()
    )
    remaining = junctions[~converted].reset_index(drop=True)
    jnear = gpd.sjoin_nearest(
        remaining, end[["aadt", "geometry"]], how="left", max_distance=JUNCTION_MATCH_M
    )
    jnear = jnear.groupby(level=0)["aadt"].max()
    busy = remaining[jnear.notna().to_numpy()].copy()
    busy["aadt"] = jnear[jnear.notna()].to_numpy()
    for row in busy.to_crs("EPSG:4326").itertuples():
        features.append(feature(row.geometry, {"kind": "giratoriu", "aadt": int(row.aadt)}))
    print(f"  {len(busy):,} busy junction candidates")

    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"\nWrote {OUT.name} ({OUT.stat().st_size / 1024:.0f} KB, {len(features):,} features)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

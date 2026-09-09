"""Refresh transport access rows from the shared health-access views.

Usage:
    uv run python -m scripts.build_health_access
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.health_access import (
    DEFAULT_HEALTH_ACCESS,
    DEFAULT_HEALTH_POINT_ACCESS,
    DEFAULT_HEALTH_POINT_ROAD_ACCESS,
    enrich_access_document,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACCESS = ROOT / "data" / "access.json"
ADMINISTRATIV_WEB_DATA = ROOT.parent / "administrativ/web/public/data"
DEFAULT_UAT_GEOMETRY = ADMINISTRATIV_WEB_DATA / "uats.geojson"
DEFAULT_ATTRIBUTES = ADMINISTRATIV_WEB_DATA / "attributes.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(ROOT.parent.parent)
    except ValueError:
        return path


def read_uat_locations(geometry_path: Path, attributes_path: Path) -> dict[str, dict[str, float]]:
    import geopandas as gpd

    attributes = read_json(attributes_path)
    sirutas = [str(siruta) for siruta in attributes["siruta"]]
    uats = gpd.read_file(geometry_path)
    if len(uats) != len(sirutas):
        raise SystemExit(
            "UAT geometry and attributes have different row counts; cannot align centroids"
        )
    if uats.crs is None:
        uats = uats.set_crs(4326)

    projected = uats.to_crs(3844)
    centroid_frame = gpd.GeoDataFrame(
        {"siruta": sirutas},
        geometry=projected.geometry.centroid,
        crs=projected.crs,
    ).to_crs(4326)
    return {
        row.siruta: {"latitude": row.geometry.y, "longitude": row.geometry.x}
        for row in centroid_frame.itertuples()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access", type=Path, default=DEFAULT_ACCESS)
    parser.add_argument("--health-access", type=Path, default=DEFAULT_HEALTH_ACCESS)
    parser.add_argument("--health-point-access", type=Path, default=DEFAULT_HEALTH_POINT_ACCESS)
    parser.add_argument(
        "--health-point-road-access",
        type=Path,
        default=DEFAULT_HEALTH_POINT_ROAD_ACCESS,
    )
    parser.add_argument("--uat-geometry", type=Path, default=DEFAULT_UAT_GEOMETRY)
    parser.add_argument("--attributes", type=Path, default=DEFAULT_ATTRIBUTES)
    parser.add_argument("--out", type=Path, default=DEFAULT_ACCESS)
    args = parser.parse_args(argv)

    if not args.access.exists():
        raise SystemExit(f"Missing {args.access} - run uv run python -m scripts.build_access")
    if not args.health_access.exists():
        raise SystemExit(f"Missing {args.health_access} - build packages/health_access first")
    if not args.health_point_access.exists():
        raise SystemExit(f"Missing {args.health_point_access} - build packages/health_access first")
    if not args.health_point_road_access.exists():
        raise SystemExit(
            f"Missing {args.health_point_road_access} - build packages/health_access first"
        )
    if not args.uat_geometry.exists():
        raise SystemExit(f"Missing {args.uat_geometry} - build administrativ web data first")
    if not args.attributes.exists():
        raise SystemExit(f"Missing {args.attributes} - build administrativ web data first")

    document = enrich_access_document(
        read_json(args.access),
        read_json(args.health_access),
        read_json(args.health_point_access),
        read_uat_locations(args.uat_geometry, args.attributes),
        read_json(args.health_point_road_access),
    )
    args.out.write_text(
        # This payload is row-heavy and the repository has a strict 60 MB tracked-size gate.
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    summary = document["summary"]
    print(
        f"{summary['healthAccessRowsWithData']:,} transport UAT rows carry health data from "
        f"{summary['healthAccessView']}; "
        f"{summary['healthAccessLocalProviders']:,} eligible local providers on routed rows"
    )
    print(
        f"{summary['healthPointAccessRowsWithDistance']:,} transport UAT rows carry nearest "
        f"provider point distances from {summary['healthPointAccessView']} with "
        f"{summary['healthPointAccessDistanceMethod']}"
    )
    print(
        f"{summary['healthPointRoadAccessRowsWithDistance']:,} transport UAT rows carry nearest "
        f"provider point road-proxy distances from {summary['healthPointRoadAccessView']} with "
        f"{summary['healthPointRoadAccessDistanceMethod']}"
    )
    print(f"Wrote {display_path(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / "packages/health_access/scripts/build_health_point_road_access.py"
DATA = ROOT / "packages/health_access/data"
ADMIN_WEB = ROOT / "simulators/administrativ/web/public/data"

spec = importlib.util.spec_from_file_location("build_health_point_road_access", BUILDER)
assert spec and spec.loader
road_access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(road_access)


def polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        ],
    }


def graph_payload(nodes: list[tuple[str, str, str, dict[str, Any]]]) -> dict[str, Any]:
    order = [siruta for siruta, _, _, _ in nodes]
    index_of = {siruta: index for index, siruta in enumerate(order)}
    graph_nodes = {}
    nodes_by_county = defaultdict(list)
    for siruta, name, county, geometry in nodes:
        node = {
            "siruta": siruta,
            "name": name,
            "county": county,
            "geometry": geometry,
            "bbox": road_access.geometry_bbox(geometry),
            "location": road_access.geometry_centroid(geometry),
        }
        graph_nodes[siruta] = node
        nodes_by_county[county].append(node)

    adjacency = [[] for _ in order]
    if len(order) == 3:
        adjacency[index_of["1"]].append((index_of["2"], 1000.0))
        adjacency[index_of["2"]].append((index_of["1"], 1000.0))
        adjacency[index_of["2"]].append((index_of["3"], 1000.0))
        adjacency[index_of["3"]].append((index_of["2"], 1000.0))

    return {
        "manifest": {
            "uatCount": len(order),
            "edgeCount": sum(len(row) for row in adjacency) // 2,
            "traversableEdgeCount": sum(len(row) for row in adjacency) // 2,
        },
        "order": order,
        "indexOf": index_of,
        "nodes": graph_nodes,
        "nodesByCounty": dict(nodes_by_county),
        "adjacency": adjacency,
    }


def point(provider_id: str, siruta: str, lat: float, lon: float, county: str = "TS") -> dict:
    return {
        "providerId": provider_id,
        "countyCode": county,
        "siruta": siruta,
        "latitude": lat,
        "longitude": lon,
    }


def point_access_fixture(points: list[dict], exclusions: list[dict] | None = None) -> dict:
    exclusions = exclusions or []
    return {
        "id": "health-point-access-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "summary": {
            "pointAccessProviders": len(points),
            "pointAccessBlockedProviders": len(exclusions),
            "namedExclusions": len(exclusions),
        },
        "points": points,
        "exclusions": exclusions,
    }


def test_build_document_routes_from_provider_snap_nodes():
    graph = graph_payload(
        [
            ("1", "ONE", "TS", polygon(0, 0, 1, 1)),
            ("2", "TWO", "TS", polygon(1, 0, 2, 1)),
            ("3", "THREE", "TS", polygon(2, 0, 3, 1)),
        ]
    )
    one = graph["nodes"]["1"]["location"]
    three = graph["nodes"]["3"]["location"]
    document = road_access.build_document(
        point_access_fixture(
            [
                point("anmcs-2025-001", "1", one["latitude"], one["longitude"]),
                point("anmcs-2025-002", "3", three["latitude"], three["longitude"]),
            ]
        ),
        graph,
        {
            "healthPointAccessSha256": "a" * 64,
            "administrativManifestSha256": "b" * 64,
            "administrativAttributesSha256": "c" * 64,
            "administrativAdjacencySha256": "d" * 64,
            "administrativUatGeometrySha256": "e" * 64,
        },
        "2026-09-09",
    )

    rows = {row[0]: row for row in document["uats"]}
    assert document["uatDistanceColumns"] == road_access.UAT_DISTANCE_COLUMNS
    assert rows["1"][1] == "anmcs-2025-001"
    assert rows["1"][5] == 0
    assert rows["2"][1] == "anmcs-2025-001"
    assert rows["2"][5] == 1000
    assert rows["3"][1] == "anmcs-2025-002"
    assert rows["3"][5] == 0
    assert document["summary"]["medianNearestMetres"] == 0


def test_bucharest_municipality_points_snap_to_sector_graph_nodes():
    graph = graph_payload([("179141", "SECTORUL 1", "B", polygon(26, 44, 27, 45))])
    sector = graph["nodes"]["179141"]["location"]
    document = road_access.build_document(
        point_access_fixture(
            [
                point(
                    "anmcs-2025-001",
                    "179132",
                    sector["latitude"],
                    sector["longitude"],
                    "B",
                )
            ]
        ),
        graph,
        {
            "healthPointAccessSha256": "a" * 64,
            "administrativManifestSha256": "b" * 64,
            "administrativAttributesSha256": "c" * 64,
            "administrativAdjacencySha256": "d" * 64,
            "administrativUatGeometrySha256": "e" * 64,
        },
        "2026-09-09",
    )

    snap = document["providerSnaps"][0]
    assert snap["providerSiruta"] == "179132"
    assert snap["snapNodeSiruta"] == "179141"
    assert snap["snapMethod"] == "bucharest-sector-polygon"
    assert document["uats"][0][5] == 0


def test_committed_road_access_view_routes_only_accepted_provider_points():
    document = json.loads(
        (DATA / "health-point-road-access-uat-2024-2026.json").read_text(encoding="utf-8")
    )
    point_access = json.loads(
        (DATA / "health-point-access-2024-2026.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((ADMIN_WEB / "manifest.json").read_text(encoding="utf-8"))

    columns = {name: index for index, name in enumerate(document["uatDistanceColumns"])}
    accepted_ids = {point["providerId"] for point in point_access["points"]}
    blocked_ids = {row["providerId"] for row in point_access["exclusions"]}
    routed_ids = {row[columns["nearestProviderId"]] for row in document["uats"]}
    snap_nodes = {snap["snapNodeSiruta"] for snap in document["providerSnaps"]}

    assert document["id"] == "health-point-road-access-uat-2024-2026"
    assert document["summary"]["uats"] == manifest["uatCount"] == len(document["uats"])
    assert document["summary"]["providers"] == point_access["summary"]["pointAccessProviders"]
    assert document["summary"]["providerSnaps"] == len(document["providerSnaps"]) == 206
    assert document["summary"]["pointAccessBlockedProviders"] == 386
    assert document["summary"]["pointAccessNamedExclusions"] == 386
    assert document["summary"]["distanceMethod"] == road_access.DISTANCE_METHOD
    assert routed_ids <= accepted_ids
    assert routed_ids.isdisjoint(blocked_ids)
    assert len(document["exclusions"]) == len(blocked_ids)
    assert all(row[columns["providerSnapNodeSiruta"]] in snap_nodes for row in document["uats"])
    assert all(
        row[columns["roadGraphMetres"]] + row[columns["providerSnapMetres"]]
        == row[columns["roadProxyMetres"]]
        for row in document["uats"]
    )

    limitation_ids = {limitation["id"] for limitation in document["limitations"]}
    assert "road-proxy-not-door-to-door" in limitation_ids
    assert "provider-point-exclusions-carried-forward" in limitation_ids
    assert "bucharest-snaps-to-sector-nodes" in limitation_ids


def test_committed_road_access_view_is_reproducible():
    expected = json.loads(
        (DATA / "health-point-road-access-uat-2024-2026.json").read_text(encoding="utf-8")
    )

    rebuilt = road_access.build_from_files(
        DATA / "health-point-access-2024-2026.json",
        ADMIN_WEB / "manifest.json",
        ADMIN_WEB / "attributes.json",
        ADMIN_WEB / "adjacency.bin",
        ADMIN_WEB / "uats.geojson",
        expected["retrievedDate"],
    )

    assert rebuilt == expected

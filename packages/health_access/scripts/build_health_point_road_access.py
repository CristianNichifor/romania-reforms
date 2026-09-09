"""Build UAT-to-provider-point road-proxy health access.

The source point layer is not a distance model. This builder is the first shared
consumer of those points: it snaps each accepted provider coordinate to an
administrativ UAT road-graph node, runs multi-source Dijkstra over the committed
road-distance graph, and publishes compact UAT rows.

The output is still a proxy, not door-to-door routing. The graph starts and ends
at UAT road nodes; the provider endpoint is represented by a straight-line
destination offset from the snapped node to the provider coordinate.

Usage:
    uv run python packages/health_access/scripts/build_health_point_road_access.py
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import struct
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Final

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV_WEB = REPO_ROOT / "simulators/administrativ/web/public/data"
POINT_ACCESS = PACKAGE_ROOT / "data/health-point-access-2024-2026.json"
MANIFEST = ADMINISTRATIV_WEB / "manifest.json"
ATTRIBUTES = ADMINISTRATIV_WEB / "attributes.json"
ADJACENCY = ADMINISTRATIV_WEB / "adjacency.bin"
UAT_GEOMETRY = ADMINISTRATIV_WEB / "uats.geojson"

ACCESS_VIEW_ID: Final[str] = "health-point-road-access-uat-2024-2026"
HEALTH_POINT_ACCESS_VIEW_ID: Final[str] = "health-point-access-2024-2026"
OUT = PACKAGE_ROOT / f"data/{ACCESS_VIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 1
BUCHAREST_MUNICIPALITY_SIRUTA: Final[str] = "179132"
DISTANCE_METHOD: Final[str] = "road-graph-to-snap-node-plus-straight-line-offset"
PROVIDER_SNAP_METHOD: Final[str] = "provider-coordinate-to-administrativ-uat-road-node"
ROUTING_METHOD: Final[str] = "multi-source-dijkstra-road-metres"
UAT_DISTANCE_COLUMNS: Final[list[str]] = [
    "siruta",
    "nearestProviderId",
    "providerSnapNodeSiruta",
    "roadGraphMetres",
    "providerSnapMetres",
    "roadProxyMetres",
]
EARTH_RADIUS_METRES: Final[float] = 6_371_008.8
WEB_MERCATOR_RADIUS_METRES: Final[float] = 6_378_137.0
WEB_MERCATOR_MAX_LATITUDE: Final[float] = 85.05112878


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def finite_float(value: object, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def straight_line_metres(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    hav = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_METRES * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def project_wgs84(lon: float, lat: float) -> tuple[float, float]:
    clipped_lat = max(min(lat, WEB_MERCATOR_MAX_LATITUDE), -WEB_MERCATOR_MAX_LATITUDE)
    return (
        WEB_MERCATOR_RADIUS_METRES * math.radians(lon),
        WEB_MERCATOR_RADIUS_METRES
        * math.log(math.tan(math.pi / 4 + math.radians(clipped_lat) / 2)),
    )


def unproject_wgs84(x: float, y: float) -> tuple[float, float]:
    return (
        math.degrees(x / WEB_MERCATOR_RADIUS_METRES),
        math.degrees(2 * math.atan(math.exp(y / WEB_MERCATOR_RADIUS_METRES)) - math.pi / 2),
    )


def geometry_positions(geometry: dict[str, Any]) -> list[list[float]]:
    if geometry["type"] == "Polygon":
        return [position for ring in geometry["coordinates"] for position in ring]
    if geometry["type"] == "MultiPolygon":
        return [
            position for polygon in geometry["coordinates"] for ring in polygon for position in ring
        ]
    raise ValueError(f"unsupported UAT geometry type {geometry['type']}")


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    positions = geometry_positions(geometry)
    lons = [finite_float(position[0], "geometry.longitude") for position in positions]
    lats = [finite_float(position[1], "geometry.latitude") for position in positions]
    return min(lons), min(lats), max(lons), max(lats)


def ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    points = [
        project_wgs84(
            finite_float(point[0], "geometry.longitude"),
            finite_float(point[1], "geometry.latitude"),
        )
        for point in ring
    ]
    if len(points) < 3:
        raise ValueError("UAT geometry ring has fewer than three points")
    if points[0] != points[-1]:
        points.append(points[0])

    double_area = 0.0
    cx_acc = 0.0
    cy_acc = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        cross = x0 * y1 - x1 * y0
        double_area += cross
        cx_acc += (x0 + x1) * cross
        cy_acc += (y0 + y1) * cross

    if abs(double_area) < 1e-6:
        xs = [point[0] for point in points[:-1]]
        ys = [point[1] for point in points[:-1]]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return abs(double_area / 2), cx_acc / (3 * double_area), cy_acc / (3 * double_area)


def polygon_centroid(polygon: list[list[list[float]]]) -> tuple[float, float, float]:
    if not polygon:
        raise ValueError("UAT polygon has no rings")
    outer_area, outer_x, outer_y = ring_centroid(polygon[0])
    total_area = outer_area
    x_acc = outer_x * outer_area
    y_acc = outer_y * outer_area
    for hole in polygon[1:]:
        hole_area, hole_x, hole_y = ring_centroid(hole)
        total_area -= hole_area
        x_acc -= hole_x * hole_area
        y_acc -= hole_y * hole_area
    if total_area <= 0:
        return outer_area, outer_x, outer_y
    return total_area, x_acc / total_area, y_acc / total_area


def geometry_centroid(geometry: dict[str, Any]) -> dict[str, float]:
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        raise ValueError(f"unsupported UAT geometry type {geometry['type']}")

    total_area = 0.0
    x_acc = 0.0
    y_acc = 0.0
    for polygon in polygons:
        area, x, y = polygon_centroid(polygon)
        total_area += area
        x_acc += x * area
        y_acc += y * area
    if total_area <= 0:
        raise ValueError("UAT geometry has zero area")
    lon, lat = unproject_wgs84(x_acc / total_area, y_acc / total_area)
    return {"latitude": lat, "longitude": lon}


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    if not ring:
        return False
    vertices = ring if ring[0] == ring[-1] else [*ring, ring[0]]
    inside = False
    for a, b in zip(vertices, vertices[1:], strict=False):
        x0 = finite_float(a[0], "geometry.longitude")
        y0 = finite_float(a[1], "geometry.latitude")
        x1 = finite_float(b[0], "geometry.longitude")
        y1 = finite_float(b[1], "geometry.latitude")
        if (y0 > lat) != (y1 > lat):
            crossing_x = ((x1 - x0) * (lat - y0) / (y1 - y0)) + x0
            if lon < crossing_x:
                inside = not inside
    return inside


def point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(lon, lat, polygon[0]):
        return False
    return not any(point_in_ring(lon, lat, hole) for hole in polygon[1:])


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    if geometry["type"] == "Polygon":
        return point_in_polygon(lon, lat, geometry["coordinates"])
    if geometry["type"] == "MultiPolygon":
        return any(point_in_polygon(lon, lat, polygon) for polygon in geometry["coordinates"])
    raise ValueError(f"unsupported UAT geometry type {geometry['type']}")


def read_graph_payload(
    manifest_file: Path,
    attributes_file: Path,
    adjacency_file: Path,
    geometry_file: Path,
) -> dict[str, Any]:
    manifest = read_json(manifest_file)
    attributes = read_json(attributes_file)
    geometry = read_json(geometry_file)
    order = [str(siruta) for siruta in attributes["siruta"]]
    features = geometry["features"]
    if len(order) != len(features):
        raise ValueError("administrativ attributes and geometry have different row counts")
    if len(order) != int(manifest["uatCount"]):
        raise ValueError("administrativ manifest UAT count differs from attributes")

    index_of = {siruta: index for index, siruta in enumerate(order)}
    if len(index_of) != len(order):
        duplicates = [siruta for siruta, count in Counter(order).items() if count > 1]
        raise ValueError(
            "duplicate SIRUTA rows in administrativ attributes: " + ", ".join(duplicates)
        )

    nodes: dict[str, dict[str, Any]] = {}
    nodes_by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for siruta, name, county, feature in zip(
        order,
        attributes["name"],
        attributes["county"],
        features,
        strict=True,
    ):
        node = {
            "siruta": siruta,
            "name": name,
            "county": county,
            "geometry": feature["geometry"],
            "bbox": geometry_bbox(feature["geometry"]),
            "location": geometry_centroid(feature["geometry"]),
        }
        nodes[siruta] = node
        nodes_by_county[county].append(node)

    adjacency = [[] for _ in order]
    edge_count = int(manifest["edgeCount"])
    raw = adjacency_file.read_bytes()
    required_size = edge_count * 13
    if len(raw) < required_size:
        raise ValueError("administrativ adjacency payload is shorter than manifest declares")

    edge_b_offset = edge_count * 2
    road_offset = edge_count * 4
    traversable_offset = edge_count * 12
    for edge_index in range(edge_count):
        if raw[traversable_offset + edge_index] != 1:
            continue
        a = struct.unpack_from("<H", raw, edge_index * 2)[0]
        b = struct.unpack_from("<H", raw, edge_b_offset + edge_index * 2)[0]
        road_m = struct.unpack_from("<f", raw, road_offset + edge_index * 4)[0]
        if a >= len(order) or b >= len(order):
            raise ValueError("administrativ adjacency references a missing UAT node")
        if not math.isfinite(road_m) or road_m < 0:
            continue
        adjacency[a].append((b, road_m))
        adjacency[b].append((a, road_m))

    return {
        "manifest": manifest,
        "order": order,
        "indexOf": index_of,
        "nodes": nodes,
        "nodesByCounty": dict(nodes_by_county),
        "adjacency": adjacency,
    }


def find_containing_node(
    lat: float,
    lon: float,
    county: str,
    graph: dict[str, Any],
) -> dict[str, Any] | None:
    matches = []
    for node in graph["nodesByCounty"].get(county, []):
        min_lon, min_lat, max_lon, max_lat = node["bbox"]
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue
        if point_in_geometry(lon, lat, node["geometry"]):
            matches.append(node)
    if not matches:
        return None
    return min(
        matches,
        key=lambda node: straight_line_metres(
            lat,
            lon,
            node["location"]["latitude"],
            node["location"]["longitude"],
        ),
    )


def nearest_county_node(
    lat: float,
    lon: float,
    county: str,
    graph: dict[str, Any],
) -> dict[str, Any] | None:
    nodes = graph["nodesByCounty"].get(county, [])
    if not nodes:
        return None
    return min(
        nodes,
        key=lambda node: straight_line_metres(
            lat,
            lon,
            node["location"]["latitude"],
            node["location"]["longitude"],
        ),
    )


def provider_snaps(point_access: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
    if point_access["id"] != HEALTH_POINT_ACCESS_VIEW_ID:
        raise ValueError(f"expected {HEALTH_POINT_ACCESS_VIEW_ID}, got {point_access['id']}")

    snaps = []
    for point in sorted(point_access["points"], key=lambda item: item["providerId"]):
        lat = finite_float(point["latitude"], f"{point['providerId']}.latitude")
        lon = finite_float(point["longitude"], f"{point['providerId']}.longitude")
        provider_siruta = str(point["siruta"])
        county = point["countyCode"]

        contained = find_containing_node(lat, lon, county, graph)
        if contained is not None:
            snap_node = contained
            if snap_node["siruta"] == provider_siruta:
                snap_method = "provider-siruta-polygon"
            elif provider_siruta == BUCHAREST_MUNICIPALITY_SIRUTA:
                snap_method = "bucharest-sector-polygon"
            else:
                snap_method = "point-containing-uat-polygon"
        elif provider_siruta in graph["indexOf"]:
            snap_node = graph["nodes"][provider_siruta]
            snap_method = "provider-siruta-centroid"
        else:
            snap_node = nearest_county_node(lat, lon, county, graph)
            snap_method = "nearest-county-uat-centroid"

        if snap_node is None:
            raise ValueError(f"provider point cannot be snapped to graph: {point['providerId']}")

        snap_distance = straight_line_metres(
            lat,
            lon,
            snap_node["location"]["latitude"],
            snap_node["location"]["longitude"],
        )
        snaps.append(
            {
                "providerId": point["providerId"],
                "countyCode": county,
                "providerSiruta": provider_siruta,
                "snapNodeSiruta": snap_node["siruta"],
                "snapNodeName": snap_node["name"],
                "snapMethod": snap_method,
                "snapDistanceMetres": int(round(snap_distance)),
            }
        )

    expected = int(point_access["summary"]["pointAccessProviders"])
    if len(snaps) != expected:
        raise ValueError(
            f"snapped {len(snaps)} providers, but point access summary declares {expected}"
        )
    return snaps


def better_distance(
    candidate_distance: float,
    candidate_provider: str,
    current_distance: float,
    current_provider: str | None,
) -> bool:
    if candidate_distance < current_distance - 1e-9:
        return True
    return abs(candidate_distance - current_distance) <= 1e-9 and (
        current_provider is None or candidate_provider < current_provider
    )


def uat_distances(graph: dict[str, Any], snaps: list[dict[str, Any]]) -> list[list[Any]]:
    order = graph["order"]
    adjacency = graph["adjacency"]
    best_distance = [math.inf for _ in order]
    best_provider: list[str | None] = [None for _ in order]
    heap: list[tuple[float, str, int]] = []
    snap_by_provider = {snap["providerId"]: snap for snap in snaps}

    for snap in snaps:
        node_index = graph["indexOf"][snap["snapNodeSiruta"]]
        provider_id = snap["providerId"]
        distance = float(snap["snapDistanceMetres"])
        if better_distance(
            distance, provider_id, best_distance[node_index], best_provider[node_index]
        ):
            best_distance[node_index] = distance
            best_provider[node_index] = provider_id
            heapq.heappush(heap, (distance, provider_id, node_index))

    while heap:
        distance, provider_id, node_index = heapq.heappop(heap)
        if (
            abs(distance - best_distance[node_index]) > 1e-9
            or provider_id != best_provider[node_index]
        ):
            continue
        for neighbour, edge_metres in adjacency[node_index]:
            candidate = distance + edge_metres
            if better_distance(
                candidate,
                provider_id,
                best_distance[neighbour],
                best_provider[neighbour],
            ):
                best_distance[neighbour] = candidate
                best_provider[neighbour] = provider_id
                heapq.heappush(heap, (candidate, provider_id, neighbour))

    rows = []
    missing = []
    for node_index, siruta in enumerate(order):
        provider_id = best_provider[node_index]
        if provider_id is None or not math.isfinite(best_distance[node_index]):
            missing.append(siruta)
            continue
        snap = snap_by_provider[provider_id]
        snap_metres = int(snap["snapDistanceMetres"])
        total_metres = int(round(best_distance[node_index]))
        road_metres = max(0, total_metres - snap_metres)
        rows.append(
            [
                siruta,
                provider_id,
                snap["snapNodeSiruta"],
                road_metres,
                snap_metres,
                total_metres,
            ]
        )

    if missing:
        raise ValueError("unroutable UAT road graph nodes: " + ", ".join(missing[:10]))
    return rows


def median_int(values: list[int]) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def compact_exclusions(point_access: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "kind": "provider-excluded-from-road-point-access",
            "source": point_access["id"],
            "providerId": row["providerId"],
            "pointAccessBlockedReason": row["pointAccessBlockedReason"],
        }
        for row in sorted(point_access["exclusions"], key=lambda item: item["providerId"])
    ]


def build_document(
    point_access: dict[str, Any],
    graph: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
) -> dict[str, Any]:
    snaps = provider_snaps(point_access, graph)
    rows = uat_distances(graph, snaps)
    snap_distances = [snap["snapDistanceMetres"] for snap in snaps]
    total_distances = [row[5] for row in rows]
    snap_methods = dict(sorted(Counter(snap["snapMethod"] for snap in snaps).items()))

    summary = {
        "uats": len(rows),
        "providers": int(point_access["summary"]["pointAccessProviders"]),
        "providerSnaps": len(snaps),
        "providerSnapNodes": len({snap["snapNodeSiruta"] for snap in snaps}),
        "pointAccessBlockedProviders": int(point_access["summary"]["pointAccessBlockedProviders"]),
        "pointAccessNamedExclusions": int(point_access["summary"]["namedExclusions"]),
        "distanceMethod": DISTANCE_METHOD,
        "providerSnapMethod": PROVIDER_SNAP_METHOD,
        "routingMethod": ROUTING_METHOD,
        "medianNearestMetres": median_int(total_distances),
        "medianProviderSnapMetres": median_int(snap_distances),
        "maxProviderSnapMetres": max(snap_distances),
        "snapMethods": snap_methods,
    }

    return {
        "$schema": "../schema/health-point-road-access.schema.json",
        "id": ACCESS_VIEW_ID,
        "title": "UAT-level routed provider-point health access",
        "publisher": "Ministerul Sanatatii / ANMCS / Cristian Nichifor",
        "scope": "uat-to-provider-point-road-proxy",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": f"{point_access['id']} + administrativ web road graph",
            "locator": (
                "accepted provider coordinates snapped to administrativ UAT road-graph nodes; "
                "nearest provider per UAT found by multi-source Dijkstra over road metres"
            ),
            "confidence": "derived",
            "note": (
                "Distance is a road proxy: UAT road node to provider snap node over the "
                "administrativ graph, plus straight-line provider-to-snap-node offset."
            ),
        },
        "accessModel": {
            "kind": "uat-provider-point-road-proxy",
            "providerSnapMethod": PROVIDER_SNAP_METHOD,
            "routingMethod": ROUTING_METHOD,
            "distanceMethod": DISTANCE_METHOD,
            "distanceFormula": (
                "roadProxyMetres = roadGraphMetres(origin UAT node, provider snap UAT node) "
                "+ providerSnapMetres(provider coordinate, snap UAT centroid)"
            ),
            "distanceIncludes": [
                "administrativ road graph metres between UAT road nodes",
                "straight-line destination offset from snapped UAT node to provider coordinate",
            ],
            "distanceExcludes": [
                "origin household or neighbourhood offset inside the origin UAT",
                "street-network routing from the snapped UAT node to the provider doorway",
                "travel time, congestion and service availability",
            ],
        },
        "registry": {
            "healthPointAccess": {
                "id": point_access["id"],
                "periodStart": point_access["periodStart"],
                "periodEnd": point_access["periodEnd"],
            },
            "roadGraph": {
                "id": "administrativ-web-public-road-distance",
                "uatCount": int(graph["manifest"]["uatCount"]),
                "edgeCount": int(graph["manifest"]["edgeCount"]),
                "traversableEdgeCount": int(graph["manifest"]["traversableEdgeCount"]),
            },
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": "packages/health_access/scripts/build_health_point_road_access.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "providerSnaps": snaps,
        "uatDistanceColumns": UAT_DISTANCE_COLUMNS,
        "uats": rows,
        "exclusions": compact_exclusions(point_access),
        "limitations": [
            limitation(
                "road-proxy-not-door-to-door",
                "material",
                ["accessModel.distanceMethod", "uats"],
                (
                    "The provider coordinate is not inserted as a road-network node. It is "
                    "snapped to an administrativ UAT road node, routed through the UAT graph, "
                    "then adjusted with a straight-line provider offset. The result is a "
                    "road-proxy distance, not exact door-to-door distance or travel time."
                ),
            ),
            limitation(
                "provider-point-exclusions-carried-forward",
                "material",
                ["exclusions"],
                (
                    f"{point_access['summary']['pointAccessBlockedProviders']} providers "
                    "without accepted point evidence remain excluded from routed point access. "
                    "They are carried as compact provider-id exclusions and remain fully named "
                    "in health-point-access-2024-2026."
                ),
            ),
            limitation(
                "bucharest-snaps-to-sector-nodes",
                "material",
                ["providerSnaps"],
                (
                    "Bucharest provider points are published at municipality SIRUTA level, "
                    "while the administrativ road graph contains sector nodes. The routing "
                    "contract snaps those points to containing sector polygons when possible."
                ),
            ),
            limitation(
                "origin-is-uat-road-node",
                "material",
                ["uats"],
                (
                    "Each UAT row starts from the administrativ graph node for that UAT, not "
                    "from a citizen's home. Local intra-UAT access at the origin is outside "
                    "this shared proxy."
                ),
            ),
        ],
    }


def build_from_files(
    point_access_path: Path,
    manifest_path: Path,
    attributes_path: Path,
    adjacency_path: Path,
    geometry_path: Path,
    retrieved_date: str,
) -> dict[str, Any]:
    point_access = read_json(point_access_path)
    graph = read_graph_payload(manifest_path, attributes_path, adjacency_path, geometry_path)
    return build_document(
        point_access,
        graph,
        {
            "healthPointAccessSha256": sha256_file(point_access_path),
            "administrativManifestSha256": sha256_file(manifest_path),
            "administrativAttributesSha256": sha256_file(attributes_path),
            "administrativAdjacencySha256": sha256_file(adjacency_path),
            "administrativUatGeometrySha256": sha256_file(geometry_path),
        },
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-point-access", type=Path, default=POINT_ACCESS)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--attributes", type=Path, default=ATTRIBUTES)
    parser.add_argument("--adjacency", type=Path, default=ADJACENCY)
    parser.add_argument("--uat-geometry", type=Path, default=UAT_GEOMETRY)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    document = build_from_files(
        args.health_point_access,
        args.manifest,
        args.attributes,
        args.adjacency,
        args.uat_geometry,
        args.retrieved_date,
    )
    # This routed UAT payload is mostly compact rows; pretty-printing expands it enough to
    # matter under the repository size gate.
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    summary = document["summary"]
    print(
        f"wrote {args.output} with {summary['uats']:,} routed UAT rows, "
        f"{summary['providerSnaps']} provider snaps and "
        f"{summary['pointAccessNamedExclusions']} point exclusions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

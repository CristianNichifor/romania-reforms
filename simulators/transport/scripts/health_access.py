"""Attach the shared health-access UAT view to transport access rows.

Transport publishes access only for UATs that its road model can route to a centre. The shared
health view is broader, so the summary here keeps both counts visible: national source totals
from `packages/health_access`, and local-provider counts on transport's own routed rows.
"""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Final

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_HEALTH_ACCESS: Final[Path] = (
    REPO_ROOT / "packages/health_access/data/health-service-access-uat-2024-2026.json"
)
DEFAULT_HEALTH_POINT_ACCESS: Final[Path] = (
    REPO_ROOT / "packages/health_access/data/health-point-access-2024-2026.json"
)
DEFAULT_HEALTH_POINT_ROAD_ACCESS: Final[Path] = (
    REPO_ROOT / "packages/health_access/data/health-point-road-access-uat-2024-2026.json"
)

BUCHAREST: Final[str] = "B"
HEALTH_ACCESS_VIEW_ID: Final[str] = "health-service-access-uat-2024-2026"
HEALTH_ACCESS_LIMITATION_ID: Final[str] = "sanatatea-vine-din-pachetul-shared"
HEALTH_POINT_ACCESS_VIEW_ID: Final[str] = "health-point-access-2024-2026"
HEALTH_POINT_ACCESS_LIMITATION_ID: Final[str] = "sanatatea-punctuala-in-linie-dreapta"
HEALTH_POINT_DISTANCE_METHOD: Final[str] = "straight-line"
HEALTH_POINT_ROAD_ACCESS_VIEW_ID: Final[str] = "health-point-road-access-uat-2024-2026"
HEALTH_POINT_ROAD_ACCESS_LIMITATION_ID: Final[str] = "sanatatea-punctuala-rutata-e-proxy"
HEALTH_POINT_ROAD_ACCESS_DISTANCE_METHOD: Final[str] = (
    "road-graph-to-snap-node-plus-straight-line-offset"
)
HEALTH_POINT_ROW_FIELDS: Final[tuple[str, ...]] = (
    "nearestHealthPointProviderId",
    "nearestHealthPointName",
    "nearestHealthPointCounty",
    "nearestHealthPointDistanceMetres",
    "nearestHealthPointDistanceMethod",
    "nearestHealthPointClinicalBeds",
)
HEALTH_POINT_ROAD_ROW_FIELDS: Final[tuple[str, ...]] = (
    "nearestHealthPointRoadProviderId",
    "nearestHealthPointRoadProxyMetres",
)
EARTH_RADIUS_METRES: Final[float] = 6_371_008.8


def normalise_siruta(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.lstrip("0") or "0"


def health_units_by_siruta(access: dict[str, Any]) -> dict[str, dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    duplicate_sirutas = []
    for unit in access["units"]:
        siruta = normalise_siruta(unit["siruta"])
        if siruta in units:
            duplicate_sirutas.append(siruta)
        units[siruta] = unit
    if duplicate_sirutas:
        listed = ", ".join(sorted(set(duplicate_sirutas))[:10])
        raise ValueError(f"shared health-access view has duplicate SIRUTA rows: {listed}")
    return units


def finite_float(value: object, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def health_points(point_access: dict[str, Any]) -> list[dict[str, Any]]:
    if point_access["id"] != HEALTH_POINT_ACCESS_VIEW_ID:
        raise ValueError(f"expected {HEALTH_POINT_ACCESS_VIEW_ID}, got {point_access['id']}")

    points: list[dict[str, Any]] = []
    duplicate_ids = []
    seen: set[str] = set()
    for point in point_access["points"]:
        provider_id = str(point["providerId"])
        if provider_id in seen:
            duplicate_ids.append(provider_id)
        seen.add(provider_id)

        lat = finite_float(point["latitude"], f"{provider_id}.latitude")
        lon = finite_float(point["longitude"], f"{provider_id}.longitude")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"health point {provider_id} has coordinates outside WGS84 bounds")

        out = dict(point)
        out["latitude"] = lat
        out["longitude"] = lon
        points.append(out)

    if duplicate_ids:
        listed = ", ".join(sorted(set(duplicate_ids))[:10])
        raise ValueError(f"point health-access view has duplicate provider rows: {listed}")
    if not points:
        raise ValueError("point health-access view has no eligible provider points")

    expected = int(point_access["summary"]["pointAccessProviders"])
    if len(points) != expected:
        raise ValueError(
            "point health-access provider count does not match summary: "
            f"{len(points)} points, summary says {expected}"
        )
    return points


def health_point_road_access(
    point_road_access: dict[str, Any],
    accepted_provider_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if point_road_access["id"] != HEALTH_POINT_ROAD_ACCESS_VIEW_ID:
        raise ValueError(
            f"expected {HEALTH_POINT_ROAD_ACCESS_VIEW_ID}, got {point_road_access['id']}"
        )
    summary = point_road_access["summary"]
    if summary["distanceMethod"] != HEALTH_POINT_ROAD_ACCESS_DISTANCE_METHOD:
        raise ValueError(
            f"point road health-access view changed distance method: {summary['distanceMethod']}"
        )

    columns = {name: index for index, name in enumerate(point_road_access["uatDistanceColumns"])}
    required = {
        "siruta",
        "nearestProviderId",
        "providerSnapNodeSiruta",
        "roadProxyMetres",
    }
    missing = sorted(required - columns.keys())
    if missing:
        raise ValueError("point road health-access view is missing columns: " + ", ".join(missing))

    rows: dict[str, dict[str, Any]] = {}
    duplicate_sirutas: list[str] = []
    unknown_providers: list[str] = []
    for row in point_road_access["uats"]:
        siruta = normalise_siruta(row[columns["siruta"]])
        if siruta in rows:
            duplicate_sirutas.append(siruta)

        provider_id = str(row[columns["nearestProviderId"]])
        if provider_id not in accepted_provider_ids:
            unknown_providers.append(provider_id)
        road_proxy_metres = int(row[columns["roadProxyMetres"]])
        if road_proxy_metres < 0:
            raise ValueError(f"point road health-access view has negative distance for {siruta}")
        rows[siruta] = {
            "nearestProviderId": provider_id,
            "providerSnapNodeSiruta": normalise_siruta(row[columns["providerSnapNodeSiruta"]]),
            "roadProxyMetres": road_proxy_metres,
        }

    if duplicate_sirutas:
        listed = ", ".join(sorted(set(duplicate_sirutas))[:10])
        raise ValueError(f"point road health-access view has duplicate SIRUTA rows: {listed}")
    if unknown_providers:
        listed = ", ".join(sorted(set(unknown_providers))[:10])
        raise ValueError(
            "point road health-access view routes providers outside accepted point-access "
            f"providers: {listed}"
        )
    expected_rows = int(summary["uats"])
    if len(rows) != expected_rows:
        raise ValueError(
            "point road health-access row count does not match summary: "
            f"{len(rows)} rows, summary says {expected_rows}"
        )
    return rows


def normalise_row_locations(
    row_locations: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    locations: dict[str, dict[str, float]] = {}
    duplicate_sirutas = []
    for siruta, location in row_locations.items():
        normalised = normalise_siruta(siruta)
        if normalised in locations:
            duplicate_sirutas.append(normalised)
        locations[normalised] = {
            "latitude": finite_float(location["latitude"], f"{normalised}.latitude"),
            "longitude": finite_float(location["longitude"], f"{normalised}.longitude"),
        }
    if duplicate_sirutas:
        listed = ", ".join(sorted(set(duplicate_sirutas))[:10])
        raise ValueError(f"transport row locations have duplicate SIRUTA rows: {listed}")
    return locations


def straight_line_metres(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Haversine distance in metres between two WGS84 points."""
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    hav = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_METRES * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def nearest_health_point(
    location: dict[str, float],
    points: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    best_point = points[0]
    best_metres = math.inf
    for point in points:
        metres = straight_line_metres(
            location["latitude"],
            location["longitude"],
            point["latitude"],
            point["longitude"],
        )
        if metres < best_metres:
            best_point = point
            best_metres = metres
    return best_point, int(round(best_metres))


def median_int(values: list[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return int(round((ordered[middle - 1] + ordered[middle]) / 2))


def population_weighted_median_int(rows: list[dict[str, Any]], field: str) -> int:
    weighted = [
        (int(row[field]), int(row.get("population", 0)))
        for row in rows
        if row.get(field) is not None and int(row.get("population", 0)) > 0
    ]
    if not weighted:
        return median_int([int(row[field]) for row in rows if row.get(field) is not None])
    total = sum(population for _, population in weighted)
    running = 0
    for value, population in sorted(weighted):
        running += population
        if running >= total / 2:
            return value
    return weighted[-1][0]


def health_access_limitation(access: dict[str, Any]) -> dict[str, Any]:
    blocked = int(access["summary"]["blockedProviders"])
    return {
        "id": HEALTH_ACCESS_LIMITATION_ID,
        "text": (
            "Accesul la sănătate vine din vederea shared health_access, care numără doar "
            "furnizorii serviceAccessEligible. Rândurile transportului păstrează numai "
            "UAT-urile rutate de modelul de transport, deci totalul local de aici poate fi "
            "mai mic decât totalul național din pachet. "
            f"{blocked} furnizori cu localizare doar la nivel de județ rămân excluși nominal "
            "și nu sunt tratați ca furnizori locali sau ca distanță zero."
        ),
        "severity": "material",
        "affects": ["access"],
    }


def health_point_access_limitation(point_access: dict[str, Any]) -> dict[str, Any]:
    providers = int(point_access["summary"]["pointAccessProviders"])
    blocked = int(point_access["summary"]["pointAccessBlockedProviders"])
    return {
        "id": HEALTH_POINT_ACCESS_LIMITATION_ID,
        "text": (
            "Accesul punctual la sănătate folosește vederea health-point-access-2024-2026: "
            f"{providers} furnizori cu coordonate acceptate. Distanța din transport este "
            "în linie dreaptă de la centroidul UAT la coordonata furnizorului, nu timp rutier "
            "și nu timp cu transport public. "
            f"{blocked} furnizori fără punct acceptat rămân excluși nominal din calculul "
            "celui mai apropiat furnizor."
        ),
        "severity": "material",
        "affects": ["access"],
    }


def health_point_road_access_limitation(point_road_access: dict[str, Any]) -> dict[str, Any]:
    summary = point_road_access["summary"]
    providers = int(summary["providers"])
    blocked = int(summary["pointAccessBlockedProviders"])
    distance_method = summary["distanceMethod"]
    snap_method = summary["providerSnapMethod"]
    routing_method = summary["routingMethod"]
    return {
        "id": HEALTH_POINT_ROAD_ACCESS_LIMITATION_ID,
        "text": (
            "Accesul punctual rutat-proxy la sănătate folosește vederea "
            f"{HEALTH_POINT_ROAD_ACCESS_VIEW_ID}: {providers} furnizori cu punct acceptat sunt "
            f"atașați la noduri UAT prin {snap_method}, apoi rutați cu {routing_method}. "
            f"Distanța publicată este {distance_method}; furnizorul nu devine nod de drum și "
            f"{blocked} furnizori fără punct acceptat rămân excluși nominal."
        ),
        "severity": "material",
        "affects": ["access"],
    }


def health_point_provenance(
    provenance: dict[str, Any],
    *,
    with_road_access: bool = False,
) -> dict[str, Any]:
    out = deepcopy(provenance)
    locator = out.get("locator")
    point_locator = "health-point-access-2024-2026 cu distanță straight-line de la centroidul UAT"
    road_locator = (
        "health-point-road-access-uat-2024-2026 cu distanță "
        "road-graph-to-snap-node-plus-straight-line-offset"
    )
    if isinstance(locator, str):
        if HEALTH_POINT_ACCESS_VIEW_ID not in locator:
            out["locator"] = f"{locator}; {point_locator}"
    else:
        out["locator"] = point_locator
    if with_road_access and HEALTH_POINT_ROAD_ACCESS_VIEW_ID not in out["locator"]:
        out["locator"] = f"{out['locator']}; {road_locator}"

    note = out.get("note")
    point_note = (
        "Cel mai apropiat punct de sănătate este calculat separat, în linie dreaptă, "
        "de la centroidul UAT la coordonata furnizorului acceptat."
    )
    road_note = (
        "Metricul rutat-proxy folosește vederea shared point-to-road și păstrează distanța "
        "în linie dreaptă doar ca termen de comparație."
    )
    if isinstance(note, str):
        if "Cel mai apropiat punct de sănătate" not in note:
            out["note"] = f"{note} {point_note}"
    else:
        out["note"] = point_note
    if with_road_access and "Metricul rutat-proxy" not in out["note"]:
        out["note"] = f"{out['note']} {road_note}"
    return out


def enrich_access_document(
    document: dict[str, Any],
    access: dict[str, Any],
    point_access: dict[str, Any] | None = None,
    row_locations: dict[str, dict[str, float]] | None = None,
    point_road_access: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if access["id"] != HEALTH_ACCESS_VIEW_ID:
        raise ValueError(f"expected {HEALTH_ACCESS_VIEW_ID}, got {access['id']}")
    with_point_access = point_access is not None or row_locations is not None
    if with_point_access and (point_access is None or row_locations is None):
        raise ValueError("point health-access enrichment needs both point_access and row_locations")
    with_road_access = point_road_access is not None
    if with_road_access and point_access is None:
        raise ValueError(
            "point road health-access enrichment needs point_access to verify accepted providers"
        )

    units = health_units_by_siruta(access)
    points = health_points(point_access) if point_access is not None else []
    point_ids = {point["providerId"] for point in points}
    road_points = (
        health_point_road_access(point_road_access, point_ids)
        if point_road_access is not None
        else {}
    )
    if point_road_access is not None and point_access is not None:
        point_summary = point_access["summary"]
        road_summary = point_road_access["summary"]
        if int(road_summary["providers"]) != int(point_summary["pointAccessProviders"]):
            raise ValueError("point road provider count does not match point-access summary")
        if int(road_summary["pointAccessBlockedProviders"]) != int(
            point_summary["pointAccessBlockedProviders"]
        ):
            raise ValueError(
                "point road blocked-provider count does not match point-access summary"
            )
        if int(road_summary["pointAccessNamedExclusions"]) != int(point_summary["namedExclusions"]):
            raise ValueError("point road named-exclusion count does not match point-access summary")
    locations = normalise_row_locations(row_locations) if row_locations is not None else {}
    seen_rows: set[str] = set()
    duplicate_rows = []
    missing = []
    missing_locations = []
    missing_road_points = []
    enriched_rows: list[dict[str, Any]] = []

    for row in document["uats"]:
        siruta = normalise_siruta(row["siruta"])
        if siruta in seen_rows:
            duplicate_rows.append(siruta)
        seen_rows.add(siruta)

        out = dict(row)
        if with_point_access:
            for field in HEALTH_POINT_ROW_FIELDS:
                out.pop(field, None)
        if with_road_access:
            for field in HEALTH_POINT_ROAD_ROW_FIELDS:
                out.pop(field, None)
        unit = units.get(siruta)
        if unit is None:
            if row.get("county") == BUCHAREST:
                out.update(
                    {
                        "hasLocalHealthProvider": None,
                        "localHealthProviderCount": None,
                        "localHealthClinicalBedProviders": None,
                        "localHealthClinicalBeds": None,
                        "healthAccessSectorRowExcluded": True,
                    }
                )
            else:
                missing.append(siruta)
                continue
        else:
            out.update(
                {
                    "hasLocalHealthProvider": bool(unit["hasLocalProvider"]),
                    "localHealthProviderCount": int(unit["localProviderCount"]),
                    "localHealthClinicalBedProviders": int(unit["localClinicalBedProviders"]),
                    "localHealthClinicalBeds": round(float(unit["localClinicalBeds"]), 2),
                    "healthAccessSectorRowExcluded": False,
                }
            )

        if with_point_access:
            location = locations.get(siruta)
            if location is None:
                missing_locations.append(siruta)
            else:
                point, distance_metres = nearest_health_point(location, points)
                out.update(
                    {
                        "nearestHealthPointProviderId": point["providerId"],
                        "nearestHealthPointDistanceMetres": distance_metres,
                    }
                )
        if with_road_access:
            road_point = road_points.get(siruta)
            if road_point is None:
                missing_road_points.append(siruta)
            else:
                out.update(
                    {
                        "nearestHealthPointRoadProviderId": road_point["nearestProviderId"],
                        "nearestHealthPointRoadProxyMetres": road_point["roadProxyMetres"],
                    }
                )
        enriched_rows.append(out)

    if duplicate_rows:
        listed = ", ".join(sorted(set(duplicate_rows))[:10])
        raise ValueError(f"transport access has duplicate SIRUTA rows: {listed}")
    if missing:
        listed = ", ".join(missing[:10])
        raise ValueError(f"shared health-access view is missing transport UAT rows: {listed}")
    if missing_locations:
        listed = ", ".join(missing_locations[:10])
        raise ValueError(f"point health-access is missing transport UAT row locations: {listed}")
    if missing_road_points:
        listed = ", ".join(missing_road_points[:10])
        raise ValueError(f"point road health-access is missing transport UAT rows: {listed}")

    rows_with_data = [row for row in enriched_rows if row["localHealthProviderCount"] is not None]
    summary = {
        **document["summary"],
        "healthAccessView": access["id"],
        "healthAccessEligibleProviders": int(access["summary"]["eligibleProviders"]),
        "healthAccessBlockedProviders": int(access["summary"]["blockedProviders"]),
        "healthAccessNamedExclusions": int(access["summary"]["namedExclusions"]),
        "healthAccessRowsWithData": len(rows_with_data),
        "healthAccessUatsWithLocalProvider": sum(
            1 for row in rows_with_data if row["hasLocalHealthProvider"] is True
        ),
        "healthAccessLocalProviders": sum(
            row["localHealthProviderCount"] for row in rows_with_data
        ),
        "healthAccessLocalClinicalBedProviders": sum(
            row["localHealthClinicalBedProviders"] for row in rows_with_data
        ),
        "healthAccessLocalClinicalBeds": round(
            sum(row["localHealthClinicalBeds"] for row in rows_with_data),
            2,
        ),
        "healthAccessSectorRowsExcluded": sum(
            1 for row in enriched_rows if row["healthAccessSectorRowExcluded"]
        ),
    }
    if with_point_access and point_access is not None:
        rows_with_distance = [
            row for row in enriched_rows if row.get("nearestHealthPointDistanceMetres") is not None
        ]
        distances = [int(row["nearestHealthPointDistanceMetres"]) for row in rows_with_distance]
        summary.update(
            {
                "healthPointAccessView": point_access["id"],
                "healthPointAccessProviders": int(point_access["summary"]["pointAccessProviders"]),
                "healthPointAccessBlockedProviders": int(
                    point_access["summary"]["pointAccessBlockedProviders"]
                ),
                "healthPointAccessNamedExclusions": int(point_access["summary"]["namedExclusions"]),
                "healthPointAccessRowsWithDistance": len(rows_with_distance),
                "healthPointAccessDistanceMethod": HEALTH_POINT_DISTANCE_METHOD,
                "healthPointAccessMedianNearestMetres": median_int(distances),
                "healthPointAccessPopulationWeightedMedianNearestMetres": (
                    population_weighted_median_int(
                        rows_with_distance,
                        "nearestHealthPointDistanceMetres",
                    )
                ),
            }
        )
    if with_road_access and point_road_access is not None:
        rows_with_road_distance = [
            row for row in enriched_rows if row.get("nearestHealthPointRoadProxyMetres") is not None
        ]
        road_distances = [
            int(row["nearestHealthPointRoadProxyMetres"]) for row in rows_with_road_distance
        ]
        if not road_distances:
            raise ValueError("point road health-access produced no transport distances")
        road_summary = point_road_access["summary"]
        summary.update(
            {
                "healthPointRoadAccessView": point_road_access["id"],
                "healthPointRoadAccessSourceRows": int(road_summary["uats"]),
                "healthPointRoadAccessProviders": int(road_summary["providers"]),
                "healthPointRoadAccessBlockedProviders": int(
                    road_summary["pointAccessBlockedProviders"]
                ),
                "healthPointRoadAccessNamedExclusions": int(
                    road_summary["pointAccessNamedExclusions"]
                ),
                "healthPointRoadAccessRowsWithDistance": len(rows_with_road_distance),
                "healthPointRoadAccessDistanceMethod": road_summary["distanceMethod"],
                "healthPointRoadAccessProviderSnapMethod": road_summary["providerSnapMethod"],
                "healthPointRoadAccessRoutingMethod": road_summary["routingMethod"],
                "healthPointRoadAccessMedianNearestMetres": median_int(road_distances),
                "healthPointRoadAccessPopulationWeightedMedianNearestMetres": (
                    population_weighted_median_int(
                        rows_with_road_distance,
                        "nearestHealthPointRoadProxyMetres",
                    )
                ),
            }
        )

    replacement_limitations = {HEALTH_ACCESS_LIMITATION_ID}
    if with_point_access:
        replacement_limitations.add(HEALTH_POINT_ACCESS_LIMITATION_ID)
    if with_road_access:
        replacement_limitations.add(HEALTH_POINT_ROAD_ACCESS_LIMITATION_ID)
    limitations = [
        limitation
        for limitation in document["limitations"]
        if limitation["id"] not in replacement_limitations
    ]
    limitations.append(health_access_limitation(access))
    if with_point_access and point_access is not None:
        limitations.append(health_point_access_limitation(point_access))
    if with_road_access and point_road_access is not None:
        limitations.append(health_point_road_access_limitation(point_road_access))

    enriched = deepcopy(document)
    enriched["summary"] = summary
    enriched["uats"] = enriched_rows
    enriched["limitations"] = limitations
    if with_point_access or with_road_access:
        enriched["provenance"] = health_point_provenance(
            document["provenance"],
            with_road_access=with_road_access,
        )
    return enriched

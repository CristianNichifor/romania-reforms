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

BUCHAREST: Final[str] = "B"
HEALTH_ACCESS_VIEW_ID: Final[str] = "health-service-access-uat-2024-2026"
HEALTH_ACCESS_LIMITATION_ID: Final[str] = "sanatatea-vine-din-pachetul-shared"
HEALTH_POINT_ACCESS_VIEW_ID: Final[str] = "health-point-access-2024-2026"
HEALTH_POINT_ACCESS_LIMITATION_ID: Final[str] = "sanatatea-punctuala-in-linie-dreapta"
HEALTH_POINT_DISTANCE_METHOD: Final[str] = "straight-line"
HEALTH_POINT_ROW_FIELDS: Final[tuple[str, ...]] = (
    "nearestHealthPointProviderId",
    "nearestHealthPointName",
    "nearestHealthPointCounty",
    "nearestHealthPointDistanceMetres",
    "nearestHealthPointDistanceMethod",
    "nearestHealthPointClinicalBeds",
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


def health_point_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(provenance)
    locator = out.get("locator")
    point_locator = "health-point-access-2024-2026 cu distanță straight-line de la centroidul UAT"
    if isinstance(locator, str):
        if HEALTH_POINT_ACCESS_VIEW_ID not in locator:
            out["locator"] = f"{locator}; {point_locator}"
    else:
        out["locator"] = point_locator

    note = out.get("note")
    point_note = (
        "Cel mai apropiat punct de sănătate este calculat separat, în linie dreaptă, "
        "de la centroidul UAT la coordonata furnizorului acceptat."
    )
    if isinstance(note, str):
        if "Cel mai apropiat punct de sănătate" not in note:
            out["note"] = f"{note} {point_note}"
    else:
        out["note"] = point_note
    return out


def enrich_access_document(
    document: dict[str, Any],
    access: dict[str, Any],
    point_access: dict[str, Any] | None = None,
    row_locations: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    if access["id"] != HEALTH_ACCESS_VIEW_ID:
        raise ValueError(f"expected {HEALTH_ACCESS_VIEW_ID}, got {access['id']}")
    with_point_access = point_access is not None or row_locations is not None
    if with_point_access and (point_access is None or row_locations is None):
        raise ValueError("point health-access enrichment needs both point_access and row_locations")

    units = health_units_by_siruta(access)
    points = health_points(point_access) if point_access is not None else []
    locations = normalise_row_locations(row_locations) if row_locations is not None else {}
    seen_rows: set[str] = set()
    duplicate_rows = []
    missing = []
    missing_locations = []
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

    replacement_limitations = {HEALTH_ACCESS_LIMITATION_ID}
    if with_point_access:
        replacement_limitations.add(HEALTH_POINT_ACCESS_LIMITATION_ID)
    limitations = [
        limitation
        for limitation in document["limitations"]
        if limitation["id"] not in replacement_limitations
    ]
    limitations.append(health_access_limitation(access))
    if with_point_access and point_access is not None:
        limitations.append(health_point_access_limitation(point_access))

    enriched = deepcopy(document)
    enriched["summary"] = summary
    enriched["uats"] = enriched_rows
    enriched["limitations"] = limitations
    if with_point_access:
        enriched["provenance"] = health_point_provenance(document["provenance"])
    return enriched

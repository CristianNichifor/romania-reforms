"""Attach the shared health-access UAT view to transport access rows.

Transport publishes access only for UATs that its road model can route to a centre. The shared
health view is broader, so the summary here keeps both counts visible: national source totals
from `packages/health_access`, and local-provider counts on transport's own routed rows.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Final

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_HEALTH_ACCESS: Final[Path] = (
    REPO_ROOT / "packages/health_access/data/health-service-access-uat-2024-2026.json"
)

BUCHAREST: Final[str] = "B"
HEALTH_ACCESS_VIEW_ID: Final[str] = "health-service-access-uat-2024-2026"
HEALTH_ACCESS_LIMITATION_ID: Final[str] = "sanatatea-vine-din-pachetul-shared"


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


def enrich_access_document(document: dict[str, Any], access: dict[str, Any]) -> dict[str, Any]:
    if access["id"] != HEALTH_ACCESS_VIEW_ID:
        raise ValueError(f"expected {HEALTH_ACCESS_VIEW_ID}, got {access['id']}")

    units = health_units_by_siruta(access)
    seen_rows: set[str] = set()
    duplicate_rows = []
    missing = []
    enriched_rows: list[dict[str, Any]] = []

    for row in document["uats"]:
        siruta = normalise_siruta(row["siruta"])
        if siruta in seen_rows:
            duplicate_rows.append(siruta)
        seen_rows.add(siruta)

        out = dict(row)
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
                enriched_rows.append(out)
                continue
            missing.append(siruta)
            continue

        out.update(
            {
                "hasLocalHealthProvider": bool(unit["hasLocalProvider"]),
                "localHealthProviderCount": int(unit["localProviderCount"]),
                "localHealthClinicalBedProviders": int(unit["localClinicalBedProviders"]),
                "localHealthClinicalBeds": round(float(unit["localClinicalBeds"]), 2),
                "healthAccessSectorRowExcluded": False,
            }
        )
        enriched_rows.append(out)

    if duplicate_rows:
        listed = ", ".join(sorted(set(duplicate_rows))[:10])
        raise ValueError(f"transport access has duplicate SIRUTA rows: {listed}")
    if missing:
        listed = ", ".join(missing[:10])
        raise ValueError(f"shared health-access view is missing transport UAT rows: {listed}")

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

    limitations = [
        limitation
        for limitation in document["limitations"]
        if limitation["id"] != HEALTH_ACCESS_LIMITATION_ID
    ]
    limitations.append(health_access_limitation(access))

    enriched = deepcopy(document)
    enriched["summary"] = summary
    enriched["uats"] = enriched_rows
    enriched["limitations"] = limitations
    return enriched

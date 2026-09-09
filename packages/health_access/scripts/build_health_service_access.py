"""Build UAT-level health service access views from the shared health mart.

The view is intentionally conservative: only providers marked serviceAccessEligible
in the health mart are counted in UAT rows. County-only providers stay named in
exclusions so consumers cannot accidentally treat them as local providers.

Usage:
    uv run python packages/health_access/scripts/build_health_service_access.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Final

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HEALTH_MART = PACKAGE_ROOT / "data/health-access-mart-2024-2025.json"
UAT_REGISTRY = REPO_ROOT / "packages/uat_registry/data/uat-registry-2026.json"
ACCESS_VIEW_ID: Final[str] = "health-service-access-uat-2024-2026"
OUT = PACKAGE_ROOT / f"data/{ACCESS_VIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 1
LOCAL_ACCESS_LEVELS: Final[set[str]] = {"municipality", "town", "commune"}
OWNER_TYPES: Final[tuple[str, ...]] = ("public", "private", "unknown")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def owner_counts(providers: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(provider.get("ownerType", "unknown") for provider in providers)
    return {owner_type: counts[owner_type] for owner_type in OWNER_TYPES}


def provider_summary(provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "providerId": provider["providerId"],
        "name": provider["name"],
        "ownerType": provider["ownerType"],
        "bedCount": provider["bedCount"],
        "specialties": provider["specialties"],
        "accreditationCategory": provider["accreditationCategory"],
        "locationConfidence": provider["locationConfidence"],
    }


def county_name_index(registry: dict[str, Any], health_mart: dict[str, Any]) -> dict[str, str]:
    names = {
        row["countyCode"]: row["countyName"]
        for row in health_mart["summary"]["byCounty"]
        if row.get("countyCode") and row.get("countyName")
    }
    for unit in registry["units"]:
        if unit.get("level") == "county":
            names.setdefault(unit["countyCode"], unit["countyName"])
    return names


def build_document(
    health_mart: dict[str, Any],
    registry: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
) -> dict[str, Any]:
    records = health_mart["records"]
    eligible = [record for record in records if record["serviceAccessEligible"]]
    blocked = [record for record in records if not record["serviceAccessEligible"]]

    providers_by_siruta: dict[str, list[dict[str, Any]]] = defaultdict(list)
    eligible_by_county: Counter[str] = Counter()
    blocked_by_county: Counter[str] = Counter(record["countyCode"] for record in blocked)
    eligible_with_beds_by_county: Counter[str] = Counter()
    eligible_beds_by_county: dict[str, float] = defaultdict(float)

    for provider in eligible:
        providers_by_siruta[provider["siruta"]].append(provider)
        eligible_by_county[provider["countyCode"]] += 1
        if provider["bedCount"] is not None:
            eligible_with_beds_by_county[provider["countyCode"]] += 1
            eligible_beds_by_county[provider["countyCode"]] += provider["bedCount"]

    for providers in providers_by_siruta.values():
        providers.sort(key=lambda provider: provider["providerId"])

    scope_counties = health_mart["summary"]["scopeCounties"]
    county_names = county_name_index(registry, health_mart)
    by_county: dict[str, dict[str, Any]] = {
        county_code: {
            "countyCode": county_code,
            "countyName": county_names.get(county_code, county_code),
            "uats": 0,
            "uatsWithLocalProvider": 0,
            "population": 0,
            "populationWithLocalProvider": 0,
            "eligibleProviders": eligible_by_county[county_code],
            "blockedProviders": blocked_by_county[county_code],
            "eligibleProvidersWithClinicalBeds": eligible_with_beds_by_county[county_code],
            "eligibleProviderLevelClinicalBeds": round(eligible_beds_by_county[county_code], 2),
        }
        for county_code in scope_counties
    }

    units: list[dict[str, Any]] = []
    excluded_sector_rows = 0
    for unit in registry["units"]:
        level = unit["level"]
        if level == "sector":
            excluded_sector_rows += 1
            continue
        if level not in LOCAL_ACCESS_LEVELS:
            continue

        local_providers = providers_by_siruta.get(unit["siruta"], [])
        population = unit.get("population")
        population_value = population or 0
        has_local_provider = bool(local_providers)
        local_bed_count = round(sum(provider["bedCount"] or 0 for provider in local_providers), 2)
        local_specialties = sorted(
            {
                specialty
                for provider in local_providers
                for specialty in provider.get("specialties", [])
            }
        )

        county = by_county[unit["countyCode"]]
        county["uats"] += 1
        county["population"] += population_value
        if has_local_provider:
            county["uatsWithLocalProvider"] += 1
            county["populationWithLocalProvider"] += population_value

        units.append(
            {
                "siruta": unit["siruta"],
                "name": unit["name"],
                "shortName": unit["shortName"],
                "level": level,
                "countyCode": unit["countyCode"],
                "countyName": unit["countyName"],
                "population": population,
                "populationSource": unit.get("populationSource"),
                "hasLocalProvider": has_local_provider,
                "localProviderCount": len(local_providers),
                "localClinicalBedProviders": sum(
                    1 for provider in local_providers if provider["bedCount"] is not None
                ),
                "localClinicalBeds": local_bed_count,
                "localOwnerTypes": owner_counts(local_providers),
                "localSpecialties": local_specialties,
                "localProviders": [provider_summary(provider) for provider in local_providers],
                "countyEligibleProviderCount": eligible_by_county[unit["countyCode"]],
                "countyBlockedProviderCount": blocked_by_county[unit["countyCode"]],
            }
        )

    provider_ids_in_view = {
        provider["providerId"] for unit in units for provider in unit["localProviders"]
    }
    eligible_provider_ids = {provider["providerId"] for provider in eligible}
    missing_eligible = sorted(eligible_provider_ids - provider_ids_in_view)
    if missing_eligible:
        raise ValueError(
            "eligible providers missing from local UAT view: " + ", ".join(missing_eligible)
        )

    exclusions = [
        {
            "kind": "provider-excluded-from-service-access",
            "source": health_mart["id"],
            "providerId": provider["providerId"],
            "name": provider["name"],
            "countyCode": provider["countyCode"],
            "locationConfidence": provider["locationConfidence"],
            "reason": (
                "The provider has only county-level location evidence in the health mart "
                "and is blocked from UAT-level service-access calculations."
            ),
        }
        for provider in sorted(blocked, key=lambda provider: provider["providerId"])
    ]

    summary = {
        "uats": len(units),
        "uatsWithLocalProvider": sum(1 for unit in units if unit["hasLocalProvider"]),
        "population": sum(unit["population"] or 0 for unit in units),
        "populationWithLocalProvider": sum(
            unit["population"] or 0 for unit in units if unit["hasLocalProvider"]
        ),
        "eligibleProviders": len(eligible),
        "blockedProviders": len(blocked),
        "eligibleProvidersWithClinicalBeds": sum(
            1 for provider in eligible if provider["bedCount"] is not None
        ),
        "eligibleProviderLevelClinicalBeds": round(
            sum(provider["bedCount"] or 0 for provider in eligible), 2
        ),
        "namedExclusions": len(exclusions),
        "excludedSectorRows": excluded_sector_rows,
        "byCounty": [by_county[county_code] for county_code in scope_counties],
    }

    return {
        "$schema": "../schema/health-service-access.schema.json",
        "id": ACCESS_VIEW_ID,
        "title": "UAT-level health service access view",
        "publisher": "Ministerul Sanatatii / ANMCS / Institutul National de Statistica",
        "scope": "uat-level",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": f"{health_mart['id']} + {registry['id']}",
            "locator": (
                "health mart records filtered by serviceAccessEligible; "
                "UAT registry units filtered to municipality, town and commune levels"
            ),
            "confidence": "derived",
            "note": (
                "Counts are UAT co-location indicators, not routing or travel-time measures. "
                "County-only health providers are excluded and named separately."
            ),
        },
        "registry": {
            "healthMart": {
                "id": health_mart["id"],
                "periodStart": health_mart["periodStart"],
                "periodEnd": health_mart["periodEnd"],
            },
            "uatRegistry": {"id": registry["id"], "period": registry["period"]},
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": "packages/health_access/scripts/build_health_service_access.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "units": units,
        "exclusions": exclusions,
        "limitations": [
            limitation(
                "uat-colocation-not-travel-time",
                "material",
                ["hasLocalProvider", "localProviderCount", "populationWithLocalProvider"],
                (
                    "This view reports whether an eligible provider is located in the same UAT. "
                    "It does not estimate travel distance, travel time or cross-border access."
                ),
            ),
            limitation(
                "county-only-providers-excluded",
                "material",
                ["localProviderCount", "countyBlockedProviderCount", "exclusions"],
                (
                    "Providers without UAT-level location evidence are excluded from local "
                    "counts and kept as named exclusions."
                ),
            ),
            limitation(
                "bucharest-sectors-excluded",
                "material",
                ["units", "population"],
                (
                    "Bucharest sector rows are not included because the health mart can only "
                    "place Bucharest providers at municipality level."
                ),
            ),
            limitation(
                "provider-beds-partial",
                "note",
                ["localClinicalBeds", "eligibleProviderLevelClinicalBeds"],
                (
                    "Provider-level bed counts exist only for health mart rows matched "
                    "confidently to the Ministry clinical-beds workbook."
                ),
            ),
        ],
    }


def build_from_files(
    health_mart_path: Path,
    registry_path: Path,
    retrieved_date: str,
) -> dict[str, Any]:
    health_mart = json.loads(health_mart_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return build_document(
        health_mart,
        registry,
        {
            "healthAccessMartSha256": sha256_file(health_mart_path),
            "uatRegistrySha256": sha256_file(registry_path),
        },
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-mart", type=Path, default=HEALTH_MART)
    parser.add_argument("--uat-registry", type=Path, default=UAT_REGISTRY)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    document = build_from_files(args.health_mart, args.uat_registry, args.retrieved_date)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['uats']} UATs and "
        f"{document['summary']['eligibleProviders']} eligible providers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

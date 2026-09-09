"""Build provider-level health point evidence from the shared health mart.

The first point-evidence slice is deliberately conservative: it carries every
provider from the health mart, but blocks all providers from point routing until
street-address or coordinate evidence is imported.

Usage:
    uv run python packages/health_access/scripts/build_health_provider_points.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HEALTH_MART = PACKAGE_ROOT / "data/health-access-mart-2024-2025.json"
POINT_VIEW_ID: Final[str] = "health-provider-points-2024-2026"
OUT = PACKAGE_ROOT / f"data/{POINT_VIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 1


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def none_address_evidence() -> dict[str, Any]:
    return {"method": "none", "source": None, "sourceValue": None, "retrievedDate": None}


def none_point_evidence() -> dict[str, Any]:
    return {"method": "none", "source": None, "sourceValue": None, "retrievedDate": None}


def point_access_blocked_reason(provider: dict[str, Any]) -> str:
    if provider["locationConfidence"] == "county-only":
        return "county-only-location"
    return "no-point-evidence"


def provider_point(provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "providerId": provider["providerId"],
        "name": provider["name"],
        "countyCode": provider["countyCode"],
        "countyName": provider["countyName"],
        "siruta": provider["siruta"],
        "localityName": provider["localityName"],
        "locationConfidence": provider["locationConfidence"],
        "serviceAccessEligible": bool(provider["serviceAccessEligible"]),
        "address": None,
        "addressEvidence": none_address_evidence(),
        "latitude": None,
        "longitude": None,
        "pointConfidence": "none",
        "pointEvidence": none_point_evidence(),
        "pointAccessEligible": False,
        "pointAccessBlockedReason": point_access_blocked_reason(provider),
    }


def exclusion(provider: dict[str, Any], source: str) -> dict[str, Any]:
    reason = provider["pointAccessBlockedReason"]
    if reason == "county-only-location":
        text = (
            "The provider has only county-level location evidence in the health mart, "
            "so it is blocked from point-level routing until address or coordinate "
            "evidence is attached."
        )
    else:
        text = (
            "The provider has UAT-level service-access evidence but no street-address "
            "or coordinate evidence, so it is blocked from point-level routing."
        )
    return {
        "kind": "provider-excluded-from-point-access",
        "source": source,
        "providerId": provider["providerId"],
        "name": provider["name"],
        "countyCode": provider["countyCode"],
        "pointAccessBlockedReason": reason,
        "reason": text,
    }


def routeable_point_providers(document: dict[str, Any]) -> list[dict[str, Any]]:
    routeable = []
    for provider in document["providers"]:
        if not provider["pointAccessEligible"]:
            continue
        if provider["latitude"] is None or provider["longitude"] is None:
            raise ValueError(
                "pointAccessEligible provider has no coordinates: "
                f"{provider['providerId']}"
            )
        routeable.append(provider)
    return routeable


def county_name_index(health_mart: dict[str, Any]) -> dict[str, str]:
    return {
        row["countyCode"]: row["countyName"]
        for row in health_mart["summary"]["byCounty"]
        if row.get("countyCode") and row.get("countyName")
    }


def by_county_summary(
    providers: list[dict[str, Any]],
    health_mart: dict[str, Any],
) -> list[dict[str, Any]]:
    by_county: dict[str, dict[str, int]] = {}
    for provider in providers:
        county_code = provider["countyCode"]
        row = by_county.setdefault(
            county_code,
            {
                "providers": 0,
                "serviceAccessEligibleProviders": 0,
                "pointAccessEligibleProviders": 0,
                "pointAccessBlockedProviders": 0,
            },
        )
        row["providers"] += 1
        if provider["serviceAccessEligible"]:
            row["serviceAccessEligibleProviders"] += 1
        if provider["pointAccessEligible"]:
            row["pointAccessEligibleProviders"] += 1
        else:
            row["pointAccessBlockedProviders"] += 1

    names = county_name_index(health_mart)
    return [
        {
            "countyCode": county_code,
            "countyName": names.get(county_code, county_code),
            **by_county.get(
                county_code,
                {
                    "providers": 0,
                    "serviceAccessEligibleProviders": 0,
                    "pointAccessEligibleProviders": 0,
                    "pointAccessBlockedProviders": 0,
                },
            ),
        }
        for county_code in health_mart["summary"]["scopeCounties"]
    ]


def assert_unique_provider_ids(records: list[dict[str, Any]]) -> None:
    counts = Counter(record["providerId"] for record in records)
    duplicates = sorted(provider_id for provider_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError("duplicate provider ids: " + ", ".join(duplicates))


def build_document(
    health_mart: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str | None = None,
) -> dict[str, Any]:
    records = health_mart["records"]
    assert_unique_provider_ids(records)

    providers = [provider_point(record) for record in records]
    point_access_eligible = [provider for provider in providers if provider["pointAccessEligible"]]
    point_access_blocked = [
        provider for provider in providers if not provider["pointAccessEligible"]
    ]
    service_access_eligible = [
        provider for provider in providers if provider["serviceAccessEligible"]
    ]

    summary = {
        "providers": len(providers),
        "serviceAccessEligibleProviders": len(service_access_eligible),
        "serviceAccessBlockedProviders": len(providers) - len(service_access_eligible),
        "pointAccessEligibleProviders": len(point_access_eligible),
        "pointAccessBlockedProviders": len(point_access_blocked),
        "providersWithAddress": sum(1 for provider in providers if provider["address"]),
        "providersWithCoordinates": sum(
            1
            for provider in providers
            if provider["latitude"] is not None and provider["longitude"] is not None
        ),
        "addressEvidence": count_by(
            [provider["addressEvidence"]["method"] for provider in providers]
        ),
        "pointConfidence": count_by([provider["pointConfidence"] for provider in providers]),
        "blockedReasons": count_by(
            [
                provider["pointAccessBlockedReason"]
                for provider in providers
                if provider["pointAccessBlockedReason"]
            ]
        ),
        "byCounty": by_county_summary(providers, health_mart),
    }

    return {
        "$schema": "../schema/health-provider-points.schema.json",
        "id": POINT_VIEW_ID,
        "title": "Provider-level health point evidence",
        "publisher": health_mart["publisher"],
        "scope": "provider-point-evidence",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date or health_mart["retrievedDate"],
        "provenance": {
            "source": health_mart["id"],
            "locator": (
                "provider rows from the shared health access mart; no address or "
                "coordinate source imported yet"
            ),
            "confidence": "derived",
            "note": (
                "This file is a point-evidence contract. The first version blocks "
                "every provider from point routing until explicit address or "
                "coordinate evidence is attached."
            ),
        },
        "registry": {
            "healthMart": {
                "id": health_mart["id"],
                "periodStart": health_mart["periodStart"],
                "periodEnd": health_mart["periodEnd"],
            }
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": "packages/health_access/scripts/build_health_provider_points.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "providers": providers,
        "exclusions": [
            exclusion(provider, health_mart["id"])
            for provider in providers
            if not provider["pointAccessEligible"]
        ],
        "limitations": [
            limitation(
                "point-evidence-not-yet-imported",
                "material",
                ["latitude", "longitude", "pointAccessEligible"],
                (
                    "This first point-evidence contract does not import provider "
                    "street addresses or coordinates, so every provider is blocked "
                    "from point-level routing."
                ),
            ),
            limitation(
                "county-only-not-promoted-to-points",
                "material",
                ["pointAccessEligible", "pointAccessBlockedReason"],
                (
                    "County-only health mart rows cannot become point-access "
                    "locations until provider-level address or coordinate evidence "
                    "exists."
                ),
            ),
            limitation(
                "bucharest-sector-needs-address-evidence",
                "material",
                ["siruta", "pointAccessEligible"],
                (
                    "Bucharest municipality-level providers are not assigned to "
                    "sectors without address evidence."
                ),
            ),
        ],
    }


def build_from_files(
    health_mart_path: Path,
    retrieved_date: str | None = None,
) -> dict[str, Any]:
    health_mart = json.loads(health_mart_path.read_text(encoding="utf-8"))
    return build_document(
        health_mart,
        {"healthAccessMartSha256": sha256_file(health_mart_path)},
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-mart", type=Path, default=HEALTH_MART)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date")
    args = parser.parse_args(argv)

    document = build_from_files(args.health_mart, args.retrieved_date)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['providers']} providers and "
        f"{document['summary']['pointAccessEligibleProviders']} point-eligible providers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build point-level health access view from accepted provider coordinates.

The view is intentionally a provider point layer, not a distance model. It
includes only providers marked pointAccessEligible in the provider-point
contract and names every blocked provider separately.

Usage:
    uv run python packages/health_access/scripts/build_health_point_access.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HEALTH_MART = PACKAGE_ROOT / "data/health-access-mart-2024-2025.json"
PROVIDER_POINTS = PACKAGE_ROOT / "data/health-provider-points-2024-2026.json"
ACCESS_VIEW_ID: Final[str] = "health-point-access-2024-2026"
OUT = PACKAGE_ROOT / f"data/{ACCESS_VIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 1
OWNER_TYPES: Final[tuple[str, ...]] = ("public", "private", "unknown")
SUPPORTED_CONSUMER_DISTANCE_METHODS: Final[tuple[str, ...]] = ("straight-line", "routed")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def mart_by_provider_id(health_mart: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index = {provider["providerId"]: provider for provider in health_mart["records"]}
    if len(index) != len(health_mart["records"]):
        counts = Counter(provider["providerId"] for provider in health_mart["records"])
        duplicates = sorted(provider_id for provider_id, count in counts.items() if count > 1)
        raise ValueError("duplicate health mart provider ids: " + ", ".join(duplicates))
    return index


def point_provider_summary(
    provider: dict[str, Any],
    health_provider: dict[str, Any],
) -> dict[str, Any]:
    if provider["latitude"] is None or provider["longitude"] is None:
        raise ValueError(
            "pointAccessEligible provider has no coordinates: "
            f"{provider['providerId']}"
        )
    if not provider["serviceAccessEligible"]:
        raise ValueError(
            f"pointAccessEligible provider is not serviceAccessEligible: {provider['providerId']}"
        )

    return {
        "providerId": provider["providerId"],
        "name": provider["name"],
        "countyCode": provider["countyCode"],
        "countyName": provider["countyName"],
        "siruta": provider["siruta"],
        "localityName": provider["localityName"],
        "locationConfidence": provider["locationConfidence"],
        "serviceAccessEligible": bool(provider["serviceAccessEligible"]),
        "address": provider["address"],
        "latitude": provider["latitude"],
        "longitude": provider["longitude"],
        "ownerType": health_provider["ownerType"],
        "bedCount": health_provider["bedCount"],
        "specialties": health_provider["specialties"],
        "accreditationCategory": health_provider["accreditationCategory"],
        "addressEvidence": provider["addressEvidence"],
        "pointConfidence": provider["pointConfidence"],
        "pointEvidence": provider["pointEvidence"],
        "accessUse": "eligible-for-point-level-access",
    }


def exclusion(provider: dict[str, Any], source: str) -> dict[str, Any]:
    reason = provider["pointAccessBlockedReason"]
    if reason == "county-only-location":
        text = (
            "The provider is blocked from point-level access because the health mart has "
            "only county-level location evidence for this row."
        )
    elif reason == "ambiguous-address":
        text = (
            "The provider is blocked from point-level access because the address source "
            "has multiple exact name/county candidates."
        )
    elif reason == "invalid-coordinate":
        text = (
            "The provider is blocked from point-level access because its coordinate "
            "candidate failed the automated bounds check."
        )
    elif reason == "outside-expected-uat":
        text = (
            "The provider is blocked from point-level access because its coordinate "
            "candidate failed the expected UAT consistency check."
        )
    elif reason == "manual-review-needed":
        text = (
            "The provider is blocked from point-level access because its coordinate "
            "candidate needs manual review."
        )
    else:
        text = (
            "The provider is blocked from point-level access because no accepted "
            "coordinate evidence is attached."
        )

    return {
        "kind": "provider-excluded-from-point-access",
        "source": source,
        "providerId": provider["providerId"],
        "name": provider["name"],
        "countyCode": provider["countyCode"],
        "serviceAccessEligible": bool(provider["serviceAccessEligible"]),
        "locationConfidence": provider["locationConfidence"],
        "hasAddress": provider["address"] is not None,
        "pointAccessBlockedReason": reason,
        "reason": text,
    }


def county_name_index(
    health_mart: dict[str, Any],
    provider_points: dict[str, Any],
) -> dict[str, str]:
    names = {
        row["countyCode"]: row["countyName"]
        for row in health_mart["summary"]["byCounty"]
        if row.get("countyCode") and row.get("countyName")
    }
    for row in provider_points["summary"]["byCounty"]:
        names.setdefault(row["countyCode"], row["countyName"])
    return names


def owner_counts(points: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(point.get("ownerType", "unknown") for point in points)
    return {owner_type: counts[owner_type] for owner_type in OWNER_TYPES}


def by_county_summary(
    points: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    health_mart: dict[str, Any],
    provider_points: dict[str, Any],
) -> list[dict[str, Any]]:
    points_by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exclusions_by_county: Counter[str] = Counter()
    for point in points:
        points_by_county[point["countyCode"]].append(point)
    for row in exclusions:
        exclusions_by_county[row["countyCode"]] += 1

    names = county_name_index(health_mart, provider_points)
    return [
        {
            "countyCode": county_code,
            "countyName": names.get(county_code, county_code),
            "pointAccessProviders": len(points_by_county[county_code]),
            "pointAccessBlockedProviders": exclusions_by_county[county_code],
            "providersWithClinicalBeds": sum(
                1 for point in points_by_county[county_code] if point["bedCount"] is not None
            ),
            "providerLevelClinicalBeds": round(
                sum(point["bedCount"] or 0 for point in points_by_county[county_code]),
                2,
            ),
            "ownerTypes": owner_counts(points_by_county[county_code]),
        }
        for county_code in health_mart["summary"]["scopeCounties"]
    ]


def build_document(
    provider_points: dict[str, Any],
    health_mart: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str,
) -> dict[str, Any]:
    mart_index = mart_by_provider_id(health_mart)
    unknown = sorted(
        provider["providerId"]
        for provider in provider_points["providers"]
        if provider["providerId"] not in mart_index
    )
    if unknown:
        raise ValueError("provider points missing from health mart: " + ", ".join(unknown[:10]))

    points = [
        point_provider_summary(provider, mart_index[provider["providerId"]])
        for provider in provider_points["providers"]
        if provider["pointAccessEligible"]
    ]
    exclusions = [
        exclusion(provider, provider_points["id"])
        for provider in provider_points["providers"]
        if not provider["pointAccessEligible"]
    ]

    source_point_ids = {
        provider["providerId"]
        for provider in provider_points["providers"]
        if provider["pointAccessEligible"]
    }
    view_point_ids = {provider["providerId"] for provider in points}
    if view_point_ids != source_point_ids:
        missing = sorted(source_point_ids - view_point_ids)
        raise ValueError("point-eligible providers missing from point view: " + ", ".join(missing))

    summary = {
        "providers": len(provider_points["providers"]),
        "pointAccessProviders": len(points),
        "pointAccessBlockedProviders": len(exclusions),
        "providersWithClinicalBeds": sum(1 for point in points if point["bedCount"] is not None),
        "providerLevelClinicalBeds": round(sum(point["bedCount"] or 0 for point in points), 2),
        "namedExclusions": len(exclusions),
        "distanceMethod": "not-computed",
        "consumerDistanceMethodRequired": True,
        "supportedConsumerDistanceMethods": list(SUPPORTED_CONSUMER_DISTANCE_METHODS),
        "pointConfidence": count_by([point["pointConfidence"] for point in points]),
        "pointEvidence": count_by([point["pointEvidence"]["method"] for point in points]),
        "blockedReasons": count_by(
            [
                row["pointAccessBlockedReason"]
                for row in exclusions
                if row["pointAccessBlockedReason"]
            ]
        ),
        "byCounty": by_county_summary(points, exclusions, health_mart, provider_points),
    }

    return {
        "$schema": "../schema/health-point-access.schema.json",
        "id": ACCESS_VIEW_ID,
        "title": "Point-level health access view",
        "publisher": "Ministerul Sanatatii / ANMCS",
        "scope": "provider-point-level",
        "periodStart": "2024",
        "periodEnd": "2026",
        "retrievedDate": retrieved_date,
        "provenance": {
            "source": f"{provider_points['id']} + {health_mart['id']}",
            "locator": (
                "provider-point contract rows filtered by pointAccessEligible and "
                "joined back to the health mart by providerId for provider attributes"
            ),
            "confidence": "derived",
            "note": (
                "This is a provider point layer. Consumers deriving distances from it "
                "must declare whether they use straight-line or routed distance."
            ),
        },
        "accessModel": {
            "kind": "provider-point-layer",
            "distanceMethod": "not-computed",
            "consumerDistanceMethodRequired": True,
            "supportedConsumerDistanceMethods": list(SUPPORTED_CONSUMER_DISTANCE_METHODS),
        },
        "registry": {
            "providerPoints": {
                "id": provider_points["id"],
                "periodStart": provider_points["periodStart"],
                "periodEnd": provider_points["periodEnd"],
            },
            "healthMart": {
                "id": health_mart["id"],
                "periodStart": health_mart["periodStart"],
                "periodEnd": health_mart["periodEnd"],
            },
        },
        "sourceHashes": source_hashes,
        "transform": {
            "script": "packages/health_access/scripts/build_health_point_access.py",
            "version": TRANSFORM_VERSION,
        },
        "summary": summary,
        "points": points,
        "exclusions": exclusions,
        "limitations": [
            limitation(
                "point-layer-not-distance-model",
                "material",
                ["accessModel", "summary.distanceMethod"],
                (
                    "This view publishes accepted provider coordinates only. It does "
                    "not calculate nearest-provider distance, travel time or catchments."
                ),
            ),
            limitation(
                "blocked-provider-rows-excluded",
                "material",
                ["points", "exclusions"],
                (
                    "Providers without pointAccessEligible true are excluded from the "
                    "point layer and kept as named exclusions, so consumers cannot treat "
                    "them as local or zero-distance access."
                ),
            ),
            limitation(
                "consumer-distance-method-must-be-declared",
                "material",
                ["accessModel.supportedConsumerDistanceMethods"],
                (
                    "Consumers that derive access from these points must state whether "
                    "they use straight-line distance or routed distance."
                ),
            ),
            limitation(
                "provider-beds-partial",
                "note",
                ["providerLevelClinicalBeds", "providersWithClinicalBeds"],
                (
                    "Provider-level bed counts exist only for health mart rows matched "
                    "confidently to the Ministry clinical-beds workbook."
                ),
            ),
        ],
    }


def build_from_files(
    provider_points_path: Path,
    health_mart_path: Path,
    retrieved_date: str,
) -> dict[str, Any]:
    provider_points = json.loads(provider_points_path.read_text(encoding="utf-8"))
    health_mart = json.loads(health_mart_path.read_text(encoding="utf-8"))
    return build_document(
        provider_points,
        health_mart,
        {
            "providerPointsSha256": sha256_file(provider_points_path),
            "healthAccessMartSha256": sha256_file(health_mart_path),
        },
        retrieved_date,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-points", type=Path, default=PROVIDER_POINTS)
    parser.add_argument("--health-mart", type=Path, default=HEALTH_MART)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    document = build_from_files(args.provider_points, args.health_mart, args.retrieved_date)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['pointAccessProviders']} "
        "point-access providers "
        f"and {document['summary']['namedExclusions']} exclusions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

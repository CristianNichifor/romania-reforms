"""Build provider-level health point evidence from the shared health mart.

This builder carries every provider from the health mart and attaches address
and coordinate evidence where the Ministry source can be matched safely.

Usage:
    uv run python packages/health_access/scripts/build_health_provider_points.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Final

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HEALTH_MART = PACKAGE_ROOT / "data/health-access-mart-2024-2025.json"
ADDRESS_SOURCE = PACKAGE_ROOT / "sources/ms-unitati-sanitare-2026.json"
POINT_VIEW_ID: Final[str] = "health-provider-points-2024-2026"
OUT = PACKAGE_ROOT / f"data/{POINT_VIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 3
ROMANIA_LATITUDE_RANGE: Final[tuple[float, float]] = (43.0, 49.0)
ROMANIA_LONGITUDE_RANGE: Final[tuple[float, float]] = (20.0, 30.0)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict[str, Any]:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def normalise_text(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def none_address_evidence() -> dict[str, Any]:
    return {"method": "none", "source": None, "sourceValue": None, "retrievedDate": None}


def none_point_evidence() -> dict[str, Any]:
    return {"method": "none", "source": None, "sourceValue": None, "retrievedDate": None}


def point_access_blocked_reason(
    provider: dict[str, Any],
    address_match_status: str | None,
    source_record: dict[str, Any] | None = None,
) -> str:
    if address_match_status == "ambiguous":
        return "ambiguous-address"
    if provider["locationConfidence"] == "county-only":
        return "county-only-location"
    if source_record and has_published_coordinate(source_record):
        if not coordinate_in_romania(
            source_record["latitude"],
            source_record["longitude"],
        ):
            return "invalid-coordinate"
        if source_record.get("countyCode") != provider["countyCode"]:
            return "manual-review-needed"
        if not provider["serviceAccessEligible"]:
            return "manual-review-needed"
    return "no-point-evidence"


def address_evidence(
    address_source: dict[str, Any],
    source_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "method": "official-provider-address",
        "source": address_source["id"],
        "sourceValue": source_record["address"],
        "retrievedDate": address_source["retrievedDate"],
    }


def has_published_coordinate(source_record: dict[str, Any]) -> bool:
    return bool(
        source_record.get("hasPublishedCoordinate")
        and source_record.get("latitude") is not None
        and source_record.get("longitude") is not None
    )


def coordinate_in_romania(latitude: float, longitude: float) -> bool:
    return (
        ROMANIA_LATITUDE_RANGE[0] <= latitude <= ROMANIA_LATITUDE_RANGE[1]
        and ROMANIA_LONGITUDE_RANGE[0] <= longitude <= ROMANIA_LONGITUDE_RANGE[1]
    )


def accepted_coordinate(
    provider: dict[str, Any],
    source_record: dict[str, Any] | None,
) -> tuple[float, float] | None:
    if not source_record or not has_published_coordinate(source_record):
        return None
    if not provider["serviceAccessEligible"]:
        return None
    if provider["locationConfidence"] == "county-only":
        return None
    if source_record.get("countyCode") != provider["countyCode"]:
        return None

    latitude = source_record["latitude"]
    longitude = source_record["longitude"]
    if not coordinate_in_romania(latitude, longitude):
        return None
    return latitude, longitude


def coordinate_evidence(
    address_source: dict[str, Any],
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    return {
        "method": "published-coordinate",
        "source": address_source["id"],
        "sourceValue": f"{latitude:.6f},{longitude:.6f}",
        "retrievedDate": address_source["retrievedDate"],
    }


def provider_point(
    provider: dict[str, Any],
    address_source: dict[str, Any] | None,
    source_record: dict[str, Any] | None,
    address_match_status: str | None,
) -> dict[str, Any]:
    coordinate = accepted_coordinate(provider, source_record)
    point_access_eligible = coordinate is not None
    latitude, longitude = coordinate if coordinate else (None, None)
    return {
        "providerId": provider["providerId"],
        "name": provider["name"],
        "countyCode": provider["countyCode"],
        "countyName": provider["countyName"],
        "siruta": provider["siruta"],
        "localityName": provider["localityName"],
        "locationConfidence": provider["locationConfidence"],
        "serviceAccessEligible": bool(provider["serviceAccessEligible"]),
        "address": source_record["address"] if source_record else None,
        "addressEvidence": (
            address_evidence(address_source, source_record)
            if address_source and source_record
            else none_address_evidence()
        ),
        "latitude": latitude,
        "longitude": longitude,
        "pointConfidence": "official-coordinate" if coordinate else "none",
        "pointEvidence": (
            coordinate_evidence(address_source, latitude, longitude)
            if address_source and coordinate
            else none_point_evidence()
        ),
        "pointAccessEligible": point_access_eligible,
        "pointAccessBlockedReason": (
            None
            if point_access_eligible
            else point_access_blocked_reason(provider, address_match_status, source_record)
        ),
    }


def exclusion(provider: dict[str, Any], source: str) -> dict[str, Any]:
    reason = provider["pointAccessBlockedReason"]
    if reason == "ambiguous-address":
        text = (
            "The provider has multiple exact name/county address candidates in the "
            "address source, so it is blocked from point-level routing until the "
            "address is reviewed."
        )
    elif reason == "county-only-location":
        text = (
            "The provider has only county-level location evidence in the health mart, "
            "so it is blocked from point-level routing until provider- or UAT-level "
            "location evidence is attached."
        )
    elif reason == "invalid-coordinate":
        text = (
            "The provider has a published coordinate candidate outside the accepted "
            "Romania bounds, so it is blocked from point-level routing until reviewed."
        )
    elif reason == "manual-review-needed":
        text = (
            "The provider has coordinate evidence that does not satisfy the automated "
            "acceptance checks, so it is blocked from point-level routing until reviewed."
        )
    elif provider["address"]:
        text = (
            "The provider has official address evidence but no accepted coordinate "
            "evidence, so it is blocked from point-level routing."
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


def address_match_index(
    address_source: dict[str, Any] | None,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not address_source:
        return {}

    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in address_source["records"]:
        county_code = record.get("countyCode")
        if not county_code or not record.get("hasStreetAddress"):
            continue
        key = (normalise_text(record["name"]), county_code)
        index.setdefault(key, []).append(record)
    return index


def match_address_record(
    provider: dict[str, Any],
    index: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str | None]:
    matches = index.get((normalise_text(provider["name"]), provider["countyCode"]), [])
    if len(matches) == 1:
        return matches[0], "matched"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, None


def build_document(
    health_mart: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str | None = None,
    address_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = health_mart["records"]
    assert_unique_provider_ids(records)

    address_index = address_match_index(address_source)
    address_match_status_by_provider: dict[str, str] = {}
    providers = []
    for record in records:
        source_record, match_status = match_address_record(record, address_index)
        if match_status:
            address_match_status_by_provider[record["providerId"]] = match_status
        providers.append(provider_point(record, address_source, source_record, match_status))

    point_access_eligible = [provider for provider in providers if provider["pointAccessEligible"]]
    point_access_blocked = [
        provider for provider in providers if not provider["pointAccessEligible"]
    ]
    service_access_eligible = [
        provider for provider in providers if provider["serviceAccessEligible"]
    ]
    coordinate_rejection_reasons = {
        "county-only-location",
        "invalid-coordinate",
        "manual-review-needed",
    }
    coordinate_matched = [
        provider
        for provider in providers
        if provider["addressEvidence"]["method"] != "none"
        and (
            provider["pointEvidence"]["method"] == "published-coordinate"
            or provider["pointAccessBlockedReason"] in coordinate_rejection_reasons
        )
    ]
    coordinate_rejected = [
        provider for provider in coordinate_matched if not provider["pointAccessEligible"]
    ]

    summary = {
        "providers": len(providers),
        "serviceAccessEligibleProviders": len(service_access_eligible),
        "serviceAccessBlockedProviders": len(providers) - len(service_access_eligible),
        "addressSourceRecords": len(address_source["records"]) if address_source else 0,
        "addressSourceRecordsWithStreetAddress": (
            sum(1 for record in address_source["records"] if record["hasStreetAddress"])
            if address_source
            else 0
        ),
        "addressSourceRecordsWithCoordinates": (
            sum(1 for record in address_source["records"] if has_published_coordinate(record))
            if address_source
            else 0
        ),
        "addressMatchedProviders": sum(
            1 for status in address_match_status_by_provider.values() if status == "matched"
        ),
        "ambiguousAddressProviders": sum(
            1 for status in address_match_status_by_provider.values() if status == "ambiguous"
        ),
        "pointAccessEligibleProviders": len(point_access_eligible),
        "pointAccessBlockedProviders": len(point_access_blocked),
        "providersWithAddress": sum(1 for provider in providers if provider["address"]),
        "providersWithCoordinates": sum(
            1
            for provider in providers
            if provider["latitude"] is not None and provider["longitude"] is not None
        ),
        "coordinateMatchedProviders": len(coordinate_matched),
        "coordinateAcceptedProviders": len(point_access_eligible),
        "coordinateRejectedProviders": len(coordinate_rejected),
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
        "provenance": provider_point_provenance(health_mart, address_source),
        "registry": {
            "healthMart": {
                "id": health_mart["id"],
                "periodStart": health_mart["periodStart"],
                "periodEnd": health_mart["periodEnd"],
            },
            **(
                {
                    "addressSource": {
                        "id": address_source["id"],
                        "publisher": address_source["publisher"],
                        "sourceUrl": address_source["sourceUrl"],
                        "retrievedDate": address_source["retrievedDate"],
                    }
                }
                if address_source
                else {}
            ),
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
                "coordinate-source-ministry-marker",
                "note",
                ["latitude", "longitude", "pointEvidence"],
                (
                    "Accepted coordinates come from Ministry of Health map markers "
                    "attached to exact normalised provider-name and county address "
                    "matches."
                ),
            ),
            limitation(
                "coordinate-uat-polygon-validation-not-applied",
                "material",
                ["latitude", "longitude", "pointAccessEligible"],
                (
                    "This slice applies Romania bounding-box and source/provider "
                    "county checks. UAT polygon containment is not applied because "
                    "the committed UAT geometry available to this package is not "
                    "SIRUTA-keyed."
                ),
            ),
            limitation(
                "address-source-exact-name-only",
                "material",
                ["address", "addressEvidence"],
                (
                    "The Ministry address import accepts only exact normalised "
                    "provider-name and county matches. Non-exact source candidates "
                    "remain unfilled until manual or stricter automated review."
                ),
            ),
            limitation(
                "county-only-not-promoted-to-points",
                "material",
                ["pointAccessEligible", "pointAccessBlockedReason"],
                (
                    "County-only health mart rows remain blocked even when an exact "
                    "Ministry address or marker match exists, because the mart has no "
                    "provider- or UAT-level location anchor for those rows."
                ),
            ),
            limitation(
                "bucharest-sector-needs-address-evidence",
                "material",
                ["siruta", "pointAccessEligible"],
                (
                    "Bucharest municipality-level providers are not reassigned to "
                    "sectors by the coordinate import; sector-level service placement "
                    "requires explicit address-to-sector resolution."
                ),
            ),
        ],
    }


def provider_point_provenance(
    health_mart: dict[str, Any],
    address_source: dict[str, Any] | None,
) -> dict[str, str]:
    if not address_source:
        return {
            "source": health_mart["id"],
            "locator": (
                "provider rows from the shared health access mart; no address or "
                "coordinate source imported yet"
            ),
            "confidence": "derived",
            "note": (
                "This file is a point-evidence contract. Providers are blocked "
                "from point routing until explicit address or coordinate evidence "
                "is attached."
            ),
        }

    return {
        "source": f"{health_mart['id']} + {address_source['id']}",
        "locator": (
            "provider rows from the shared health access mart joined to the "
            "Ministry of Health unitati sanitare map extract by exact normalised "
            "provider name and county"
        ),
        "confidence": "derived",
        "note": (
            "Official address and marker-coordinate evidence is attached where exact "
            "name/county matches exist. Only non-county-only, service-eligible "
            "providers with accepted coordinates are eligible for point routing."
        ),
    }


def build_from_files(
    health_mart_path: Path,
    address_source_path: Path | None = ADDRESS_SOURCE,
    retrieved_date: str | None = None,
) -> dict[str, Any]:
    health_mart = json.loads(health_mart_path.read_text(encoding="utf-8"))
    address_source = (
        json.loads(address_source_path.read_text(encoding="utf-8"))
        if address_source_path
        else None
    )
    source_hashes = {"healthAccessMartSha256": sha256_file(health_mart_path)}
    if address_source_path:
        source_hashes["msUnitatiSanitareSha256"] = sha256_file(address_source_path)
    return build_document(
        health_mart,
        source_hashes,
        retrieved_date,
        address_source,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-mart", type=Path, default=HEALTH_MART)
    parser.add_argument("--address-source", type=Path, default=ADDRESS_SOURCE)
    parser.add_argument("--no-address-source", action="store_true")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date")
    args = parser.parse_args(argv)

    address_source = None if args.no_address_source else args.address_source
    document = build_from_files(args.health_mart, address_source, args.retrieved_date)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {document['summary']['providers']} providers and "
        f"{document['summary']['providersWithAddress']} addresses "
        f"({document['summary']['pointAccessEligibleProviders']} point-eligible providers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

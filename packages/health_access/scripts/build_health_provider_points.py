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
ADDRESS_ALIASES = PACKAGE_ROOT / "sources/ms-unitati-sanitare-address-aliases-2026.json"
COORDINATE_REVIEWS = PACKAGE_ROOT / "sources/ms-unitati-sanitare-coordinate-reviews-2026.json"
POINT_VIEW_ID: Final[str] = "health-provider-points-2024-2026"
OUT = PACKAGE_ROOT / f"data/{POINT_VIEW_ID}.json"
TRANSFORM_VERSION: Final[int] = 5
ROMANIA_LATITUDE_RANGE: Final[tuple[float, float]] = (43.0, 49.0)
ROMANIA_LONGITUDE_RANGE: Final[tuple[float, float]] = (20.0, 30.0)
ADDRESS_ALIAS_SOURCE_ID: Final[str] = "ministerul-sanatatii-unitati-sanitare-address-aliases-2026"
COORDINATE_REVIEW_SOURCE_ID: Final[str] = (
    "ministerul-sanatatii-unitati-sanitare-coordinate-reviews-2026"
)
EXACT_ADDRESS_MATCH_METHOD: Final[str] = "exact-normalised-name-county"
CURATED_ADDRESS_MATCH_METHOD: Final[str] = "curated-same-county-official-name-alias"
REVIEWED_COORDINATE_MATCH_METHOD: Final[str] = "reviewed-exact-name-county-coordinate-only"
REVIEWED_COORDINATE_EVIDENCE_METHOD: Final[str] = "reviewed-published-coordinate"


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
    source_record: dict[str, Any],
    latitude: float,
    longitude: float,
    reviewed_coordinate_only: bool = False,
) -> dict[str, Any]:
    method = (
        REVIEWED_COORDINATE_EVIDENCE_METHOD if reviewed_coordinate_only else "published-coordinate"
    )
    source_value = (
        f"{source_record['sourceRecordId']}:{latitude:.6f},{longitude:.6f}"
        if reviewed_coordinate_only
        else f"{latitude:.6f},{longitude:.6f}"
    )
    return {
        "method": method,
        "source": address_source["id"],
        "sourceValue": source_value,
        "retrievedDate": address_source["retrievedDate"],
    }


def provider_point(
    provider: dict[str, Any],
    address_source: dict[str, Any] | None,
    address_record: dict[str, Any] | None,
    coordinate_record: dict[str, Any] | None,
    address_match_status: str | None,
    reviewed_coordinate_only: bool = False,
) -> dict[str, Any]:
    coordinate = accepted_coordinate(provider, coordinate_record)
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
        "address": address_record["address"] if address_record else None,
        "addressSourceRecordId": (
            (address_record or coordinate_record)["sourceRecordId"]
            if address_record or coordinate_record
            else None
        ),
        "addressMatchMethod": (
            EXACT_ADDRESS_MATCH_METHOD
            if address_match_status == "matched"
            else CURATED_ADDRESS_MATCH_METHOD
            if address_match_status == "alias"
            else None
        ),
        "addressEvidence": (
            address_evidence(address_source, address_record)
            if address_source and address_record
            else none_address_evidence()
        ),
        "latitude": latitude,
        "longitude": longitude,
        "pointConfidence": "official-coordinate" if coordinate else "none",
        "pointEvidence": (
            coordinate_evidence(
                address_source,
                coordinate_record,
                latitude,
                longitude,
                reviewed_coordinate_only,
            )
            if address_source and coordinate_record and coordinate
            else none_point_evidence()
        ),
        "pointAccessEligible": point_access_eligible,
        "pointAccessBlockedReason": (
            None
            if point_access_eligible
            else point_access_blocked_reason(provider, address_match_status, coordinate_record)
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
                f"pointAccessEligible provider has no coordinates: {provider['providerId']}"
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


def address_records_by_id(address_source: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not address_source:
        return {}

    rows: dict[str, dict[str, Any]] = {}
    duplicates = []
    for record in address_source["records"]:
        source_record_id = record["sourceRecordId"]
        if source_record_id in rows:
            duplicates.append(source_record_id)
        rows[source_record_id] = record
    if duplicates:
        listed = ", ".join(sorted(set(duplicates))[:10])
        raise ValueError(f"address source has duplicate source record ids: {listed}")
    return rows


def address_alias_index(
    address_aliases: dict[str, Any] | None,
    source_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not address_aliases:
        return {}
    if address_aliases["id"] != ADDRESS_ALIAS_SOURCE_ID:
        raise ValueError(f"expected {ADDRESS_ALIAS_SOURCE_ID}, got {address_aliases['id']}")

    aliases: dict[str, dict[str, Any]] = {}
    duplicate_providers = []
    duplicate_source_records = []
    used_source_records: set[str] = set()
    for alias in address_aliases["aliases"]:
        provider_id = alias["providerId"]
        source_record_id = alias["sourceRecordId"]
        if provider_id in aliases:
            duplicate_providers.append(provider_id)
        if source_record_id in used_source_records:
            duplicate_source_records.append(source_record_id)
        used_source_records.add(source_record_id)

        source_record = source_records.get(source_record_id)
        if source_record is None:
            raise ValueError(f"address alias references missing source row: {source_record_id}")
        if source_record.get("countyCode") != alias["countyCode"]:
            raise ValueError(
                f"address alias county differs from source row: {provider_id} -> {source_record_id}"
            )
        if not source_record.get("hasStreetAddress"):
            raise ValueError(
                f"address alias references source row without street address: {source_record_id}"
            )
        aliases[provider_id] = source_record

    if duplicate_providers:
        listed = ", ".join(sorted(set(duplicate_providers))[:10])
        raise ValueError(f"address alias file has duplicate provider ids: {listed}")
    if duplicate_source_records:
        listed = ", ".join(sorted(set(duplicate_source_records))[:10])
        raise ValueError(f"address alias file reuses source record ids: {listed}")
    return aliases


def coordinate_review_index(
    coordinate_reviews: dict[str, Any] | None,
    source_records: dict[str, dict[str, Any]],
    providers_by_id: dict[str, dict[str, Any]],
    used_source_record_ids: set[str],
    providers_with_address_records: set[str],
) -> dict[str, dict[str, Any]]:
    if not coordinate_reviews:
        return {}
    if coordinate_reviews["id"] != COORDINATE_REVIEW_SOURCE_ID:
        raise ValueError(f"expected {COORDINATE_REVIEW_SOURCE_ID}, got {coordinate_reviews['id']}")

    reviews: dict[str, dict[str, Any]] = {}
    duplicate_providers = []
    duplicate_source_records = []
    reviewed_source_record_ids: set[str] = set()
    for review in coordinate_reviews["acceptances"]:
        provider_id = review["providerId"]
        source_record_id = review["sourceRecordId"]
        if provider_id in reviews:
            duplicate_providers.append(provider_id)
        if (
            source_record_id in used_source_record_ids
            or source_record_id in reviewed_source_record_ids
        ):
            duplicate_source_records.append(source_record_id)
        reviewed_source_record_ids.add(source_record_id)

        provider = providers_by_id.get(provider_id)
        if provider is None:
            raise ValueError(f"coordinate review references missing provider: {provider_id}")

        source_record = source_records.get(source_record_id)
        if source_record is None:
            raise ValueError(f"coordinate review references missing source row: {source_record_id}")
        if review["matchMethod"] != REVIEWED_COORDINATE_MATCH_METHOD:
            raise ValueError(
                f"coordinate review has unsupported match method: {review['matchMethod']}"
            )
        if provider["countyCode"] != review["countyCode"]:
            raise ValueError(f"coordinate review county differs from provider row: {provider_id}")
        if source_record.get("countyCode") != review["countyCode"]:
            raise ValueError(
                "coordinate review county differs from source row: "
                f"{provider_id} -> {source_record_id}"
            )
        if normalise_text(provider["name"]) != normalise_text(source_record["name"]):
            raise ValueError(
                f"coordinate review is not an exact name match: {provider_id} -> {source_record_id}"
            )
        if source_record.get("hasStreetAddress"):
            raise ValueError(
                f"coordinate review references source row with street address: {source_record_id}"
            )
        if provider_id in providers_with_address_records:
            raise ValueError(
                f"coordinate review provider already has address evidence: {provider_id}"
            )
        if not has_published_coordinate(source_record):
            raise ValueError(
                f"coordinate review references source row without coordinates: {source_record_id}"
            )
        if not coordinate_in_romania(source_record["latitude"], source_record["longitude"]):
            raise ValueError(f"coordinate review references invalid coordinate: {source_record_id}")
        if not provider["serviceAccessEligible"]:
            raise ValueError(
                f"coordinate review provider is not service-access eligible: {provider_id}"
            )
        if provider["locationConfidence"] == "county-only":
            raise ValueError(f"coordinate review provider has county-only location: {provider_id}")
        reviews[provider_id] = source_record

    if duplicate_providers:
        listed = ", ".join(sorted(set(duplicate_providers))[:10])
        raise ValueError(f"coordinate review file has duplicate provider ids: {listed}")
    if duplicate_source_records:
        listed = ", ".join(sorted(set(duplicate_source_records))[:10])
        raise ValueError(f"coordinate review file reuses source record ids: {listed}")
    return reviews


def match_address_record(
    provider: dict[str, Any],
    index: dict[tuple[str, str], list[dict[str, Any]]],
    aliases: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    matches = index.get((normalise_text(provider["name"]), provider["countyCode"]), [])
    if len(matches) == 1:
        return matches[0], "matched"
    if len(matches) > 1:
        return None, "ambiguous"
    alias = (aliases or {}).get(provider["providerId"])
    if alias is not None:
        if alias.get("countyCode") != provider["countyCode"]:
            raise ValueError(
                "address alias county differs from provider row: "
                f"{provider['providerId']} -> {alias['sourceRecordId']}"
            )
        return alias, "alias"
    return None, None


def build_document(
    health_mart: dict[str, Any],
    source_hashes: dict[str, str],
    retrieved_date: str | None = None,
    address_source: dict[str, Any] | None = None,
    address_aliases: dict[str, Any] | None = None,
    coordinate_reviews: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = health_mart["records"]
    assert_unique_provider_ids(records)
    providers_by_id = {record["providerId"]: record for record in records}

    address_index = address_match_index(address_source)
    source_records = address_records_by_id(address_source)
    address_aliases_by_provider = address_alias_index(address_aliases, source_records)
    address_match_status_by_provider: dict[str, str] = {}
    address_source_record_by_provider: dict[str, str] = {}
    address_record_by_provider: dict[str, dict[str, Any]] = {}
    for record in records:
        source_record, match_status = match_address_record(
            record,
            address_index,
            address_aliases_by_provider,
        )
        if match_status:
            address_match_status_by_provider[record["providerId"]] = match_status
        if source_record:
            address_source_record_by_provider[record["providerId"]] = source_record[
                "sourceRecordId"
            ]
            address_record_by_provider[record["providerId"]] = source_record

    source_record_counts = Counter(address_source_record_by_provider.values())
    duplicate_source_records = sorted(
        source_record_id for source_record_id, count in source_record_counts.items() if count > 1
    )
    if duplicate_source_records:
        raise ValueError(
            "address source records matched multiple providers: "
            + ", ".join(duplicate_source_records[:10])
        )

    coordinate_records_by_provider = coordinate_review_index(
        coordinate_reviews,
        source_records,
        providers_by_id,
        set(address_source_record_by_provider.values()),
        set(address_record_by_provider),
    )
    providers = [
        provider_point(
            record,
            address_source,
            address_record_by_provider.get(record["providerId"]),
            coordinate_records_by_provider.get(record["providerId"])
            or address_record_by_provider.get(record["providerId"]),
            address_match_status_by_provider.get(record["providerId"]),
            record["providerId"] in coordinate_records_by_provider,
        )
        for record in records
    ]

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
        if provider["addressSourceRecordId"]
        and (
            provider["pointEvidence"]["method"]
            in {"published-coordinate", REVIEWED_COORDINATE_EVIDENCE_METHOD}
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
            1
            for status in address_match_status_by_provider.values()
            if status in {"matched", "alias"}
        ),
        "addressExactMatchedProviders": sum(
            1 for status in address_match_status_by_provider.values() if status == "matched"
        ),
        "addressAliasMatchedProviders": sum(
            1 for status in address_match_status_by_provider.values() if status == "alias"
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
        "addressMatchMethods": count_by(
            [provider["addressMatchMethod"] or "none" for provider in providers]
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
        "provenance": provider_point_provenance(
            health_mart,
            address_source,
            address_aliases,
            coordinate_reviews,
        ),
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
            **(
                {
                    "addressAliases": {
                        "id": address_aliases["id"],
                        "reviewedDate": address_aliases["reviewedDate"],
                        "aliases": len(address_aliases["aliases"]),
                    }
                }
                if address_aliases
                else {}
            ),
            **(
                {
                    "coordinateReviews": {
                        "id": coordinate_reviews["id"],
                        "reviewedDate": coordinate_reviews["reviewedDate"],
                        "acceptances": len(coordinate_reviews["acceptances"]),
                    }
                }
                if coordinate_reviews
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
                    "attached to exact normalised provider-name and county matches, "
                    "curated same-county source-record aliases, and reviewed "
                    "coordinate-only exact source-row acceptances."
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
                "address-source-exact-or-curated-id-only",
                "material",
                ["address", "addressEvidence"],
                (
                    "The Ministry address import accepts exact normalised "
                    "provider-name and county matches, plus audited providerId to "
                    "sourceRecordId aliases from "
                    "ms-unitati-sanitare-address-aliases-2026. Other non-exact "
                    "source candidates remain unfilled until manual or stricter "
                    "automated review."
                ),
            ),
            limitation(
                "coordinate-only-review-is-not-address-evidence",
                "material",
                ["address", "addressEvidence", "pointEvidence"],
                (
                    "Reviewed coordinate-only acceptances attach a source-record-pinned "
                    "published coordinate without filling an address. Their address "
                    "evidence remains method none until a street-address source is found."
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
    address_aliases: dict[str, Any] | None = None,
    coordinate_reviews: dict[str, Any] | None = None,
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
        "source": (
            f"{health_mart['id']} + {address_source['id']}"
            + (f" + {address_aliases['id']}" if address_aliases else "")
            + (f" + {coordinate_reviews['id']}" if coordinate_reviews else "")
        ),
        "locator": (
            "provider rows from the shared health access mart joined to the "
            "Ministry of Health unitati sanitare map extract by exact normalised "
            "provider name and county"
            + (
                ", with additional curated same-county source-record aliases"
                if address_aliases
                else ""
            )
            + (
                ", and reviewed coordinate-only exact source-record acceptances"
                if coordinate_reviews
                else ""
            )
        ),
        "confidence": "derived",
        "note": (
            "Official address and marker-coordinate evidence is attached where exact "
            "name/county matches or curated source-record aliases exist. Reviewed "
            "coordinate-only acceptances attach coordinates without creating address "
            "evidence. Only non-county-only, service-eligible providers with accepted "
            "coordinates are eligible for point routing."
        ),
    }


def build_from_files(
    health_mart_path: Path,
    address_source_path: Path | None = ADDRESS_SOURCE,
    address_aliases_path: Path | None = ADDRESS_ALIASES,
    retrieved_date: str | None = None,
    *,
    coordinate_reviews_path: Path | None = COORDINATE_REVIEWS,
) -> dict[str, Any]:
    if address_source_path is None:
        address_aliases_path = None
        coordinate_reviews_path = None

    health_mart = json.loads(health_mart_path.read_text(encoding="utf-8"))
    address_source = (
        json.loads(address_source_path.read_text(encoding="utf-8")) if address_source_path else None
    )
    address_aliases = (
        json.loads(address_aliases_path.read_text(encoding="utf-8"))
        if address_aliases_path
        else None
    )
    coordinate_reviews = (
        json.loads(coordinate_reviews_path.read_text(encoding="utf-8"))
        if coordinate_reviews_path
        else None
    )
    source_hashes = {"healthAccessMartSha256": sha256_file(health_mart_path)}
    if address_source_path:
        source_hashes["msUnitatiSanitareSha256"] = sha256_file(address_source_path)
    if address_aliases_path:
        source_hashes["msUnitatiSanitareAliasesSha256"] = sha256_file(address_aliases_path)
    if coordinate_reviews_path:
        source_hashes["msUnitatiSanitareCoordinateReviewsSha256"] = sha256_file(
            coordinate_reviews_path
        )
    return build_document(
        health_mart,
        source_hashes,
        retrieved_date,
        address_source,
        address_aliases,
        coordinate_reviews,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-mart", type=Path, default=HEALTH_MART)
    parser.add_argument("--address-source", type=Path, default=ADDRESS_SOURCE)
    parser.add_argument("--address-aliases", type=Path, default=ADDRESS_ALIASES)
    parser.add_argument("--coordinate-reviews", type=Path, default=COORDINATE_REVIEWS)
    parser.add_argument("--no-address-source", action="store_true")
    parser.add_argument("--no-address-aliases", action="store_true")
    parser.add_argument("--no-coordinate-reviews", action="store_true")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--retrieved-date")
    args = parser.parse_args(argv)

    address_source = None if args.no_address_source else args.address_source
    address_aliases = None if args.no_address_aliases else args.address_aliases
    coordinate_reviews = None if args.no_coordinate_reviews else args.coordinate_reviews
    if address_source is None:
        address_aliases = None
        coordinate_reviews = None
    document = build_from_files(
        args.health_mart,
        address_source,
        address_aliases,
        args.retrieved_date,
        coordinate_reviews_path=coordinate_reviews,
    )
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

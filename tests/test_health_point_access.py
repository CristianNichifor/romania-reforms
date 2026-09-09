from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
POINT_ACCESS_BUILDER = (
    ROOT / "packages" / "health_access" / "scripts" / "build_health_point_access.py"
)
DATA = ROOT / "packages" / "health_access" / "data"

spec = importlib.util.spec_from_file_location("build_health_point_access", POINT_ACCESS_BUILDER)
assert spec and spec.loader
health_point_access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_point_access)


def evidence(method: str, source_value: str) -> dict:
    return {
        "method": method,
        "source": "fixture-source",
        "sourceValue": source_value,
        "retrievedDate": "2026-09-09",
    }


def point_provider(
    provider_id: str,
    point_access_eligible: bool,
    point_access_blocked_reason: str | None = None,
    latitude: float | None = 44.1,
    longitude: float | None = 26.1,
) -> dict:
    return {
        "providerId": provider_id,
        "name": f"SPITALUL {provider_id}",
        "countyCode": "TS",
        "countyName": "Test",
        "siruta": "101" if point_access_eligible else None,
        "localityName": "MUNICIPIUL TEST" if point_access_eligible else None,
        "locationConfidence": "name-derived-locality" if point_access_eligible else "county-only",
        "serviceAccessEligible": point_access_eligible,
        "address": "Strada Sanatatii nr. 1, Municipiul Test" if point_access_eligible else None,
        "addressSourceRecordId": "ms-unitati-sanitare-001" if point_access_eligible else None,
        "addressMatchMethod": "exact-normalised-name-county" if point_access_eligible else None,
        "addressEvidence": evidence("official-provider-address", "Strada Sanatatii nr. 1"),
        "latitude": latitude if point_access_eligible else None,
        "longitude": longitude if point_access_eligible else None,
        "pointConfidence": "official-coordinate" if point_access_eligible else "none",
        "pointEvidence": evidence("published-coordinate", "44.100000,26.100000")
        if point_access_eligible
        else {"method": "none", "source": None, "sourceValue": None, "retrievedDate": None},
        "pointAccessEligible": point_access_eligible,
        "pointAccessBlockedReason": point_access_blocked_reason,
    }


def mart_provider(provider_id: str, bed_count: float | None = 12.0) -> dict:
    return {
        "providerId": provider_id,
        "name": f"SPITALUL {provider_id}",
        "countyCode": "TS",
        "countyName": "Test",
        "ownerType": "public",
        "bedCount": bed_count,
        "specialties": ["cardiology"] if bed_count is not None else [],
        "accreditationCategory": "fixture",
    }


def fixture_provider_points(records: list[dict] | None = None) -> dict:
    providers = records or [
        point_provider("anmcs-2025-001", True),
        point_provider("anmcs-2025-002", False, "county-only-location"),
    ]
    return {
        "id": "health-provider-points-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "summary": {
            "byCounty": [{"countyCode": "TS", "countyName": "Test"}],
        },
        "providers": providers,
    }


def fixture_health_mart(records: list[dict] | None = None) -> dict:
    return {
        "id": "health-access-mart-2024-2025",
        "periodStart": "2024",
        "periodEnd": "2025",
        "summary": {
            "scopeCounties": ["TS"],
            "byCounty": [{"countyCode": "TS", "countyName": "Test"}],
        },
        "records": records
        or [
            mart_provider("anmcs-2025-001"),
            mart_provider("anmcs-2025-002", None),
        ],
    }


def test_build_document_filters_to_point_access_eligible_providers():
    document = health_point_access.build_document(
        fixture_provider_points(),
        fixture_health_mart(),
        {"providerPointsSha256": "a" * 64, "healthAccessMartSha256": "b" * 64},
        "2026-09-09",
    )

    assert document["id"] == "health-point-access-2024-2026"
    assert document["accessModel"] == {
        "kind": "provider-point-layer",
        "distanceMethod": "not-computed",
        "consumerDistanceMethodRequired": True,
        "supportedConsumerDistanceMethods": ["straight-line", "routed"],
    }
    assert document["summary"]["providers"] == 2
    assert document["summary"]["pointAccessProviders"] == 1
    assert document["summary"]["pointAccessBlockedProviders"] == 1
    assert document["summary"]["providersWithClinicalBeds"] == 1
    assert document["summary"]["providerLevelClinicalBeds"] == 12.0
    assert document["summary"]["namedExclusions"] == 1
    assert document["summary"]["distanceMethod"] == "not-computed"
    assert document["summary"]["consumerDistanceMethodRequired"] is True
    assert document["summary"]["pointEvidence"] == {"published-coordinate": 1}
    assert document["summary"]["blockedReasons"] == {"county-only-location": 1}

    point = document["points"][0]
    assert point["providerId"] == "anmcs-2025-001"
    assert point["latitude"] == 44.1
    assert point["longitude"] == 26.1
    assert point["locationConfidence"] == "name-derived-locality"
    assert point["serviceAccessEligible"] is True
    assert point["ownerType"] == "public"
    assert point["specialties"] == ["cardiology"]
    assert point["accessUse"] == "eligible-for-point-level-access"

    exclusion = document["exclusions"][0]
    assert exclusion["providerId"] == "anmcs-2025-002"
    assert exclusion["pointAccessBlockedReason"] == "county-only-location"
    assert exclusion["hasAddress"] is False


def test_build_document_refuses_point_access_rows_without_coordinates():
    providers = [point_provider("anmcs-2025-001", True, latitude=None)]

    with pytest.raises(ValueError, match="no coordinates"):
        health_point_access.build_document(
            fixture_provider_points(providers),
            fixture_health_mart([mart_provider("anmcs-2025-001")]),
            {"providerPointsSha256": "a" * 64, "healthAccessMartSha256": "b" * 64},
            "2026-09-09",
        )


def test_build_document_refuses_provider_points_missing_from_health_mart():
    with pytest.raises(ValueError, match="missing from health mart"):
        health_point_access.build_document(
            fixture_provider_points([point_provider("anmcs-2025-001", True)]),
            fixture_health_mart([mart_provider("anmcs-2025-002")]),
            {"providerPointsSha256": "a" * 64, "healthAccessMartSha256": "b" * 64},
            "2026-09-09",
        )


def test_committed_health_point_access_uses_only_point_eligible_providers():
    provider_points = json.loads(
        (DATA / "health-provider-points-2024-2026.json").read_text(encoding="utf-8")
    )
    point_access = json.loads(
        (DATA / "health-point-access-2024-2026.json").read_text(encoding="utf-8")
    )

    source_point_ids = {
        provider["providerId"]
        for provider in provider_points["providers"]
        if provider["pointAccessEligible"]
    }
    source_blocked_ids = {
        provider["providerId"]
        for provider in provider_points["providers"]
        if not provider["pointAccessEligible"]
    }
    view_point_ids = {provider["providerId"] for provider in point_access["points"]}
    excluded_ids = {exclusion["providerId"] for exclusion in point_access["exclusions"]}

    assert point_access["id"] == "health-point-access-2024-2026"
    assert point_access["summary"]["providers"] == 592
    assert point_access["summary"]["pointAccessProviders"] == 202
    assert point_access["summary"]["pointAccessBlockedProviders"] == 390
    assert point_access["summary"]["namedExclusions"] == 390
    assert point_access["summary"]["distanceMethod"] == "not-computed"
    assert point_access["summary"]["supportedConsumerDistanceMethods"] == [
        "straight-line",
        "routed",
    ]
    assert point_access["summary"]["pointConfidence"] == {"official-coordinate": 202}
    assert point_access["summary"]["pointEvidence"] == {"published-coordinate": 202}
    assert point_access["summary"]["blockedReasons"] == {
        "county-only-location": 268,
        "no-point-evidence": 122,
    }
    assert view_point_ids == source_point_ids
    assert excluded_ids == source_blocked_ids
    assert view_point_ids.isdisjoint(excluded_ids)
    assert all(
        point["accessUse"] == "eligible-for-point-level-access" for point in point_access["points"]
    )
    assert all(point["latitude"] is not None for point in point_access["points"])
    assert all(point["longitude"] is not None for point in point_access["points"])

    limitation_ids = {limitation["id"] for limitation in point_access["limitations"]}
    assert "point-layer-not-distance-model" in limitation_ids
    assert "blocked-provider-rows-excluded" in limitation_ids
    assert "consumer-distance-method-must-be-declared" in limitation_ids

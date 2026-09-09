from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
POINT_BUILDER = (
    ROOT / "packages" / "health_access" / "scripts" / "build_health_provider_points.py"
)
DATA = ROOT / "packages" / "health_access" / "data"

spec = importlib.util.spec_from_file_location("build_health_provider_points", POINT_BUILDER)
assert spec and spec.loader
health_provider_points = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_provider_points)


def access_provider(
    provider_id: str,
    siruta: str | None,
    service_access_eligible: bool,
    location_confidence: str = "name-derived-locality",
) -> dict:
    return {
        "providerId": provider_id,
        "name": f"SPITALUL {provider_id}",
        "countyCode": "TS",
        "countyName": "Test",
        "siruta": siruta,
        "localityName": "MUNICIPIUL TEST" if siruta else None,
        "locationConfidence": location_confidence,
        "serviceAccessEligible": service_access_eligible,
    }


def fixture_health_mart() -> dict:
    return {
        "id": "health-access-mart-2024-2025",
        "publisher": "Ministerul Sanatatii / ANMCS",
        "periodStart": "2024",
        "periodEnd": "2025",
        "retrievedDate": "2026-09-09",
        "summary": {
            "scopeCounties": ["TS"],
            "byCounty": [{"countyCode": "TS", "countyName": "Test"}],
        },
        "records": [
            access_provider("anmcs-2025-001", "101", True),
            access_provider("anmcs-2025-002", None, False, "county-only"),
        ],
    }


def test_build_document_creates_blocked_point_rows_for_every_provider():
    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64},
        "2026-09-09",
    )

    assert len(document["providers"]) == 2
    assert all(not provider["pointAccessEligible"] for provider in document["providers"])
    assert all(provider["address"] is None for provider in document["providers"])
    assert all(provider["latitude"] is None for provider in document["providers"])
    assert all(provider["longitude"] is None for provider in document["providers"])
    assert all(
        provider["addressEvidence"]["method"] == "none"
        for provider in document["providers"]
    )
    assert all(
        provider["pointEvidence"]["method"] == "none"
        for provider in document["providers"]
    )

    assert document["summary"]["providers"] == 2
    assert document["summary"]["serviceAccessEligibleProviders"] == 1
    assert document["summary"]["serviceAccessBlockedProviders"] == 1
    assert document["summary"]["pointAccessEligibleProviders"] == 0
    assert document["summary"]["pointAccessBlockedProviders"] == 2
    assert document["summary"]["addressEvidence"] == {"none": 2}
    assert document["summary"]["pointConfidence"] == {"none": 2}
    assert {row["providerId"] for row in document["exclusions"]} == {
        "anmcs-2025-001",
        "anmcs-2025-002",
    }


def test_county_only_rows_keep_a_stronger_block_reason():
    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64},
    )

    by_id = {provider["providerId"]: provider for provider in document["providers"]}

    assert by_id["anmcs-2025-001"]["pointAccessBlockedReason"] == "no-point-evidence"
    assert by_id["anmcs-2025-002"]["pointAccessBlockedReason"] == "county-only-location"
    assert document["summary"]["blockedReasons"] == {
        "county-only-location": 1,
        "no-point-evidence": 1,
    }


def test_routeable_point_providers_ignores_blocked_rows_and_requires_coordinates():
    document = {
        "providers": [
            {
                "providerId": "blocked",
                "pointAccessEligible": False,
                "latitude": 44.0,
                "longitude": 26.0,
            },
            {
                "providerId": "routeable",
                "pointAccessEligible": True,
                "latitude": 44.0,
                "longitude": 26.0,
            },
        ]
    }

    assert [
        provider["providerId"]
        for provider in health_provider_points.routeable_point_providers(document)
    ] == ["routeable"]

    broken = {
        "providers": [
            {
                "providerId": "missing-coordinate",
                "pointAccessEligible": True,
                "latitude": None,
                "longitude": 26.0,
            }
        ]
    }
    with pytest.raises(ValueError, match="no coordinates"):
        health_provider_points.routeable_point_providers(broken)


def test_duplicate_provider_ids_are_refused():
    mart = fixture_health_mart()
    mart["records"][1]["providerId"] = "anmcs-2025-001"

    with pytest.raises(ValueError, match="duplicate provider ids: anmcs-2025-001"):
        health_provider_points.build_document(mart, {"healthAccessMartSha256": "a" * 64})


def test_committed_provider_points_cover_the_health_mart():
    health_mart = json.loads(
        (DATA / "health-access-mart-2024-2025.json").read_text(encoding="utf-8")
    )
    points = json.loads(
        (DATA / "health-provider-points-2024-2026.json").read_text(encoding="utf-8")
    )

    mart_provider_ids = {provider["providerId"] for provider in health_mart["records"]}
    point_provider_ids = {provider["providerId"] for provider in points["providers"]}

    assert point_provider_ids == mart_provider_ids
    assert points["summary"]["providers"] == 592
    assert (
        points["summary"]["serviceAccessEligibleProviders"]
        == health_mart["summary"]["serviceAccessEligibleProviders"]
    )
    assert points["summary"]["serviceAccessBlockedProviders"] == 268
    assert points["summary"]["pointAccessEligibleProviders"] == 0
    assert points["summary"]["pointAccessBlockedProviders"] == 592
    assert (
        points["summary"]["blockedReasons"]["county-only-location"]
        == health_mart["summary"]["locationConfidence"]["county-only"]
    )
    assert (
        points["summary"]["blockedReasons"]["no-point-evidence"]
        == health_mart["summary"]["records"]
        - health_mart["summary"]["locationConfidence"]["county-only"]
    )
    assert all(not provider["pointAccessEligible"] for provider in points["providers"])
    assert all(
        provider["addressEvidence"]["method"] == "none"
        for provider in points["providers"]
    )
    assert all(
        provider["pointConfidence"] == "none" for provider in points["providers"]
    )
    assert len(points["exclusions"]) == 592

    limitation_ids = {limitation["id"] for limitation in points["limitations"]}
    assert "point-evidence-not-yet-imported" in limitation_ids
    assert "county-only-not-promoted-to-points" in limitation_ids

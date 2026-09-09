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
SOURCES = ROOT / "packages" / "health_access" / "sources"

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


def source_record(
    source_record_id: str,
    name: str,
    address: str,
    county_code: str | None = "TS",
    has_street_address: bool = True,
    latitude: float | None = 44.1,
    longitude: float | None = 26.1,
    has_published_coordinate: bool = True,
) -> dict:
    return {
        "sourceRecordId": source_record_id,
        "sourceOrdinal": int(source_record_id.rsplit("-", 1)[1]),
        "name": name,
        "countyCode": county_code,
        "address": address,
        "hasStreetAddress": has_street_address,
        "latitude": latitude,
        "longitude": longitude,
        "hasPublishedCoordinate": has_published_coordinate,
        "detailUrl": f"https://ms.ro/ro/unitati-sanitare/{source_record_id}/",
    }


def fixture_address_source(records: list[dict] | None = None) -> dict:
    source_records = records or [
        source_record(
            "ms-unitati-sanitare-001",
            "SPITALUL anmcs-2025-001",
            "Strada Sanatatii nr. 1, Municipiul Test",
        )
    ]
    return {
        "id": "ministerul-sanatatii-unitati-sanitare-2026",
        "publisher": "Ministerul Sanatatii",
        "sourceUrl": "https://ms.ro/ro/unitati-sanitare/",
        "retrievedDate": "2026-09-09",
        "records": source_records,
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
    assert points["summary"]["addressSourceRecords"] == 301
    assert points["summary"]["addressSourceRecordsWithStreetAddress"] == 290
    assert points["summary"]["addressSourceRecordsWithCoordinates"] == 301
    assert points["summary"]["addressMatchedProviders"] == 174
    assert points["summary"]["ambiguousAddressProviders"] == 0
    assert points["summary"]["pointAccessEligibleProviders"] == 162
    assert points["summary"]["pointAccessBlockedProviders"] == 430
    assert points["summary"]["providersWithAddress"] == 174
    assert points["summary"]["providersWithCoordinates"] == 162
    assert points["summary"]["coordinateMatchedProviders"] == 174
    assert points["summary"]["coordinateAcceptedProviders"] == 162
    assert points["summary"]["coordinateRejectedProviders"] == 12
    assert points["summary"]["addressEvidence"] == {
        "none": 418,
        "official-provider-address": 174,
    }
    assert points["summary"]["pointConfidence"] == {
        "none": 430,
        "official-coordinate": 162,
    }
    assert (
        points["summary"]["blockedReasons"]["county-only-location"]
        == health_mart["summary"]["locationConfidence"]["county-only"]
    )
    assert all(
        not provider["pointAccessEligible"]
        for provider in points["providers"]
        if provider["locationConfidence"] == "county-only"
    )
    assert points["summary"]["blockedReasons"]["no-point-evidence"] == 162
    assert sum(1 for provider in points["providers"] if provider["pointAccessEligible"]) == 162
    assert all(
        provider["pointConfidence"] == "official-coordinate"
        for provider in points["providers"]
        if provider["pointAccessEligible"]
    )
    assert len(points["exclusions"]) == 430

    limitation_ids = {limitation["id"] for limitation in points["limitations"]}
    assert "coordinate-source-ministry-marker" in limitation_ids
    assert "coordinate-uat-polygon-validation-not-applied" in limitation_ids
    assert "address-source-exact-name-only" in limitation_ids
    assert "county-only-not-promoted-to-points" in limitation_ids


def test_build_document_attaches_exact_county_safe_address_evidence():
    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64, "msUnitatiSanitareSha256": "b" * 64},
        "2026-09-09",
        fixture_address_source(),
    )

    by_id = {provider["providerId"]: provider for provider in document["providers"]}
    provider = by_id["anmcs-2025-001"]

    assert provider["address"] == "Strada Sanatatii nr. 1, Municipiul Test"
    assert provider["addressEvidence"] == {
        "method": "official-provider-address",
        "source": "ministerul-sanatatii-unitati-sanitare-2026",
        "sourceValue": "Strada Sanatatii nr. 1, Municipiul Test",
        "retrievedDate": "2026-09-09",
    }
    assert provider["latitude"] == 44.1
    assert provider["longitude"] == 26.1
    assert provider["pointConfidence"] == "official-coordinate"
    assert provider["pointEvidence"] == {
        "method": "published-coordinate",
        "source": "ministerul-sanatatii-unitati-sanitare-2026",
        "sourceValue": "44.100000,26.100000",
        "retrievedDate": "2026-09-09",
    }
    assert provider["pointAccessEligible"] is True
    assert provider["pointAccessBlockedReason"] is None

    assert document["registry"]["addressSource"]["id"] == (
        "ministerul-sanatatii-unitati-sanitare-2026"
    )
    assert document["summary"]["addressSourceRecords"] == 1
    assert document["summary"]["addressSourceRecordsWithStreetAddress"] == 1
    assert document["summary"]["addressSourceRecordsWithCoordinates"] == 1
    assert document["summary"]["addressMatchedProviders"] == 1
    assert document["summary"]["pointAccessEligibleProviders"] == 1
    assert document["summary"]["pointAccessBlockedProviders"] == 1
    assert document["summary"]["providersWithAddress"] == 1
    assert document["summary"]["providersWithCoordinates"] == 1
    assert document["summary"]["coordinateMatchedProviders"] == 1
    assert document["summary"]["coordinateAcceptedProviders"] == 1
    assert document["summary"]["coordinateRejectedProviders"] == 0
    assert document["summary"]["addressEvidence"] == {
        "none": 1,
        "official-provider-address": 1,
    }
    assert document["summary"]["pointConfidence"] == {
        "none": 1,
        "official-coordinate": 1,
    }


def test_build_document_rejects_coordinates_outside_romania_bounds():
    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64, "msUnitatiSanitareSha256": "b" * 64},
        "2026-09-09",
        fixture_address_source(
            [
                source_record(
                    "ms-unitati-sanitare-001",
                    "SPITALUL anmcs-2025-001",
                    "Strada Sanatatii nr. 1, Municipiul Test",
                    latitude=50.0,
                    longitude=26.1,
                )
            ]
        ),
    )

    provider = document["providers"][0]

    assert provider["address"] == "Strada Sanatatii nr. 1, Municipiul Test"
    assert provider["latitude"] is None
    assert provider["longitude"] is None
    assert provider["pointEvidence"]["method"] == "none"
    assert provider["pointAccessEligible"] is False
    assert provider["pointAccessBlockedReason"] == "invalid-coordinate"
    assert document["summary"]["coordinateMatchedProviders"] == 1
    assert document["summary"]["coordinateAcceptedProviders"] == 0
    assert document["summary"]["coordinateRejectedProviders"] == 1
    assert document["summary"]["blockedReasons"]["invalid-coordinate"] == 1


def test_build_document_keeps_county_only_address_matches_blocked_from_points():
    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64, "msUnitatiSanitareSha256": "b" * 64},
        "2026-09-09",
        fixture_address_source(
            [
                source_record(
                    "ms-unitati-sanitare-001",
                    "SPITALUL anmcs-2025-002",
                    "Strada Sanatatii nr. 2, Municipiul Test",
                )
            ]
        ),
    )

    provider = document["providers"][1]

    assert provider["address"] == "Strada Sanatatii nr. 2, Municipiul Test"
    assert provider["latitude"] is None
    assert provider["longitude"] is None
    assert provider["pointAccessEligible"] is False
    assert provider["pointAccessBlockedReason"] == "county-only-location"
    assert document["summary"]["coordinateMatchedProviders"] == 1
    assert document["summary"]["coordinateAcceptedProviders"] == 0
    assert document["summary"]["coordinateRejectedProviders"] == 1


def test_build_document_ignores_non_street_address_source_rows():
    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64, "msUnitatiSanitareSha256": "b" * 64},
        "2026-09-09",
        fixture_address_source(
            [
                source_record(
                    "ms-unitati-sanitare-001",
                    "SPITALUL anmcs-2025-001",
                    "Comuna Test, judetul Test",
                    has_street_address=False,
                )
            ]
        ),
    )

    provider = document["providers"][0]

    assert provider["address"] is None
    assert provider["addressEvidence"]["method"] == "none"
    assert document["summary"]["addressSourceRecords"] == 1
    assert document["summary"]["addressSourceRecordsWithStreetAddress"] == 0
    assert document["summary"]["addressMatchedProviders"] == 0
    assert document["summary"]["providersWithAddress"] == 0


def test_build_document_keeps_ambiguous_address_candidates_blocked():
    duplicate_candidates = [
        source_record(
            "ms-unitati-sanitare-001",
            "SPITALUL anmcs-2025-001",
            "Strada Sanatatii nr. 1, Municipiul Test",
        ),
        source_record(
            "ms-unitati-sanitare-002",
            "SPITALUL anmcs-2025-001",
            "Strada Sanatatii nr. 2, Municipiul Test",
        ),
    ]

    document = health_provider_points.build_document(
        fixture_health_mart(),
        {"healthAccessMartSha256": "a" * 64, "msUnitatiSanitareSha256": "b" * 64},
        "2026-09-09",
        fixture_address_source(duplicate_candidates),
    )

    provider = document["providers"][0]
    exclusion = next(
        row for row in document["exclusions"] if row["providerId"] == provider["providerId"]
    )

    assert provider["address"] is None
    assert provider["addressEvidence"]["method"] == "none"
    assert provider["pointAccessBlockedReason"] == "ambiguous-address"
    assert exclusion["pointAccessBlockedReason"] == "ambiguous-address"
    assert document["summary"]["ambiguousAddressProviders"] == 1


def test_build_document_does_not_use_fuzzy_address_matches():
    mart = fixture_health_mart()
    mart["records"][0]["name"] = "SPITALUL GENERAL C.F. PLOIESTI"
    mart["records"][0]["countyCode"] = "PH"
    mart["records"][0]["countyName"] = "Prahova"

    document = health_provider_points.build_document(
        mart,
        {"healthAccessMartSha256": "a" * 64, "msUnitatiSanitareSha256": "b" * 64},
        "2026-09-09",
        fixture_address_source(
            [
                source_record(
                    "ms-unitati-sanitare-001",
                    "Spitalul Judeţean de Urgenţă Ploieşti",
                    "Strada Gageni nr. 100, Ploiesti",
                    county_code="PH",
                )
            ]
        ),
    )

    assert document["providers"][0]["address"] is None
    assert document["summary"]["addressMatchedProviders"] == 0


def test_committed_ms_address_source_extract_is_available():
    source = json.loads(
        (SOURCES / "ms-unitati-sanitare-2026.json").read_text(encoding="utf-8")
    )

    assert source["id"] == "ministerul-sanatatii-unitati-sanitare-2026"
    assert source["summary"]["sourceRecords"] == 301
    assert source["summary"]["sourceRecordsWithStreetAddress"] > 250
    assert source["summary"]["sourceRecordsWithCoordinates"] == 301
    assert source["summary"]["duplicateDetailUrls"] == 0
    assert all(record["hasPublishedCoordinate"] for record in source["records"])
    assert all(record["latitude"] is not None for record in source["records"])
    assert all(record["longitude"] is not None for record in source["records"])

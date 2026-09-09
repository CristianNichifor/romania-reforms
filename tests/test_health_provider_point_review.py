from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_BUILDER = (
    ROOT / "packages" / "health_access" / "scripts" / "build_health_provider_point_review.py"
)
DATA = ROOT / "packages" / "health_access" / "data"
SOURCES = ROOT / "packages" / "health_access" / "sources"

spec = importlib.util.spec_from_file_location("build_health_provider_point_review", REVIEW_BUILDER)
assert spec and spec.loader
health_provider_point_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_provider_point_review)


def provider_point(
    provider_id: str,
    name: str,
    blocked_reason: str | None = "no-point-evidence",
    address_source_record_id: str | None = None,
) -> dict:
    return {
        "providerId": provider_id,
        "name": name,
        "countyCode": "TS",
        "countyName": "Test",
        "siruta": "101",
        "localityName": "MUNICIPIUL TEST",
        "locationConfidence": "name-derived-locality",
        "serviceAccessEligible": blocked_reason is not None,
        "addressSourceRecordId": address_source_record_id,
        "pointAccessEligible": blocked_reason is None,
        "pointAccessBlockedReason": blocked_reason,
    }


def fixture_provider_points() -> dict:
    return {
        "id": "health-provider-points-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "summary": {
            "providers": 4,
            "pointAccessEligibleProviders": 1,
            "pointAccessBlockedProviders": 3,
        },
        "providers": [
            provider_point("anmcs-2025-001", "SPITALUL TEST"),
            provider_point("anmcs-2025-002", "SPITALUL GENERAL C.F. TEST"),
            provider_point("anmcs-2025-003", "SPITALUL FARA CANDIDAT"),
            provider_point(
                "anmcs-2025-004",
                "SPITALUL DEJA ACCEPTAT",
                None,
                "ms-unitati-sanitare-009",
            ),
        ],
    }


def mart_provider(provider_id: str) -> dict:
    return {
        "providerId": provider_id,
        "ownerType": "public",
        "bedCount": 12.0,
        "specialties": ["cardiology"],
    }


def fixture_health_mart() -> dict:
    return {
        "id": "health-access-mart-2024-2025",
        "periodStart": "2024",
        "periodEnd": "2025",
        "records": [mart_provider(f"anmcs-2025-00{index}") for index in range(1, 5)],
    }


def source_record(
    source_record_id: str,
    name: str,
    has_street_address: bool = True,
) -> dict:
    return {
        "sourceRecordId": source_record_id,
        "name": name,
        "countyCode": "TS",
        "address": "Strada Test nr. 1" if has_street_address else name,
        "hasStreetAddress": has_street_address,
        "latitude": 44.1,
        "longitude": 26.1,
        "hasPublishedCoordinate": True,
        "detailUrl": f"https://ms.ro/ro/unitati-sanitare/{source_record_id}/",
    }


def fixture_address_source() -> dict:
    return {
        "id": "ministerul-sanatatii-unitati-sanitare-2026",
        "publisher": "Ministerul Sanatatii",
        "sourceUrl": "https://ms.ro/ro/unitati-sanitare/",
        "retrievedDate": "2026-09-09",
        "summary": {"sourceRecords": 3},
        "records": [
            source_record("ms-unitati-sanitare-001", "SPITALUL TEST", False),
            source_record("ms-unitati-sanitare-002", "Spitalul General Cai Ferate Test"),
            source_record("ms-unitati-sanitare-009", "Spitalul deja acceptat"),
        ],
    }


def fixture_address_aliases() -> dict:
    return {
        "id": "ministerul-sanatatii-unitati-sanitare-address-aliases-2026",
        "reviewedDate": "2026-09-09",
        "aliases": [],
    }


def test_build_document_reports_remaining_no_point_evidence_candidates():
    document = health_provider_point_review.build_document(
        fixture_provider_points(),
        fixture_health_mart(),
        fixture_address_source(),
        fixture_address_aliases(),
        {
            "providerPointsSha256": "a" * 64,
            "healthAccessMartSha256": "b" * 64,
            "msUnitatiSanitareSha256": "c" * 64,
            "msUnitatiSanitareAliasesSha256": "d" * 64,
        },
        "2026-09-09",
    )

    records = {record["providerId"]: record for record in document["records"]}

    assert list(records) == ["anmcs-2025-001", "anmcs-2025-002", "anmcs-2025-003"]
    assert records["anmcs-2025-001"]["candidateStatus"] == ("exact-source-row-lacks-street-address")
    assert records["anmcs-2025-001"]["candidates"][0]["reviewMethod"] == (
        "exact-normalised-name-county-without-street-address"
    )
    assert records["anmcs-2025-001"]["candidates"][0]["hasStreetAddress"] is False
    assert records["anmcs-2025-002"]["candidateStatus"] == ("has-unused-ministry-review-candidate")
    assert records["anmcs-2025-002"]["candidates"][0]["sourceRecordId"] == (
        "ms-unitati-sanitare-002"
    )
    assert records["anmcs-2025-002"]["candidates"][0]["reviewSignal"] == "high"
    assert records["anmcs-2025-003"]["candidateStatus"] == "no-ministry-review-candidate"
    assert records["anmcs-2025-003"]["candidateCount"] == 0

    assert document["summary"]["reviewProviders"] == 3
    assert document["summary"]["providersWithAnyCandidate"] == 2
    assert document["summary"]["candidateRows"] == 2
    assert document["summary"]["candidateStatus"] == {
        "exact-source-row-lacks-street-address": 1,
        "has-unused-ministry-review-candidate": 1,
        "no-ministry-review-candidate": 1,
    }
    assert document["summary"]["ministrySourceRecordsAlreadyMatched"] == 1
    assert document["summary"]["unusedMinistryStreetSourceRecords"] == 1


def test_committed_review_covers_remaining_service_eligible_no_point_rows():
    provider_points = json.loads(
        (DATA / "health-provider-points-2024-2026.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (DATA / "health-provider-point-evidence-review-2024-2026.json").read_text(encoding="utf-8")
    )

    expected_ids = {
        provider["providerId"]
        for provider in provider_points["providers"]
        if provider["serviceAccessEligible"]
        and provider["pointAccessBlockedReason"] == "no-point-evidence"
    }
    report_ids = {record["providerId"] for record in report["records"]}
    used_source_ids = {
        provider["addressSourceRecordId"]
        for provider in provider_points["providers"]
        if provider.get("addressSourceRecordId")
    }

    assert report["id"] == "health-provider-point-evidence-review-2024-2026"
    assert report_ids == expected_ids
    assert report["summary"]["reviewProviders"] == 118
    assert report["summary"]["providersWithAnyCandidate"] == 4
    assert report["summary"]["candidateRows"] == 8
    assert report["summary"]["candidateStatus"] == {
        "has-unused-ministry-review-candidate": 4,
        "no-ministry-review-candidate": 114,
    }
    assert report["summary"]["reviewSignal"] == {
        "low": 4,
        "none": 114,
    }
    assert report["summary"]["existingAddressAliases"] == 40

    remaining_candidate_ids = {
        record["providerId"]
        for record in report["records"]
        if record["candidateStatus"] != "no-ministry-review-candidate"
    }
    assert remaining_candidate_ids == {
        "anmcs-2025-038",
        "anmcs-2025-115",
        "anmcs-2025-140",
        "anmcs-2025-584",
    }

    for record in report["records"]:
        assert record["candidateCount"] == len(record["candidates"])
        assert record["pointAccessBlockedReason"] == "no-point-evidence"
        for candidate in record["candidates"]:
            assert candidate["countyCode"] == record["countyCode"]
            if candidate["reviewMethod"] == ("exact-normalised-name-county-without-street-address"):
                assert candidate["hasStreetAddress"] is False
            else:
                assert candidate["hasStreetAddress"] is True
                assert candidate["sourceRecordId"] not in used_source_ids

    limitation_ids = {limitation["id"] for limitation in report["limitations"]}
    assert "review-report-not-point-evidence" in limitation_ids
    assert "token-overlap-is-not-fuzzy-acceptance" in limitation_ids
    assert "exact-source-row-may-still-lack-street-address" in limitation_ids


def test_committed_review_report_is_reproducible():
    expected = json.loads(
        (DATA / "health-provider-point-evidence-review-2024-2026.json").read_text(encoding="utf-8")
    )

    rebuilt = health_provider_point_review.build_from_files(
        DATA / "health-provider-points-2024-2026.json",
        DATA / "health-access-mart-2024-2025.json",
        SOURCES / "ms-unitati-sanitare-2026.json",
        SOURCES / "ms-unitati-sanitare-address-aliases-2026.json",
        expected["retrievedDate"],
    )

    assert rebuilt == expected

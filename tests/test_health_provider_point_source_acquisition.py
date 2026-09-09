from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILDER = (
    ROOT
    / "packages"
    / "health_access"
    / "scripts"
    / "build_health_provider_point_source_acquisition.py"
)
DATA = ROOT / "packages" / "health_access" / "data"

spec = importlib.util.spec_from_file_location("build_health_source_acquisition", BUILDER)
assert spec and spec.loader
health_source_acquisition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_source_acquisition)


def provider_point(provider_id: str, blocked_reason: str | None = "no-point-evidence") -> dict:
    return {
        "providerId": provider_id,
        "serviceAccessEligible": blocked_reason is not None,
        "pointAccessBlockedReason": blocked_reason,
    }


def fixture_provider_points(provider_ids: list[str]) -> dict:
    return {
        "id": "health-provider-points-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "summary": {
            "providers": len(provider_ids),
            "pointAccessEligibleProviders": 0,
            "pointAccessBlockedProviders": len(provider_ids),
        },
        "providers": [provider_point(provider_id) for provider_id in provider_ids],
    }


def candidate(source_record_id: str) -> dict:
    return {
        "sourceRecordId": source_record_id,
        "reviewMethod": "locality-name-token-overlap-same-county-unused-source",
    }


def review_record(
    provider_id: str,
    candidate_status: str = "no-ministry-review-candidate",
    owner_type: str = "public",
    bed_count: float | None = None,
) -> dict:
    candidates = (
        [candidate("ms-unitati-sanitare-001")]
        if candidate_status == "has-unused-ministry-review-candidate"
        else []
    )
    return {
        "providerId": provider_id,
        "name": f"SPITALUL {provider_id}",
        "countyCode": "TS",
        "countyName": "Test",
        "siruta": "101",
        "localityName": "MUNICIPIUL TEST",
        "locationConfidence": "name-derived-locality",
        "ownerType": owner_type,
        "bedCount": bed_count,
        "specialties": ["cardiology"] if bed_count else [],
        "pointAccessBlockedReason": "no-point-evidence",
        "candidateStatus": candidate_status,
        "reviewSignal": "low" if candidates else "none",
        "candidateCount": len(candidates),
        "candidates": candidates,
    }


def fixture_point_review(records: list[dict]) -> dict:
    return {
        "id": "health-provider-point-evidence-review-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "summary": {"reviewProviders": len(records)},
        "records": records,
    }


def test_build_document_prioritises_remaining_review_rows():
    records = [
        review_record("anmcs-2025-001", "has-unused-ministry-review-candidate"),
        review_record("anmcs-2025-002", bed_count=120.0),
        review_record("anmcs-2025-003"),
        review_record("anmcs-2025-004", owner_type="private"),
    ]
    document = health_source_acquisition.build_document(
        fixture_provider_points([record["providerId"] for record in records]),
        fixture_point_review(records),
        {"providerPointsSha256": "a" * 64, "providerPointReviewSha256": "b" * 64},
        "2026-09-09",
    )

    assert document["id"] == "health-provider-point-source-acquisition-2024-2026"
    assert [record["providerId"] for record in document["records"]] == [
        "anmcs-2025-001",
        "anmcs-2025-002",
        "anmcs-2025-003",
        "anmcs-2025-004",
    ]
    assert document["summary"]["acquisitionStatus"] == {
        "needs-new-source": 3,
        "needs-provider-specific-evidence": 1,
    }
    assert document["summary"]["acquisitionPriority"] == {
        "p1-locality-candidate-needs-provider-evidence": 1,
        "p2-public-bed-provider-no-ministry-candidate": 1,
        "p3-public-provider-no-ministry-candidate": 1,
        "p4-private-or-unknown-provider-no-ministry-candidate": 1,
    }
    assert document["summary"]["sourceSearchTypes"] == {
        "cnas-or-official-contracting-list": 4,
        "dsp-or-local-authority-list": 4,
        "ministry-locality-candidate-provider-verification": 1,
        "osm-named-feature-manual-review": 4,
        "provider-official-website": 4,
    }

    first = document["records"][0]
    assert first["acquisitionStatus"] == "needs-provider-specific-evidence"
    assert first["ministryCandidateSourceRecordIds"] == ["ms-unitati-sanitare-001"]
    assert "verified-ministry-source-row-alias" in first["acceptableEvidence"]
    assert first["nextAction"] == "verify-locality-only-ministry-candidate-with-provider-source"


def test_build_document_rejects_stale_review_rows():
    with pytest.raises(ValueError, match="do not match provider-point"):
        health_source_acquisition.build_document(
            fixture_provider_points(["anmcs-2025-001"]),
            fixture_point_review([review_record("anmcs-2025-002")]),
            {"providerPointsSha256": "a" * 64, "providerPointReviewSha256": "b" * 64},
            "2026-09-09",
        )


def test_committed_source_acquisition_queue_covers_remaining_review_rows():
    provider_points = json.loads(
        (DATA / "health-provider-points-2024-2026.json").read_text(encoding="utf-8")
    )
    point_review = json.loads(
        (DATA / "health-provider-point-evidence-review-2024-2026.json").read_text(encoding="utf-8")
    )
    acquisition = json.loads(
        (DATA / "health-provider-point-source-acquisition-2024-2026.json").read_text(
            encoding="utf-8"
        )
    )

    review_ids = {record["providerId"] for record in point_review["records"]}
    acquisition_ids = {record["providerId"] for record in acquisition["records"]}
    no_point_ids = {
        provider["providerId"]
        for provider in provider_points["providers"]
        if provider["serviceAccessEligible"]
        and provider["pointAccessBlockedReason"] == "no-point-evidence"
    }

    assert acquisition_ids == review_ids == no_point_ids
    assert acquisition["summary"]["providerPoints"] == 592
    assert acquisition["summary"]["pointAccessEligibleProviders"] == 206
    assert acquisition["summary"]["pointAccessBlockedProviders"] == 386
    assert acquisition["summary"]["reviewProviders"] == 118
    assert acquisition["summary"]["acquisitionProviders"] == 118
    assert acquisition["summary"]["localityOnlyCandidateProviders"] == 4
    assert acquisition["summary"]["noMinistryCandidateProviders"] == 114
    assert acquisition["summary"]["publicBedNoCandidateProviders"] == 13
    assert acquisition["summary"]["acquisitionStatus"] == {
        "needs-new-source": 114,
        "needs-provider-specific-evidence": 4,
    }
    assert acquisition["summary"]["acquisitionPriority"] == {
        "p1-locality-candidate-needs-provider-evidence": 4,
        "p2-public-bed-provider-no-ministry-candidate": 13,
        "p3-public-provider-no-ministry-candidate": 45,
        "p4-private-or-unknown-provider-no-ministry-candidate": 56,
    }
    assert acquisition["summary"]["sourceSearchTypes"] == {
        "cnas-or-official-contracting-list": 118,
        "dsp-or-local-authority-list": 118,
        "ministry-locality-candidate-provider-verification": 4,
        "osm-named-feature-manual-review": 118,
        "provider-official-website": 118,
    }

    locality_candidate_ids = {
        record["providerId"]
        for record in acquisition["records"]
        if record["acquisitionPriority"] == "p1-locality-candidate-needs-provider-evidence"
    }
    assert locality_candidate_ids == {
        "anmcs-2025-038",
        "anmcs-2025-115",
        "anmcs-2025-140",
        "anmcs-2025-584",
    }
    assert all(
        record["candidateStatus"] != "has-unused-ministry-review-candidate"
        or record["reviewSignal"] == "low"
        for record in acquisition["records"]
    )

    limitation_ids = {limitation["id"] for limitation in acquisition["limitations"]}
    assert "source-acquisition-not-point-evidence" in limitation_ids
    assert "locality-only-ministry-candidates-not-accepted" in limitation_ids
    assert "external-source-license-must-be-recorded" in limitation_ids


def test_committed_source_acquisition_queue_is_reproducible():
    expected = json.loads(
        (DATA / "health-provider-point-source-acquisition-2024-2026.json").read_text(
            encoding="utf-8"
        )
    )

    rebuilt = health_source_acquisition.build_from_files(
        DATA / "health-provider-points-2024-2026.json",
        DATA / "health-provider-point-evidence-review-2024-2026.json",
        expected["retrievedDate"],
    )

    assert rebuilt == expected

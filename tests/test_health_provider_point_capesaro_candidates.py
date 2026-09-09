from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = (
    ROOT / "packages" / "health_access" / "scripts" / "import_anmcs_capesaro_public_hospitals.py"
)
CANDIDATE_BUILDER = (
    ROOT
    / "packages"
    / "health_access"
    / "scripts"
    / "build_health_provider_point_capesaro_candidates.py"
)
DATA = ROOT / "packages" / "health_access" / "data"
SOURCES = ROOT / "packages" / "health_access" / "sources"

importer_spec = importlib.util.spec_from_file_location("import_capesaro", IMPORTER)
assert importer_spec and importer_spec.loader
import_capesaro = importlib.util.module_from_spec(importer_spec)
importer_spec.loader.exec_module(import_capesaro)

builder_spec = importlib.util.spec_from_file_location(
    "build_capesaro_candidates", CANDIDATE_BUILDER
)
assert builder_spec and builder_spec.loader
build_capesaro_candidates = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(build_capesaro_candidates)


def raw_capesaro_row(
    source_id: str,
    source_code: str | None,
    name: str,
    county_name: str = "Test",
    active: str = "1",
    address: str = "Str. Test nr. 1",
) -> dict:
    return {
        "general": {
            "id": source_id,
            "cod_anmcs": source_code,
            "name": name,
            "active": active,
            "lat": "44.100000",
            "lng": "26.100000",
            "address_sediu_social": address,
            "website": "example.test",
            "judet": county_name,
            "city": "Municipiul Test",
        }
    }


def capesaro_source_record(
    source_code: str,
    name: str,
    county_code: str = "TS",
    active: bool = True,
    has_street_address: bool = True,
) -> dict:
    return {
        "sourceRecordId": f"capesaro-2026-{source_code}",
        "sourceOrdinal": 1,
        "sourceNativeId": "28022000",
        "sourceCode": source_code,
        "name": name,
        "countyCode": county_code,
        "sourceCountyName": "Test",
        "sourceCity": "Municipiul Test",
        "address": "Strada Test nr. 1",
        "hasStreetAddress": has_street_address,
        "latitude": 44.1,
        "longitude": 26.1,
        "hasPublishedCoordinate": True,
        "website": "example.test",
        "active": active,
    }


def fixture_capesaro_source(records: list[dict]) -> dict:
    return {
        "id": "anmcs-capesaro-public-hospitals-2026",
        "publisher": "Autoritatea Nationala de Management al Calitatii in Sanatate",
        "sourceUrl": "https://capesaro.gov.ro/hospitals_public.php?ajax=1",
        "retrievedDate": "2026-09-09",
        "summary": {
            "sourceRecords": len(records),
            "activeSourceRecords": sum(1 for record in records if record["active"]),
        },
        "records": records,
    }


def acquisition_record(
    provider_id: str,
    name: str,
    county_code: str = "TS",
    owner_type: str = "public",
) -> dict:
    return {
        "providerId": provider_id,
        "name": name,
        "countyCode": county_code,
        "countyName": "Test",
        "siruta": "101",
        "localityName": "MUNICIPIUL TEST",
        "ownerType": owner_type,
        "acquisitionPriority": (
            "p3-public-provider-no-ministry-candidate"
            if owner_type == "public"
            else "p4-private-or-unknown-provider-no-ministry-candidate"
        ),
    }


def fixture_source_acquisition(records: list[dict]) -> dict:
    return {
        "id": "health-provider-point-source-acquisition-2024-2026",
        "periodStart": "2024",
        "periodEnd": "2026",
        "summary": {"acquisitionProviders": len(records)},
        "records": records,
    }


def test_importer_builds_compact_capesaro_source_extract():
    raw_source = json.dumps(
        [
            raw_capesaro_row("28022001", "A001", "SPITALUL TEST", "București"),
            raw_capesaro_row("28022002", None, "SPITALUL FARA COD", "Cluj", address=""),
        ]
    )

    document = import_capesaro.build_document(raw_source, "2026-09-09")

    assert document["id"] == "anmcs-capesaro-public-hospitals-2026"
    assert document["summary"]["sourceRecords"] == 2
    assert document["summary"]["activeSourceRecords"] == 2
    assert document["summary"]["sourceRecordsWithCounty"] == 2
    assert document["summary"]["sourceRecordsWithStreetAddress"] == 1
    assert document["summary"]["sourceRecordsWithCoordinates"] == 2
    assert document["records"][0]["sourceRecordId"] == "capesaro-2026-A001"
    assert document["records"][0]["countyCode"] == "B"
    assert document["records"][1]["sourceRecordId"] == "capesaro-2026-id-28022002"
    assert document["records"][1]["sourceCode"] is None
    assert document["records"][1]["hasStreetAddress"] is False


def test_build_document_reports_capesaro_candidates_without_promoting_evidence():
    document = build_capesaro_candidates.build_document(
        fixture_source_acquisition(
            [
                acquisition_record("anmcs-2025-001", "SPITALUL TEST"),
                acquisition_record("anmcs-2025-002", "SPITALUL FARA CANDIDAT"),
                acquisition_record(
                    "anmcs-2025-003",
                    "SOCIETATEA TEST HEALTH S.R.L.",
                    owner_type="private",
                ),
            ]
        ),
        fixture_capesaro_source(
            [
                capesaro_source_record("A001", "SPITALUL TEST"),
                capesaro_source_record("A002", "SPITALUL TEST", county_code="CJ"),
                capesaro_source_record("A003", "SPITALUL FARA CANDIDAT", active=False),
                capesaro_source_record("B001", "SOCIETATEA TEST HEALTH S.R.L."),
                capesaro_source_record("B002", "SOCIETATEA TEST HEALTH S.R.L.", active=False),
            ]
        ),
        {"sourceAcquisitionSha256": "a" * 64, "capesaroSourceSha256": "b" * 64},
        "2026-09-09",
    )

    by_provider = {record["providerId"]: record for record in document["records"]}

    assert document["id"] == "health-provider-point-capesaro-candidates-2024-2026"
    assert document["scope"] == "provider-point-capesaro-candidate-review"
    assert document["summary"]["sourceAcquisitionProviders"] == 3
    assert document["summary"]["providersWithCandidates"] == 2
    assert document["summary"]["providersWithoutCandidates"] == 1
    assert document["summary"]["candidateRows"] == 2
    assert document["summary"]["publicProvidersWithCandidates"] == 1
    assert document["summary"]["candidateStatus"] == {
        "has-capesaro-candidate": 2,
        "no-capesaro-candidate": 1,
    }
    assert by_provider["anmcs-2025-001"]["candidateSignal"] == "high"
    assert by_provider["anmcs-2025-001"]["candidates"][0]["sourceRecordId"] == (
        "capesaro-2026-A001"
    )
    assert by_provider["anmcs-2025-002"]["candidateSignal"] == "none"
    assert by_provider["anmcs-2025-002"]["nextAction"] == "continue-other-source-acquisition"
    assert by_provider["anmcs-2025-003"]["nextAction"] == (
        "review-capesaro-source-row-for-supplemental-evidence"
    )

    limitation_ids = {limitation["id"] for limitation in document["limitations"]}
    assert "candidate-report-not-point-evidence" in limitation_ids


def test_committed_capesaro_candidate_report_covers_remaining_acquisition_queue():
    if (
        not (SOURCES / "anmcs-capesaro-public-hospitals-2026.json").exists()
        or not (DATA / "health-provider-point-capesaro-candidates-2024-2026.json").exists()
    ):
        pytest.skip("CAPeSaRo release assets were not fetched")

    source_acquisition = json.loads(
        (DATA / "health-provider-point-source-acquisition-2024-2026.json").read_text(
            encoding="utf-8"
        )
    )
    capesaro_source = json.loads(
        (SOURCES / "anmcs-capesaro-public-hospitals-2026.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (DATA / "health-provider-point-capesaro-candidates-2024-2026.json").read_text(
            encoding="utf-8"
        )
    )

    acquisition_ids = {record["providerId"] for record in source_acquisition["records"]}
    report_ids = {record["providerId"] for record in report["records"]}
    source_by_id = {record["sourceRecordId"]: record for record in capesaro_source["records"]}

    assert report_ids == acquisition_ids
    assert capesaro_source["summary"] == {
        "sourceRecords": 731,
        "activeSourceRecords": 680,
        "sourceRecordsWithCounty": 731,
        "sourceRecordsWithStreetAddress": 687,
        "sourceRecordsWithCoordinates": 731,
        "duplicateSourceCodes": 0,
        "duplicateSourceNames": 3,
    }
    assert report["summary"]["sourceAcquisitionProviders"] == 72
    assert report["summary"]["capesaroSourceRecords"] == 731
    assert report["summary"]["activeCapesaroSourceRecords"] == 680
    assert report["summary"]["providersWithCandidates"] == 24
    assert report["summary"]["providersWithoutCandidates"] == 48
    assert report["summary"]["candidateRows"] == 28
    assert report["summary"]["publicProviders"] == 16
    assert report["summary"]["publicProvidersWithCandidates"] == 6
    assert report["summary"]["publicProvidersWithoutCandidates"] == 10
    assert report["summary"]["candidateSignals"] == {
        "high": 9,
        "low": 7,
        "medium": 8,
        "none": 48,
    }
    assert report["summary"]["candidateMatchMethods"] == {
        "contained-normalised-name-county": 7,
        "exact-normalised-name-county": 9,
        "token-overlap-same-county": 4,
        "weak-token-overlap-same-county": 8,
    }
    assert report["summary"]["candidateOwnerTypes"] == {
        "private": 17,
        "public": 6,
        "unknown": 1,
    }

    for record in report["records"]:
        assert record["candidateCount"] == len(record["candidates"])
        for candidate in record["candidates"]:
            source_record = source_by_id[candidate["sourceRecordId"]]
            assert source_record["countyCode"] == record["countyCode"]
            assert source_record["active"] is True
            assert source_record["hasStreetAddress"] is True
            assert source_record["hasPublishedCoordinate"] is True

    limitation_ids = {limitation["id"] for limitation in report["limitations"]}
    assert "candidate-report-not-point-evidence" in limitation_ids
    assert "token-overlap-is-review-only" in limitation_ids
    assert "inactive-or-incomplete-capesaro-rows-excluded" in limitation_ids


def test_committed_capesaro_candidate_report_is_reproducible():
    if (
        not (SOURCES / "anmcs-capesaro-public-hospitals-2026.json").exists()
        or not (DATA / "health-provider-point-capesaro-candidates-2024-2026.json").exists()
    ):
        pytest.skip("CAPeSaRo release assets were not fetched")

    expected = json.loads(
        (DATA / "health-provider-point-capesaro-candidates-2024-2026.json").read_text(
            encoding="utf-8"
        )
    )

    rebuilt = build_capesaro_candidates.build_from_files(
        DATA / "health-provider-point-source-acquisition-2024-2026.json",
        SOURCES / "anmcs-capesaro-public-hospitals-2026.json",
        expected["retrievedDate"],
    )

    assert rebuilt == expected

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "packages" / "health_access" / "scripts" / "import_health_access.py"
ACCESS_BUILDER = ROOT / "packages" / "health_access" / "scripts" / "build_health_service_access.py"
DATA = ROOT / "packages" / "health_access" / "data"

spec = importlib.util.spec_from_file_location("import_health_access", IMPORTER)
assert spec and spec.loader
health_access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_access)

access_spec = importlib.util.spec_from_file_location("build_health_service_access", ACCESS_BUILDER)
assert access_spec and access_spec.loader
health_service_access = importlib.util.module_from_spec(access_spec)
access_spec.loader.exec_module(health_service_access)


def provider(provider_id: str, name: str, county_code: str = "B") -> dict:
    return {
        "providerId": provider_id,
        "name": name,
        "countyCode": county_code,
    }


def clinical(row: int, name: str, beds: float) -> dict:
    return {
        "clinicalRow": row,
        "sheetRow": row + 10,
        "name": name,
        "bedCount": beds,
        "specialtyBeds": {},
        "specialties": [],
    }


def fixture_registry() -> dict:
    return {
        "id": "uat-registry-2026",
        "period": "2026",
        "units": [
            {
                "siruta": "179132",
                "name": "MUNICIPIUL BUCURESTI",
                "shortName": "BUCURESTI",
                "level": "municipality",
                "countyCode": "B",
            },
            {
                "siruta": "54975",
                "name": "MUNICIPIUL CLUJ-NAPOCA",
                "shortName": "CLUJ-NAPOCA",
                "level": "municipality",
                "countyCode": "CJ",
            },
            {
                "siruta": "55008",
                "name": "MUNICIPIUL DEJ",
                "shortName": "DEJ",
                "level": "municipality",
                "countyCode": "CJ",
            },
        ],
    }


def fixture_access_registry() -> dict:
    return {
        "id": "uat-registry-2026",
        "period": "2026",
        "units": [
            {
                "siruta": "100",
                "name": "JUDETUL TEST",
                "shortName": "TEST",
                "level": "county",
                "countyCode": "TS",
                "countyName": "Test",
                "population": 10_000,
                "populationSource": "fixture",
            },
            {
                "siruta": "101",
                "name": "MUNICIPIUL TEST",
                "shortName": "TEST",
                "level": "municipality",
                "countyCode": "TS",
                "countyName": "Test",
                "population": 8_000,
                "populationSource": "fixture",
            },
            {
                "siruta": "102",
                "name": "COMUNA LIPSITA",
                "shortName": "LIPSITA",
                "level": "commune",
                "countyCode": "TS",
                "countyName": "Test",
                "population": 2_000,
                "populationSource": "fixture",
            },
            {
                "siruta": "103",
                "name": "TEST SECTORUL 1",
                "shortName": "SECTORUL 1",
                "level": "sector",
                "countyCode": "TS",
                "countyName": "Test",
                "population": None,
                "populationSource": None,
            },
        ],
    }


def access_provider(
    provider_id: str,
    siruta: str | None,
    eligible: bool,
    bed_count: float | None = None,
) -> dict:
    return {
        "providerId": provider_id,
        "name": f"SPITALUL {provider_id}",
        "countyCode": "TS",
        "countyName": "Test",
        "siruta": siruta,
        "localityName": "MUNICIPIUL TEST" if siruta else None,
        "locationConfidence": "name-derived-locality" if siruta else "county-only",
        "locationEvidence": {
            "method": "provider-name-locality-match" if siruta else "county-only-source",
            "sourceFields": ["fixture"],
            "sourceValue": "fixture",
            "accessUse": "eligible-for-uat-level-access" if eligible else "blocked-county-only",
        },
        "serviceAccessEligible": eligible,
        "ownerType": "public",
        "bedCount": bed_count,
        "specialties": ["cardiology"] if bed_count else [],
        "specialtyBeds": {},
        "accreditationCategory": "fixture",
        "accreditationScore": None,
        "accreditationDecision": None,
        "accreditationOrder": None,
        "accreditationPeriod": None,
        "sourceRows": {
            "anmcsOrdinal": 1,
            "anmcsSheetRow": 1,
            "clinicalBedsRow": None,
            "clinicalBedsSheetRow": None,
        },
    }


def fixture_health_mart() -> dict:
    return {
        "id": "health-access-mart-2024-2025",
        "periodStart": "2024",
        "periodEnd": "2025",
        "summary": {
            "scopeCounties": ["TS"],
            "byCounty": [{"countyCode": "TS", "countyName": "Test"}],
        },
        "records": [
            access_provider("anmcs-2025-001", "101", True, 12.0),
            access_provider("anmcs-2025-002", None, False),
        ],
    }


def test_clinical_matching_rejects_generic_and_wrong_city_rows():
    providers = [
        provider("anmcs-2025-009", "SPITALUL CLINIC FILANTROPIA BUCURESTI"),
        provider("anmcs-2025-132", "SPITALUL CLINIC JUDETEAN DE URGENTA ILFOV"),
        provider(
            "anmcs-2025-005",
            'SPITALUL UNIVERSITAR DE URGENTA MILITAR CENTRAL "DR. CAROL DAVILA"',
        ),
        provider("anmcs-2025-195", 'SPITALUL ORASENESC "PROF.DR. IOAN PUSCAS"'),
        provider("anmcs-2025-368", "CLINICA SF. LUCIA S.R.L."),
    ]
    clinical_rows = [
        clinical(26, 'Spit. clinc municipal "Filantropia" Craiova', 495),
        clinical(47, "Spit. clinic judetean de urgenta Ilfov", 171),
        clinical(66, 'Spit. clinic "Filantropia"', 116),
        clinical(94, "Spit. Universitar de Urgenta Bucuresti", 1099),
        clinical(89, 'Spit.Clinic de Urgenta "Sf.Ioan"', 430),
    ]

    matches = health_access.match_clinical_rows(providers, clinical_rows)

    assert matches["anmcs-2025-009"]["clinicalRow"] == 66
    assert matches["anmcs-2025-132"]["clinicalRow"] == 47
    assert "anmcs-2025-005" not in matches
    assert "anmcs-2025-195" not in matches
    assert "anmcs-2025-368" not in matches


def test_location_derivation_uses_registry_and_bucharest_municipality():
    index = health_access.registry_index(fixture_registry())

    dej = health_access.locate_provider(
        provider("anmcs-2025-200", "SPITALUL MUNICIPAL DEJ", "CJ"), index
    )
    cluj = health_access.locate_provider(
        provider("anmcs-2025-201", "SPITALUL CLINIC CLUJ-NAPOCA", "CJ"), index
    )
    bucharest = health_access.locate_provider(
        provider("anmcs-2025-202", "SPITALUL CLINIC COLTEA", "B"), index
    )

    assert dej["siruta"] == "55008"
    assert dej["locationConfidence"] == "name-derived-locality"
    assert dej["locationEvidence"]["method"] == "provider-name-locality-match"
    assert health_access.service_access_eligible(dej)
    assert cluj["siruta"] == "54975"
    assert bucharest["siruta"] == "179132"
    assert bucharest["locationConfidence"] == "municipality-from-county"
    assert bucharest["locationEvidence"]["accessUse"] == "eligible-for-uat-level-access"
    assert health_access.service_access_eligible(bucharest)

    blocked = health_access.locate_provider(
        provider("anmcs-2025-203", "SPITALUL FARA LOCALITATE", "CJ"), index
    )
    assert blocked["siruta"] is None
    assert blocked["locationConfidence"] == "county-only"
    assert blocked["locationEvidence"]["accessUse"] == "blocked-county-only"
    assert not health_access.service_access_eligible(blocked)


def test_health_service_access_counts_only_eligible_uat_providers():
    document = health_service_access.build_document(
        fixture_health_mart(),
        fixture_access_registry(),
        {
            "healthAccessMartSha256": "a" * 64,
            "uatRegistrySha256": "b" * 64,
        },
        "2026-09-09",
    )
    units_by_siruta = {unit["siruta"]: unit for unit in document["units"]}

    assert document["summary"]["uats"] == 2
    assert document["summary"]["uatsWithLocalProvider"] == 1
    assert document["summary"]["eligibleProviders"] == 1
    assert document["summary"]["blockedProviders"] == 1
    assert document["summary"]["namedExclusions"] == 1
    assert document["summary"]["excludedSectorRows"] == 1
    assert units_by_siruta["101"]["localProviderCount"] == 1
    assert units_by_siruta["101"]["localClinicalBeds"] == 12.0
    assert units_by_siruta["101"]["localSpecialties"] == ["cardiology"]
    assert units_by_siruta["102"]["localProviderCount"] == 0
    assert units_by_siruta["101"]["countyBlockedProviderCount"] == 1
    assert all(unit["level"] != "sector" for unit in document["units"])
    assert document["exclusions"][0]["providerId"] == "anmcs-2025-002"


def test_committed_health_access_mart_covers_national_scope():
    document = json.loads((DATA / "health-access-mart-2024-2025.json").read_text(encoding="utf-8"))
    records = document["records"]
    by_id = {record["providerId"]: record for record in records}

    assert document["id"] == "health-access-mart-2024-2025"
    assert document["scope"] == "national"
    assert len(document["summary"]["scopeCounties"]) == 42
    assert document["summary"]["records"] == 592
    assert document["summary"]["providersWithClinicalBeds"] == 68
    assert document["summary"]["providersWithoutClinicalBeds"] == 524
    assert document["summary"]["countyTotalBeds"] == 116828.0
    assert document["summary"]["locationConfidence"]["county-only"] == 268
    assert document["summary"]["serviceAccessEligibleProviders"] == 324
    assert document["summary"]["serviceAccessBlockedProviders"] == 268
    assert by_id["anmcs-2025-009"]["sourceRows"]["clinicalBedsRow"] == 66
    assert by_id["anmcs-2025-024"]["sourceRows"]["clinicalBedsRow"] == 18
    assert by_id["anmcs-2025-028"]["sourceRows"]["clinicalBedsRow"] == 20
    assert by_id["anmcs-2025-005"]["bedCount"] is None
    assert by_id["anmcs-2025-368"]["bedCount"] is None
    assert by_id["anmcs-2025-132"]["sourceRows"]["clinicalBedsRow"] == 47
    assert all(record["sourceRows"]["clinicalBedsRow"] != 89 for record in records)
    assert any(
        exclusion["source"] == "clinical-beds"
        and exclusion["name"] == 'Spit.Clinic de Urgenţă "Sf.Ioan"'
        and exclusion["countyCode"] is None
        for exclusion in document["exclusions"]
    )
    assert any(
        record["countyCode"] == "CJ" and record["siruta"] == "54975" and record["bedCount"]
        for record in records
    )
    assert all(
        record["serviceAccessEligible"]
        == (
            record["siruta"] is not None
            and record["locationConfidence"] != "county-only"
            and record["locationEvidence"]["accessUse"] == "eligible-for-uat-level-access"
        )
        for record in records
    )
    blocked_provider_names = {
        record["name"] for record in records if not record["serviceAccessEligible"]
    }
    assert all(
        exclusion["name"] in blocked_provider_names
        for exclusion in document["exclusions"]
        if exclusion["kind"] == "provider-without-uat-location"
    )
    assert {
        "clinical-beds-provider-scope-is-partial",
        "location-derived-from-provider-name",
        "bucharest-sector-not-identifiable",
    } <= {limitation["id"] for limitation in document["limitations"]}


def test_committed_health_service_access_uses_only_eligible_providers():
    mart = json.loads((DATA / "health-access-mart-2024-2025.json").read_text(encoding="utf-8"))
    access = json.loads(
        (DATA / "health-service-access-uat-2024-2026.json").read_text(encoding="utf-8")
    )
    eligible_provider_ids = {
        record["providerId"] for record in mart["records"] if record["serviceAccessEligible"]
    }
    blocked_provider_ids = {
        record["providerId"] for record in mart["records"] if not record["serviceAccessEligible"]
    }
    provider_ids_in_view = {
        provider["providerId"] for unit in access["units"] for provider in unit["localProviders"]
    }
    excluded_provider_ids = {exclusion["providerId"] for exclusion in access["exclusions"]}

    assert access["id"] == "health-service-access-uat-2024-2026"
    assert access["summary"]["uats"] == 3181
    assert (
        access["summary"]["eligibleProviders"] == mart["summary"]["serviceAccessEligibleProviders"]
    )
    assert access["summary"]["blockedProviders"] == mart["summary"]["serviceAccessBlockedProviders"]
    assert access["summary"]["namedExclusions"] == len(blocked_provider_ids)
    assert access["summary"]["excludedSectorRows"] == 6
    assert provider_ids_in_view == eligible_provider_ids
    assert excluded_provider_ids == blocked_provider_ids
    assert provider_ids_in_view.isdisjoint(excluded_provider_ids)
    assert all(unit["level"] != "sector" for unit in access["units"])
    assert access["summary"]["populationWithLocalProvider"] == sum(
        unit["population"] or 0 for unit in access["units"] if unit["hasLocalProvider"]
    )
    assert {
        "uat-colocation-not-travel-time",
        "county-only-providers-excluded",
        "bucharest-sectors-excluded",
    } <= {limitation["id"] for limitation in access["limitations"]}

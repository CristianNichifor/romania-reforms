from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "packages" / "health_access" / "scripts" / "import_health_access.py"
DATA = ROOT / "packages" / "health_access" / "data"

spec = importlib.util.spec_from_file_location("import_health_access", IMPORTER)
assert spec and spec.loader
health_access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_access)


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
    assert cluj["siruta"] == "54975"
    assert bucharest["siruta"] == "179132"
    assert bucharest["locationConfidence"] == "municipality-from-county"


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
    assert {
        "clinical-beds-provider-scope-is-partial",
        "location-derived-from-provider-name",
        "bucharest-sector-not-identifiable",
    } <= {limitation["id"] for limitation in document["limitations"]}

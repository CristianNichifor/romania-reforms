from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
BUILDER = (
    ROOT
    / "packages"
    / "public_enterprise_governance"
    / "scripts"
    / "build_public_enterprise_administrative_footprint.py"
)
DATA = ROOT / "packages" / "public_enterprise_governance" / "data"
FOOTPRINT = DATA / "public-enterprise-administrative-footprint-2024-2026.json"
SCHEMA = (
    ROOT
    / "packages"
    / "public_enterprise_governance"
    / "schema"
    / "public-enterprise-administrative-footprint.schema.json"
)

spec = importlib.util.spec_from_file_location("build_public_enterprise_footprint", BUILDER)
assert spec and spec.loader
build_public_enterprise_footprint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_public_enterprise_footprint)

sys.path.insert(0, str(ROOT / "scripts"))
from validate_data import registry  # noqa: E402


def registry_doc() -> dict[str, Any]:
    return {
        "id": "uat-registry-2026",
        "period": "2026",
        "units": [
            {
                "siruta": "10",
                "name": "JUDETUL TEST",
                "shortName": "TEST",
                "level": "county",
                "countyCode": "TS",
                "countyName": "TEST",
                "cui": "900",
                "population": 10000,
            },
            {
                "siruta": "100",
                "name": "MUNICIPIUL ALPHA",
                "shortName": "ALPHA",
                "level": "municipality",
                "countyCode": "TS",
                "countyName": "TEST",
                "cui": "1000",
                "population": 7000,
            },
            {
                "siruta": "200",
                "name": "ALPHA",
                "shortName": "ALPHA",
                "level": "commune",
                "countyCode": "OT",
                "countyName": "OTHER",
                "cui": "2000",
                "population": 3000,
            },
        ],
    }


def test_build_document_aggregates_to_uats_and_keeps_unmatched_exclusions() -> None:
    document = build_public_enterprise_footprint.build_document(
        anexa3={
            "companies": [
                {
                    "cui": "1",
                    "name": "Company A",
                    "apt": "CONSILIUL LOCAL ALPHA",
                    "tip_apt": "Local-Consiliu Local",
                    "stare": "funcțiune",
                    "status": "PROFIT",
                },
                {
                    "cui": "1",
                    "name": "Company A duplicate",
                    "apt": "CONSILIUL LOCAL ALPHA",
                    "tip_apt": "Local-Consiliu Local",
                    "stare": "funcțiune",
                    "status": "PROFIT",
                },
                {
                    "cui": "2",
                    "name": "Company B",
                    "apt": "CONSILIUL LOCAL MISSING",
                    "tip_apt": "Local-Consiliu Local",
                    "stare": "funcțiune",
                    "status": "PIERDERE",
                },
            ]
        },
        mfin={
            "companii": {
                "1": {
                    "cifra_afaceri": 1000,
                    "profit_net": 100,
                    "pierdere_neta": 0,
                    "datorii": 40,
                    "nr_salariati": 5,
                }
            }
        },
        search={"companii": {"1": {"judet_nume": "TEST"}}},
        registry=registry_doc(),
        subsidies={"years": {"2025": {"uats": [{"cui": "1000", "total": 250}]}}},
        hashes={
            "anexa3SummarySha256": "a" * 64,
            "mfinBilanturiSha256": "b" * 64,
            "companiiSearchSha256": "c" * 64,
            "subventiiLocaleSha256": "d" * 64,
            "uatRegistrySha256": "e" * 64,
        },
        retrieved_date="2026-09-10",
    )

    assert document["summary"]["companyCount"] == 1
    assert document["summary"]["duplicateCompanyRows"] == 1
    assert document["summary"]["unmatchedCompanies"] == 1
    assert document["uats"] == [
        {
            "siruta": "100",
            "name": "MUNICIPIUL ALPHA",
            "level": "municipality",
            "countyCode": "TS",
            "countyName": "TEST",
            "population": 7000,
            "authorityCount": 1,
            "companyCount": 1,
            "activeCompanyCount": 1,
            "companiesWithFinancials": 1,
            "lossMakingCompanyCount": 0,
            "subsidizedCompanyCount": 0,
            "employeeCount": 5,
            "revenueRon": 1000.0,
            "profitLossRon": 100.0,
            "debtRon": 40.0,
            "subsidiesRon": 250.0,
        }
    ]
    assert {row["reason"] for row in document["exclusions"]} == {
        "duplicate-company-authority",
        "unmatched-authority",
    }


def test_committed_footprint_validates_and_does_not_ship_company_rows() -> None:
    document = json.loads(FOOTPRINT.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))

    assert errors == []
    assert document["summary"]["companyCount"] > 1000
    forbidden = {"cui", "enterpriseName", "personName", "onrcNumber"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value.keys())
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(document)

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "packages" / "local_finance" / "scripts" / "import_local_finance.py"
DATA = ROOT / "packages" / "local_finance" / "data"

spec = importlib.util.spec_from_file_location("import_local_finance", IMPORTER)
assert spec and spec.loader
import_local_finance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_local_finance)


def line(functional: str, economic: str, amount: float) -> dict:
    return {"functional_code": functional, "economic_code": economic, "amount": amount}


def test_full_scope_keeps_the_whole_roster_and_marks_records_as_full_import():
    uats = [
        {"siruta": "1017", "name": "MUNICIPIUL ALBA IULIA"},
        {"siruta": "AB", "name": "JUDETUL ALBA"},
    ]

    selected = import_local_finance.select_uats_for_scope(uats, "full")

    assert [row["siruta"] for row in selected] == ["1017", "AB"]
    assert {row["sampleRole"] for row in selected} == {"full-import"}
    assert import_local_finance.mart_id("full", [2025]) == "local-finance-mart-2025"
    assert (
        import_local_finance.mart_id("sample", [2023, 2024, 2025])
        == "local-finance-mart-sample-2023-2025"
    )


def test_record_from_lines_derives_finance_indicators_from_classification_prefixes():
    record = import_local_finance.record_from_lines(
        {
            "siruta": "1017",
            "name": "MUNICIPIUL ALBA IULIA",
            "county": "AB",
            "population": 1,
            "sampleRole": "county-seat",
        },
        {
            "siruta": "1017",
            "cui": "4562923",
            "name": "MUNICIPIUL ALBA IULIA",
            "level": "municipality",
            "countyCode": "AB",
            "population": 100,
            "populationSource": "ins-tempo-pop107d-locality",
        },
        2025,
        [
            line("04.02.01", "00.00.00", 80),
            line("03.18.00", "00.00.00", 20),
        ],
        [
            line("51.01.03", "10.01.01", 10),
            line("70.06.00", "71.01.01", 5),
            line("65.04.01", "20.01.01", 15),
        ],
        [line("70.06.00", "71.01.01", 5)],
    )

    assert record["population"] == 100
    assert record["revenueRon"] == 100
    assert record["ownRevenueRon"] == 20
    assert record["transferRevenueRon"] == 80
    assert record["personnelSpendingRon"] == 10
    assert record["capitalSpendingRon"] == 5
    assert record["developmentSpendingRon"] == 5
    assert record["ownRevenueShare"] == 0.2
    assert record["spendingPerInhabitantRon"] == 0.3


def test_full_validation_checks_numeric_registry_join_but_keeps_county_councils():
    records = []
    for index in range(3001):
        records.append(
            {
                "year": 2025,
                "siruta": str(1000 + index),
                "sampleRole": "full-import",
                "level": "commune",
                "countyCode": "AB",
                "revenueRon": 1.0,
                "spendingRon": 1.0,
                "developmentSpendingRon": 1.0,
            }
        )
    for index in range(40):
        records.append(
            {
                "year": 2025,
                "siruta": f"X{index}",
                "sampleRole": "full-import",
                "level": "county",
                "countyCode": f"X{index}",
                "revenueRon": 1.0,
                "spendingRon": 1.0,
                "developmentSpendingRon": 1.0,
            }
        )
    mart = {
        "id": "local-finance-mart-2025",
        "scope": "full",
        "periodStart": "2025",
        "periodEnd": "2025",
        "retrievedDate": "2026-09-08",
        "summary": {
            "uats": len(records),
            "years": 1,
            "records": len(records),
            "registryMatchedUats": 3001,
            "byYear": [{"year": 2025, "developmentSpendingRon": 1.0}],
        },
        "records": records,
        "limitations": [],
    }

    report = import_local_finance.build_validation_report(mart)

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["full-national-scope"] == "pass"
    assert statuses["registry-join"] == "pass"


def test_legacy_budget_document_keeps_the_impozit_teren_shape():
    uats = [
        {"siruta": "1017", "name": "MUNICIPIUL ALBA IULIA", "county": "AB", "population": 100},
        {"siruta": "AB", "name": "JUDETUL ALBA", "county": "AB", "population": 1000},
    ]
    revenue = {"1017": (100.0, 20.0), "AB": (1000.0, 300.0)}
    spending = {"1017": (50.0, 0.0), "AB": (500.0, 0.0)}

    document = import_local_finance.build_legacy_budget_document(uats, revenue, spending, 2025)

    assert document["$schema"] == "../schema/buget-uat.schema.json"
    assert document["summary"]["uatsReporting"] == 2
    assert document["uats"][0]["level"] == "uat"
    assert document["uats"][0]["ownShare"] == 0.2
    assert document["uats"][1]["level"] == "county"


def test_legacy_budget_document_round_trips_from_mart_records():
    budget = json.loads(
        (ROOT / "simulators" / "impozit-teren" / "data" / "buget-uat-2025.json").read_text(
            encoding="utf-8"
        )
    )
    records = [
        {
            "year": 2025,
            "siruta": row["siruta"],
            "name": f"registry name for {row['siruta']}",
            "transparentaName": row["name"],
            "countyCode": row["county"],
            "population": row["population"],
            "revenueRon": row["revenueRon"],
            "ownRevenueRon": row["ownRevenueRon"],
            "spendingRon": row["spendingRon"],
        }
        for row in budget["uats"]
    ]
    for row in budget["excluded"]:
        records.append(
            {
                "year": 2025,
                "siruta": row["siruta"],
                "name": row["name"],
                "transparentaName": row["name"],
                "countyCode": "B",
                "population": round(row["reportedSpendingRon"] / row["perInhabitantRon"]),
                "revenueRon": 0.0,
                "ownRevenueRon": 0.0,
                "spendingRon": row["reportedSpendingRon"],
            }
        )

    document = import_local_finance.build_legacy_budget_document_from_records(records, 2025)

    assert document["summary"] == budget["summary"]
    assert document["uats"] == budget["uats"]
    assert [row["siruta"] for row in document["excluded"]] == [
        row["siruta"] for row in budget["excluded"]
    ]


def test_committed_local_finance_sample_covers_the_first_slice_scope():
    mart = json.loads(
        (DATA / "local-finance-mart-sample-2023-2025.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (DATA / "local-finance-validation-report-2023-2025.json").read_text(encoding="utf-8")
    )

    assert mart["summary"]["uats"] == 10
    assert mart["summary"]["years"] == 3
    assert mart["summary"]["records"] == 30
    assert mart["summary"]["registryMatchedUats"] == 10

    roles = {row["role"] for row in mart["sample"]}
    assert {"county-seat", "bucharest-sector", "rural-commune"} <= roles

    rural_counties = {
        row["countyCode"]
        for row in mart["records"]
        if row["sampleRole"] == "rural-commune" and row["level"] == "commune"
    }
    assert len(rural_counties) >= 3

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert report["summary"]["failed"] == 0
    assert statuses["sample-scope"] == "pass"
    assert statuses["registry-join"] == "pass"
    assert statuses["development-expense-type-coverage"] == "warning"
    assert statuses["data-gov-2024-national-comparison"] == "warning"


def test_committed_full_2025_mart_exports_the_impozit_teren_budget():
    mart = json.loads((DATA / "local-finance-mart-2025.json").read_text(encoding="utf-8"))
    budget = json.loads(
        (ROOT / "simulators" / "impozit-teren" / "data" / "buget-uat-2025.json").read_text(
            encoding="utf-8"
        )
    )

    assert mart["scope"] == "full"
    assert mart["summary"]["uats"] > 3000
    assert mart["summary"]["years"] == 1

    regenerated = import_local_finance.build_legacy_budget_document_from_mart(mart, 2025)

    assert regenerated == budget

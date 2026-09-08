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

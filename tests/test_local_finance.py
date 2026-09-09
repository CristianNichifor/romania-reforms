from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "packages" / "local_finance" / "scripts" / "import_local_finance.py"
DATA = ROOT / "packages" / "local_finance" / "data"
DATA_ASSETS = ROOT / "data-assets.json"
FULL_HISTORY_MART = DATA / "local-finance-mart-2023-2025.json"

spec = importlib.util.spec_from_file_location("import_local_finance", IMPORTER)
assert spec and spec.loader
import_local_finance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_local_finance)


def impozit_teren_budget_from_shared_history() -> dict:
    if not FULL_HISTORY_MART.exists():
        pytest.skip("release asset was not fetched")
    mart = json.loads(FULL_HISTORY_MART.read_text(encoding="utf-8"))
    return import_local_finance.build_legacy_budget_document_from_mart(mart, 2025)


def line(functional: str, economic: str, amount: float) -> dict:
    return {"functional_code": functional, "economic_code": economic, "amount": amount}


def arrears_registry() -> dict:
    return {
        "units": [
            {
                "siruta": "10",
                "name": "JUDEŢUL ALBA",
                "shortName": "ALBA",
                "level": "county",
                "countyCode": "AB",
                "countyName": "ALBA",
            },
            {
                "siruta": "29",
                "name": "JUDEŢUL ARAD",
                "shortName": "ARAD",
                "level": "county",
                "countyCode": "AR",
                "countyName": "ARAD",
            },
            {
                "siruta": "9502",
                "name": "INEU",
                "shortName": "INEU",
                "level": "town",
                "countyCode": "AR",
                "countyName": "ARAD",
            },
        ]
    }


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


def test_data_gov_arrears_index_prefers_later_duplicate_uat_resource():
    package = {
        "success": True,
        "result": {
            "license_title": "OGL-ROU-1.0",
            "organization": {"title": "Ministerul Finanţelor Publice"},
            "resources": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "ArierateBGCiunie2018.xls",
                    "description": "Arierate ale bugetului general consolidat - iunie 2018",
                    "url": "https://example.test/arieratebgciunie2018.xls",
                    "created": "2018-08-03T08:00:00",
                    "position": 1,
                },
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "ArierateUAT30062018.xls",
                    "description": "",
                    "url": "https://example.test/arierateuat30062018.xls",
                    "created": "2018-08-03T08:00:00",
                    "position": 2,
                },
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "name": (
                        "Situaţia-plăţilor-restante-mai-mari-de-90-de-zile-la-data-de-30.06.2018-"
                    ),
                    "description": "",
                    "url": "https://example.test/valid-arierateuat30062018.xls",
                    "created": "2018-08-08T13:00:00",
                    "position": 3,
                },
                {
                    "id": "44444444-4444-4444-4444-444444444444",
                    "name": "ArierateUAT31122017.xls",
                    "description": "",
                    "url": "https://example.test/arierateuat31122017.xls",
                    "created": "2018-08-03T08:00:00",
                    "position": 4,
                },
            ],
        },
    }

    index = import_local_finance.build_arrears_resource_index(
        package, "2026-09-09", package_sha256="a" * 64
    )

    assert index["summary"]["resources"] == 4
    assert index["summary"]["uatResources"] == 2
    assert index["summary"]["coveredYears"] == [2017, 2018]
    assert index["summary"]["latestUatSnapshotDate"] == "2018-06-30"
    assert index["summary"]["has2025UatResource"] is False
    assert index["latestUatResource"]["resourceId"] == "33333333-3333-3333-3333-333333333333"
    assert index["latestUatResource"]["duplicateResources"] == 2
    assert {
        "data-gov-arrears-current-years-unavailable",
        "data-gov-arrears-duplicate-uploads",
    } <= {limitation["id"] for limitation in index["limitations"]}


def test_arrears_rows_join_county_councils_and_localities_by_name_within_county():
    rows = [
        ["", "TOTAL", 150.0],
        ["", "din care:", ""],
        [1.0, "ALBA", 10.0],
        ["", "Consiliul Judeţean Alba", 10.0],
        [2.0, "ARAD", 140.0],
        ["", "Ineu", 100.0],
        ["", "Missing Place", 40.0],
    ]

    snapshot = import_local_finance.parse_arrears_rows(rows, arrears_registry(), "2018-06-30")

    assert snapshot["recordsBySiruta"] == {"9502": 100.0, "AB": 10.0}
    assert snapshot["summary"]["countySubtotalRows"] == 2
    assert snapshot["summary"]["authorityRows"] == 3
    assert snapshot["summary"]["matchedRows"] == 2
    assert snapshot["summary"]["unmatchedRows"] == 1
    assert snapshot["summary"]["workbookTotalArrearsRon"] == 150.0
    assert snapshot["summary"]["unmatchedArrearsRon"] == 40.0


def test_arrears_snapshot_enriches_only_matching_mart_year_and_sets_missing_rows_to_zero():
    records = [
        {"year": 2018, "siruta": "AB", "population": 2, "arrearsRon": None},
        {"year": 2018, "siruta": "9502", "population": 4, "arrearsRon": None},
        {"year": 2018, "siruta": "9999", "population": 5, "arrearsRon": None},
        {"year": 2025, "siruta": "9502", "population": 4, "arrearsRon": None},
    ]
    snapshot = {
        "snapshotDate": "2018-06-30",
        "recordsBySiruta": {"AB": 10.0, "9502": 100.0},
    }

    changed = import_local_finance.apply_arrears_snapshot(records, snapshot)

    assert changed == 3
    assert records[0]["arrearsRon"] == 10.0
    assert records[0]["arrearsPerInhabitantRon"] == 5.0
    assert records[1]["arrearsRon"] == 100.0
    assert records[2]["arrearsRon"] == 0.0
    assert records[2]["arrearsPerInhabitantRon"] == 0.0
    assert records[3]["arrearsRon"] is None


def test_arrears_coverage_warns_when_official_package_has_no_requested_year():
    mart = {
        "records": [{"year": 2025, "siruta": "1017", "arrearsRon": None}],
    }
    arrears_resources = {
        "summary": {
            "coveredYears": [2017, 2018],
            "latestUatSnapshotDate": "2018-06-30",
        }
    }

    check = import_local_finance.arrears_coverage_check(mart, arrears_resources)

    assert check["status"] == "warning"
    assert check["metrics"]["missingYears"] == "2025"
    assert check["metrics"]["latestUatSnapshotDate"] == "2018-06-30"


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
    assert record["arrearsPerInhabitantRon"] is None


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
    budget = impozit_teren_budget_from_shared_history()
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


def test_full_2023_2025_history_is_documented_as_a_release_asset():
    assets = json.loads(DATA_ASSETS.read_text(encoding="utf-8"))["assets"]
    entry = next(asset for asset in assets if asset["id"] == "local-finance-mart-2023-2025")

    assert entry["destination"] == "packages/local_finance/data/local-finance-mart-2023-2025.json"
    assert entry["bytes"] > 9_000_000
    assert len(entry["sha256"]) == 64
    assert "9,684" in entry["what"]


def test_full_2023_2025_history_report_covers_the_release_payload():
    report = json.loads(
        (DATA / "local-finance-validation-report-2023-2025.json").read_text(encoding="utf-8")
    )

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert report["summary"]["failed"] == 0
    assert report["martId"] == "local-finance-mart-2023-2025"
    assert statuses["full-national-scope"] == "pass"
    assert statuses["registry-join"] == "pass"
    assert statuses["development-expense-type-coverage"] == "warning"
    assert statuses["data-gov-2024-national-comparison"] == "warning"
    assert statuses["data-gov-arrears-coverage"] == "warning"


def test_fetched_full_2023_2025_mart_covers_the_national_history():
    if not FULL_HISTORY_MART.exists():
        pytest.skip("release asset was not fetched")

    mart = json.loads(FULL_HISTORY_MART.read_text(encoding="utf-8"))

    assert mart["scope"] == "full"
    assert mart["summary"]["uats"] == 3228
    assert mart["summary"]["years"] == 3
    assert mart["summary"]["records"] == 9684
    assert mart["summary"]["registryMatchedUats"] == 3187


def test_fetched_full_history_exports_the_impozit_teren_budget():
    if not FULL_HISTORY_MART.exists():
        pytest.skip("release asset was not fetched")
    mart = json.loads(FULL_HISTORY_MART.read_text(encoding="utf-8"))

    assert mart["scope"] == "full"
    assert mart["summary"]["uats"] > 3000
    assert mart["summary"]["years"] == 3

    budget = import_local_finance.build_legacy_budget_document_from_mart(mart, 2025)

    assert budget["id"] == "buget-uat-2025"
    assert budget["summary"]["uatsReporting"] == 3225
    assert budget["summary"]["spendingRon"] == pytest.approx(184_822_260_751.28)
    assert [row["siruta"] for row in budget["excluded"]] == ["179141", "179187", "179169"]


def test_committed_arrears_index_documents_no_2025_source_for_the_full_mart():
    index = json.loads((DATA / "data-gov-arrears-resources.json").read_text(encoding="utf-8"))
    report = json.loads(
        (DATA / "local-finance-validation-report-2023-2025.json").read_text(encoding="utf-8")
    )

    assert index["summary"]["latestUatSnapshotDate"] == "2018-06-30"
    assert index["summary"]["has2025UatResource"] is False
    assert index["latestUatResource"]["url"].endswith("/arierateuat30062018.xls")

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["data-gov-arrears-coverage"] == "warning"
    assert {
        "data-gov-arrears-current-years-unavailable",
        "data-gov-arrears-duplicate-uploads",
    } <= {limitation["id"] for limitation in report["limitations"]}

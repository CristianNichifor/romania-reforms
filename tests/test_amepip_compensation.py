from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = (
    ROOT
    / "packages"
    / "public_enterprise_governance"
    / "scripts"
    / "import_amepip_compensation.py"
)
DATA = ROOT / "packages" / "public_enterprise_governance" / "data"
INVENTORY = DATA / "amepip-source-inventory-2025-2026.json"
SAMPLE = DATA / "amepip-compensation-sample-august-2025.json"

spec = importlib.util.spec_from_file_location("import_amepip_compensation", IMPORTER)
assert spec and spec.loader
import_amepip_compensation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_amepip_compensation)


def test_amount_parser_handles_pdf_spacing_and_non_numeric_values():
    assert import_amepip_compensation.parse_amount("4,455") == 4455
    assert import_amepip_compensation.parse_amount("1 2,820") == 12820
    assert import_amepip_compensation.parse_amount("3 40,000") == 340000
    assert import_amepip_compensation.parse_amount("-") is None
    assert import_amepip_compensation.parse_amount("Nu a fost stabilită") is None
    assert import_amepip_compensation.parse_amount("Insolventa/Diverse") is None


def test_table_row_parser_preserves_identity_role_amounts_and_raw_values():
    row = [
        "2",
        "MINISTERUL SANATATII",
        "ANTIBIOTICE",
        "1973096",
        "Ioan Nani",
        "Director/directorat",
        "6 3,060",
        "Nu a fost stabilită",
    ]

    record = import_amepip_compensation.parse_table_row(
        row, source_row_number=8, source_page_number=1
    )

    assert record["sourceRecordId"] == "amepip-compensation-sample-august-2025-0008"
    assert record["enterpriseOrdinal"] == 2
    assert record["authorityName"] == "MINISTERUL SANATATII"
    assert record["enterpriseName"] == "ANTIBIOTICE"
    assert record["cui"] == "1973096"
    assert record["personName"] == "Ioan Nani"
    assert record["roleType"] == "director"
    assert record["monthlyFixedGrossRon"] == 63060
    assert record["annualVariableGrossRon"] is None
    assert record["rawAnnualVariableGross"] == "Nu a fost stabilită"
    assert record["provenance"]["locator"] == "page 1, parsed row 8"


def test_build_document_reports_full_source_coverage_but_commits_sample_rows():
    records = [
        import_amepip_compensation.parse_table_row(
            [
                "1",
                "APT",
                "COMPANIA A",
                "123",
                "Ana Pop",
                "Membru CA/CS",
                "4,000",
                "-",
            ],
            source_row_number=1,
            source_page_number=1,
        ),
        import_amepip_compensation.parse_table_row(
            [
                "1",
                "APT",
                "COMPANIA A",
                "123",
                "Ana Pop",
                "Director/directorat",
                "1 0,000",
                "1 00,000",
            ],
            source_row_number=2,
            source_page_number=1,
        ),
    ]

    document = import_amepip_compensation.build_document(
        records,
        source_sha256="a" * 64,
        source_page_count=1,
        retrieved_date="2026-09-10",
        sample_size=1,
    )

    assert document["summary"]["sourceRows"] == 2
    assert document["summary"]["sampleRows"] == 1
    assert document["summary"]["enterprises"] == 1
    assert document["summary"]["people"] == 1
    assert document["summary"]["boardRows"] == 1
    assert document["summary"]["directorRows"] == 1
    assert len(document["records"]) == 1
    assert {limitation["id"] for limitation in document["limitations"]} >= {
        "amepip-reuse-license-not-published",
        "amepip-pdf-layout-sensitive",
        "amepip-sample-not-full-mart",
    }


def test_committed_sample_matches_source_inventory_and_sample_contract():
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    august_source = next(
        source
        for source in inventory["sources"]
        if source["id"] == "amepip-indemnizatii-ip-centrale-august-2025"
    )

    assert sample["sourceId"] == august_source["id"]
    assert sample["sourceSha256"] == august_source["sha256"]
    assert sample["summary"]["sourceRows"] >= sample["summary"]["sampleRows"]
    assert sample["summary"]["sourceRows"] >= 700
    assert sample["summary"]["rowsWithCui"] == sample["summary"]["sourceRows"]
    assert sample["summary"]["directorRows"] > 0
    assert sample["summary"]["boardRows"] > 0
    assert len(sample["records"]) == sample["summary"]["sampleRows"]
    assert sample["records"][0]["cui"] == "1923799"

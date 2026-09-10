from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = (
    ROOT
    / "packages"
    / "public_enterprise_governance"
    / "scripts"
    / "import_amepip_compensation.py"
)
COMPARISON_BUILDER = (
    ROOT / "simulators" / "salarizare" / "scripts" / "build_amepip_compensation_comparison.py"
)
DATA = ROOT / "packages" / "public_enterprise_governance" / "data"
INVENTORY = DATA / "amepip-source-inventory-2025-2026.json"
SAMPLE = DATA / "amepip-compensation-sample-august-2025.json"
MART_SCHEMA = (
    ROOT
    / "packages"
    / "public_enterprise_governance"
    / "schema"
    / "amepip-compensation-mart.schema.json"
)
FISCAL_SCHEMA = ROOT / "simulators" / "salarizare" / "schema" / "fiscal.schema.json"

spec = importlib.util.spec_from_file_location("import_amepip_compensation", IMPORTER)
assert spec and spec.loader
import_amepip_compensation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_amepip_compensation)

comparison_spec = importlib.util.spec_from_file_location(
    "build_amepip_compensation_comparison",
    COMPARISON_BUILDER,
)
assert comparison_spec and comparison_spec.loader
build_amepip_compensation_comparison = importlib.util.module_from_spec(comparison_spec)
comparison_spec.loader.exec_module(build_amepip_compensation_comparison)

sys.path.insert(0, str(ROOT / "scripts"))
from validate_data import registry  # noqa: E402


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
    assert document["summary"]["emittedRows"] == 1
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


def test_build_mart_document_declares_release_policy_and_salarizare_contract():
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
            document_id=import_amepip_compensation.MART_DOCUMENT_ID,
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
            document_id=import_amepip_compensation.MART_DOCUMENT_ID,
        ),
    ]

    document = import_amepip_compensation.build_mart_document(
        records,
        source_sha256="a" * 64,
        source_page_count=1,
        retrieved_date="2026-09-10",
    )

    schema = json.loads(MART_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))

    assert errors == []
    assert document["id"] == "amepip-compensation-mart-august-2025"
    assert document["summary"]["sourceRows"] == 2
    assert document["summary"]["emittedRows"] == 2
    assert "sampleRows" not in document["summary"]
    assert len(document["records"]) == 2
    assert document["records"][0]["sourceRecordId"] == "amepip-compensation-mart-august-2025-0001"
    assert document["releasePolicy"]["storage"] == "release-asset"
    assert document["releasePolicy"]["destination"].endswith(
        "amepip-compensation-mart-august-2025.json"
    )
    assert document["consumerContracts"][0]["consumer"] == "salarizare"
    assert document["consumerContracts"][0]["status"] == "release-asset-required"
    limitation_ids = {limitation["id"] for limitation in document["limitations"]}
    assert "amepip-mart-release-required" in limitation_ids
    assert "amepip-sample-not-full-mart" not in limitation_ids


def test_compensation_comparison_emits_aggregate_fiscal_series_without_nominal_keys():
    source = {
        "pay_scale_rows": [
            {"kind": "ref", "label": "Salariu minim brut", "value": 4000},
            {"kind": "ref", "label": "Salariu mediu brut 2025", "value": 10000},
            {"kind": "ref", "label": "Președintele României", "value": 30000},
            {"kind": "tier", "label": "COMPANIA A", "value": 50000},
            {"kind": "tier", "label": "COMPANIA B", "value": 70000},
            {"kind": "tier-top", "label": "COMPANIA C", "value": 90000},
            {"kind": "extreme", "label": "COMPANIA C (cu bonus anual)", "value": 270000},
        ]
    }

    document = build_amepip_compensation_comparison.build_comparison_document(
        source,
        retrieved_date="2026-09-10",
    )

    schema = json.loads(FISCAL_SCHEMA.read_text(encoding="utf-8"))
    schema_document = dict(document)
    schema_document.pop("$schema", None)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(schema_document), key=lambda error: list(error.path))
    assert errors == []

    by_id = {series["id"]: series for series in document["series"]}
    assert by_id["companiidestat-pay-scale-fixed-tier-count"]["observations"][0]["value"] == 3
    assert by_id["companiidestat-pay-scale-fixed-median"]["observations"][0]["value"] == 70000
    assert by_id["companiidestat-pay-scale-fixed-top"]["observations"][0]["value"] == 90000
    assert (
        by_id["companiidestat-pay-scale-extreme-monthly-equivalent"]["observations"][0]["value"]
        == 270000
    )
    assert by_id["companiidestat-pay-scale-fixed-top-to-average-gross"]["unit"] == "RATE"

    forbidden = {"cui", "enterpriseName", "authorityName", "personName"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value.keys())
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            assert "COMPANIA" not in value
            assert "Ana Pop" not in value
            assert "Ion Pop" not in value
            assert "COMPANIA A" not in value

    walk(document)


def test_generated_full_mart_destination_is_gitignored():
    result = subprocess.run(  # noqa: S603
        [
            "git",
            "check-ignore",
            "-q",
            str(import_amepip_compensation.MART_OUT.relative_to(ROOT)),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0


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
    assert sample["summary"]["emittedRows"] == sample["summary"]["sampleRows"]
    assert sample["summary"]["sourceRows"] >= 700
    assert sample["summary"]["rowsWithCui"] == sample["summary"]["sourceRows"]
    assert sample["summary"]["directorRows"] > 0
    assert sample["summary"]["boardRows"] > 0
    assert len(sample["records"]) == sample["summary"]["sampleRows"]
    assert sample["records"][0]["cui"] == "1923799"

"""Build AMEPIP compensation documents from the August 2025 nominal PDF.

The raw PDF is an official AMEPIP attachment, but it is not committed. The default output is a
small committed sample plus coverage metrics. Use `--scope mart` to generate the full row-level
mart that should be published as a release asset, not committed.

Usage:
    uv run python packages/public_enterprise_governance/scripts/import_amepip_compensation.py \
      --source /tmp/amepip-inventory/indemnizatii-ip-centrale-august-2025.pdf \
      --retrieved-date 2026-09-10

    uv run python packages/public_enterprise_governance/scripts/import_amepip_compensation.py \
      --scope mart \
      --source /tmp/amepip-inventory/indemnizatii-ip-centrale-august-2025.pdf \
      --retrieved-date 2026-09-10
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Final

import pdfplumber

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID: Final[str] = "amepip-indemnizatii-ip-centrale-august-2025"
SAMPLE_DOCUMENT_ID: Final[str] = "amepip-compensation-sample-august-2025"
MART_DOCUMENT_ID: Final[str] = "amepip-compensation-mart-august-2025"
SAMPLE_OUT: Final[Path] = PACKAGE_ROOT / f"data/{SAMPLE_DOCUMENT_ID}.json"
MART_OUT: Final[Path] = PACKAGE_ROOT / f"data/{MART_DOCUMENT_ID}.json"
TRANSFORM_VERSION: Final[str] = "2026-09-10.1"
SOURCE_PAGE_URL: Final[str] = "https://amepip.gov.ro/indemnizatii-ca-cs/"
SOURCE_URL: Final[str] = (
    "https://amepip.gov.ro/wp-content/uploads/2025/08/"
    "Situatia-indemnizatiilor-nominale-IP-centrale-august-2025.pdf"
)
UA: Final[str] = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
DEFAULT_SAMPLE_SIZE: Final[int] = 50


def out_for_scope(scope: str) -> Path:
    return MART_OUT if scope == "mart" else SAMPLE_OUT


def clean_text(value: object) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()
    return text or None


def fold(value: object) -> str:
    text = str(value or "").upper().replace("Ţ", "Ț").replace("Ş", "Ș")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_amount(value: object) -> int | None:
    text = clean_text(value)
    if not text or text == "-":
        return None
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+|\d{1,3}([,.]\d{3})+", compact):
        return int(compact.replace(",", "").replace(".", ""))
    return None


def role_type(role: str | None) -> str:
    folded = fold(role)
    if "DIRECTOR" in folded:
        return "director"
    if "CA/CS" in folded or "MEMBRU" in folded:
        return "board"
    return "unknown"


def source_record_id(source_row_number: int, *, document_id: str = SAMPLE_DOCUMENT_ID) -> str:
    return f"{document_id}-{source_row_number:04d}"


def parse_table_row(
    row: list[object],
    *,
    source_row_number: int,
    source_page_number: int,
    document_id: str = SAMPLE_DOCUMENT_ID,
) -> dict | None:
    if not row or clean_text(row[0]) == "Nr.Crt":
        return None
    if len(row) < 8:
        return None

    cui = clean_text(row[3])
    if not cui or not re.fullmatch(r"\d+", cui):
        return None

    enterprise_ordinal_text = clean_text(row[0])
    enterprise_ordinal = (
        int(enterprise_ordinal_text)
        if enterprise_ordinal_text and enterprise_ordinal_text.isdigit()
        else None
    )
    raw_monthly_fixed = clean_text(row[6])
    raw_annual_variable = clean_text(row[7])
    role = clean_text(row[5])

    return {
        "sourceRecordId": source_record_id(source_row_number, document_id=document_id),
        "sourceRowNumber": source_row_number,
        "sourcePageNumber": source_page_number,
        "enterpriseOrdinal": enterprise_ordinal,
        "authorityName": clean_text(row[1]) or "",
        "enterpriseName": clean_text(row[2]) or "",
        "cui": cui,
        "personName": clean_text(row[4]),
        "role": role,
        "roleType": role_type(role),
        "monthlyFixedGrossRon": parse_amount(raw_monthly_fixed),
        "annualVariableGrossRon": parse_amount(raw_annual_variable),
        "rawMonthlyFixedGross": raw_monthly_fixed,
        "rawAnnualVariableGross": raw_annual_variable,
        "provenance": {
            "source": SOURCE_ID,
            "locator": f"page {source_page_number}, parsed row {source_row_number}",
            "confidence": "derived",
            "note": "Parsed from AMEPIP PDF table cells with source raw amount strings preserved.",
        },
    }


def parse_pdf_records(
    source_pdf: bytes, *, document_id: str = SAMPLE_DOCUMENT_ID
) -> tuple[list[dict], int]:
    records: list[dict] = []
    with pdfplumber.open(io.BytesIO(source_pdf)) as pdf:
        page_count = len(pdf.pages)
        for source_page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for row in table:
                    parsed = parse_table_row(
                        row,
                        source_row_number=len(records) + 1,
                        source_page_number=source_page_number,
                        document_id=document_id,
                    )
                    if parsed:
                        records.append(parsed)
    return records, page_count


def limitation(id_: str, severity: str, affects: list[str], text: str) -> dict:
    return {"id": id_, "severity": severity, "affects": affects, "text": text}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source_bytes(location: str | Path) -> bytes:
    text = str(location)
    if re.match(r"https?://", text):
        request = urllib.request.Request(text, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    return Path(text).read_bytes()


def summarize_records(records: list[dict], *, emitted_rows: int) -> dict:
    enterprises = {(record["cui"], record["enterpriseName"]) for record in records}
    authorities = {record["authorityName"] for record in records}
    people = {record["personName"] for record in records if record["personName"]}
    role_counts = Counter(record["roleType"] for record in records)
    missing_role_rows = sum(1 for record in records if not record["role"])
    missing_person_rows = sum(1 for record in records if not record["personName"])

    return {
        "sourceRows": len(records),
        "emittedRows": emitted_rows,
        "enterprises": len(enterprises),
        "authorities": len(authorities),
        "people": len(people),
        "rowsWithCui": sum(1 for record in records if record["cui"]),
        "rowsWithMonthlyFixedGross": sum(
            1 for record in records if record["monthlyFixedGrossRon"] is not None
        ),
        "rowsWithAnnualVariableGross": sum(
            1 for record in records if record["annualVariableGrossRon"] is not None
        ),
        "rowsWithNonNumericMonthlyFixed": sum(
            1
            for record in records
            if record["rawMonthlyFixedGross"]
            and record["monthlyFixedGrossRon"] is None
            and record["rawMonthlyFixedGross"] != "-"
        ),
        "rowsWithNonNumericAnnualVariable": sum(
            1
            for record in records
            if record["rawAnnualVariableGross"]
            and record["annualVariableGrossRon"] is None
            and record["rawAnnualVariableGross"] != "-"
        ),
        "boardRows": role_counts["board"],
        "directorRows": role_counts["director"],
        "unknownRoleRows": role_counts["unknown"],
        "missingRoleRows": missing_role_rows,
        "missingPersonRows": missing_person_rows,
    }


def base_document(
    *,
    document_id: str,
    schema: str,
    title: str,
    source_sha256: str,
    source_page_count: int,
    retrieved_date: str,
    provenance_note: str,
) -> dict:
    return {
        "$schema": "../schema/amepip-compensation-sample.schema.json",
        "id": document_id,
        "title": title,
        "sourceId": SOURCE_ID,
        "publisher": "Agentia pentru Monitorizarea si Evaluarea Performantelor Intreprinderilor Publice",
        "sourcePageUrl": SOURCE_PAGE_URL,
        "sourceUrl": SOURCE_URL,
        "retrievedDate": retrieved_date,
        "license": (
            "Official public AMEPIP PDF; reusable data/export license not published on the "
            "source page."
        ),
        "transformVersion": TRANSFORM_VERSION,
        "sourceSha256": source_sha256,
        "sourcePageCount": source_page_count,
        "provenance": {
            "source": SOURCE_ID,
            "locator": SOURCE_URL,
            "confidence": "derived",
            "note": provenance_note,
        },
    } | {"$schema": schema}


def common_limitations(*, include_sample_limitation: bool) -> list[dict]:
    limitations = [
        limitation(
            "amepip-reuse-license-not-published",
            "material",
            ["compensation"],
            (
                "The AMEPIP source page publishes the official PDF but does not publish "
                "explicit reusable data/export terms."
            ),
        ),
        limitation(
            "amepip-pdf-layout-sensitive",
            "material",
            ["parser", "amounts"],
            (
                "The source is a PDF table. Parsed numeric values keep raw amount strings "
                "so extraction issues can be audited before a full mart is used by consumers."
            ),
        ),
    ]
    if include_sample_limitation:
        limitations.append(
            limitation(
                "amepip-sample-not-full-mart",
                "blocking",
                ["consumer-imports"],
                (
                    "The committed records are a sample only. Consumers must not treat this "
                    "document as the full AMEPIP compensation mart."
                ),
            )
        )
    return limitations


def build_document(
    records: list[dict],
    *,
    source_sha256: str,
    source_page_count: int,
    retrieved_date: str,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> dict:
    sample = records[:sample_size]
    summary = summarize_records(records, emitted_rows=len(sample))
    summary["sampleRows"] = len(sample)

    return base_document(
        document_id=SAMPLE_DOCUMENT_ID,
        schema="../schema/amepip-compensation-sample.schema.json",
        title="AMEPIP nominal compensation sample - August 2025 central public enterprises",
        source_sha256=source_sha256,
        source_page_count=source_page_count,
        retrieved_date=retrieved_date,
        provenance_note=(
            "Compact sample derived from all parsed AMEPIP August 2025 nominal compensation rows."
        ),
    ) | {
        "summary": summary,
        "records": sample,
        "limitations": common_limitations(include_sample_limitation=True),
        "nextSlice": {
            "scope": "AMEPIP compensation mart release asset",
            "deliverable": (
                "Publish the full August 2025 compensation mart as a checksum-pinned release "
                "asset and build a salarizare comparison payload from that asset."
            ),
            "doneWhen": (
                "The mart is uploaded, data-assets.json carries its size and checksum, and the "
                "salarizare app consumes only an aggregate/comparison payload."
            ),
        },
    }


def build_mart_document(
    records: list[dict],
    *,
    source_sha256: str,
    source_page_count: int,
    retrieved_date: str,
) -> dict:
    return base_document(
        document_id=MART_DOCUMENT_ID,
        schema="../schema/amepip-compensation-mart.schema.json",
        title="AMEPIP nominal compensation mart - August 2025 central public enterprises",
        source_sha256=source_sha256,
        source_page_count=source_page_count,
        retrieved_date=retrieved_date,
        provenance_note=(
            "Full row-level mart derived from all parsed AMEPIP August 2025 nominal "
            "compensation rows."
        ),
    ) | {
        "summary": summarize_records(records, emitted_rows=len(records)),
        "records": records,
        "releasePolicy": {
            "storage": "release-asset",
            "assetId": MART_DOCUMENT_ID,
            "destination": f"packages/public_enterprise_governance/data/{MART_DOCUMENT_ID}.json",
            "publishCommand": f"uv run python scripts/publish_release_data.py --id {MART_DOCUMENT_ID}",
            "gitPolicy": (
                "Do not commit this generated mart. Commit only the schema, sample, docs and "
                "checksum-pinned data-assets.json entry after publishing."
            ),
        },
        "consumerContracts": [
            {
                "consumer": "salarizare",
                "status": "release-asset-required",
                "joinKeys": ["cui"],
                "comparisonFields": [
                    "roleType",
                    "monthlyFixedGrossRon",
                    "annualVariableGrossRon",
                    "authorityName",
                    "enterpriseName",
                ],
                "limitationText": (
                    "AMEPIP publishes nominal gross fixed and variable compensation for "
                    "central public-enterprise board/director rows. Compare these rows with "
                    "public-pay grids as governance compensation context, not as payroll "
                    "entitlements or whole-public-sector salaries."
                ),
            }
        ],
        "limitations": common_limitations(include_sample_limitation=False)
        + [
            limitation(
                "amepip-mart-release-required",
                "blocking",
                ["consumer-imports"],
                (
                    "Consumers must not import a locally generated mart unless the same bytes "
                    "are published as a release asset and pinned in data-assets.json."
                ),
            )
        ],
        "nextSlice": {
            "scope": "salarizare public-enterprise compensation comparison",
            "deliverable": (
                "Publish the mart release asset, then build a compact salarizare comparison "
                "payload that aggregates public-enterprise management compensation against "
                "salary-grid and benchmark context."
            ),
            "doneWhen": (
                "The app shows AMEPIP management compensation as a clearly limited comparison "
                "layer and does not load the row-level mart directly in the browser."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["sample", "mart"], default="sample")
    parser.add_argument("--source", default=SOURCE_URL, help="PDF path or URL")
    parser.add_argument("--retrieved-date", required=True)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    source_pdf = read_source_bytes(args.source)
    document_id = MART_DOCUMENT_ID if args.scope == "mart" else SAMPLE_DOCUMENT_ID
    records, page_count = parse_pdf_records(source_pdf, document_id=document_id)
    if args.scope == "mart":
        document = build_mart_document(
            records,
            source_sha256=sha256_bytes(source_pdf),
            source_page_count=page_count,
            retrieved_date=args.retrieved_date,
        )
    else:
        document = build_document(
            records,
            source_sha256=sha256_bytes(source_pdf),
            source_page_count=page_count,
            retrieved_date=args.retrieved_date,
            sample_size=args.sample_size,
        )
    out = args.out or out_for_scope(args.scope)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {out} with {document['summary']['emittedRows']} {args.scope} rows "
        f"from {document['summary']['sourceRows']} parsed rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read the state-company indicator workbook into one row per company.

The workbook has three sheets. `Indicatori calculati` carries the financial ratios per company
and year; `Indicatori formular` carries the non-financial indicators, including the one this
simulator needs — the full-time-equivalent headcount; `kpi` is the indicator dictionary. This
import keeps identity, activity (CAEN), status and headcount, and drops the ratio columns: a
consolidation argument is about how many operators exist and how big they are, not about their
ROA.

Headcount is the latest year a company reports it. It is present for a minority of companies,
so every employee total this feeds is a **lower bound**, carried as a limitation rather than
smoothed over.

Usage:
    uv run python scripts/import_soe.py
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "companii-stat-finnefin.xlsx"
OUT = ROOT / "data" / "companii-2025.json"

FINANCIAL_SHEET = "Indicatori calculati"
NONFINANCIAL_SHEET = "Indicatori formular"
HEADCOUNT = "Număr de angajați cu echivalent normă întreagă"

# Company ids whose reported headcount is a data-entry error, checked against the workbook
# itself. A generic threshold would quietly discard a genuinely large operator, so the guard
# is this explicit table: each row is one company, one reported figure, and the reason it is
# excluded. Excluded, not dropped — the entries travel in dataQuality, so a reader can see
# what was removed and argue with it.
HEADCOUNT_OUTLIERS = {
    1217: {
        "cui": 27811667,
        "name": "UTILITĂŢI ŞI SERVICII PUBLICE MURIGHIOL SRL",
        "reported": 10776,
        "year": 2023,
        "reason": "2019–2022 report no headcount; the 2023 figure exceeds the commune's "
        "population several times over and is an entry error in the source.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_sheet(name: str) -> list[dict]:
    import openpyxl  # noqa: PLC0415

    workbook = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    rows = workbook[name].iter_rows(values_only=True)
    header = next(rows)
    return [dict(zip(header, row, strict=False)) for row in rows if row and row[0]]


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing source {SOURCE}")

    financial = load_sheet(FINANCIAL_SHEET)
    nonfinancial = load_sheet(NONFINANCIAL_SHEET)

    headcount: dict[int, dict[int, float]] = collections.defaultdict(dict)
    for row in nonfinancial:
        value = row.get(HEADCOUNT)
        if value is not None:
            headcount[row["company_id"]][row["year"]] = value

    companies: dict[int, dict] = {}
    for row in financial:
        company = companies.setdefault(
            row["company_id"],
            {
                "id": row["company_id"],
                "cui": row["cui"],
                "name": row["company"],
                "registrationNumber": row["registration_number"],
                "caen": (row["CAEN(ONRC)"] or "").strip() or None,
                "status": row["status"],
            },
        )
        years = headcount.get(row["company_id"], {})
        if years and row["company_id"] not in HEADCOUNT_OUTLIERS:
            company["employees"] = years[max(years)]
            company["employeesYear"] = max(years)

    rows = sorted(companies.values(), key=lambda c: c["name"])
    by_status = collections.Counter(c["status"] for c in rows)
    with_headcount = sum(1 for c in rows if c.get("employees") is not None)

    payload = {
        "$schema": "../schema/companii.schema.json",
        "id": "companii-stat-2025",
        "title": "Companiile de stat: identitate, activitate și angajați",
        "publisher": "Cristian Nichifor",
        "period": "2019-2024",
        "provenance": {
            "source": "companii-stat-finnefin",
            "locator": "foaia Indicatori calculati (identitate, CAEN, status) și foaia "
            "Indicatori formular (Număr de angajați cu echivalent normă întreagă)",
            "confidence": "verbatim",
            "note": "Angajații sunt ultimul an raportat de fiecare companie, cu excepțiile "
            "din dataQuality. Fișierul sursă este reținut în sources/ cu amprenta SHA-256.",
        },
        "sourceChecksum": {"sha256": sha256(SOURCE), "file": SOURCE.name},
        "dataQuality": {
            "headcountExcluded": [
                {"companyId": company_id, **entry}
                for company_id, entry in sorted(HEADCOUNT_OUTLIERS.items())
            ],
        },
        "summary": {
            "companies": len(rows),
            "withHeadcount": with_headcount,
            "byStatus": dict(by_status.most_common()),
        },
        "companies": rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} companies ({with_headcount} with headcount) -> {OUT}")


if __name__ == "__main__":
    main()

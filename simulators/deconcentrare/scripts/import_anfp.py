"""Read the ANFP 2025 register of public institutions into a classified dataset.

The registry this simulator needs is not the 2010 fixed-width list that circulates as
"Registrul Național al Instituțiilor Publice". That file describes a state that no longer
exists: it still names `Ministerul Dezvoltării Regionale și Locuinței` (2008–2010), the
`Autoritatea Națională a Vămilor` (pre-2011), the `Garda Financiară` (pre-2013) and the
`Autoritatea pentru Străini` (pre-2010). Building a 2026 reform proposal on it would be
attacked on the vintage before the argument was heard.

The current source is the list ANFP publishes every year on data.gov.ro: every public
institution or authority that manages public functions. The 2025 edition is a clean four-column
export — `DenumireInstitutie`, `TipInstitutie`, `Judet`, `Localitate` — and, crucially, its
`TipInstitutie` column already separates the **central** administration from the **territorial
deconcentrated services** that are this simulator's subject. That classification is the source's
own, not ours.

Usage:
    uv run python scripts/import_anfp.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "anfp-institutii-2025.xlsx"
OUT = ROOT / "data" / "institutii-2025.json"

SHEET = "Export"
COLUMNS = ("DenumireInstitutie", "TipInstitutie", "Judet", "Localitate")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def read_rows() -> list[dict]:
    import openpyxl  # noqa: PLC0415

    workbook = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    sheet = workbook[SHEET]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows)
    if tuple(header) != COLUMNS:
        raise SystemExit(f"unexpected columns: {header!r}; expected {COLUMNS!r}")
    out = []
    for row in rows:
        if not row or not row[0]:
            continue
        name, kind, county, locality = (value or "" for value in row[:4])
        out.append(
            {
                "name": str(name).strip(),
                "type": str(kind).strip(),
                "county": str(county).strip(),
                "locality": str(locality).strip(),
            }
        )
    return out


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing source {SOURCE}")
    institutions = read_rows()

    by_type: dict[str, int] = {}
    for row in institutions:
        by_type[row["type"]] = by_type.get(row["type"], 0) + 1

    payload = {
        "$schema": "../schema/institutii.schema.json",
        "id": "anfp-institutii-2025",
        "title": "Instituții/autorități publice care raportează situația lor către ANFP, 2025",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "anfp-institutii-2025",
            "locator": "data.gov.ro, setul ANFP 2025, foaia Export, coloanele "
            "DenumireInstitutie / TipInstitutie / Judet / Localitate",
            "confidence": "verbatim",
            "note": "Tipul instituției (central / teritorial deconcentrat / local) este "
            "clasificarea publicată de ANFP, nu una construită aici. Fișierul sursă este "
            "reținut în sources/ cu amprenta SHA-256 de mai jos.",
        },
        "sourceChecksum": {"sha256": sha256(SOURCE), "file": SOURCE.name},
        "summary": {"total": len(institutions), "byType": by_type},
        "institutions": institutions,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(institutions)} institutions -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

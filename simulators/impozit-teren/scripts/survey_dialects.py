"""Profile every cached study, so the parsers can be planned instead of discovered.

Alba's reader cost about fifteen attempts, and each of the four things it had to learn —
merged cells, three column widths in one document, captions printed rotated, land tables that
look exactly like the flat-price tables above them — arrived as a separate failure. Every one
of them is visible in a single pass over the cache.

This is that pass. It reads no PDFs; it reads what `extract_cache.py` already wrote, so the
whole country is profiled in about a second and the answer to "how many parsers is this
really" stops being a guess.

What it measures, and why each one decides something:

    currency     lei or euro. CNP Bacău prices in euro and CNP Alba Iulia in lei, and a
                 number is meaningless until you know which.
    decimals     comma or dot. Sibiu uses both, on facing pages.
    reader       whether flattened text carries the values — "CC 8,45" on one line — or
                 whether they only survive as table cells.
    merged       how often a cell in a land table is blank. A blank is a merged cell
                 inheriting from above, and a document full of them cannot be read as text.
    widths       how many distinct column counts its land tables come in.

Usage:
    uv run python simulators/impozit-teren/scripts/survey_dialects.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import CACHE, load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# A land table names a use category. These are the words every chamber uses for them, and
# looking for the words rather than for a layout is what makes this work across chambers.
CATEGORY_WORDS = re.compile(r"arabil|p[ăa][sș]un|f[âa]ne[țţ]|livezi|vii\b|intravilan", re.I)
# The Bacău style: a category code and its value on one flattened line.
TEXT_ROW = re.compile(r"^\s*(CC|V\+L|P\+F|TS|A)\s+\d+[.,]?\d*\s*$", re.M)
BUILDINGS_ONLY = re.compile(r"constructii|cladiri", re.I)


def profile(name: str) -> dict:
    document = load(name)
    pages = document["pages"]
    text = "\n".join(page["text"] for page in pages)

    land_tables = []
    for page in pages:
        for table in page["tables"]:
            head = " ".join(c for row in table["cells"][:3] for c in row)
            if CATEGORY_WORDS.search(head) and len(table["cells"]) >= 3:
                land_tables.append(table)

    cells = [c for t in land_tables for row in t["cells"] for c in row]
    blank = sum(1 for c in cells if not c)
    widths = Counter(len(t["cells"][0]) for t in land_tables if t["cells"])

    lei = len(re.findall(r"lei\s*/\s*m", text, re.I))
    euro = len(re.findall(r"eur[o]?\s*/\s*m|€\s*/\s*m", text, re.I))
    comma = len(re.findall(r"\d,\d\d\b", text))
    dot = len(re.findall(r"\d\.\d\d\b", text))
    text_rows = len(TEXT_ROW.findall(text))

    return {
        "file": name,
        "pages": len(pages),
        "landTables": len(land_tables),
        "currency": "RON" if lei > euro else "EUR" if euro else "?",
        "decimals": "," if comma > dot else "." if dot else "?",
        "mergedShare": round(blank / len(cells), 2) if cells else 0.0,
        "widths": sorted(widths),
        "textRows": text_rows,
        "reader": "text" if text_rows > 200 else "tables" if len(land_tables) >= 3 else "neither",
        "buildingsOnly": bool(BUILDINGS_ONLY.search(name)) and not land_tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="write the profile as data")
    args = parser.parse_args()

    manifest_path = ROOT / "sources" / "studies-2026.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_file = {study["file"]: study for study in manifest["studies"]}

    names = sorted(p.name[: -len(".json.gz")] for p in CACHE.glob("*.json.gz"))
    rows = []
    for name in names:
        row = profile(name)
        study = by_file.get(name, {})
        row["chamber"] = study.get("chamber", "?")
        row["counties"] = study.get("counties", [])
        rows.append(row)

    rows.sort(key=lambda r: (r["chamber"], r["file"]))
    print(f"{'chamber':<16}{'counties':<16}{'reader':<9}{'cur':<5}{'dec':<5}"
          f"{'merged':<8}{'tables':<8}{'widths':<12}file")
    for row in rows:
        print(
            f"{row['chamber']:<16}{','.join(row['counties']):<16}{row['reader']:<9}"
            f"{row['currency']:<5}{row['decimals']:<5}{row['mergedShare']:<8}"
            f"{row['landTables']:<8}{str(row['widths'])[:11]:<12}{row['file'][:44]}"
        )

    readers = Counter(row["reader"] for row in rows)
    chambers = {row["chamber"] for row in rows if row["reader"] != "neither"}
    print(f"\nreaders needed: {dict(readers)}   chambers with land data: {len(chambers)}")
    print(f"currencies: {dict(Counter(row['currency'] for row in rows))}")

    if args.json:
        out = ROOT / "data" / "survey-dialecte-2026.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

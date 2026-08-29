"""Import the Ministry of Finance's monthly count of filled public-sector posts.

    uv run --with xlrd python scripts/import_posturi.py sources/postocupateiunie2026.xls

Writes data/headcount/posturi-ocupate-<yyyy-mm>.json.

This is the denominator Article 21(2) is measured against — posts per ordonator
principal de credite — and the only published figure that lets aggregate() produce a
wage bill rather than a per-person illustration.

What it is not: a distribution across the 1176 positions of the grid. The file has 71
rows, the grid has 1176 positions, and nothing published bridges them. Any assignment of
posts to positions is an assumption the caller has to make and the UI has to state.

The sheet mixes three kinds of row at three depths — a grand total, sections and groups,
and the institutions themselves — with no column saying which is which. Adding them all
up would double-count the state roughly threefold, so each row is classified from its
label and the arithmetic is reconciled against the published subtotals before writing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent

MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
    "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11,
    "decembrie": 12,
}

TOTAL = re.compile(r"^\s*TOTAL", re.IGNORECASE)
SECTION = re.compile(r"^\s*(I+)\.\s")          # I. ADMINISTRAȚIE PUBLICĂ CENTRALĂ
GROUP = re.compile(r"^\s*(\d+)\s*\.")           # 1. Instituții finanțate integral…
SUBLINE = re.compile(r"^\s*[-–]\s")             # - unități sanitare de subordonare…


def classify(label: str) -> str:
    if TOTAL.match(label):
        return "total"
    if SECTION.match(label):
        return "section"
    if GROUP.match(label):
        return "group"
    if SUBLINE.match(label):
        return "subline"
    return "institution"


def slug(text: str) -> str:
    out = (
        text.lower()
        .replace("ă", "a").replace("â", "a").replace("î", "i")
        .replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")
    )
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return re.sub(r"-+", "-", out)[:60]


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sources/postocupateiunie2026.xls"
    if not source.exists():
        raise SystemExit(f"missing {source}")

    book = xlrd.open_workbook(source)
    sheet = book.sheet_by_index(0)

    period = None
    for r in range(min(sheet.nrows, 8)):
        for c in range(sheet.ncols):
            text = str(sheet.cell_value(r, c)).strip().lower()
            match = re.match(r"^([a-zăâîșț]+)\s+(\d{4})$", text)
            if match and match.group(1) in MONTHS:
                period = f"{match.group(2)}-{MONTHS[match.group(1)]:02d}"
    if not period:
        raise SystemExit("could not read the month from the sheet header")

    rows: list[dict] = []
    section = group = None
    for r in range(sheet.nrows):
        label = str(sheet.cell_value(r, 1)).strip() if sheet.ncols > 1 else ""
        raw = sheet.cell_value(r, 2) if sheet.ncols > 2 else ""
        if not label or not isinstance(raw, float):
            continue
        posts = int(round(raw))
        kind = classify(label)
        clean = re.sub(r"\s+", " ", label).strip()

        if kind == "section":
            section, group = clean, None
        elif kind == "group":
            group = clean

        rows.append(
            {
                "key": slug(clean),
                "label": clean,
                "kind": kind,
                "section": None if kind in ("total", "section") else section,
                "group": None if kind in ("total", "section", "group") else group,
                "filledPosts": posts,
            }
        )

    # Where a group publishes a total larger than the sum of the lines under it, the
    # difference is real staff the source simply never itemises. Carrying it as an
    # explicit remainder keeps the leaves reconciling with the published subtotals;
    # dropping it would quietly shrink the state by tens of thousands of posts.
    for grp in [r for r in rows if r["kind"] == "group"]:
        children = [r for r in rows
                    if r["group"] == grp["label"] and r["kind"] in ("institution", "subline")]
        if not children:
            continue
        gap = grp["filledPosts"] - sum(c["filledPosts"] for c in children)
        if gap > 0:
            rows.insert(
                rows.index(children[-1]) + 1,
                {
                    "key": f"{slug(grp['label'])}-nedetaliat",
                    "label": f"{grp['label']} — parte nedetaliată în sursă",
                    "kind": "institution",
                    "section": grp["section"],
                    "group": grp["label"],
                    "filledPosts": gap,
                    "unitemised": True,
                },
            )

    # Reconcile before writing. If the leaves do not add up to the published subtotals,
    # the classifier has mislabelled something and every downstream figure is wrong.
    by_kind = {k: sum(r["filledPosts"] for r in rows if r["kind"] == k) for k in
               ("total", "section", "group", "institution", "subline")}
    total = next(r["filledPosts"] for r in rows if r["kind"] == "total")
    sections = by_kind["section"]

    checks = []
    checks.append(("sections sum to the grand total", sections, total))
    for grp in [r for r in rows if r["kind"] == "group"]:
        children = [
            r for r in rows
            if r["group"] == grp["label"] and r["kind"] in ("institution", "subline")
        ]
        if children:
            checks.append(
                (f"children of {grp['label'][:44]!r}", sum(c["filledPosts"] for c in children), grp["filledPosts"])
            )

    print(f"period {period}: {len(rows)} rows, {total:,} posts total".replace(",", " "))
    worst = 0
    for name, got, want in checks:
        delta = got - want
        worst = max(worst, abs(delta) / max(want, 1))
        flag = "ok " if abs(delta) <= max(1, want * 0.005) else "OFF"
        print(f"  [{flag}] {name}: {got:,} vs {want:,} ({delta:+,})".replace(",", " "))

    document = {
        "$schema": "../../schema/headcount.schema.json",
        "id": f"posturi-ocupate-{period}",
        "period": period,
        "publisher": "Ministerul Finanțelor",
        "title": "Numărul de posturi ocupate în instituțiile și autoritățile publice",
        "totalPosts": total,
        "provenance": {
            "source": "mf-posturi-ocupate",
            "locator": f"{source.name}, foaia '{sheet.name}'",
            "confidence": "verbatim",
            "note": "Raportare lunară a Ministerului Finanțelor. Publicată pe mfinante.gov.ro; o copie mai veche există și pe data.gov.ro sub licența OGL-ROU-1.0.",
        },
        "rows": rows,
        "limitations": [
            {
                "id": "nu-e-pe-functii",
                "text": "Fișierul are 71 de rânduri, grila are 1176 de funcții, iar nimic publicat nu leagă un ordonator de repartiția lui pe funcții. Orice distribuție a posturilor pe funcții este o ipoteză a celui care o face, nu un fapt. Agregarea pe ordonator este solidă; agregarea pe funcție nu.",
                "affects": ["aggregate"],
                "severity": "blocking",
            },
            {
                "id": "posturi-nu-persoane",
                "text": "Se numără posturi ocupate, nu persoane. Cumulul de funcții, timpul parțial și posturile în afara organigramei de la Art. 15 alin. (9) nu se văd aici.",
                "affects": ["aggregate"],
                "severity": "material",
            },
            {
                "id": "ierarhie-nu-se-insumeaza",
                "text": "Rândurile sunt pe trei niveluri — total, secțiuni și grupe, instituții. Însumarea tuturor ar tripla numărul real. Numai rândurile de tip 'institution' și 'subline' se adună, iar concordanța lor cu subtotalurile publicate e verificată la import.",
                "affects": ["aggregate"],
                "severity": "note",
            },
        ],
    }

    out = ROOT / f"data/headcount/posturi-ocupate-{period}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    if worst > 0.005:
        print("  NOTE: a subtotal does not reconcile; see the flags above before trusting any total.")


if __name__ == "__main__":
    main()

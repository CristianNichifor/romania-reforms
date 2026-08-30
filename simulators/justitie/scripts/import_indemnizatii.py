"""What the law pays a judge, by grade.

Chapter 10 of the reform argues that magistrates' pay is unpredictable — a base plus sporuri,
indemnities, compensations and supplements — and should become a single fixed figure. Testing
any of that needs the base the law actually prints, and it was not in the repository: the pay
simulator imported Anexa V's Chapter VIII, which is grefieri, specialists and archivists, and
stops short of the magistrates themselves. Its 184 justice positions contain no judge.

They are in Chapter I of the same annex, in the pay simulator's own copy of the law. This
reads them from there rather than fetching the law twice.

**These are top-of-scale figures and the wage bill built from them is an upper bound.** The
printed table has six seniority columns, and for the four graded ranks only the last — "peste
20 ani" — carries a value; the trainee row is the one exception, printing all six from 8.149
to 10.400 lei. Costing everything at the top of its scale is therefore the only consistent
choice available, and it is consistently too high: a judiciary is not made of twenty-year
veterans. The limitation says so rather than the number pretending otherwise.

What this cannot do is evidence the chapter's actual claim. Showing that sporuri inflate pay
beyond the base needs what is *paid*, and the budget execution data carries no justice line —
389 series, none of them justice. The gap between scale and spend stays unmeasured here.

Usage:
    uv run python scripts/import_indemnizatii.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT.parent / "salarizare" / "sources" / "legea-153-2017.html"
OUT = ROOT / "data" / "indemnizatii-2022.json"

HEADING = "Indemnizația de încadrare pentru judecători, procurori"
# Chapter II of the same annex pays the auxiliary staff — the 8.001 people the CSM report
# counts beside the judges, and most of the payroll this simulator could not price.
AUXILIARY_ANCHOR = "funcții auxiliare de specialitate din cadrul instanțelor"
AUXILIARY_ROWS = {
    "grefier-sef": "Prim-grefier, grefier-șef secție, grefier-șef, grefier-șef cabinet",
    "grefier-s": "specialist criminalist gradul I",
    "grefier-debutant": "specialist criminalist debutant",
}

# Court tier to the grade the law pays it. A judge's grade tracks the level of the court, which
# is what makes the join to the caseload data possible at all.
GRADE_OF_TIER = {
    "iccj": "ICCJ",
    "curte-de-apel": "curte de apel",
    "tribunal": "tribunal",
    "judecatorie": "judecătorie",
}


def cells_of(row: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
    ]


def main() -> int:
    if not LAW.exists():
        raise SystemExit(f"Missing {LAW}; the pay simulator holds the law")

    html = LAW.read_text(encoding="utf-8", errors="ignore")
    start = html.find(HEADING)
    if start < 0:
        raise SystemExit("Chapter I of Annex V not found in the law")

    grades: list[dict] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html[start : start + 120_000], re.S):
        cells = cells_of(row)
        filled = [c for c in cells if c]
        if len(filled) < 5 or not re.match(r"^\d+$", filled[0]):
            continue
        name = filled[1]
        # Section B of the same chapter pays procurors on a parallel scale. The paper
        # reorganises the prosecution service alongside the courts, so both are read.
        if not name.lower().startswith(("judecător", "procuror")):
            continue
        # Values are Romanian-formatted: 26.250 lei and a 10,50 coefficient. Pairs run from
        # the third cell onward, one per seniority step that the table actually fills.
        numbers = filled[3:]
        steps = [
            {
                "monthlyLei": float(numbers[i].replace(".", "").replace(",", ".")),
                "coefficient": float(numbers[i + 1].replace(",", ".")),
            }
            for i in range(0, len(numbers) - 1, 2)
        ]
        if not steps:
            continue
        grades.append(
            {
                "name": name,
                "seniority": filled[2],
                "steps": steps,
                # Costed at the top of whatever the table prints, which for every rank but the
                # trainee is its only value.
                "monthlyLei": steps[-1]["monthlyLei"],
                "coefficient": steps[-1]["coefficient"],
                "provenance": {
                    "source": "legea-153-2017",
                    "locator": f"Anexa nr. V, Capitolul I, litera A, rândul {filled[0]}",
                    "confidence": "verbatim",
                },
            }
        )

    if not grades:
        raise SystemExit("no judge rows parsed; the table shape changed")
    if not any(g["name"].lower().startswith("procuror") for g in grades):
        raise SystemExit("no procuror rows parsed; section B of the chapter changed")

    # The four grades the court map uses must all be present, or a court tier ends up unpriced
    # and its wage bill silently reads as zero.
    missing = [
        tier
        for tier, grade in GRADE_OF_TIER.items()
        if not any(grade.lower() in g["name"].lower() for g in grades)
    ]
    if missing:
        print(f"no pay grade found for: {missing}", file=sys.stderr)
        return 1

    print(f"judge grades: {len(grades)}")
    for grade in grades:
        print(f"  {grade['coefficient']:>6.2f} × ref   {grade['monthlyLei']:>9,.0f} lei   "
              f"({len(grade['steps'])} treaptă/trepte)   {grade['name'][:48]}")

    # Read backwards from the chapter's closing note: the table has no heading of its own that
    # survives the HTML, but the note defining "vechime în funcție" sits immediately after it.
    auxiliary: list[dict] = []
    end = html.lower().find(AUXILIARY_ANCHOR)
    if end < 0:
        print("Chapter II of Annex V not found; auxiliary staff cannot be priced", file=sys.stderr)
        return 1
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html[max(0, end - 160_000) : end], re.S):
        filled = [c for c in cells_of(row) if c]
        if len(filled) < 4 or not re.match(r"^\d+$", filled[0]):
            continue
        name = filled[1]
        lei = next((c for c in filled[3:] if re.fullmatch(r"\d{4,5}", c)), None)
        if lei is None or "grefier" not in name.lower():
            continue
        for key, needle in AUXILIARY_ROWS.items():
            if needle.lower() in name.lower() and not any(a["key"] == key for a in auxiliary):
                auxiliary.append(
                    {
                        "key": key,
                        "name": name,
                        "monthlyLei": float(lei),
                        "provenance": {
                            "source": "legea-153-2017",
                            "locator": f"Anexa nr. V, Capitolul II, rândul {filled[0]}",
                            "confidence": "verbatim",
                        },
                    }
                )
    missing_aux = [k for k in AUXILIARY_ROWS if not any(a["key"] == k for a in auxiliary)]
    if missing_aux:
        print(f"auxiliary rows not found: {missing_aux}", file=sys.stderr)
        return 1
    print("\nauxiliar (Anexa V, Cap. II):")
    for row in auxiliary:
        print(f"  {row['monthlyLei']:>9,.0f} lei   {row['name'][:60]}")

    document = {
        "$schema": "../schema/indemnizatii.schema.json",
        "id": "indemnizatii-2022",
        "title": "Indemnizația de încadrare a judecătorilor, pe grade",
        "publisher": "Parlamentul României",
        "period": "2022",
        "provenance": {
            "source": "legea-153-2017",
            "locator": "Anexa nr. V, Capitolul I, litera A",
            "confidence": "verbatim",
            "note": (
                "Sumele sunt cele tipărite pentru anul 2022. Tabelul are șase coloane de "
                "gradație; pentru cele patru grade de judecător doar ultima — „peste 20 ani” "
                "— are valoare, iar rândul judecătorului stagiar le are pe toate șase. "
                "Costul e calculat la vârful grilei fiecăruia."
            ),
        },
        "grades": grades,
        "auxiliary": auxiliary,
        "tierToGrade": GRADE_OF_TIER,
        "limitations": [
            {
                "id": "doar-varful-grilei",
                "text": (
                    "Pentru cele patru grade de judecător, legea tipărește doar indemnizația "
                    "pentru „peste 20 de ani” în funcție. O instanță nu e făcută din "
                    "judecători cu douăzeci de ani vechime, așa că orice cost calculat din "
                    "ele este o limită de sus, nu o estimare."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "fara-sporuri",
                "text": (
                    "Este indemnizația de bază, fără sporuri, indemnizații de hrană, "
                    "compensații sau alte drepturi — exact ce reproșează capitolul 10 "
                    "sistemului actual. Cât se plătește peste bază se știe acum, dar la nivel "
                    "de sistem, nu de grad: instanțele plătesc în sporuri 24,9% din salariile "
                    "de bază (vezi sporuri-2025). Cifrele de aici rămân indemnizația goală."
                ),
                "severity": "material",
                "affects": ["cost", "salarizare"],
            },
            {
                "id": "sumele-sunt-din-2022",
                "text": (
                    "Cifrele sunt cele ale anului 2022, iar volumul de dosare e din 2025. "
                    "Costurile de aici sunt în lei 2022 pe activitatea din 2025."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

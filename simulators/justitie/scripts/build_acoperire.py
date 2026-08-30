"""How much of the paper this simulator actually checks, chapter by chapter.

The page grew by whatever happened to be computable, so its sections are named after topics —
"Sporurile", "Parchetele" — and a reader has no way to map them back to the document they come
from, or to see what was left out. A simulator that silently omits a chapter is making a claim
about coverage without stating it.

This builds the ledger: every chapter of the paper, with what the simulator does about it.

Three states, and the third splits in a way that matters:

  * **simulat** — something here computes it, and the documents are named. Four chapters.
  * **citat** — carried as the paper's own text, because it is institutional design rather
    than a quantity. ANIR, the KPI framework, the implementation plan.
  * **negacoperit** — and the honest distinction is between a chapter that *could* be built
    and one that is not a quantity at all. Nothing is left in the first group. Chapter 1 is an
    argument; there is nothing to compute. Keeping the distinction still matters: collapsing
    the two would be dishonest in opposite directions — one hides work, the other invents it.

Chapters 7, 10 and 11 are both simulated and quoted: their measurable parts are computed and
their design parts are carried verbatim. The ledger records both rather than forcing a choice.

Chapter 16 was the largest of the buildable gaps and is now simulated. It turned out not to be
missing arithmetic but unreconciled arithmetic: six figures asserted in a bullet list, three of
which disagree with the pay grid, the vacancy count and the court estate this repository
already holds.

Chapters 4 and 5 were the last two, and they close the same way: the Danish comparison is
checked against the paper's own premises and Eurostat's populations, and the headline of 5.1 —
"de trei ori mai multe instante" — comes out at 2,3. Every chapter that can be computed now is.

**The status of each chapter is a judgement, not a reading.** Titles and pages come out of the
PDF; whether a chapter counts as covered is mine, and it is marked `assumed` for that reason.
What is not a judgement is whether the named documents exist: the build fails if any of them
is missing, so "4 of 19" cannot drift into fiction while the files move underneath it.

Usage:
    uv run --with pypdf python scripts/build_acoperire.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "reforma-sistem-judiciar-romania.pdf"
OUT = ROOT / "data" / "acoperire.json"

# Chapter number -> (title as printed, a distinctive prefix to find the heading by).
CHAPTERS = {
    1: ("Introducere – De ce avem nevoie de reformă profundă", "Introducere"),
    2: ("Radiografia sistemului judiciar românesc", "Radiografia"),
    3: ("Probleme sistemice care blochează funcționalitatea", "Probleme sistemice"),
    4: ("Modelul danez", "Modelul danez"),
    5: ("Diferențe structurale România – Danemarca", "Diferente structurale"),
    6: ("Viziunea de reformă și principiile noului sistem", "Viziunea de reforma"),
    7: ("Noua arhitectură instituțională", "Noua arhitectura institutionala"),
    8: ("Administrația Națională a Instanțelor", "Administratia Nationala a Instantelor"),
    9: ("Reforma resurselor umane", "Reforma resurselor umane"),
    10: ("Reforma salarizării", "Reforma salarizarii"),
    11: ("Reforma pensiilor", "Reforma pensiilor"),
    12: ("Noua hartă judiciară", "Noua harta judiciara"),
    13: ("Digitalizare și infrastructură", "Digitalizare"),
    14: ("KPI și performanță", "KPI"),
    15: ("Plan de implementare", "Plan de implementare"),
    16: ("Resurse necesare", "Resurse necesare"),
    17: ("Impactul reformei", "Impactul reformei"),
    18: ("Concluzie", "Concluzie"),
    19: ("Sinteză", "Sinteza"),
}

# What the simulator does about each. Documents are named so the claim can be checked.
SIMULATED = {
    4: ["danemarca-comparatie"],
    5: ["danemarca-comparatie"],
    7: ["instante-localizate-2025", "arondare-noua", "parchete-2025", "acces-servicii"],
    10: ["indemnizatii-2022", "sporuri-2025", "costuri-proiect-2026"],
    11: ["pensii-2025", "pensii-comparatie"],
    16: ["resurse-necesare"],
    12: ["costuri-2025", "acces-2025", "arondare-noua", "eficienta-csm", "personal-2025"],
}

# Carried as the paper's own text in design-reforma.
QUOTED = {7, 8, 9, 10, 11, 13, 14, 15}

# Chapters nothing here touches. "buildable" means the data exists and the work does not;
# "not-a-quantity" means there is nothing to compute even in principle.
GAPS = {
    1: "not-a-quantity",
    2: "not-a-quantity",
    3: "not-a-quantity",
    6: "not-a-quantity",
    17: "not-a-quantity",
    18: "not-a-quantity",
    19: "not-a-quantity",
}

GAP_WHY = {
    1: "Diagnostic și motivație; nu conține cantități de verificat.",
    2: "Descriere a sistemului; cifrele ei sunt reluate în capitolele care se simulează.",
    3: "Enumerare de probleme structurale, argumentativă.",
    6: "Principii de reformă.",
    17: "Impacturi revendicate, dintre care multe depind de capitolul 16.",
    18: "Concluzie.",
    19: "Sinteză; nu apare în cuprins, doar în corp.",
}


def main() -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")
    pages = [
        re.sub(r"\s+", " ", p.extract_text() or "") for p in PdfReader(str(SOURCE)).pages
    ]

    chapters = []
    for number, (title, needle) in CHAPTERS.items():
        # The last page carrying the heading is the body one: the table of contents comes
        # first, so a first-match rule finds the contents entry instead of the chapter.
        found = [
            i + 1
            for i, text in enumerate(pages)
            if re.search(rf"(?<!\d){number}\.\s*{re.escape(needle[:16])}", text, re.I)
        ]
        if not found:
            print(f"chapter {number} ({needle}) not found in the paper", file=sys.stderr)
            return 1
        documents = SIMULATED.get(number, [])
        chapters.append(
            {
                "number": number,
                "title": title,
                "page": found[-1],
                "simulated": documents,
                "quoted": number in QUOTED,
                "gap": GAPS.get(number),
                "why": GAP_WHY.get(number),
                "status": (
                    "simulat" if documents else "citat" if number in QUOTED else "negacoperit"
                ),
            }
        )

    # The check that keeps the headline honest: every document a chapter claims must exist.
    missing = [
        f"{c['number']}:{d}"
        for c in chapters
        for d in c["simulated"]
        if not (ROOT / "data" / f"{d}.json").exists()
    ]
    if missing:
        print(f"chapters name documents that do not exist: {missing}", file=sys.stderr)
        return 1

    counts = {
        "simulat": sum(1 for c in chapters if c["status"] == "simulat"),
        "citat": sum(1 for c in chapters if c["status"] == "citat"),
        "negacoperit": sum(1 for c in chapters if c["status"] == "negacoperit"),
        "buildable": sum(1 for c in chapters if c["gap"] == "buildable"),
        "notAQuantity": sum(1 for c in chapters if c["gap"] == "not-a-quantity"),
        "total": len(chapters),
    }

    for c in chapters:
        mark = {"simulat": "●", "citat": "○", "negacoperit": "✕"}[c["status"]]
        extra = f"  [{c['gap']}]" if c["gap"] else (f"  {len(c['simulated'])} documente" if c["simulated"] else "")
        print(f"  {mark} {c['number']:>2}. p.{c['page']:<3} {c['title'][:46]:<48}{extra}")
    print(f"\nsimulat {counts['simulat']}   citat {counts['citat']}   "
          f"negacoperit {counts['negacoperit']} (din care {counts['buildable']} se pot construi)")

    document = {
        "$schema": "../schema/acoperire.schema.json",
        "id": "acoperire",
        "title": "Ce verifică simulatorul din lucrare, capitol cu capitol",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": "Cuprins și titlurile de capitol din corpul lucrării",
            "confidence": "assumed",
            "note": (
                "Titlurile și paginile sunt citite din PDF. Încadrarea fiecărui capitol — "
                "simulat, citat sau neacoperit — este o judecată a autorului simulatorului, nu "
                "o lectură a lucrării. Ce nu e judecată: documentele numite trebuie să existe, "
                "altfel construcția eșuează."
            ),
        },
        "counts": counts,
        "chapters": chapters,
        "limitations": [
            {
                "id": "incadrarea-e-o-judecata",
                "text": (
                    "Ce înseamnă „simulat” e o judecată. Capitolul 7 e trecut ca simulat pentru "
                    "că harta, arondarea și parchetele se calculează — dar tot capitolul 7 "
                    "propune și lucruri care nu se măsoară, iar acelea sunt doar citate. Un "
                    "capitol poate fi în ambele stări, și trei sunt."
                ),
                "severity": "material",
                "affects": ["acoperire"],
            },
            {
                "id": "capitolul-19-nu-e-in-cuprins",
                "text": (
                    "Cuprinsul lucrării se oprește la 18, dar corpul are un al nouăsprezecelea "
                    "capitol, „Sinteză”. Ledgerul îl numără, deci totalul de aici este 19, nu "
                    "18 cât ar spune cuprinsul."
                ),
                "severity": "note",
                "affects": ["acoperire"],
            },
            {
                "id": "acoperire-nu-inseamna-validare",
                "text": (
                    "Un capitol „simulat” nu e un capitol confirmat. Simulatorul calculează ce "
                    "propune și, uneori, contrazice — premisa de eficiență din capitolul 12 e "
                    "verificată și nu se susține. Acoperire înseamnă că s-a verificat ceva, nu "
                    "că a ieșit bine."
                ),
                "severity": "material",
                "affects": ["acoperire"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

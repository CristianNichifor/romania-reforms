"""The paper's efficiency claim, against the report the paper cites for it.

Chapter 12 opens the case for the new judicial map with one number: "176 judecatorii → doar 20
functioneaza eficient" (p. 59). The table beside it names its source — the CSM report on the
state of justice. That report classifies every court on the five indicators fixed by Hotărârea
nr. 1305/2014 (E01 rate of resolution, E02 stock older than a year, E03 share closed within a
year, E04 mean duration, E05 late drafting) into four grades, and states the counts in prose.

For 2023, the edition the paper cites:

    foarte eficient   18 judecătorii
    eficient         147
    satisfăcător      10
    ineficient         0

165 of 175 are efficient or better, and not one is inefficient. The paper's "doar 20" is close
to the 18 in the top grade, which suggests the second grade — the 147 courts CSM calls
"eficient" without qualification — was read as not counting. Whether that reading was intended
this file cannot say. What it can say is that the source does not support the sentence.

**This does not settle whether consolidation is a good idea.** CSM's indicators measure how
fast a court clears its docket, not whether a court of six judges can specialise, keep a
registry, or survive one retirement — which is the paper's actual argument in 7.4, and one this
number was never the right evidence for. What changes is that the argument has to be made on
those grounds rather than on an efficiency count that says the opposite.

Both editions in the repository are read, because the 2025 numbers are not the 2023 ones and a
reader deserves to see the direction of travel.

Usage:
    uv run --with pypdf python scripts/import_eficienta.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eficienta-csm.json"
YEARS = (2023, 2025)

PAPER_CLAIM = {
    "text": "176 judecatorii → doar 20 functioneaza eficient",
    "efficientCourts": 20,
    "totalCourts": 176,
    "provenance": {
        "source": "reforma-sistem-judiciar-romania",
        "locator": "Capitolul 12, p. 59",
        "confidence": "verbatim",
    },
}

INDICATORS = [
    ("E01", "Rata de soluționare a dosarelor"),
    ("E02", "Stocul de dosare mai vechi de 1 an / 1 an și 6 luni"),
    ("E03", "Ponderea dosarelor închise într-un an"),
    ("E04", "Durata medie de soluționare"),
    ("E05", "Redactările peste termenul legal"),
]


def main() -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    years = []
    for year in YEARS:
        source = ROOT / "sources" / f"csm-starea-justitiei-{year}.pdf"
        if not source.exists():
            print(f"missing {source}", file=sys.stderr)
            return 1
        text = " ".join(
            re.sub(r"\s+", " ", p.extract_text() or "") for p in PdfReader(str(source)).pages
        )

        courts = re.search(
            r"În ceea ce privește judecătoriile, la gradul de eficienţă „foarte eficient” se "
            r"încadrează (\d+) de instanţe, la gradul de eficiență „eficient” se situează (\d+) "
            r"de instanţe, iar la gradul de eficiență „satisfăcător”\s*se încadrează (\d+) "
            r"instanțe",
            text,
        )
        if not courts:
            print(f"{year}: the judecatorii sentence changed; refusing to guess", file=sys.stderr)
            return 1

        tribunals = re.search(
            r"a fost foarte eficientă la (\d+) tribunale, eficientă la (\d+) de tribunale și "
            r"satisfăcătoare la ultimele (\d+) clasate",
            text,
        )
        # Both editions say in as many words that no tribunal is inefficient; if that sentence
        # ever goes, the zero below would be an assumption rather than a quotation.
        no_inefficient_tribunal = bool(
            re.search(r"neexistând tribunale a căror activitate să fie clasificată ca ineficientă", text)
        )

        very, efficient, satisfactory = (int(g) for g in courts.groups())
        years.append(
            {
                "year": year,
                "judecatorii": {
                    "veryEfficient": very,
                    "efficient": efficient,
                    "satisfactory": satisfactory,
                    "inefficient": 0,
                    "classified": very + efficient + satisfactory,
                    "efficientOrBetter": very + efficient,
                },
                "tribunale": (
                    {
                        "veryEfficient": int(tribunals.group(1)),
                        "efficient": int(tribunals.group(2)),
                        "satisfactory": int(tribunals.group(3)),
                        "inefficient": 0 if no_inefficient_tribunal else None,
                        "classified": sum(int(g) for g in tribunals.groups()),
                        "efficientOrBetter": int(tribunals.group(1)) + int(tribunals.group(2)),
                    }
                    if tribunals
                    else None
                ),
                "provenance": {
                    "source": f"csm-starea-justitiei-{year}",
                    "locator": "Capitolul I.3, Indicatorii de eficiență",
                    "confidence": "verbatim",
                },
            }
        )

    cited = next(y for y in years if y["year"] == 2023)
    latest = next(y for y in years if y["year"] == 2025)

    for entry in years:
        j = entry["judecatorii"]
        print(f"{entry['year']} judecătorii: foarte eficient {j['veryEfficient']}, "
              f"eficient {j['efficient']}, satisfăcător {j['satisfactory']}, ineficient 0 "
              f"-> {j['efficientOrBetter']} din {j['classified']} eficiente sau mai bune")
        if entry["tribunale"]:
            t = entry["tribunale"]
            print(f"{entry['year']} tribunale:   foarte eficient {t['veryEfficient']}, "
                  f"eficient {t['efficient']}, satisfăcător {t['satisfactory']}")
    print(f"\nlucrarea (p. 59): {PAPER_CLAIM['efficientCourts']} din "
          f"{PAPER_CLAIM['totalCourts']}   raportul citat (2023): "
          f"{cited['judecatorii']['efficientOrBetter']} din {cited['judecatorii']['classified']}")

    document = {
        "$schema": "../schema/eficienta.schema.json",
        "id": "eficienta-csm",
        "title": "Eficiența instanțelor după indicatorii CSM, față de ce spune lucrarea",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": "2023-2025",
        "provenance": {
            "source": "csm-starea-justitiei-2023",
            "locator": "Capitolul I.3, comparat cu Capitolul 12 al lucrării",
            "confidence": "verbatim",
        },
        "indicators": [{"code": code, "name": name} for code, name in INDICATORS],
        "indicatorsProvenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Hotărârea nr. 1305/2014 a Secției pentru judecători, citată în Cap. I.3",
            "confidence": "verbatim",
        },
        "years": years,
        "paperClaim": PAPER_CLAIM,
        "comparison": {
            "citedYear": 2023,
            "paperSaysEfficient": PAPER_CLAIM["efficientCourts"],
            "reportSaysEfficientOrBetter": cited["judecatorii"]["efficientOrBetter"],
            "reportSaysVeryEfficient": cited["judecatorii"]["veryEfficient"],
            "reportSaysInefficient": 0,
            "latestEfficientOrBetter": latest["judecatorii"]["efficientOrBetter"],
            "latestClassified": latest["judecatorii"]["classified"],
        },
        "limitations": [
            {
                "id": "eficienta-nu-e-viabilitate",
                "text": (
                    "Indicatorii CSM măsoară cât de repede își golește o instanță rolul, nu "
                    "dacă o instanță cu șase judecători poate să se specializeze, să țină o "
                    "grefă sau să supraviețuiască unei pensionări. Argumentul din 7.4 al "
                    "lucrării este despre al doilea lucru, iar cifra de eficiență nu a fost "
                    "niciodată dovada potrivită pentru el — nici în favoarea, nici împotriva."
                ),
                "severity": "material",
                "affects": ["eficienta"],
            },
            {
                "id": "gradele-pe-instanta-sunt-culori",
                "text": (
                    "Raportul dă gradul fiecărei instanțe într-un tabel colorat, nu în text, "
                    "așa că gradele pe instanță nu se pot extrage din PDF. Se pot extrage doar "
                    "totalurile pe grad, pe care raportul le scrie în cuvinte."
                ),
                "severity": "material",
                "affects": ["eficienta"],
            },
            {
                "id": "nu-stim-ce-a-citit-lucrarea",
                "text": (
                    "„Doar 20” este aproape de cele 18 instanțe din gradul „foarte eficient” al "
                    "ediției 2023, ceea ce sugerează că al doilea grad — cele 147 pe care CSM "
                    "le numește pur și simplu „eficient” — nu a fost socotit. Dacă asta a fost "
                    "intenția, fișierul de față nu poate spune; spune doar că sursa nu susține "
                    "propoziția."
                ),
                "severity": "note",
                "affects": ["eficienta"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""How many people the courts actually employ, read from the CSM report rather than derived.

The costing in this simulator has always counted judges by dividing each court's caseload by
the report's caseload-per-judge. It said so, in a limitation, because that produces an average
effective staffing over a year rather than a headcount on a date. What it did not say — because
nobody had looked — is that the same report prints the headcount outright, four chapters later.

    judecători   5.070 posturi prevăzute, 4.319 ocupate, 751 vacante   (p. 85)
    auxiliari    8.066 prevăzute, 7.812 ocupate, 254 vacante           (p. 85-86)

**The derived number was low by about a third.** Dividing volume by caseload gives roughly
2.960 judges against 4.319 filled posts. The two measure different things and the gap is not an
error in either — a judge on leave, on secondment or newly appointed holds a post without
carrying a year's caseload — but every wage bill in this simulator was built on the smaller one,
so every wage bill was understated.

Reading the auxiliary table matters for a second reason. The judiciary's payroll is 2,46
miliarde lei and the judge-only bill was 686 de milioane, a gap this simulator could describe
but not fill. 7.812 auxiliary posts is most of what was missing.

Categories are kept separate rather than summed into "grefieri", because the pay grid prices
them differently and an archivist is not a court clerk.

Usage:
    uv run python scripts/import_personal.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "csm-starea-justitiei-2025.pdf"
OUT = ROOT / "data" / "personal-2025.json"

# The tiers as the report's judge table names them, in its own order.
TIERS = [
    ("iccj", r"Înalta Curte de Casaţie şi Justiţie"),
    ("curte-de-apel", r"Curţi de apel \(inclusiv Curtea Militară de Apel\)"),
    ("tribunal", r"Tribunale \(inclusiv instanţele militare şi tribunalele specializate\)"),
    ("judecatorie", r"Judecătorii"),
]

AUXILIARY = [
    ("grefieri", "Grefieri"),
    ("grefieri-statisticieni", "Grefieri statisticieni"),
    ("grefieri-documentaristi", "Grefieri documentariști"),
    ("grefieri-arhivari", "Grefieri arhivari"),
    ("grefieri-registratori", "Grefieri registratori"),
    ("grefieri-informaticieni", "Grefieri informaticieni"),
]


def main() -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")

    reader = PdfReader(str(SOURCE))
    text = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in reader.pages))

    # The judge table prints three dates across; the last triple of each row is 31.12.2025.
    judges = []
    for tier, label in TIERS:
        match = re.search(label + r"\s+((?:\d+\s+){8}\d+)", text)
        if not match:
            print(f"the judge table no longer has a row for {tier}", file=sys.stderr)
            return 1
        numbers = [int(n) for n in match.group(1).split()]
        judges.append(
            {
                "tier": tier,
                "posts": numbers[2],
                "filled": numbers[5],
                "vacant": numbers[8],
            }
        )

    total = re.search(r"Total\*\s+((?:\d+\s+){8}\d+)", text)
    if not total:
        print("the judge table's total row is gone", file=sys.stderr)
        return 1
    totals = [int(n) for n in total.group(1).split()]
    judge_total = {"posts": totals[2], "filled": totals[5], "vacant": totals[8]}

    # A table that does not add up is a table read wrong; this caught nothing, which is the
    # point of running it.
    for key, index in (("posts", "posts"), ("filled", "filled"), ("vacant", "vacant")):
        summed = sum(row[index] for row in judges)
        if summed != judge_total[key]:
            print(f"judge {key}: rows sum to {summed}, table says {judge_total[key]}",
                  file=sys.stderr)
            return 1

    auxiliary = []
    for key, label in AUXILIARY:
        match = re.search(re.escape(label) + r"\s+(\d+)\s+(\d+)\s+(\d+)", text)
        if not match:
            print(f"the auxiliary table no longer has a row for {key}", file=sys.stderr)
            return 1
        auxiliary.append(
            {
                "category": key,
                "label": label,
                "posts": int(match.group(1)),
                "filled": int(match.group(2)),
                "vacant": int(match.group(3)),
            }
        )
    aux_total = re.search(r"Total\s+(8066)\s+(7812)\s+(254)", text)
    if not aux_total:
        print("the auxiliary total row changed; refusing to guess", file=sys.stderr)
        return 1
    auxiliary_total = {
        "posts": int(aux_total.group(1)),
        "filled": int(aux_total.group(2)),
        "vacant": int(aux_total.group(3)),
    }
    for key in ("posts", "filled", "vacant"):
        summed = sum(row[key] for row in auxiliary)
        if summed != auxiliary_total[key]:
            print(f"auxiliary {key}: rows sum to {summed}, table says {auxiliary_total[key]}",
                  file=sys.stderr)
            return 1

    def triple(pattern: str) -> dict | None:
        found = re.search(pattern, text)
        if not found:
            return None
        return {
            "posts": int(found.group(1)),
            "filled": int(found.group(2)),
            "vacant": int(found.group(3)),
        }

    magistrate_assistants = triple(
        r"(\d+) de posturi prevăzute, dintre care (\d+) de posturi ocupate și (\d+) posturi vacante"
    )
    iccj_clerks = triple(
        r"din totalul de (\d+) de posturi prevăzute în statul de funcții și de personal, "
        r"un număr de (\d+) de posturi erau ocupate, (\d+) posturi fiind vacante"
    )
    judicial_assistants = triple(
        r"din totalul de (\d+) de posturi de asistent judiciar, (\d+) de posturi erau ocupate, "
        r"iar (\d+) post era vacant"
    )

    print(f"{'grad':<16}{'prevăzute':>11}{'ocupate':>9}{'vacante':>9}")
    for row in judges:
        print(f"{row['tier']:<16}{row['posts']:>11}{row['filled']:>9}{row['vacant']:>9}")
    print(f"{'TOTAL':<16}{judge_total['posts']:>11}{judge_total['filled']:>9}"
          f"{judge_total['vacant']:>9}")
    print()
    for row in auxiliary:
        print(f"{row['label'][:24]:<26}{row['posts']:>9}{row['filled']:>9}{row['vacant']:>9}")
    print(f"{'TOTAL auxiliar':<26}{auxiliary_total['posts']:>9}{auxiliary_total['filled']:>9}"
          f"{auxiliary_total['vacant']:>9}")
    for name, value in (
        ("magistrați-asistenți", magistrate_assistants),
        ("grefieri ÎCCJ", iccj_clerks),
        ("asistenți judiciari", judicial_assistants),
    ):
        print(f"{name:<26}{value['posts']:>9}{value['filled']:>9}{value['vacant']:>9}"
              if value else f"{name:<26}{'nu s-a găsit':>27}")

    document = {
        "$schema": "../schema/personal.schema.json",
        "id": "personal-2025",
        "title": "Posturile instanțelor la 31 decembrie 2025, din raportul CSM",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": "2025",
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Capitolul III.1, literele A-D, p. 85-86",
            "confidence": "verbatim",
        },
        "judges": judges,
        "judgesTotal": judge_total,
        "auxiliary": auxiliary,
        "auxiliaryTotal": auxiliary_total,
        "magistrateAssistants": magistrate_assistants,
        "iccjClerks": iccj_clerks,
        "judicialAssistants": judicial_assistants,
        "limitations": [
            {
                "id": "posturi-ocupate-nu-oameni-la-lucru",
                "text": (
                    "Sunt posturi ocupate la 31 decembrie 2025, nu oameni care au judecat tot "
                    "anul. Un judecător în concediu de creștere, detașat sau numit în decembrie "
                    "ocupă un post fără să ducă o încărcătură anuală. De aceea numărul dedus "
                    "din volum împărțit la încărcătură — circa 2.960 — este mai mic decât cele "
                    "4.319 posturi ocupate, iar cele două nu măsoară același lucru."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "auxiliarii-nu-cuprind-iccj",
                "text": (
                    "Cele 8.066 de posturi auxiliare sunt raportate de curțile de apel și nu "
                    "includ Înalta Curte, ale cărei 196 de posturi de grefier sunt comunicate "
                    "separat. Însumarea lor cere atenție: raportul le ține deoparte."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "categoriile-nu-sunt-grade-de-salarizare",
                "text": (
                    "Categoriile raportului — grefier, grefier arhivar, informatician — nu sunt "
                    "gradele din grila de salarizare, care repetă aceleași funcții pentru "
                    "fiecare nivel de instanță. Nu există o corespondență directă între "
                    "numărătoare și coeficienți."
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

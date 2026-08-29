"""Two pension reforms, side by side — the paper's and the Government's.

Chapter 11 of the reform paper and the Ministry of Justice bill of 19 November 2025 were
written at the same time about the same problem, and they do not agree. On the single most
consequential mechanical detail they point in opposite directions: the paper removes sporuri
from the calculation base, the bill writes them in.

Neither is scored. What the simulator can do is put the two rules against the same judge and
show what each pays, so a reader can see that "reforming service pensions" describes two very
different futures.

Usage:
    uv run python scripts/build_pensii_comparatie.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "pensii-comparatie.json"
BENCHMARKS = ROOT.parent / "salarizare" / "data" / "fiscal" / "benchmarks.json"

# Chapter 11 of the paper, read from pages 58-59.
PAPER = {
    "principles": [
        "contributivitate",
        "plafonare",
        "transparență",
        "eliminarea sporurilor din baza de calcul",
        "creșterea vârstei de pensionare",
    ],
    "formula": "pensie contributivă + supliment de cel mult 20%",
    "supplementPercent": 20,
    "supplementCondition": "doar pentru continuitatea în sistem",
    "capDescription": "un salariu mediu brut pe economie",
    "retirementAgeFrom": 58,
    "retirementAgeTo": 65,
    "transitionYears": 10,
    "provenance": {
        "source": "reforma-sistem-judiciar-romania",
        "locator": "Capitolul 11, p. 58-59",
        "confidence": "verbatim",
    },
}


def main() -> int:
    bill_file = ROOT / "data" / "pensii-2025.json"
    if not bill_file.exists() or not BENCHMARKS.exists():
        raise SystemExit("run import_pensii.py first, and export the pay simulator's data")

    bill = json.loads(bill_file.read_text(encoding="utf-8"))
    benchmarks = json.loads(BENCHMARKS.read_text(encoding="utf-8"))
    average = next(
        (
            s["observations"][-1]["value"]
            for v in benchmarks.values()
            if isinstance(v, list)
            for s in v
            if isinstance(s, dict) and s.get("id") == "avg-gross-monthly-ro"
        ),
        None,
    )
    if average is None:
        print("no Romanian average gross wage in the benchmarks", file=sys.stderr)
        return 1

    rows = []
    for grade in bill["byGrade"]:
        # The paper caps the whole pension at one average gross wage, whatever the grade. The
        # bill's floor is a percentage of the grade's own indemnity. So the paper's ceiling can
        # sit below the bill's floor, and for the senior grades it does.
        rows.append(
            {
                "grade": grade["grade"],
                "currentLei": grade["currentLei"],
                "billFloorLei": grade["proposedFloorLei"],
                "paperCapLei": round(average),
                "paperCapBelowBillFloor": average < grade["proposedFloorLei"],
            }
        )

    below = sum(1 for r in rows if r["paperCapBelowBillFloor"])
    print(f"salariul mediu brut (RO, 2024): {average:,.0f} lei\n")
    print(f"{'grad':<44}{'azi':>10}{'proiect':>10}{'plafon lucrare':>16}")
    for r in rows:
        mark = "  <" if r["paperCapBelowBillFloor"] else ""
        print(f"{r['grade'][:42]:<44}{r['currentLei']:>10,}{r['billFloorLei']:>10,}"
              f"{r['paperCapLei']:>16,}{mark}")
    print(f"\n  grades where the paper's cap is below the bill's floor: {below} of {len(rows)}")

    document = {
        "$schema": "../schema/pensii-comparatie.schema.json",
        "id": "pensii-comparatie",
        "title": "Două reforme ale pensiilor de serviciu, față în față",
        "publisher": "Cristian Nichifor",
        "published": False,
        "period": "2025",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": "Capitolul 11, comparat cu proiectul MJ din 19 noiembrie 2025",
            "confidence": "derived",
        },
        "averageGrossWageLei": round(average, 2),
        "paper": PAPER,
        "bill": {
            "percent": bill["proposed"]["percent"],
            "seniorityYears": bill["proposed"]["seniorityYears"],
            "baseDescription": bill["proposed"]["baseDescription"],
            "netCapPercent": bill["proposed"]["netCapPercent"],
            "provenance": bill["proposed"]["provenance"],
        },
        "byGrade": rows,
        "disagreements": [
            {
                "id": "sporurile-in-baza",
                "text": (
                    "Lucrarea scoate sporurile din baza de calcul; proiectul le scrie înăuntru, "
                    "explicit — „media indemnizațiilor de încadrare brute lunare și a "
                    "sporurilor pentru care au fost reținute contribuții”. Este detaliul care "
                    "decide cel mai mult din cuantum, și cele două merg în direcții opuse."
                ),
            },
            {
                "id": "plafonul",
                "text": (
                    f"Lucrarea plafonează pensia la un salariu mediu brut — {average:,.0f} lei. "
                    "Proiectul o plafonează la 70% din venitul net al persoanei, deci "
                    "proporțional cu propriul salariu. Plafonul lucrării este sub pragul "
                    f"proiectului la {below} din {len(rows)} grade."
                ).replace(",", "."),
            },
            {
                "id": "varsta",
                "text": (
                    "Lucrarea cere 58 de ani acum și 65 la final; proiectul nu schimbă vârsta, "
                    "ci vechimea — de la 25 la 35 de ani de muncă."
                ),
            },
        ],
        "limitations": [
            {
                "id": "lucrarea-nu-e-lege",
                "text": (
                    "Lucrarea este propunerea autorului acestui simulator, nu un act normativ. "
                    "Proiectul este un document al Guvernului aflat în dezbatere publică. Sunt "
                    "comparate ca argumente, nu ca norme de rang egal."
                ),
                "severity": "material",
                "affects": ["pensii"],
            },
            {
                "id": "pensia-contributiva-nu-e-calculata",
                "text": (
                    "Formula lucrării pornește de la pensia contributivă, care depinde de "
                    "contribuțiile fiecărei persoane pe toată cariera. Nu se poate calcula din "
                    "datele de aici, așa că din propunerea lucrării se poate arăta doar "
                    "plafonul, nu și cuantumul."
                ),
                "severity": "blocking",
                "affects": ["pensii"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

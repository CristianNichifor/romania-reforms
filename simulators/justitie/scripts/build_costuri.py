"""What the judiciary's judges cost, and what consolidation does to that.

Joins two things the repository already holds: how many judges each court has, reconstructed
from the CSM report, and what the law pays a judge of that grade, read from Annex V Chapter I.
Multiplying gives the base wage bill — per court, per grade, and under the staffing the
proposal would need.

**The question that used to decide a third of the answer is settled, and the paper settles it.**
This file long said the paper merges judecătorii and tribunale without saying what grade the
merged court's judges hold — a difference of hundreds of millions a year between 17.250 and
22.500 lei a month. It does say, twice. The architecture table on p. 43 lists judecătoriile as
DESFIINȚATE and level 2 as "Judecătorii + Tribunale consolidate ~42"; p. 45 spells out that the
reform "elimină judecătoriile ca instituții administrative separate" and that their judging
function "este preluată integral de tribunale județene sau metropolitane". The surviving
institution is the tribunal, so the merged court is a tribunal and its judges are paid at
tribunal grade.

The judecătorie-grade figures stay in the file as the counterfactual — what the same judiciary
would have cost had the merged court been the junior one — but they are no longer offered as
an equal reading of the paper.

Everything here is base indemnity at the top of the printed scale. It is an upper bound on the
base and a lower bound on what is actually paid, because the sporuri the chapter argues about
are not in it and cannot be found in the public data.

Usage:
    uv run python scripts/build_costuri.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "costuri-2025.json"

MONTHS = 12

# The grade of the merged first-level court, read out of the paper rather than left open.
RESOLVED_GRADE = {
    "grade": "tribunal",
    "provenance": {
        "source": "reforma-sistem-judiciar-romania",
        "locator": "p. 43, tabelul 7.8; p. 45, clarificarea privind desființarea judecătoriilor",
        "confidence": "verbatim",
        "note": (
            "„Judecatorii DESFIINTATE”; nivelul 2 este „Judecatorii + Tribunale consolidate”, "
            "iar funcția de judecată „este preluata integral de tribunale judetene sau "
            "metropolitane”. Instanța care supraviețuiește este tribunalul."
        ),
    },
}

# The per-judge caseload the merged courts would run at. The report prints two rates and the
# paper picks neither, so the wage bill is computed across the range rather than at a point.
TARGETS = {
    "tribunal": 932.3,
    "actual": 1325.0,
    "judecatorie": 1479.0,
}


def main() -> int:
    grades_file = ROOT / "data" / "indemnizatii-2022.json"
    courts_file = ROOT / "data" / "instante-localizate-2025.json"
    for path in (grades_file, courts_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    grades = json.loads(grades_file.read_text(encoding="utf-8"))
    courts = json.loads(courts_file.read_text(encoding="utf-8"))["courts"]

    pay_of_tier: dict[str, float] = {}
    for tier, needle in grades["tierToGrade"].items():
        match = next(
            (g for g in grades["grades"] if needle.lower() in g["name"].lower()), None
        )
        if match is None:
            print(f"no pay grade for tier {tier}", file=sys.stderr)
            return 1
        pay_of_tier[tier] = match["monthlyLei"]

    # The CSM report prints the headcount outright, four chapters after the caseload tables
    # this file was built from. Filled posts replace the derived count for what the judiciary
    # costs today; the derived one stays for the scenarios, which ask how many judges a
    # caseload target would need rather than how many exist.
    personal_file = ROOT / "data" / "personal-2025.json"
    published = {}
    if personal_file.exists():
        personal = json.loads(personal_file.read_text(encoding="utf-8"))
        published = {row["tier"]: row["filled"] for row in personal["judges"]}

    by_tier = []
    today_total = 0.0
    for tier in ("iccj", "curte-de-apel", "tribunal", "judecatorie"):
        selected = [c for c in courts if c["tier"] == tier]
        derived = round(sum(c.get("judges") or 0 for c in selected), 1)
        judges = float(published.get(tier, derived))
        annual = judges * pay_of_tier[tier] * MONTHS
        today_total += annual
        by_tier.append(
            {
                "tier": tier,
                "courts": len(selected),
                "judges": judges,
                "judgesDerived": derived,
                "monthlyLei": pay_of_tier[tier],
                "annualLei": round(annual),
            }
        )

    # The rest of the payroll. Judges were never most of it: the CSM counts 8.001 auxiliary
    # posts against 4.319 judges, and until now this file priced only the smaller half.
    auxiliary_bill = None
    if published and personal.get("auxiliary"):
        aux_rates = {a["key"]: a["monthlyLei"] for a in grades.get("auxiliary", [])}
        heads = personal["auxiliaryTotal"]["filled"] + (personal["iccjClerks"] or {}).get("filled", 0)
        # A band, not a point: the report counts clerks without saying which pay grade or
        # seniority each holds, so the floor is the entry rate and the ceiling the top of the
        # ordinary clerk scale. Chief-clerk posts exist and are not counted separately, so even
        # the ceiling is short.
        if {"grefier-s", "grefier-debutant"} <= aux_rates.keys():
            auxiliary_bill = {
                "posts": heads,
                "lowMonthlyLei": aux_rates["grefier-debutant"],
                "highMonthlyLei": aux_rates["grefier-s"],
                "annualLowLei": round(heads * aux_rates["grefier-debutant"] * MONTHS),
                "annualHighLei": round(heads * aux_rates["grefier-s"] * MONTHS),
            }

    # Level 1 is what the proposal reorganises: judecatorii and tribunale become 42 courts.
    level_one = [c for c in courts if c["tier"] in ("judecatorie", "tribunal")]
    volume = sum(c["volume"] for c in level_one)
    # Level 1 today, on the same published basis as the totals above. Leaving it derived while
    # the totals moved to filled posts would make every "față de azi" difference compare a
    # caseload-implied establishment against a real payroll — two different quantities
    # subtracted from each other.
    if published:
        judges_today = float(published["tribunal"] + published["judecatorie"])
        today_level_one = (
            published["tribunal"] * pay_of_tier["tribunal"]
            + published["judecatorie"] * pay_of_tier["judecatorie"]
        ) * MONTHS
    else:
        judges_today = sum(c.get("judges") or 0 for c in level_one)
        today_level_one = sum(
            (c.get("judges") or 0) * pay_of_tier[c["tier"]] * MONTHS for c in level_one
        )

    scenarios = []
    for label, target in TARGETS.items():
        needed = round(volume / target, 1)
        for grade in ("judecatorie", "tribunal"):
            annual = needed * pay_of_tier[grade] * MONTHS
            scenarios.append(
                {
                    "target": target,
                    "targetLabel": label,
                    "gradePaid": grade,
                    "judgesNeeded": needed,
                    "annualLei": round(annual),
                    "differenceLei": round(annual - today_level_one),
                    "isPaperGrade": grade == RESOLVED_GRADE["grade"],
                }
            )

    print(f"{'grad':<16}{'instanțe':>9}{'judecători':>12}{'lei/lună':>11}{'cost anual':>17}")
    for row in by_tier:
        print(f"{row['tier']:<16}{row['courts']:>9}{row['judges']:>12,.0f}"
              f"{row['monthlyLei']:>11,.0f}{row['annualLei']:>17,.0f}")
    print(f"{'TOTAL':<16}{'':>9}{'':>12}{'':>11}{today_total:>17,.0f} lei/an")
    if auxiliary_bill:
        print(f"\nauxiliari: {auxiliary_bill['posts']:,} posturi   "
              f"{auxiliary_bill['annualLowLei']:,.0f} - {auxiliary_bill['annualHighLei']:,.0f} lei/an")
        print(f"total instanțe: {today_total + auxiliary_bill['annualLowLei']:,.0f} - "
              f"{today_total + auxiliary_bill['annualHighLei']:,.0f} lei/an")
    print(f"\nnivelul 1 azi: {judges_today:,.0f} judecători, {today_level_one:,.0f} lei/an")
    print(f"{'țintă':<12}{'grad plătit':<14}{'judecători':>12}{'cost anual':>17}{'față de azi':>17}")
    for s in scenarios:
        print(f"{s['target']:<12,.0f}{s['gradePaid']:<14}{s['judgesNeeded']:>12,.0f}"
              f"{s['annualLei']:>17,.0f}{s['differenceLei']:>+17,.0f}")

    document = {
        "$schema": "../schema/costuri.schema.json",
        "id": "costuri-2025",
        "title": "Costul de bază al judecătorilor, azi și după comasare",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "legea-153-2017",
            "locator": "Anexa nr. V, Capitolul I, litera A × numărul de judecători din raportul CSM",
            "confidence": "derived",
            "note": (
                "Indemnizația de bază, la vârful grilei, înmulțită cu numărul de judecători "
                "reconstituit din raportul CSM. Nu include sporuri."
            ),
        },
        "monthlyLeiByTier": pay_of_tier,
        "today": {
            "annualLei": round(today_total),
            "byTier": by_tier,
            "levelOne": {
                "judges": round(judges_today, 1),
                "volume": volume,
                "annualLei": round(today_level_one),
            },
        },
        "auxiliary": auxiliary_bill,
        # What the two sources say about the same payroll, and what is left over. The pay
        # simulator's headcount counts every post under the courts' ordonator principal; the
        # CSM report counts judges and auxiliary staff. The remainder is neither — drivers,
        # contract staff, IT outside the auxiliary corps.
        "reconciliation": (
            {
                "payrollPosts": 14650,
                "judgesFilled": personal["judgesTotal"]["filled"],
                "auxiliaryFilled": auxiliary_bill["posts"],
                "magistrateAssistants": (personal.get("magistrateAssistants") or {}).get("filled", 0),
                "judicialAssistants": (personal.get("judicialAssistants") or {}).get("filled", 0),
                "unaccounted": 14650
                - personal["judgesTotal"]["filled"]
                - auxiliary_bill["posts"]
                - (personal.get("magistrateAssistants") or {}).get("filled", 0)
                - (personal.get("judicialAssistants") or {}).get("filled", 0),
                "executionBaseAnnualLei": 2457065665,
            }
            if auxiliary_bill and published
            else None
        ),
        "resolvedGrade": RESOLVED_GRADE,
        "scenarios": scenarios,
        "limitations": [
            {
                "id": "tranzitia-de-grad-nu-e-stabilita",
                "text": (
                    "Instanța de nivel 1 este tribunalul: lucrarea desființează judecătoriile ca "
                    "instituții separate, iar funcția lor de judecată este preluată integral de "
                    "tribunale (p. 43 și p. 45). Cifrele sunt deci calculate la grad de tribunal. "
                    "Ce nu spune lucrarea este dacă judecătorii veniți de la judecătorii își "
                    "păstrează gradul în tranziție; dacă da, factura primilor ani este sub cea "
                    "de aici. Varianta la grad de judecătorie rămâne calculată, ca termen de "
                    "comparație, nu ca a doua citire a propunerii."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "doar-indemnizatia-de-baza",
                "text": (
                    "Sunt doar indemnizațiile de bază, la vârful grilei. Sporurile — exact "
                    "subiectul capitolului 10 — nu sunt incluse în calculul pe instanță. "
                    "Ordinul lor de mărime se cunoaște însă: instanțele plătesc în sporuri "
                    "24,9% peste salariile de bază, deci masa salarială reală este cu circa "
                    "un sfert peste cifrele de aici (vezi sporuri-2025)."
                ),
                "severity": "material",
                "affects": ["cost", "salarizare"],
            },
            {
                "id": "numarul-de-judecatori-e-derivat",
                "text": (
                    "Costul de azi folosește posturile ocupate tipărite de CSM la 31 decembrie "
                    "2025 — 4.319 judecători. Scenariile folosesc în continuare numărul dedus "
                    "din volum împărțit la încărcătură, fiindcă ele întreabă de câți judecători "
                    "ar fi nevoie, nu câți sunt. Cele două nu măsoară același lucru: cel dedus "
                    "e de circa 2.960, un efectiv mediu pe an, nu un cap de om la o dată."
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

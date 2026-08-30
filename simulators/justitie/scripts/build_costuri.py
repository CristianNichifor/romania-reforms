"""What the judiciary's judges cost, and what consolidation does to that.

Joins two things the repository already holds: how many judges each court has, reconstructed
from the CSM report, and what the law pays a judge of that grade, read from Annex V Chapter I.
Multiplying gives the base wage bill — per court, per grade, and under the staffing the
proposal would need.

**One question the reform paper does not answer decides a third of the answer.** It merges
judecătorii and tribunale into a single first-level court and never says what grade that
court's judges hold. At judecătorie grade a judge costs 17.250 lei a month; at tribunal grade,
22.500. Across the numbers involved that is a difference of hundreds of millions a year, so
both are computed and neither is presented as the answer.

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

    by_tier = []
    today_total = 0.0
    for tier in ("iccj", "curte-de-apel", "tribunal", "judecatorie"):
        selected = [c for c in courts if c["tier"] == tier]
        # Rounded first, then multiplied. Storing a rounded headcount beside a total computed
        # from the unrounded one leaves the document unable to reproduce its own arithmetic,
        # which is exactly what a reader checking it would try.
        judges = round(sum(c.get("judges") or 0 for c in selected), 1)
        annual = judges * pay_of_tier[tier] * MONTHS
        today_total += annual
        by_tier.append(
            {
                "tier": tier,
                "courts": len(selected),
                "judges": judges,
                "monthlyLei": pay_of_tier[tier],
                "annualLei": round(annual),
            }
        )

    # Level 1 is what the proposal reorganises: judecatorii and tribunale become 42 courts.
    level_one = [c for c in courts if c["tier"] in ("judecatorie", "tribunal")]
    volume = sum(c["volume"] for c in level_one)
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
                }
            )

    print(f"{'grad':<16}{'instanțe':>9}{'judecători':>12}{'lei/lună':>11}{'cost anual':>17}")
    for row in by_tier:
        print(f"{row['tier']:<16}{row['courts']:>9}{row['judges']:>12,.0f}"
              f"{row['monthlyLei']:>11,.0f}{row['annualLei']:>17,.0f}")
    print(f"{'TOTAL':<16}{'':>9}{'':>12}{'':>11}{today_total:>17,.0f} lei/an")
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
        "scenarios": scenarios,
        "limitations": [
            {
                "id": "gradul-instantei-comasate-nu-e-stabilit",
                "text": (
                    "Propunerea unește judecătoriile și tribunalele într-o singură instanță de "
                    "nivel 1, dar nu spune ce grad au judecătorii ei. La grad de judecătorie "
                    "un judecător costă 17.250 lei pe lună, la grad de tribunal 22.500 — o "
                    "diferență de sute de milioane pe an la efectivele în discuție. Ambele "
                    "sunt calculate; niciuna nu e prezentată drept răspunsul."
                ),
                "severity": "blocking",
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
                    "Numărul de judecători nu e tipărit în raport, ci reconstituit împărțind "
                    "volumul la încărcătura pe judecător, deci e un efectiv mediu pe an, nu un "
                    "cap de om la o dată anume."
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

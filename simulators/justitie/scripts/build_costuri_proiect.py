"""What the judiciary would cost under the July 2026 pay draft, instead of the 2022 scale.

Everything this simulator says about money is priced from Anexa V of Legea 153/2017 at the
2022 figures printed in it. There is now a newer answer in the repository: the draft law of
16 July 2026 sets pay as a coefficient times a reference value of 4.100 lei, and its grid
carries all five judicial ranks. Pricing the same judiciary under both is the point of this
file.

**The draft compresses the bench.** Today's top-of-scale runs from 17.250 lei at judecătorie
grade to 26.250 at the Înalta Curte, a spread of 1,52 to 1. The draft's coefficients run 4,40
to 5,50 — a spread of 1,25. Read rank by rank it raises the bottom and cuts the top, which is
the opposite of what "reforming magistrates' pay" is usually taken to mean.

**That matters for what the merged court costs.** The paper abolishes judecătoriile and hands
their work to the tribunale, so the merged level-1 court is a tribunal and its judges are paid
at tribunal grade. Under the law in force tribunal grade costs 5.250 lei a month more than
judecătorie grade; under the draft, about 2.861. The choice is settled, but the gap still
prices one open question — whether judges arriving from a judecătorie keep their grade through
the transition — and the draft roughly halves what that transition is worth.

Two things are deliberately not done here. The 2022 and 2026 figures are in the money of their
own years and no deflator is applied, so levels are not compared — only ratios, which are
scale-free, and the two are labelled wherever they appear together. And only judges are priced:
grefieri are most of the payroll, but the headcount data does not split the courts' 14.650
posts by function, so pricing them would mean inventing the split.

Usage:
    uv run python scripts/build_costuri_proiect.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGIME = ROOT.parent / "salarizare" / "data" / "regimes" / "ro-draft-2026-07-16.json"
OUT = ROOT / "data" / "costuri-proiect-2026.json"

MONTHS = 12

# The grid names ranks in prose; the simulator keys courts by tier. Matched on the exact
# printed name so a renamed row fails loudly instead of silently pricing a tier at zero.
TIER_OF_POSITION = {
    "Judecator cu grad de ICCJ": "iccj",
    "Judecător cu grad de curte de apel": "curte-de-apel",
    "Judecător cu grad de tribunal": "tribunal",
    "Judecător cu grad de judecătorie": "judecatorie",
}
TOP_SENIORITY = "Peste 20 ani"


def main() -> int:
    if not REGIME.exists():
        raise SystemExit(f"Missing {REGIME}; the pay simulator holds the draft")

    regime = json.loads(REGIME.read_text(encoding="utf-8"))
    reference = regime["reference"]["amount"][-1]["value"]
    rounding = regime["reference"].get("rounding") or {}

    def pay(coefficient: float) -> float:
        """Coefficient times reference, rounded the way Art. 10 alin. (4) rounds it."""
        lei = coefficient * reference
        # `step` is in minor units; the law rounds to the whole leu in the employee's favour.
        step = (rounding.get("step") or 100) / 10 ** regime.get("minorUnits", 2)
        if rounding.get("mode") == "ceil":
            return math.ceil(lei / step) * step
        return round(lei / step) * step

    coefficients: dict[str, float] = {}
    for position in regime["positions"]:
        tier = TIER_OF_POSITION.get(position["name"])
        if tier is None:
            continue
        top = next(
            (v for v in position["variants"] if v.get("dims", {}).get("vechime") == TOP_SENIORITY),
            None,
        )
        if top is None:
            print(f"no '{TOP_SENIORITY}' row for {position['name']}", file=sys.stderr)
            return 1
        coefficients[tier] = top["value"]

    missing = [t for t in TIER_OF_POSITION.values() if t not in coefficients]
    if missing:
        print(f"the draft's grid no longer names: {missing}", file=sys.stderr)
        return 1

    costuri = json.loads((ROOT / "data" / "costuri-2025.json").read_text(encoding="utf-8"))
    today_pay = costuri["monthlyLeiByTier"]

    by_tier = []
    draft_total = 0.0
    for row in costuri["today"]["byTier"]:
        tier = row["tier"]
        monthly = pay(coefficients[tier])
        annual = row["judges"] * monthly * MONTHS
        draft_total += annual
        by_tier.append(
            {
                "tier": tier,
                "judges": row["judges"],
                "coefficient": coefficients[tier],
                "monthlyLei": monthly,
                "annualLei": round(annual),
                "todayMonthlyLei": today_pay[tier],
                "ratioToToday": round(monthly / today_pay[tier], 4),
            }
        )

    # Spread top to bottom, which is scale-free and therefore the one comparison the two years
    # can honestly carry between them.
    spread_today = today_pay["iccj"] / today_pay["judecatorie"]
    spread_draft = coefficients["iccj"] / coefficients["judecatorie"]

    # The gap between the two grades, priced under each regime. The paper settles which grade
    # the merged court holds; what the gap now measures is the transition, not the ambiguity.
    gap_today = today_pay["tribunal"] - today_pay["judecatorie"]
    gap_draft = pay(coefficients["tribunal"]) - pay(coefficients["judecatorie"])

    level_one = costuri["today"]["levelOne"]
    scenarios = []
    for scenario in costuri["scenarios"]:
        needed = scenario["judgesNeeded"]
        grade = scenario["gradePaid"]
        annual = needed * pay(coefficients[grade]) * MONTHS
        scenarios.append(
            {
                "target": scenario["target"],
                "targetLabel": scenario["targetLabel"],
                "gradePaid": grade,
                "judgesNeeded": needed,
                "annualLei": round(annual),
            }
        )
    # What choosing the wrong grade costs, at each staffing target, under each regime.
    swings = []
    for target in sorted({s["target"] for s in scenarios}):
        pair = {s["gradePaid"]: s for s in scenarios if s["target"] == target}
        old = {s["gradePaid"]: s for s in costuri["scenarios"] if s["target"] == target}
        swings.append(
            {
                "target": target,
                "todayLei": round(old["tribunal"]["annualLei"] - old["judecatorie"]["annualLei"]),
                "draftLei": round(pair["tribunal"]["annualLei"] - pair["judecatorie"]["annualLei"]),
            }
        )

    print(f"valoare de referință: {reference:,.0f} lei\n")
    print(f"{'grad':<16}{'coef':>10}{'proiect':>11}{'azi (2022)':>13}{'raport':>9}")
    for row in by_tier:
        print(f"{row['tier']:<16}{row['coefficient']:>10.4f}{row['monthlyLei']:>11,.0f}"
              f"{row['todayMonthlyLei']:>13,.0f}{row['ratioToToday']:>9.2f}")
    print(f"\nevantai vârf/bază:  azi {spread_today:.2f}x   proiect {spread_draft:.2f}x")
    print(f"diferența de grad:  azi {gap_today:,.0f} lei/lună   proiect {gap_draft:,.0f} lei/lună")
    print(f"\ncât valorează diferența de grad, pe an:")
    for s in swings:
        print(f"  la {s['target']:,.0f} dosare/judecător: azi {s['todayLei'] / 1e6:>7,.1f} M   "
              f"proiect {s['draftLei'] / 1e6:>7,.1f} M")

    document = {
        "$schema": "../schema/costuri-proiect.schema.json",
        "id": "costuri-proiect-2026",
        "title": "Judecătorii, plătiți după proiectul de salarizare din iulie 2026",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "proiect-lege-2026-07-16",
            "locator": "Anexa V Cap. I A+B, coeficienți × valoarea de referință de la Art. 36 alin. (2)",
            "confidence": "derived",
            "note": (
                "Coeficienții sunt citați din grila proiectului; înmulțirea cu valoarea de "
                "referință și rotunjirea sunt aplicate aici, după Art. 10 alin. (4)."
            ),
        },
        "referenceLei": reference,
        "byTier": by_tier,
        "spread": {
            "todayRatio": round(spread_today, 4),
            "draftRatio": round(spread_draft, 4),
            "compresses": spread_draft < spread_today,
        },
        "gradeGap": {
            "todayMonthlyLei": round(gap_today),
            "draftMonthlyLei": round(gap_draft),
            "narrows": gap_draft < gap_today,
        },
        "levelOne": {"volume": level_one["volume"]},
        "scenarios": scenarios,
        "gradeChoiceSwing": swings,
        "gradeIsResolved": True,
        "limitations": [
            {
                "id": "tranzitia-de-grad-nu-e-stabilita",
                "text": (
                    "Instanța de nivel 1 este tribunalul, deci gradul plătit este cel de "
                    "tribunal. Lucrarea nu spune însă ce se întâmplă cu judecătorii veniți de "
                    "la judecătorii: dacă își păstrează gradul o perioadă, factura primilor ani "
                    "este sub cea de aici. Diferența dintre grade — 5.250 lei pe lună azi, 2.861 "
                    "după proiect — este exact ce valorează această întrebare."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "ani-diferiti-fara-deflator",
                "text": (
                    "Grila în vigoare tipărește sume în lei 2022; proiectul se calculează la o "
                    "valoare de referință pentru decembrie 2026. Nu se aplică niciun deflator, "
                    "așa că nivelurile nu sunt comparabile între ele. Comparabile sunt doar "
                    "rapoartele — evantaiul vârf/bază și diferența dintre grade —, care nu "
                    "depind de unitatea de măsură."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "doar-judecatorii-sunt-evaluati",
                "text": (
                    "Sunt evaluați doar judecătorii. Grefierii sunt majoritatea celor 14.650 de "
                    "posturi ale instanțelor, iar proiectul le dă și lor coeficienți, dar datele "
                    "de personal nu împart posturile pe funcții, așa că masa lor salarială nu se "
                    "poate calcula fără a inventa împărțirea."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "varful-grilei-din-nou",
                "text": (
                    "Sunt luate coeficientele pentru „Peste 20 de ani”, ca și la grila în "
                    "vigoare, ca să fie comparate aceleași trepte. Proiectul publică însă și "
                    "treptele inferioare, pe care grila din 2022 nu le are pentru judecători, "
                    "deci costul real este sub cel de aici la ambele regimuri."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "diferenta-tranzitorie-nu-e-modelata",
                "text": (
                    "Art. 33 din proiect menține venitul din noiembrie 2026 printr-o diferență "
                    "salarială tranzitorie care intră în baza celorlalte drepturi. Fără datele "
                    "individuale din acea lună, componenta lipsește din orice cifră de aici, iar "
                    "în primii ani ea domină factura reală."
                ),
                "severity": "blocking",
                "affects": ["cost"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

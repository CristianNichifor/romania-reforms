"""What forest land earns, built from the only thing forest sells.

Farmland's yield is measured because INS surveys both its price and its rent. Forest has no
rent to survey — nobody leases woodland by the year — so until now it borrowed the arable band,
which was a placeholder on 11% of the land value in this simulator.

It does not have to be. Forest produces timber, timber is sold standing at auction, and both
halves of that are published:

    rentă/ha = recolta anuală pe hectar × prețul masei lemnoase pe picior × (1 − costurile)
    randament = rentă/ha ÷ valoarea pădurii pe hectar

The harvest comes from INS matrix AGR306A, per county, in `lemn-recoltat-*.json`. The price
comes from Romsilva's auctions. The forest value comes from the notaries' grids, which now
price forest after eight readers spent a while throwing it away.

**Standing timber, not logs.** The price used is *masa lemnoasă pe picior* — what a buyer pays
for trees still in the ground, before felling and extraction. That is the right one, because it
is what accrues to the owner of the land rather than to whoever does the work, and because the
harvest series is gross volume, which is what standing timber is measured in. Pairing it with a
sawn-timber price would be counting the sawmill's margin as ground rent.

**The owner still has costs, and they are a band.** Guarding, administration, regeneration and
forest roads come out of the stumpage revenue before anything is left as a return on the land.
Nothing publishes that share for Romania as a single figure, so it is a declared parameter of
15–35% and the yield band is mostly this parameter's width.

**Where this leaves forest against farmland.** Around 2–4%, against a measured 1,4–1,6% for
arable. Forest earning more than farmland is not obviously wrong — it is less liquid, the
income is lumpy, and a rotation is decades long — but the gap is a result rather than an
assumption, and it is the first time either half of it has been anything but assumed.

Usage:
    uv run python simulators/impozit-teren/scripts/build_randament_padure.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANDS = ("low", "central", "high")
# RNP-Romsilva, standing timber sold at auction and by negotiation, first nine months of 2025:
# an average achieved price of 230,40 lei/m³ against an average opening price of 187,89, a
# 23% premium over the reserve. The opening price is the low end because it is the floor the
# seller would have accepted.
STUMPAGE_LEI_PER_M3 = {"low": 187.89, "central": 230.40, "high": 230.40}
STUMPAGE_SOURCE = (
    "RNP-Romsilva, licitații și negocieri de masă lemnoasă pe picior, primele nouă luni ale "
    "anului 2025: preț mediu de adjudecare 230,40 lei/m³, preț mediu de pornire 187,89 lei/m³"
)
# Guarding, administration, regeneration, forest roads — what comes out of the stumpage
# revenue before the land has earned anything. Not published for Romania as one figure; this
# is a declared parameter and the band is mostly its width.
OWNER_COST_SHARE = {"low": 0.35, "central": 0.25, "high": 0.15}


def load(pattern: str) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "data").glob(pattern))
    ]


def main() -> int:
    harvests = load("lemn-recoltat-*.json")
    if not harvests:
        raise SystemExit("missing lemn-recoltat-*.json; run import_lemn_recoltat.py first")
    harvest = harvests[-1]
    per_ha = {
        row["county"]: row["m3PerHaPerYear"]
        for row in harvest["counties_measured"]
        if row["m3PerHaPerYear"]
    }

    # County tax files only — see the same guard in build_multiplu_piata.py. `impozit-incasat-*`
    # matches the prefix and has no `assumptions`.
    rate_files = [p for p in sorted((ROOT / "data").glob("impozit-*.json"))
                  if re.fullmatch(r"impozit-[a-z]{1,2}-\d{4}", p.stem)]
    if not rate_files:
        raise SystemExit("missing impozit-<judet>-<an>.json; run build_impozit.py first")
    ron_per_eur = json.loads(rate_files[0].read_text(encoding="utf-8"))["assumptions"][
        "ronPerEur"
    ]

    counties = []
    for value in load("valoare-teren-*.json"):
        code = value["counties"][0]
        # Only the hectares that actually got a price. Dividing the county's forest value by
        # all of its forest hectares mixes priced land with unpriced: Hunedoara prices forest
        # for eleven town seats and nobody else, so the average came out at 2 434 lei a
        # hectare and its yield at 15,6% — an artefact of the denominator, not a forest.
        priced = [row for row in value["localities"] if row["forestValueEur"] > 0]
        forest_value = sum(row["forestValueEur"] for row in priced)
        forest_ha = sum(row["forestHa"] for row in priced)
        cut = per_ha.get(code)
        # Both halves or nothing: a county whose grid does not price forest has no denominator,
        # and one the harvest series does not reach has no numerator.
        if not forest_value or not forest_ha or not cut:
            continue
        value_per_ha_ron = (forest_value / forest_ha) * ron_per_eur
        # Each end from the inputs that push the same way: the thin rent is the low price with
        # the high cost share, and the fat one is the opposite.
        rent = {
            "low": cut * STUMPAGE_LEI_PER_M3["low"] * (1 - OWNER_COST_SHARE["low"]),
            "central": cut * STUMPAGE_LEI_PER_M3["central"] * (1 - OWNER_COST_SHARE["central"]),
            "high": cut * STUMPAGE_LEI_PER_M3["high"] * (1 - OWNER_COST_SHARE["high"]),
        }
        counties.append(
            {
                "county": code,
                "m3PerHaPerYear": cut,
                "forestHa": round(forest_ha, 2),
                "forestShareOfCountyPriced": round(
                    forest_ha / sum(r["forestHa"] for r in value["localities"]), 4
                ),
                "forestValueRonPerHa": round(value_per_ha_ron, 2),
                "rentRonPerHaPerYear": {b: round(rent[b], 2) for b in BANDS},
                "yieldPercent": {
                    b: round(100 * rent[b] / value_per_ha_ron, 4) for b in BANDS
                },
            }
        )
    if not counties:
        raise SystemExit("no county has both a forest price and a harvest figure")

    overall = {
        b: round(statistics.median(c["yieldPercent"][b] for c in counties), 4) for b in BANDS
    }

    document = {
        "$schema": "../schema/randament-padure.schema.json",
        "id": f"randament-padure-{harvest['period']}",
        "title": "Randamentul terenului forestier, din recolta de lemn și prețul pe picior",
        "publisher": "romania-reforms",
        "counties": [c["county"] for c in counties],
        "period": harvest["period"],
        "currency": "RON",
        "provenance": {
            "source": "ins-tempo-agr306a-romsilva-grile-notariale",
            "locator": (
                "recolta pe hectar (INS AGR306A, prin lemn-recoltat) × prețul masei lemnoase "
                "pe picior (Romsilva) × (1 − cota de costuri), împărțit la valoarea pădurii pe "
                "hectar din grilele notariale"
            ),
            "confidence": "derived",
            "note": (
                "Nu există o arendă a pădurii de măsurat. Cele două intrări măsurate sunt "
                "recolta și prețul; cota de costuri a proprietarului este un parametru declarat."
            ),
        },
        "assumptions": {
            "stumpageLeiPerM3": STUMPAGE_LEI_PER_M3,
            "stumpageSource": STUMPAGE_SOURCE,
            "ownerCostShare": OWNER_COST_SHARE,
            "ronPerEur": ron_per_eur,
        },
        "summary": {
            "counties": len(counties),
            "yieldPercent": overall,
            "nationalM3PerHaPerYear": harvest["summary"]["nationalM3PerHaPerYear"],
            "arableYieldPercentForComparison": 1.43,
        },
        "counties_measured": counties,
        "limitations": [
            {
                "id": "pretul-e-national-nu-judetean",
                "text": (
                    "Prețul masei lemnoase pe picior este media Romsilva pe țară, aplicată "
                    "tuturor județelor. Rășinoasele din Suceava și foioasele din Dolj nu se "
                    "vând la același preț, iar diferența dintre județe se pierde aici — "
                    "singurul lucru care variază pe județ este recolta pe hectar."
                ),
                "severity": "material",
                "affects": ["randament-padure", "renta"],
            },
            {
                "id": "costurile-proprietarului-sunt-parametru",
                "text": (
                    "Cota de 15–35% pentru pază, administrare, regenerare și drumuri "
                    "forestiere nu este publicată nicăieri ca o singură cifră. Este un "
                    "parametru declarat, iar lățimea benzii randamentului vine în cea mai mare "
                    "parte din el."
                ),
                "severity": "blocking",
                "affects": ["randament-padure", "renta"],
            },
            {
                "id": "romsilva-e-padurea-statului",
                "text": (
                    "Prețul provine din licitațiile Romsilva, adică din pădurea statului. "
                    "Aproape jumătate din pădurea României este privată sau a "
                    "unităților administrativ-teritoriale și se vinde în alte condiții."
                ),
                "severity": "material",
                "affects": ["randament-padure"],
            },
        ],
    }

    out = ROOT / "data" / f"{document['id']}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'jud':>4} {'m³/ha':>7} {'val lei/ha':>11} {'rentă lei/ha':>13} {'randament':>10}")
    for row in sorted(counties, key=lambda c: -c["yieldPercent"]["central"]):
        print(
            f"{row['county']:>4} {row['m3PerHaPerYear']:7.2f} "
            f"{row['forestValueRonPerHa']:11,.0f} {row['rentRonPerHaPerYear']['central']:13,.0f} "
            f"{row['yieldPercent']['central']:9.2f}%"
        )
    print(
        f"\nmedian: {overall['central']:.2f}%  (bandă {overall['low']:.2f}–{overall['high']:.2f}%)"
        f"  — arabil măsurat 1,43%"
    )
    print(f"Wrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

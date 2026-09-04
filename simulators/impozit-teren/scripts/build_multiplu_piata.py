"""How far the notaries' floor sits below what farmland is actually offered at.

The simulator values land at the notaries' minimum, and the obvious objection is that the
minimum is not the market. This measures the gap for the one kind of land where both numbers
exist: extravilan arable, priced by the grid in `ghid-teren-*.json` and asked for in the
Legea 17/2014 offer register in `pret-cerut-agricol-*.json`.

    multiplu = prețul de piață ÷ prețul din grilă

and there are now **two market references**, which do not agree and should not be averaged.
The Legea 17/2014 offer register says what sellers *ask*, per county, as a median over offers.
The INS survey behind Eurostat's `apri_lprc` says what buyers *paid*, per NUTS2 region, as a
mean. Both are reported per county, side by side, with the multiple each implies.

**The answer is smaller than the objection assumes.** Over the 36 comparable counties the
median multiple is **1,236×** against asking prices and **1,239×** against INS transaction
prices; matched on the same commune it is **1,163×**. So the notaries' floor for farmland sits
at about **81% of the market**, and about 86% where the comparison is of the same place rather
than of the same county — not a fraction of it.

**The two references agree on the middle and disagree about the spread**, which is the part
worth saying. Their medians are within three thousandths of each other, so "how far below
market is the grid" gets the same answer from what sellers ask and from what buyers paid. But
six counties fall below parity against asking prices and thirteen against transactions, so the
*distributions* are not the same shape, and neither is a substitute for the other: INS reports
a regional mean over a right-skewed distribution, the barometer a per-county median, and the
survey year is 2024 against offers collected in 2026.

Two things stop this generalising, and both are in the output:

**It used to be the wrong 32%, and `summary.buildingLand` is the other two thirds.**
Curți-construcții is 68% of the land value this simulator computes — 220,8 of 324,2 mld EUR
across the forty-two counties — on under 3% of its surface, and nothing in the Legea 17/2014
register prices it. `anunturi-teren` now does, from listing asking prices in euro per square
metre, and the answer is that **the grid is not wrong by the same amount everywhere**: about
parity in municipalities, half again in towns, more than two and a half times in communes. The
median over localities and the value-weighted mean therefore differ by roughly a factor of two,
because two thirds of the building-land value sits in twenty cities where the grid is close to
right. Both are published; neither is "the" multiple. What follows still calibrates the
cheap majority of hectares and says nothing about the expensive minority — which is where a
land value tax mostly falls. `marketMultiple` in `build_renta.py` therefore stays a knob the
reader moves rather than a constant this file sets: applying an arable multiple to house plots
would be worse than the assumption of 1,0 it replaced.

**Counts, not hectares.** The barometer's percentiles are per offer and the grid's median is
per locality; neither is weighted by area. A county offering many small expensive parcels
looks dearer than its hectares are. The survey is a regional mean, so every county in a region
gets the same figure and the differences inside it vanish.

The per-UAT comparison is the strongest of the three views, because there the two prices are
about the same commune rather than about the same county, and it is reported wherever both
sources reach the same SIRUTA.

Usage:
    uv run python simulators/impozit-teren/scripts/build_multiplu_piata.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M2_PER_HA = 10_000
# Below this share of the county's valued localities carrying an arable price, the grid's
# median is not the county's — Hunedoara prices extravilan for eleven town seats and nobody
# else, which makes its "median" an urban one and its multiple meaningless.
MIN_GRID_SHARE = 0.5
BANDS = ("low", "central", "high")


def load(name: str) -> dict:
    path = ROOT / "data" / name
    if not path.exists():
        raise SystemExit(f"missing {path}; run its importer first")
    return json.loads(path.read_text(encoding="utf-8"))


def editions(prefix: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted((ROOT / "data").glob(f"{prefix}-*.json")):
        stem = path.stem[len(prefix) + 1 :]
        county, _, year = stem.rpartition("-")
        if county and year.isdigit():
            found[county.upper()] = path
    return found


def building_land() -> dict | None:
    """The other 68% of the value, which this file could not calibrate until now.

    `anunturi-teren` reads asking prices for building land off a listing portal, in euro per
    square metre — the same unit the grid publishes intravilan in — so the two divide directly.
    Optional: without that dataset the rest of this file is unchanged and this section is
    simply absent, which is what the docstring above described for the whole of its life.

    Two aggregates, because they answer different questions and disagree by a factor of two.
    The median over localities says how wrong the grid is in a typical place. The value-weighted
    mean says how wrong it is about the money, and the money is in the cities — twenty
    localities hold roughly two thirds of the built-land value in this comparison. A revenue
    argument wants the second; a fairness argument wants the first.
    """
    found = sorted((ROOT / "data").glob("anunturi-teren-*.json"))
    if not found:
        return None
    asked_doc = json.loads(found[-1].read_text(encoding="utf-8"))
    grid: dict[tuple[str, str], dict] = {}
    for path in sorted((ROOT / "data").glob("valoare-teren-*.json")):
        if "nationala" in path.name:
            continue
        county = re.search(r"valoare-teren-([a-z]{1,2})-", path.name).group(1).upper()
        for locality in json.loads(path.read_text(encoding="utf-8"))["localities"]:
            grid[(county, locality["siruta"])] = locality

    by_rank: dict[str, list[float]] = {}
    every: list[float] = []
    weighted_top = weighted_bottom = 0.0
    for row in asked_doc["localities"]:
        place = grid.get((row["county"], row["siruta"]))
        if not row.get("askedEurPerM2") or not place:
            continue
        published = place["intravilanEurPerM2"]["central"]
        if not published:
            continue
        multiple = row["askedEurPerM2"]["median"] / published
        every.append(multiple)
        by_rank.setdefault(row.get("rank") or "comune", []).append(multiple)
        # Weighted by what the grid itself says the locality's building land is worth, so the
        # weight comes from the thing being tested rather than from the thing testing it.
        value = place["builtHa"] * M2_PER_HA * published
        weighted_top += multiple * value
        weighted_bottom += value
    if len(every) < 50:
        return None
    return {
        "localities": len(every),
        "medianMultiple": round(statistics.median(every), 3),
        "valueWeightedMultiple": round(weighted_top / weighted_bottom, 3),
        "byRank": {
            kind: {"localities": len(v), "medianMultiple": round(statistics.median(v), 3)}
            for kind, v in sorted(by_rank.items())
        },
        "source": asked_doc["id"],
    }


def main() -> int:
    asked = load("pret-cerut-agricol-2026.json")
    by_county = {row["county"]: row for row in asked["prices"]}
    surveys = sorted((ROOT / "data").glob("teren-agricol-ins-*.json"))
    survey = json.loads(surveys[-1].read_text(encoding="utf-8")) if surveys else None
    paid: dict[str, tuple[str, str, float]] = {}
    if survey:
        for region in survey["regions"]:
            latest = [r for r in region["series"] if r["priceRonPerHa"]]
            if not latest or region["region"] == "RO":
                continue
            row = latest[-1]
            for county in region["counties"]:
                paid[county] = (region["region"], row["year"], row["priceRonPerHa"])
    # A county's tax file, for the exchange rate every dataset here is converted at. Matched
    # on the county pattern rather than on the `impozit-` prefix alone: `impozit-incasat-*` is
    # also an `impozit-*` file and carries no `assumptions` at all, so a loose glob would pick
    # it up the day a county code sorted after it and fail on a missing key.
    rate_source = [p for p in sorted((ROOT / "data").glob("impozit-*.json"))
                   if re.fullmatch(r"impozit-[a-z]{1,2}-\d{4}", p.stem)]
    if not rate_source:
        raise SystemExit("no impozit-<judet>-<an>.json; run build_impozit.py first")
    ron_per_eur = json.loads(rate_source[0].read_text(encoding="utf-8"))["assumptions"][
        "ronPerEur"
    ]

    rows = []
    for county, path in sorted(editions("valoare-teren").items()):
        offered = by_county.get(county)
        if offered is None:
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        localities = value["localities"]
        grid = {
            row["siruta"]: row["extravilanEurPerM2"]["A"] * M2_PER_HA * ron_per_eur
            for row in localities
            if row["extravilanEurPerM2"].get("A")
        }
        if not grid:
            continue
        share = len(grid) / len(localities)
        median = statistics.median(grid.values())

        # Same commune on both sides. The county view compares a median over localities with a
        # median over offers; this one compares a place with itself.
        pairs = []
        for local in offered["localities"]:
            own = grid.get(local["siruta"])
            if own:
                pairs.append(
                    {
                        "siruta": local["siruta"],
                        "name": local["name"],
                        "offers": local["offers"],
                        "gridRonPerHa": round(own, 2),
                        "askedRonPerHa": local["ronPerHa"],
                        "multiple": {b: round(local["ronPerHa"][b] / own, 3) for b in BANDS},
                    }
                )

        survey_row = paid.get(county)
        rows.append(
            {
                "county": county,
                "name": offered["name"],
                # The transaction reference, and the region it is really about. Carried with
                # its own year because the survey is two years behind the offer register.
                "surveyRegion": survey_row[0] if survey_row else None,
                "surveyYear": survey_row[1] if survey_row else None,
                "paidRonPerHa": round(survey_row[2], 2) if survey_row else None,
                "multipleVsPaid": (
                    round(survey_row[2] / median, 3) if survey_row else None
                ),
                "gridYear": value["period"],
                "gridPricedLocalities": len(grid),
                "gridLocalities": len(localities),
                "gridShare": round(share, 3),
                "gridMedianRonPerHa": round(median, 2),
                "offers": offered["offers"],
                "askedRonPerHa": offered["ronPerHa"],
                "multiple": {b: round(offered["ronPerHa"][b] / median, 3) for b in BANDS},
                # Stated per row rather than filtered out, so a reader sees the county and the
                # reason its number is not to be used in the same place.
                "comparable": share >= MIN_GRID_SHARE,
                "localities": sorted(pairs, key=lambda x: x["siruta"]),
            }
        )
    if not rows:
        raise SystemExit("no county has both a grid and an asked price")

    usable = [row for row in rows if row["comparable"]]
    against_paid = [row["multipleVsPaid"] for row in usable if row["multipleVsPaid"]]
    per_uat = [pair for row in usable for pair in row["localities"]]
    summary = {
        "counties": len(rows),
        "comparableCounties": len(usable),
        "matchedLocalities": len(per_uat),
        "countyMultiple": {
            b: round(statistics.median(row["multiple"][b] for row in usable), 3) for b in BANDS
        },
        "localityMultiple": (
            {
                b: round(statistics.median(pair["multiple"][b] for pair in per_uat), 3)
                for b in BANDS
            }
            if per_uat
            else None
        ),
        "countyMultipleVsPaid": (
            round(statistics.median(against_paid), 3) if against_paid else None
        ),
        "countiesBelowParity": sorted(
            row["county"] for row in usable if row["multiple"]["central"] < 1
        ),
        "countiesBelowParityVsPaid": sorted(
            row["county"]
            for row in usable
            if row["multipleVsPaid"] and row["multipleVsPaid"] < 1
        ),
        "buildingLand": building_land(),
    }

    document = {
        "$schema": "../schema/multiplu-piata.schema.json",
        "id": "multiplu-piata-2026",
        "title": (
            "Raportul dintre prețul cerut pentru teren agricol și grila notarială, pe județe"
        ),
        "publisher": "romania-reforms",
        "counties": [row["county"] for row in rows],
        "period": asked["period"],
        "currency": "RON",
        "provenance": {
            "source": "pret-cerut-agricol-2026",
            "locator": (
                "preț cerut (Legea 17/2014, agregat Verifi) ÷ mediana prețului pentru arabil "
                "extravilan din grila notarială a județului, pe unitate administrativ-"
                "teritorială și pe județ"
            ),
            "confidence": "derived",
            "note": (
                f"Conversia din EUR/m² în RON/ha folosește cursul {ron_per_eur} RON/EUR, "
                "același ca în build_impozit.py. Mediana grilei este pe localitate, mediana "
                "prețului cerut este pe ofertă; niciuna nu e ponderată cu suprafața."
            ),
        },
        "summary": summary,
        "counties_compared": rows,
        "limitations": [
            {
                "id": "cerut-contra-administrativ",
                "text": (
                    "Raportul compară un preț cerut cu un minim administrativ. Niciunul nu "
                    "este preț de tranzacționare, așa că multiplul nu spune cu cât peste "
                    "grilă se vinde efectiv pământul, ci cu cât peste ea se cere."
                ),
                "severity": "blocking",
                "affects": ["multiplu-piata", "renta"],
            },
            {
                "id": "doar-arabil-extravilan",
                "text": (
                    "Multiplul este măsurat doar pentru arabil extravilan. Curțile-construcții "
                    "sunt 64% din valoarea terenului din acest simulator și nu apar în "
                    "registrul Legii 17/2014, deci nu au niciun multiplu măsurat. De aceea "
                    "marketMultiple din build_renta.py rămâne un parametru al cititorului: "
                    "aplicarea multiplului agricol pe terenul de sub case ar fi o eroare mai "
                    "mare decât presupunerea de 1,0 pe care ar înlocui-o."
                ),
                "severity": "blocking",
                "affects": ["multiplu-piata", "renta"],
            },
            {
                "id": "cele-doua-referinte-nu-sunt-comparabile-intre-ele",
                "text": (
                    "Prețul cerut este o mediană pe județ, calculată pe ofertă; prețul plătit "
                    "este o medie pe regiune NUTS2, dintr-o anchetă cu doi ani mai veche. "
                    "Faptul că al doilea iese mai mare decât primul ține în bună măsură de "
                    "aceste diferențe, nu de piață. Cei doi multipli se citesc separat și nu "
                    "se mediază."
                ),
                "severity": "material",
                "affects": ["multiplu-piata"],
            },
            {
                "id": "medianele-nu-sunt-ponderate",
                "text": (
                    "Mediana grilei este pe localitate, iar cea a prețului cerut este pe "
                    "ofertă. Un județ cu multe oferte mici și scumpe iese mai scump decât "
                    "sunt hectarele lui, iar o localitate mare cântărește cât una mică."
                ),
                "severity": "material",
                "affects": ["multiplu-piata"],
            },
            {
                "id": "anii-nu-coincid",
                "text": (
                    "Barometrul este colectat în 2026, iar patru dintre grile sunt din 2025, "
                    "pentru că acele camere notariale nu au publicat studiu în 2026. "
                    "Multiplul acelor județe conține și un an de diferență."
                ),
                "severity": "material",
                "affects": ["multiplu-piata"],
            },
        ],
    }

    out = ROOT / "data" / "multiplu-piata-2026.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"{'județ':>11} {'grilă':>10} {'cerut':>10} {'plătit':>10} "
        f"{'→cerut':>8} {'→plătit':>8} {'UAT':>4}"
    )
    for row in sorted(rows, key=lambda x: -x["multiple"]["central"]):
        mark = "" if row["comparable"] else "  ← grilă subțire"
        paid_price = f"{row['paidRonPerHa']:10,.0f}" if row["paidRonPerHa"] else f"{'—':>10}"
        paid_mult = f"{row['multipleVsPaid']:7.2f}×" if row["multipleVsPaid"] else f"{'—':>8}"
        print(
            f"{row['name']:>11} {row['gridMedianRonPerHa']:10,.0f} "
            f"{row['askedRonPerHa']['central']:10,.0f} {paid_price} "
            f"{row['multiple']['central']:7.2f}× {paid_mult} {len(row['localities']):4d}{mark}"
        )
    band = summary["countyMultiple"]
    print(
        f"\nmediana multiplului pe {len(usable)} județe comparabile: "
        f"{band['central']:.2f}×  (p25 {band['low']:.2f}× … p75 {band['high']:.2f}×)"
    )
    if summary["localityMultiple"]:
        same = summary["localityMultiple"]
        print(
            f"pe cele {len(per_uat)} UAT-uri prezente în ambele surse: {same['central']:.2f}×"
        )
    if summary["countyMultipleVsPaid"]:
        print(
            f"mediana față de prețul plătit (ancheta INS): "
            f"{summary['countyMultipleVsPaid']:.2f}×"
        )
    print(
        f"sub paritate față de cerut: "
        f"{', '.join(summary['countiesBelowParity']) or 'niciun județ'}"
    )
    print(
        f"sub paritate față de plătit: "
        f"{', '.join(summary['countiesBelowParityVsPaid']) or 'niciun județ'}"
    )
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

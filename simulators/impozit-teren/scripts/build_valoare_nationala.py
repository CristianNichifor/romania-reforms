"""What all the land in Romania is worth, from the half of it that has been read.

Twenty-one counties are priced from their notaries' grids. Twenty-one are not, and eleven of
those never will be: four chambers publish no per-locality land table at all. So the only route
to a national figure is to predict the missing counties from the measured ones and say, in
numbers, how wrong that is likely to be.

**The measured half is not re-estimated.** A county with a grid contributes what its grid says,
band and all. Only the counties without one are predicted, and every output row says which it
is. Mixing an estimate into a measurement without labelling it is how a national total becomes
unfalsifiable.

**Three candidate predictors were tried and two were thrown away.** This matters more than the
one that was kept, because both discarded ones are what a reader would assume was used:

* *The built share of the county*, from the land register — R² **0,04**. Prahova has the
  largest built share in the country and among the cheapest building land. The share measures
  villages spreading out, not towns being valuable.
* *The NUTS2 region* — under leave-one-out it is **worse than having no predictor at all**,
  2,64× against 2,12×. Nord-Vest contains both Cluj and Sălaj; their mean predicts neither.
* *The population of the county's largest town* — **1,67×**, the only thing tried that beats
  the national mean. Land is dear where people are, and the size of the county seat carries
  that better than anything about the land itself. Adding a second variable to it made
  leave-one-out worse every time, which is what overfitting twenty-one points looks like.

So building land is `log(EUR/ha) = a + b·log(largest town)` and nothing more.

**Farmland does not need a predictor.** Its price per hectare varies far less between counties
than building land does — arable's national geometric mean predicts a held-out county to within
1,51×, and the regional mean is worse again. So each extravilan category is transferred at its
national geometric mean over the priced counties, per cadastral code, onto the missing
counties' hectares from the land register.

**The error band is measured, not chosen.** Every predicted county's band is its point estimate
divided and multiplied by the leave-one-out error of the model that produced it. That is a
statement with a definition behind it: predict a county the fit has never seen, and this is how
far off it lands. It is wide — a factor of 1,67 on the largest component — and it should be.

**București and Ilfov are excluded and named.** The fit's largest town is Iași at 390 000
people; Bucharest has 2,14 million, and applying a log-linear fit five and a half times beyond
the range it was fitted on is not extrapolation, it is invention. Ilfov is arithmetically
inside the range — its largest town, Voluntari, has 47 000 people — and substantively outside
it, because Ilfov is Bucharest's suburbs and its land is priced by a city that is not in it.
The national total here is therefore **Romania minus its capital region**, stated as such, and
the capital region is left as a named hole rather than filled with a number nobody could
defend.

Usage:
    uv run python simulators/impozit-teren/scripts/build_valoare_nationala.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_fond_funciar import TO_NOTARY  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BANDS = ("low", "central", "high")
# The land register's own forest category. It carries no notary code because the studies price
# forest per hectare in a table of its own, which is exactly how it is transferred here.
FOREST_REGISTER = "Paduri si alta vegetatie forestiera"
BUILT_REGISTER = "Ocupata cu constructii"
# Predicted apart from the rest: they are the codes with enough priced counties behind them to
# average. AP and DR are priced in three counties and two, which is not a national mean.
TRANSFERRED = ("A", "P+F", "V+L", "NP", "PADURE")
# Outside the fit and outside the country's ordinary land market. See the module docstring.
CAPITAL = ("B", "IF")


# The output is deliberately NOT called `valoare-teren-nationala-*.json`.
#
# It was, for about an hour, and in that hour the name collided with the glob that finds the
# per-county studies — here, in the map builder, in the forest-yield builder and in a test.
# Every one of them would have read this file as though it were a county, and since its
# `counties` list starts at AB it would have replaced Alba's study with the national estimate
# and refitted the model on its own output. Four call sites, one shared prefix, and the second
# build of the day quietly different from the first.
#
# Filtering the glob at each call site would have fixed four places and left the fifth for
# whoever writes it next. The prefix is what is wrong: `valoare-teren-XX` means one county's
# land, and this is not one county's land. So it is `valoare-nationala-2026.json`, and the
# collision cannot recur.


def read(pattern: str) -> dict[str, dict]:
    """Every dataset matching a glob, keyed by the county it covers."""
    found: dict[str, dict] = {}
    for path in sorted((ROOT / "data").glob(pattern)):
        document = json.loads(path.read_text(encoding="utf-8"))
        if len(document["counties"]) != 1:
            continue
        found[document["counties"][0]] = document
    return found


def measured_rates(value: dict) -> tuple[float, dict[str, float], dict[str, float]]:
    """A priced county's euro per hectare, for building land and for each extravilan code."""
    extravilan = sum(row["extravilanValueEur"] for row in value["localities"])
    built_ha = value["summary"]["builtHa"]
    built = (value["summary"]["landValueEur"]["central"] - extravilan) / built_ha
    amounts: dict[str, float] = {}
    areas: dict[str, float] = {}
    for row in value["localities"]:
        for code, amount in row.get("extravilanValueByCodeEur", {}).items():
            amounts[code] = amounts.get(code, 0.0) + amount
        for code, hectares in row.get("areaHa", {}).items():
            areas[code] = areas.get(code, 0.0) + hectares
        areas["PADURE"] = areas.get("PADURE", 0.0) + row.get("forestHa", 0.0)
    # A hundred hectares is the floor for calling something a county-wide rate. Below it the
    # ratio is one commune's price standing in for a county and the mean it feeds is noise.
    rates = {code: amounts[code] / areas[code] for code in amounts if areas.get(code, 0) > 100}
    return built, rates, areas


def fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Ordinary least squares in logs. Two parameters, twenty-one points, on purpose."""
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum(
        (x - mean_x) ** 2 for x in xs
    )
    return mean_y - slope * mean_x, slope


def leave_one_out(keys: list[str], x: dict[str, float], y: dict[str, float]) -> float:
    """The error factor: refit without each county, predict it, and spread the misses.

    This is the number that goes into the published band, so it is computed the only way that
    makes it mean anything — the county being predicted is not in the fit that predicts it.
    """
    errors = []
    for held in keys:
        rest = [k for k in keys if k != held]
        intercept, slope = fit([x[k] for k in rest], [y[k] for k in rest])
        errors.append(intercept + slope * x[held] - y[held])
    return math.exp(statistics.pstdev(errors))


def loo_mean(values: dict[str, float]) -> float:
    """The same, for a plain geometric mean with no predictor."""
    logs = {k: math.log(v) for k, v in values.items()}
    errors = [
        statistics.mean([v for j, v in logs.items() if j != k]) - logs[k] for k in logs
    ]
    return math.exp(statistics.pstdev(errors))


def main() -> int:
    values = read("valoare-teren-*.json")
    register = read("fond-funciar-*.json")
    people = read("populatie-*.json")
    if not values:
        raise SystemExit("no county is priced; run build_valoare_teren.py first")
    missing_inputs = sorted(set(register) - set(people))
    if missing_inputs:
        raise SystemExit(f"no population for {missing_inputs}; run import_populatie.py --all")

    priced = sorted(values)
    built_rate: dict[str, float] = {}
    code_rate: dict[str, dict[str, float]] = {}
    for county in priced:
        built, rates, _areas = measured_rates(values[county])
        built_rate[county] = built
        code_rate[county] = rates

    # The fit. x is the log population of the largest town, y the log price of building land.
    log_town = {c: math.log(people[c]["summary"]["largestPeople"]) for c in register}
    intercept, slope = fit(
        [log_town[c] for c in priced], [math.log(built_rate[c]) for c in priced]
    )
    # Rounded here, once, rather than on the way out. The band is built by multiplying and
    # dividing by this factor, and publishing a rounded copy of a number used at full precision
    # leaves a file whose own band does not reconstruct from its own fields.
    built_error = round(
        leave_one_out(priced, log_town, {c: math.log(built_rate[c]) for c in priced}), 4
    )
    predicted_r2 = 1 - statistics.pvariance(
        [math.log(built_rate[c]) - (intercept + slope * log_town[c]) for c in priced]
    ) / statistics.pvariance([math.log(built_rate[c]) for c in priced])

    # The extravilan transfer: one geometric mean per code, over the counties that priced it.
    transfer: dict[str, float] = {}
    transfer_error: dict[str, float] = {}
    transfer_counties: dict[str, int] = {}
    for code in TRANSFERRED:
        have = {c: code_rate[c][code] for c in priced if code in code_rate[c]}
        if len(have) < 8:
            continue
        transfer[code] = math.exp(statistics.mean(math.log(v) for v in have.values()))
        transfer_error[code] = round(loo_mean(have), 4)
        transfer_counties[code] = len(have)

    rows = []
    for county in sorted(register):
        entry = register[county]
        areas = {}
        for locality in entry["localities"]:
            for label, hectares in locality["areaHa"].items():
                code = FOREST_REGISTER if label == FOREST_REGISTER else TO_NOTARY.get(label)
                if code:
                    areas[code] = areas.get(code, 0.0) + hectares
        built_ha = entry["summary"]["builtHa"]
        total_ha = entry["summary"]["totalHa"]
        town = people[county]["summary"]

        if county in values:
            summary = values[county]["summary"]
            rows.append(
                {
                    "county": county,
                    "basis": "measured",
                    "totalHa": total_ha,
                    "builtHa": built_ha,
                    "largestTown": town["largestName"],
                    "largestPeople": town["largestPeople"],
                    "landValueEur": {b: summary["landValueEur"][b] for b in BANDS},
                    "coverageShare": summary["coverage"]["share"],
                    "pricedHa": summary["pricedHa"],
                }
            )
            continue

        if county in CAPITAL:
            rows.append(
                {
                    "county": county,
                    "basis": "excluded",
                    "totalHa": total_ha,
                    "builtHa": built_ha,
                    "largestTown": town["largestName"],
                    "largestPeople": town["largestPeople"],
                    "landValueEur": None,
                    "reason": (
                        "În afara intervalului pe care s-a estimat modelul: cel mai mare oraș "
                        "din eșantion are 390 000 de locuitori, Bucureștiul are 2,14 milioane. "
                        "Ilfovul este suburbia Bucureștiului și prețul terenului lui este dat "
                        "de un oraș care nu se află în județ."
                    ),
                }
            )
            continue

        # Building land from the fit, extravilan from the national means, both onto the
        # register's own hectares. The band is the model's leave-one-out error, applied to the
        # component that carries it: a county's arable hectares are known exactly, so the
        # uncertainty is entirely in the price per hectare.
        built_central = float(round(math.exp(intercept + slope * log_town[county]) * built_ha))
        parts_central = 0.0
        parts_low = 0.0
        parts_high = 0.0
        by_code = {}
        for code, rate in transfer.items():
            hectares = areas.get(FOREST_REGISTER if code == "PADURE" else code, 0.0)
            if not hectares:
                continue
            # Rounded once, then used everywhere. Accumulating the unrounded figure while
            # publishing the rounded one leaves a file whose own band cannot be reconstructed
            # from its own parts — a discrepancy of a few thousand euro on fourteen billion,
            # invisible to a reader and fatal to anyone checking the arithmetic.
            amount = float(round(rate * hectares))
            by_code[code] = amount
            parts_central += amount
            parts_low += amount / transfer_error[code]
            parts_high += amount * transfer_error[code]
        rows.append(
            {
                "county": county,
                "basis": "predicted",
                "totalHa": total_ha,
                "builtHa": built_ha,
                "largestTown": town["largestName"],
                "largestPeople": town["largestPeople"],
                "builtEurPerHa": round(math.exp(intercept + slope * log_town[county])),
                "landValueEur": {
                    "low": round(built_central / built_error + parts_low),
                    "central": round(built_central + parts_central),
                    "high": round(built_central * built_error + parts_high),
                },
                "builtValueEur": round(built_central),
                "extravilanValueByCodeEur": by_code,
            }
        )

    counted = [r for r in rows if r["landValueEur"]]
    total = {b: sum(r["landValueEur"][b] for r in counted) for b in BANDS}
    measured_rows = [r for r in counted if r["basis"] == "measured"]
    predicted_rows = [r for r in counted if r["basis"] == "predicted"]
    measured_total = {b: sum(r["landValueEur"][b] for r in measured_rows) for b in BANDS}
    excluded = [r for r in rows if r["basis"] == "excluded"]

    document = {
        "$schema": "../schema/valoare-nationala.schema.json",
        "id": "valoare-nationala-2026",
        "title": "Valoarea terenului în România: 21 de județe măsurate, 19 estimate, 2 excluse",
        "publisher": "romania-reforms",
        "counties": sorted(register),
        "period": "2026",
        "currency": "EUR",
        "provenance": {
            "source": "valoare-teren-*, fond-funciar-*, populatie-*",
            "locator": (
                "județele cu grilă notarială contribuie cu valoarea citită; restul sunt "
                "estimate din populația celui mai mare oraș (teren construit) și din media "
                "geometrică națională pe cod cadastral (extravilan), aplicate suprafețelor din "
                "registrul funciar"
            ),
            "confidence": "derived",
            "note": (
                "Jumătate din total este citit, cealaltă estimată. Banda estimării este eroarea "
                "leave-one-out a modelului, nu o presupunere. Bucureștiul și Ilfovul sunt în "
                "afara totalului și sunt numite ca atare."
            ),
        },
        "assumptions": {
            "builtModel": "log(EUR/ha) = a + b × log(populația celui mai mare oraș)",
            "builtIntercept": round(intercept, 6),
            "builtSlope": round(slope, 6),
            "builtR2": round(predicted_r2, 4),
            "builtLeaveOneOutErrorFactor": built_error,
            "builtFittedOnCounties": len(priced),
            "transferEurPerHa": {k: round(v, 2) for k, v in transfer.items()},
            "transferLeaveOneOutErrorFactor": dict(transfer_error),
            "transferFittedOnCounties": transfer_counties,
            "rejectedPredictors": {
                "builtShareOfCounty": "R² 0,04 — fără relație",
                "nuts2Region": "eroare LOO 2,64× — mai slab decât media națională, 2,12×",
            },
            "excludedCounties": list(CAPITAL),
        },
        "summary": {
            "counties": len(rows),
            "measuredCounties": len(measured_rows),
            "predictedCounties": len(predicted_rows),
            "excludedCounties": len(excluded),
            "totalHa": sum(r["totalHa"] for r in counted),
            "landValueEur": total,
            "measuredShareOfValue": round(
                measured_total["central"] / total["central"], 4
            ),
            "measuredShareOfArea": round(
                sum(r["totalHa"] for r in measured_rows) / sum(r["totalHa"] for r in counted), 4
            ),
        },
        "counties_valued": rows,
        "limitations": [
            {
                "id": "jumatate-din-tara-e-estimata-nu-citita",
                "text": (
                    f"Din {total['central'] / 1e9:.0f} mld EUR, "
                    f"{100 * measured_total['central'] / total['central']:.0f}% provin din "
                    "grile notariale citite și restul dintr-un model cu un singur predictor, "
                    "populația celui mai mare oraș. Modelul explică "
                    f"{100 * predicted_r2:.0f}% din varianța prețului terenului construit între "
                    f"județele măsurate și greșește un județ nevăzut cu un factor de "
                    f"{built_error:.2f}× — adică valoarea estimată a unui județ poate fi cu o "
                    "treime mai mică sau cu două treimi mai mare decât cifra din tabel."
                ),
                "severity": "blocking",
                "affects": ["valoare-nationala"],
            },
            {
                "id": "bucurestiul-lipseste-din-total",
                "text": (
                    "Totalul este România fără București și Ilfov. Cel mai mare oraș din "
                    "eșantionul pe care s-a estimat modelul are 390 000 de locuitori; "
                    "Bucureștiul are 2,14 milioane, iar o extrapolare log-liniară de cinci ori "
                    "peste intervalul măsurat nu ar fi o estimare. Cum acolo se află cel mai "
                    "scump teren din țară, totalul de aici este o subestimare a României "
                    "întregi, cu o marjă necunoscută și probabil mare."
                ),
                "severity": "blocking",
                "affects": ["valoare-nationala"],
            },
            {
                "id": "predictorul-e-populatia-dupa-domiciliu",
                "text": (
                    "Populația folosită este cea după domiciliu, nu cea rezidentă: numără unde "
                    "sunt înregistrate persoanele. Supraestimează orașele din care s-a emigrat, "
                    "deci supraestimează terenul acolo. Este singura serie publicată pe "
                    "localități pentru fiecare an."
                ),
                "severity": "material",
                "affects": ["valoare-nationala"],
            },
            {
                "id": "estimarea-mosteneste-tot-ce-limiteaza-grilele",
                "text": (
                    "Județele estimate moștenesc fiecare limitare a județelor măsurate, pentru "
                    "că din ele este estimat modelul: aceleași grile, aceeași lipsă a "
                    "ponderilor pe zone, același multiplu de piață lăsat la 1. Eroarea "
                    "leave-one-out măsoară cât de departe cade un județ față de celelalte "
                    "județe citite, nu cât de departe cad toate față de piață."
                ),
                "severity": "blocking",
                "affects": ["valoare-nationala"],
            },
        ],
    }

    out = ROOT / "data" / "valoare-nationala-2026.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"modelul terenului construit: log(EUR/ha) = {intercept:.3f} + "
        f"{slope:.3f}·log(oraș),  R² {predicted_r2:.2f},  eroare LOO {built_error:.2f}×"
    )
    print("transfer extravilan (media geometrică națională, EUR/ha):")
    for code, rate in sorted(transfer.items()):
        print(
            f"   {code:<7}{rate:9,.0f}   ±{transfer_error[code]:.2f}×   "
            f"din {transfer_counties[code]} județe"
        )
    print()
    print(f"{'':<26}{'low':>12}{'central':>12}{'high':>12}")
    for label, series in (
        (
            f"citit, {len(measured_rows)} județe (mld)",
            {b: measured_total[b] / 1e9 for b in BANDS},
        ),
        (
            f"estimat, {len(predicted_rows)} județe (mld)",
            {b: (total[b] - measured_total[b]) / 1e9 for b in BANDS},
        ),
        ("ROMÂNIA fără B+IF (mld)", {b: total[b] / 1e9 for b in BANDS}),
    ):
        print(f"{label:<26}" + "".join(f"{series[b]:12,.1f}" for b in BANDS))
    print(f"\nexclus: {', '.join(r['county'] for r in excluded)}")
    print("\ncele mai valoroase județe estimate:")
    for row in sorted(predicted_rows, key=lambda r: -r["landValueEur"]["central"])[:6]:
        print(
            f"   {row['county']:<3}{row['landValueEur']['central'] / 1e9:7.1f} mld   "
            f"{row['largestTown']} {row['largestPeople']:,}"
        )
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

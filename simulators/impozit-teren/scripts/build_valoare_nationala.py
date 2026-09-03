"""What all the land in Romania is worth, from the half of it that has been read.

All forty-two counties are priced from their notaries' grids, and this file now predicts none
of them. It was written when twenty-one were read and the rest had to be estimated from the
measured ones, and most of what follows is the record of that estimate: which predictors were
tried, which were thrown away, and how wide the error was. It is kept because the machinery is
what makes the total falsifiable — every county was checked against it as it landed, and a
chamber that stops publishing puts its county back into the predicted half tomorrow.

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

**București is measured now, and the refusal to extrapolate to it was right.** For most of this
file's life the capital was excluded as un-predictable: the fit's largest town is Iași at
390 000 people and Bucharest has 2,14 million, so reaching it meant stretching a log-linear
fit five and a half times past its range. Its chamber's own study has since been read, and the
comparison is the only test this model will ever get at that end of the scale — the fit says
**37,4 mld EUR** and the grid says **50 mld**. It would have understated the country's most
valuable county by a third, outside its own 1,65× error.

**Ilfov is read too, and nothing is excluded any more.** It was the last named hole, kept out
because its land is priced by a city that is not in it — arithmetically inside the fitted range
and substantively nowhere near it. Its chamber publishes it, so the judgement no longer has to
be made. The mechanism for excluding a county stays in place, unused: the reasoning behind it
was right and will be needed again.

**The estimate covers all 42 counties**, some read from their chambers' grids and the rest
predicted, with every row saying which it is. The split moves every time a county is read, so
it is counted at build time and printed in the title rather than recorded in this sentence.

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
# Empty, and it is worth saying why rather than deleting the mechanism. Both counties that
# were here are read now: the București chamber publishes both on its own server. The list
# stays because the judgement it encodes — that some counties cannot be predicted from the
# size of their largest town and must be named rather than guessed — is the right one to keep
# available for whatever is found next.
CAPITAL: tuple[str, ...] = ()

# Measured, counted in the total, and kept out of the regression.
#
# Ilfov's building land is 286 177 EUR/ha. The model, fitted without it, says 68 872 — a
# factor of 4,2, against an out-of-sample error of 1,61. It is not a county the size of whose
# largest town can explain, because its market is set by a city that is not in it, and that is
# the same reason it was excluded from the estimate before its study was found.
#
# Leaving it in costs every one of the eighteen predicted counties: leave-one-out goes from
# 1,61× to 1,77× and R² from 0,75 to 0,66. Taking it out is not chosen to improve the number —
# the criterion is stated in the mechanism, not in the result, and București was tested the
# same way and *kept*, because including it improved the fit rather than degrading it.
NOT_IN_FIT = ("IF",)


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
    fitted = [c for c in priced if c not in NOT_IN_FIT]
    built_rate: dict[str, float] = {}
    code_rate: dict[str, dict[str, float]] = {}
    for county in priced:
        built, rates, _areas = measured_rates(values[county])
        built_rate[county] = built
        code_rate[county] = rates

    # The fit. x is the log population of the largest town, y the log price of building land.
    log_town = {c: math.log(people[c]["summary"]["largestPeople"]) for c in register}
    intercept, slope = fit(
        [log_town[c] for c in fitted], [math.log(built_rate[c]) for c in fitted]
    )
    # Rounded here, once, rather than on the way out. The band is built by multiplying and
    # dividing by this factor, and publishing a rounded copy of a number used at full precision
    # leaves a file whose own band does not reconstruct from its own fields.
    built_error = round(
        leave_one_out(fitted, log_town, {c: math.log(built_rate[c]) for c in fitted}), 4
    )
    predicted_r2 = 1 - statistics.pvariance(
        [math.log(built_rate[c]) - (intercept + slope * log_town[c]) for c in fitted]
    ) / statistics.pvariance([math.log(built_rate[c]) for c in fitted])

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
                    # Only measured counties have one: a predicted county has no register of
                    # who owns its land, and inventing a taxable share for it would put a
                    # revenue figure on top of an estimate that is already a factor of 1,5 wide.
                    "taxableValueEur": {b: summary["taxableValueEur"][b] for b in BANDS},
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
    taxable_total = {b: sum(r["taxableValueEur"][b] for r in measured_rows) for b in BANDS}
    # Named in the limitation below rather than asserted, so the sentence cannot outlive the
    # fact it describes.
    capital = next((r for r in rows if r["county"] == "B" and r["landValueEur"]), None)
    bucharest_line = (
        f"Bucureștiul singur este {capital['landValueEur']['central'] / 1e9:.1f} mld EUR, "
        f"{100 * capital['landValueEur']['central'] / total['central']:.0f}% din total"
        if capital
        else "Bucureștiul nu are încă grilă citită"
    )
    excluded = [r for r in rows if r["basis"] == "excluded"]

    # Counted, not written down. This title said "21 de județe măsurate" for thirteen counties
    # after it stopped being true, because nothing rereads a title once it reads correctly once.
    parts = [f"{len(measured_rows)} județe măsurate"]
    if predicted_rows:
        parts.append(f"{len(predicted_rows)} estimate")
    if excluded:
        parts.append(f"{len(excluded)} excluse")

    document = {
        "$schema": "../schema/valoare-nationala.schema.json",
        "id": "valoare-nationala-2026",
        "title": f"Valoarea terenului în România: {', '.join(parts)}",
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
            "builtFittedOnCounties": len(fitted),
            "builtHeldOutOfFit": list(NOT_IN_FIT),
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
            # The base a land tax could reach, summed over the counties that have one. A tax
            # levied on the line above would be charged on state forest, county roads and the
            # Danube; art. 456 (1) a) does not allow that, and it is a quarter of the country.
            "taxableValueEur": taxable_total,
            "taxableSharePercent": round(
                100 * taxable_total["central"] / measured_total["central"], 2
            )
            if measured_total["central"]
            else 0,
            "measuredShareOfValue": round(
                measured_total["central"] / total["central"], 4
            ),
            "measuredShareOfArea": round(
                sum(r["totalHa"] for r in measured_rows) / sum(r["totalHa"] for r in counted), 4
            ),
        },
        "counties_valued": rows,
        "limitations": [
            # Written from the numbers every build. Each of these was once a statement about a
            # gap and stopped being true as chambers were read, and the frozen text went on
            # asserting it — a panel headed "tot pământul din România" carried a blocking note
            # whose id said București was missing from the total, while București sat inside it.
            *(
                [
                    {
                        "id": "o-parte-din-tara-e-estimata-nu-citita",
                        "text": (
                            f"Din {total['central'] / 1e9:.0f} mld EUR, "
                            f"{100 * measured_total['central'] / total['central']:.0f}% provin "
                            "din grile notariale citite, restul dintr-un model cu un singur "
                            "predictor, populația celui mai mare oraș. Modelul explică "
                            f"{100 * predicted_r2:.0f}% din varianța prețului terenului "
                            "construit între județele măsurate și greșește un județ nevăzut cu "
                            f"un factor de {built_error:.2f}×."
                        ),
                        "severity": "blocking",
                        "affects": ["valoare-nationala"],
                    }
                ]
                if predicted_rows
                else [
                    {
                        "id": "toata-tara-e-citita-inclusiv-bucurestiul",
                        "text": (
                            f"Totalul de {total['central'] / 1e9:.0f} mld EUR cuprinde toate "
                            f"cele {len(measured_rows)} de județe, Bucureștiul și Ilfovul "
                            f"incluse — {bucharest_line}. Nu mai este estimat niciun județ, "
                            "deci nicio parte din această cifră nu vine dintr-un model. "
                            "Ilfovul este ținut în afara *ajustării* modelului, pentru că "
                            "piața lui e dictată de un oraș care nu se află în județ, dar "
                            "valoarea lui este citită din grilă și este în total ca oricare "
                            "alta."
                        ),
                        "severity": "note",
                        "affects": ["valoare-nationala"],
                    }
                ]
            ),
            {
                "id": "banda-bucurestiului-e-cea-mai-larga",
                "text": (
                    "Banda Bucureștiului este cea mai largă din set, pentru că orașul are 277 "
                    "de subzone între 34 și 1 320 EUR/mp și nu există nicăieri suprafața "
                    "fiecăreia: cifra centrală este media neponderată a acelor prețuri, iar "
                    "capetele sunt limite, nu un interval de încredere. Când Bucureștiul era "
                    "încă neevaluat, modelul îi dădea 37,4 mld EUR; grila spune 50, deci "
                    "refuzul de a-l extrapola era justificat."
                ),
                "severity": "material",
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
                "id": "totalul-mosteneste-tot-ce-limiteaza-grilele",
                "text": (
                    "Totalul moștenește fiecare limitare a grilelor din care e făcut: aceleași "
                    "prețuri publicate fără suprafețe cu care să fie ponderate pe sat și pe "
                    "zonă, același multiplu de piață lăsat la 1. Este o sumă de citiri, deci "
                    "nu are o eroare statistică proprie — are limitările documentelor."
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
        (
            "ROMÂNIA, toate județele (mld)"
            if not excluded
            else f"ROMÂNIA fără {'+'.join(r['county'] for r in excluded)} (mld)",
            {b: total[b] / 1e9 for b in BANDS},
        ),
        (
            "din care impozabil (mld)",
            {b: taxable_total[b] / 1e9 for b in BANDS},
        ),
    ):
        print(f"{label:<30}" + "".join(f"{series[b]:12,.1f}" for b in BANDS))
    print(f"\nbaza impozabilă: {100 * taxable_total['central'] / measured_total['central']:.1f}% "
          "din valoarea județelor citite; restul e domeniu public, art. 456 alin. (1) lit. a)")
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

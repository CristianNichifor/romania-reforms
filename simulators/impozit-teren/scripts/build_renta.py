"""Land rent, and what share of it each tax actually takes.

A land value tax is argued about in the wrong unit. "0,33% of land value" means nothing to
anyone; what a landowner feels, and what the economics is actually about, is the share of the
**land rent** the tax takes. Rent is what land earns for existing — the return to holding it —
and a tax on land value is only ever a claim on some fraction of that flow.

So this file converts the stock into the flow and restates both taxes against it:

    land rent = land value × yield
    capture   = tax ÷ land rent

The capture figure is the one worth having. It says today's Fiscal Code takes a couple of per
cent of what Romanian land earns, which is a sentence anybody can argue with, and it makes the
comparison with any proposed rate immediate: a tax taking 100% of land rent is the textbook
full land value tax, and everything real sits far below it.

**The yield is a yield per category, because the land is several assets.**

*Farmland is measured.* INS surveys both what agricultural land sells for and what it rents
for, and reports both to Eurostat, so rent ÷ price is an observed return — about **1,4–1,6%**
a year for arable. Each county takes the band of its own NUTS2 region, drawn from that region's
year-to-year movement since 2019 rather than invented around a point.

*Forest is derived* — nobody rents a forest, so its yield comes from what the timber on it
earns: harvest per hectare times the standing price, less the owner's cost share, about
**2,3%**.

*The land under houses is derived too, and this is the number that changed.* It was an assumed
**3–7%** for most of this project's life, anchored on the gross residential yield. That
assumption is gone. `build_randament_construit.py` derives the same quantity from an identity
whose every other term is published — property yield minus depreciation times the building's
share of value — and gets **1,7–3,2%, with 2,5% in the middle**. This file used to carry a
limitation saying the derivation contradicted the assumption and that the rent was therefore
probably overstated. Publishing both was the inconsistency; the derivation won, because it is
built from named inputs and the assumption was an anchor.

**Halving the yield doubles the capture.** Rent is value times yield, and capture is tax over
rent, so every capture figure in this repository roughly doubled the day this changed. Nothing
about the tax or the land moved. Only the honesty of the denominator.

Applying the farmland figure to all of it would still have been the wrong move: it is a
measurement of a different asset, and at 1,4% it is lower again. So each cadastral code is
capitalised at its own band and the county's headline "rate that takes the whole rent" is the
blend — which differs between counties according to what kind of land they have, as it should.

The market multiple is the second parameter and it starts at 1. Raising it restates everything
at a chosen multiple of the published values.

**It is now an informed knob rather than a blind one, and it still defaults to 1.**
`build_multiplu_piata.py` measures the gap between the notaries' grid and what sellers ask for
farmland in the Legea 17/2014 offer register: a median of about **1,2× by county** and **1,06×
on the 73 communes where both sources price the same place** — with three counties, Iași, Sibiu
and Harghita, where the grid is *above* the asking price. For arable land the floor turns out
to be roughly the market.

That measurement is deliberately not wired in as a default, for two reasons that are in the
data rather than in an opinion. It compares an asking price with an administrative minimum, so
neither side is a transaction. And it covers extravilan farmland, which is 36% of the land
value here; the other 64% is curți-construcții, for which no per-locality market price exists
in any public Romanian source found so far. Multiplying house plots by a number measured on
fields would be a worse error than leaving the multiple at 1, because it would look like
calibration.

Usage:
    uv run python simulators/impozit-teren/scripts/build_renta.py --county BC
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agricultural_yield import forest, measured, product_of  # noqa: E402
from built_yield import ASSUMED  # noqa: E402
from built_yield import built as built_yield  # noqa: E402
from built_yield import limitation as built_limitation  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# No GHID_YEAR constant here on purpose: the chambers do not publish in step, so the edition
# is whichever one the previous stage actually wrote. See build_valoare_teren.py.


def edition(pattern: str) -> dict:
    """The newest dataset matching `pattern`, and the year it says it covers.

    Globbed rather than named, because a county's edition is a fact about which study its
    chamber published, not a constant this pipeline gets to choose.
    """
    found = sorted((ROOT / "data").glob(pattern))
    if not found:
        raise SystemExit(f"missing {pattern}; run its builder first")
    return json.loads(found[-1].read_text(encoding="utf-8"))
BANDS = ("low", "central", "high")

# Read, not chosen. This used to be a hard-coded 3-7% anchored on the residential market;
# it is now whatever `build_randament_construit.py` derives, which is about 1,7-3,2%. The
# constant is gone on purpose: the previous limitation in this very file said the derivation
# contradicted the assumption, and leaving both in the repository meant publishing a rent the
# repository's own evidence did not support. See scripts/built_yield.py.
LAND_YIELD, YIELD_SOURCE, BUILT_DERIVATION = built_yield()
def load(name: str) -> dict:
    path = ROOT / "data" / name
    if not path.exists():
        raise SystemExit(f"missing {path}; run its builder first")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", default="BC")
    parser.add_argument(
        "--market-multiple",
        type=float,
        default=1.0,
        help=(
            "restate the published values at a multiple of themselves; 1 leaves them alone. "
            "For extravilan arable, multiplu-piata-2026.json measures ~1,06-1,2x against "
            "asking prices; nothing is measured for curti-constructii."
        ),
    )
    args = parser.parse_args()
    county = args.county.upper()
    multiple = args.market_multiple

    tax = edition(f"impozit-{county.lower()}-*.json")
    grid_year = int(tax["period"])
    # One band per cadastral code, each from the survey that measured that code. Forest is
    # the exception and is named as such: nothing measures a forest yield, so it stands in
    # with the arable band and carries a blocking limitation for doing so.
    bands: dict[str, dict[str, float]] = {}
    sources: dict[str, str] = {}
    for code in ("A", "P+F", "V+L", "AP", "DR", "NP"):
        band, source = measured(county, product_of(code))
        if band:
            bands[code] = band
            sources[code] = source
    # Forest has its own derivation and no longer borrows arable's band.
    band, source = forest(county)
    if band:
        bands["PADURE"] = band
        sources["PADURE"] = source
    agri_yield, agri_source = measured(county)
    rows = []
    for record in tax["localities"]:
        value = {b: record["landValueRon"][b] * multiple for b in BANDS}
        # A yield per asset. Farmland's is measured — rent over price, from one survey — and
        # comes out near 1,5%. The land under houses has no measured yield anywhere, so it
        # takes the band derived in randament-teren-construit-2026.json, near 2,5%. Both are
        # far below the 3–7% this file used to assume for the built half.
        #
        # Extravilan carries no band of its own; it is one figure under every band, so the
        # intravilan part is whatever is left of each.
        agricultural = record["extravilanValueRon"] * multiple
        by_code = {
            code: amount * multiple
            for code, amount in record.get("extravilanValueByCodeRon", {}).items()
        }
        rent = {}
        for b in BANDS:
            built = max(0.0, value[b] - agricultural)
            if agri_yield is None:
                rent[b] = value[b] * LAND_YIELD[b] / 100
                continue
            flow = built * LAND_YIELD[b] / 100
            accounted = 0.0
            for code, amount in by_code.items():
                band = bands.get(code, agri_yield)
                flow += amount * band[b] / 100
                accounted += amount
            # Anything the split did not account for — a code with no price, or an older
            # file without the breakdown — keeps the arable band rather than falling out of
            # the rent entirely.
            flow += max(0.0, agricultural - accounted) * agri_yield[b] / 100
            rent[b] = flow
        # The band widens on both sides: the cheapest reading of the land at the lowest yield
        # against the dearest at the highest. Pairing them the other way would understate how
        # little is known.
        fiscal = record["fiscalCodeRon"]
        rows.append(
            {
                "siruta": record["siruta"],
                "name": record["name"],
                "rank": record["rank"],
                "landValueRon": {b: round(value[b]) for b in BANDS},
                "landRentRon": {b: round(rent[b]) for b in BANDS},
                # What the Fiscal Code takes out of the flow. The cheapest lawful tax against
                # the largest rent, and the dearest against the smallest, so the reported
                # spread is the widest honest one.
                "fiscalCaptureOfRent": {
                    "low": round(100 * fiscal["low"] / rent["high"], 4) if rent["high"] else None,
                    "central": round(100 * fiscal["central"] / rent["central"], 4)
                    if rent["central"]
                    else None,
                    "high": round(100 * fiscal["high"] / rent["low"], 4) if rent["low"] else None,
                },
            }
        )

    if not rows:
        print(f"FATAL: nothing to capitalise for {county}", file=sys.stderr)
        return 1

    total_rent = {b: sum(r["landRentRon"][b] for r in rows) for b in BANDS}
    total_value = {b: sum(r["landValueRon"][b] for r in rows) for b in BANDS}
    fiscal_total = {b: tax["summary"]["fiscalCodeRon"][b] for b in BANDS}
    capture = {
        "low": 100 * fiscal_total["low"] / total_rent["high"],
        "central": 100 * fiscal_total["central"] / total_rent["central"],
        "high": 100 * fiscal_total["high"] / total_rent["low"],
    }
    # The rate on value that would take the whole of the rent — the textbook full land value
    # tax, and the ceiling any proposed rate should be read against. Computed from the totals
    # rather than read off the parameter, because with two yields the county's effective rate
    # is a blend of them weighted by how much of its land is farmland — which differs by
    # county and is exactly what the split was for.
    full = {
        b: round(100 * total_rent[b] / total_value[b], 4) if total_value[b] else LAND_YIELD[b]
        for b in BANDS
    }

    if agri_yield:
        print(
            f"{county}: {len(rows)} localități, randament curți-construcții {LAND_YIELD} %, "
            f"agricol măsurat {agri_yield} %"
        )
    else:
        print(
            f"{county}: {len(rows)} localități, randament {LAND_YIELD} % "
            "(ancheta agricolă neimportată)"
        )
    print(f"{'':<28}{'low':>14}{'central':>14}{'high':>14}")
    for label, series in (
        ("valoarea terenului (mld)", {b: total_value[b] / 1e9 for b in BANDS}),
        ("renta funciară (mld/an)", {b: total_rent[b] / 1e9 for b in BANDS}),
        ("impozit azi (mil/an)", {b: fiscal_total[b] / 1e6 for b in BANDS}),
    ):
        print(f"{label:<28}" + "".join(f"{series[b]:14,.2f}" for b in BANDS))
    print(f"{'din rentă, azi (%)':<28}" + "".join(f"{capture[b]:14.2f}" for b in BANDS))
    print(f"{'cota pe valoare = toată renta':<28}" + "".join(f"{full[b]:14.2f}" for b in BANDS))

    document = {
        "$schema": "../schema/renta.schema.json",
        "id": f"renta-{county.lower()}-{grid_year}",
        "title": f"Renta funciară și cât din ea ia impozitul, județul {county}, {grid_year}",
        "publisher": "romania-reforms",
        "counties": [county],
        "period": str(grid_year),
        "currency": "RON",
        "provenance": {
            "source": f"valoare-teren-{county.lower()}-{grid_year}",
            "locator": "valoarea terenului × randament, pe unitate administrativ-teritorială",
            "confidence": "derived",
            "note": (
                "renta = valoare × randament; captura = impozit ÷ rentă. Randamentul este un "
                "parametru, nu o măsurătoare: nu există un randament publicat al terenului pe "
                "comune în România."
            ),
        },
        "assumptions": {
            "landYieldPercent": LAND_YIELD,
            "yieldSource": YIELD_SOURCE,
            # What this used to be, kept beside what it now is. A reader comparing an older
            # copy of this file has to be able to see that the number moved and why, rather
            # than discovering that every capture figure doubled between two editions.
            "landYieldPreviouslyAssumedPercent": ASSUMED,
            "builtYieldIsDerived": bool(BUILT_DERIVATION),
            "builtLandSharePercent": BUILT_DERIVATION.get("landSharePercent"),
            "urbanBuiltYieldPercent": BUILT_DERIVATION.get("urbanDerivedYieldPercent"),
            "ruralBuiltYieldPercent": BUILT_DERIVATION.get("ruralDerivedYieldPercent"),
            # Null when the survey has not been imported, in which case the single band above
            # was applied to all of the value and the figures mean what they used to.
            "agriculturalYieldPercent": agri_yield,
            "agriculturalYieldSource": agri_source,
            "yieldByCategoryPercent": bands,
            "yieldByCategorySource": sources,
            "marketMultiple": multiple,
        },
        "summary": {
            "localities": len(rows),
            "landValueRon": {b: round(total_value[b]) for b in BANDS},
            "landRentRon": {b: round(total_rent[b]) for b in BANDS},
            "fiscalCodeRon": {b: round(fiscal_total[b]) for b in BANDS},
            "fiscalCaptureOfRentPercent": {b: round(capture[b], 4) for b in BANDS},
            "fullRentRatePercent": full,
        },
        "localities": rows,
        "limitations": [
            {
                "id": "randamentul-e-parametru-nu-masuratoare",
                "text": (
                    "Nu există un randament publicat al terenului pe localități în România. "
                    "Niciuna dintre cele patru benzi folosite aici nu este o măsurătoare la "
                    "nivel de comună: cea agricolă e măsurată pe regiuni NUTS2, cea a pădurii "
                    "și cea a terenului construit sunt deduse. Renta se mișcă direct "
                    "proporțional cu ele — la jumătate de randament, renta se înjumătățește și "
                    "captura impozitului se dublează."
                ),
                "severity": "blocking",
                "affects": ["renta", "captura"],
            },
            {
                "id": "randamentul-padurii-e-dedus-nu-masurat",
                "text": (
                    "Nimeni nu publică o arendă a pădurii, deci randamentul ei nu poate fi "
                    "măsurat direct. Nu mai este însă împrumutat de la arabil: se deduce din "
                    "recolta de lemn pe hectar (INS AGR306A) înmulțită cu prețul masei "
                    "lemnoase pe picior de la licitațiile Romsilva, minus o cotă declarată de "
                    "costuri ale proprietarului — circa 2,3%, față de 1,43% măsurat la arabil. "
                    "Cota de costuri rămâne un parametru, iar prețul este o medie națională."
                ),
                "severity": "blocking",
                "affects": ["renta", "captura"],
            },
            built_limitation(LAND_YIELD),
            {
                "id": "randamentul-e-national-nu-local",
                "text": (
                    "Randamentul folosit este unul singur pentru tot județul, deși randamentele "
                    "reale variază puternic — în București periferia depășește 8% iar centrul "
                    "scade sub 6%. Un randament unic supraestimează renta acolo unde terenul e "
                    "scump și o subestimează unde e ieftin."
                ),
                "severity": "material",
                "affects": ["renta"],
            },
            {
                "id": "multiplul-de-piata-e-necalibrat",
                "text": (
                    "Multiplul de piață este lăsat la 1: valorile rămân cele publicate. Pentru "
                    "teren agricol extravilan există acum două referințe de piață — prețul "
                    "cerut din registrul Legii 17/2014 (circa 1,2× grila) și prețul plătit din "
                    "ancheta INS (circa 1,7×) — dar acoperă 36% din valoare; pentru "
                    "curți-construcții, restul de 64%, nu există niciun preț de piață publicat "
                    "pe localități. A aplica un multiplu agricol pe terenul de sub case ar fi o "
                    "eroare mai mare decât presupunerea de 1. Cine are date de tranzacții pe "
                    "curți-construcții îl poate muta, iar totul se rescalează liniar."
                ),
                "severity": "blocking",
                "affects": ["renta", "captura", "valoare"],
            },
        ],
    }

    out = ROOT / "data" / f"renta-{county.lower()}-{grid_year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

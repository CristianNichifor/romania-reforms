"""What the land of a county is worth, and therefore what a land tax could stand on.

Two halves meet here. `import_ghid.py` has the notaries' price per square metre, by category,
village by village. `import_fond_funciar.py` has the hectares of each category, per commune.
Multiplying them gives a land value per commune — which is the base a land value tax is
levied on, and the number the Fiscal Code's area-and-coefficient formula never computes.

**The multiplication is easy and the two assumptions it needs are not.** They are the whole
uncertainty of this file, so they are named, parameterised, and reported as a band rather than
buried in a single confident number.

*Which land is intravilan.* The grids price intravilan land tens to hundreds of times higher
than extravilan — Bacău's building land runs to 256 EUR/m² in zone A against 0,86 EUR/m² for
the same category outside the town. The land register does not record the split. The default
here treats **curți-construcții as intravilan and everything else as extravilan**, which is
approximately how the categories fall and is wrong at the edges in a known direction: village
gardens are arable land inside the intravilan, so the intravilan area is understated and with
it the total.

*Which value applies to a whole commune.* The grid prices each village separately and each
town zone separately, but neither villages nor zones have published areas, so there is no
weight to average them with. Rather than invent one, every commune is valued three times —
at its cheapest village, at its dearest, and at the unweighted mean — and all three travel
together. For towns the spread is the widest and the mean is the least trustworthy of the
three, because zone A is always the smallest zone and the dearest.

So `central` is a midpoint between two published extremes, not an estimate of anything
measured. The band is the honest object; the point estimate exists to be plotted.

Usage:
    uv run python simulators/impozit-teren/scripts/build_valoare_teren.py --county BC
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_ghid import key_of, keys_of, resolve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# No GHID_YEAR constant here on purpose. The chambers do not publish in step — Ploiești
# skipped 2026 entirely, so Prahova and Dâmbovița are 2025 documents sitting beside ten that
# are not — and a constant stamped every output 2026 regardless, including a provenance line
# pointing at a grid that does not exist. The year travels with the document that was read.
AREA_YEAR = 2014
M2_PER_HA = 10_000

COUNTY_TO_CHAMBER = {
    "B": "bucuresti",
    "IF": "ilfov",
    "CL": "calarasi",
    "GR": "giurgiu",
    "IL": "ialomita",
    "TR": "teleorman",
    "SV": "suceava",
    "BT": "botosani",
    "AR": "arad",
    "BV": "brasov",
    "CS": "carasseverin",
    "AG": "arges",
    "BR": "braila",
    "DJ": "dolj",
    "GJ": "gorj",
    "GL": "galati",
    "MH": "mehedinti",
    "OT": "olt",
    "CV": "covasna",
    "VS": "vaslui",
    "BC": "bacau",
    "NT": "neamt",
    "AB": "alba",
    "IS": "iasi",
    "SB": "sibiu",
    "CT": "constanta",
    "TL": "tulcea",
    "PH": "prahova",
    "MS": "mures",
    "HR": "harghita",
    "VL": "valcea",
    "VN": "vrancea",
    "DB": "dambovita",
    "BZ": "buzau",
    "HD": "hunedoara",
    "BH": "bihor",
    "SM": "satumare",
    "CJ": "cluj",
    "BN": "bistrita",
    "MM": "maramures",
    "SJ": "salaj",
    "TM": "timis",
}

# The one category treated as intravilan. Named rather than inlined because it is the single
# assumption that moves the answer most, and the app is meant to let a reader move it.
INTRAVILAN_CATEGORY = "CC"
# Everything else is valued at the commune's extravilan prices, by category.
EXTRAVILAN_CATEGORIES = ["A", "V+L", "P+F", "CC", "AP", "DR", "NP"]
# Forest is not in the register's byCategory at all — it is a separate fund, reported as
# forestHa, and the two add up to the county. It was left unvalued on the grounds that the
# studies price it per hectare in a table of its own, which is true and was not a reason: a
# third of the surface of the counties read so far is forest, and leaving it out valued
# 2,6 million hectares at nothing.
FOREST_CATEGORY = "PADURE"

# The register writes locality names with their rank in front; the grids do not.
RANK_PREFIXES = ("MUNICIPIUL ", "ORASUL ", "ORAS ", "COMUNA ")


def strip_rank(name: str) -> str:
    upper = name.upper()
    for prefix in RANK_PREFIXES:
        if upper.startswith(prefix):
            return name[len(prefix):]
    return name


ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"


def exchange_rate() -> tuple[float, str]:
    """RON per EUR, with the date it was published, because the answer moves with it.

    From the ECB rather than the BNR: the BNR's XML feed now answers with its own home page,
    and a source that has to be scraped out of a marketing page is not a source.

    Needed here and not only in the tax comparison, because chambers do not agree on a
    currency — CNP Bacău prices land in euro and CNP Alba Iulia in lei — and a land value
    stated in two units cannot be added up.
    """
    cache = ROOT / "sources" / "ecb-eurofxref-daily.xml"
    if not cache.exists():
        request = urllib.request.Request(ECB_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(response.read())
    body = cache.read_text(encoding="utf-8")
    rate = re.search(r"currency='RON'\s+rate='([\d.]+)'", body)
    date = re.search(r"time='([\d-]+)'", body)
    if not rate or not date:
        raise SystemExit("ECB reference rates: RON is not in the feed")
    return float(rate.group(1)), date.group(1)


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing {path}; run its importer first")
    return json.loads(path.read_text(encoding="utf-8"))


def intravilan_prices(grid: dict) -> dict[str, dict]:
    """Every published intravilan price for the chosen category, per locality.

    A rural commune contributes one price per village; a zoned town one per zone. Both come
    back as a plain list because neither has areas to weight it by, and pretending otherwise
    is the thing this file most wants to avoid.
    """
    prices: dict[str, dict] = {}
    for entry in grid["zoned"]:
        values = entry["intravilan"].get(INTRAVILAN_CATEGORY, {})
        published = {zone: v for zone, v in values.items() if v is not None}
        if published:
            # Registered under every spelling of the name, because the land register writes
            # Bârsănești as BARSANESTI and Târgu Ocna as TARGU OCNA — the same â/a split the
            # notaries' own pages disagree about. Matching one spelling lost 16 communes
            # across two counties, and a commune that fails to join is a commune with no land.
            for key in keys_of(entry["name"]):
                prices[key] = {
                    "kind": "zone",
                    "parts": published,
                    "rank": entry["rank"],
                    "name": entry["name"],
                }
    for commune in grid["communes"]:
        # Keyed by position, not by name. Several readers emit more than one reading under the
        # same label — Bihor prices Oradea zone by zone and calls every row ORADEA — and a dict
        # keyed on the name kept only the last of them. That silently valued the county's
        # largest city at 220 lei/m² instead of a band from 1 200 down, and the resulting
        # figure looked like a bad parse rather than a dropped one. The label is kept for
        # reading; uniqueness comes from the index.
        published = {
            f"{village['name']} #{position}": village["intravilan"][INTRAVILAN_CATEGORY]
            for position, village in enumerate(commune["villages"], start=1)
            if village["intravilan"].get(INTRAVILAN_CATEGORY) is not None
        }
        # A town that also has villages keeps its zone grid: the zones price the town itself,
        # which is where its building land is, and the villages are priced beside it. Merging
        # the two lists would let a village drag a town's floor down by a factor of ten.
        if published and not keys_of(commune["name"]) & prices.keys():
            for key in keys_of(commune["name"]):
                prices[key] = {
                    "kind": "village",
                    "parts": published,
                    "rank": commune["rank"],
                    "name": commune["name"],
                }
    return prices


def extravilan_prices(grid: dict) -> dict[str, dict[str, float]]:
    prices: dict[str, dict[str, float]] = {}
    for entry in grid["zoned"]:
        if entry["extravilan"]:
            for key in keys_of(entry["name"]):
                prices[key] = entry["extravilan"]
    for commune in grid["communes"]:
        if commune["extravilan"] and not keys_of(commune["name"]) & prices.keys():
            for key in keys_of(commune["name"]):
                prices[key] = commune["extravilan"]
    return prices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", default="BC", choices=sorted(COUNTY_TO_CHAMBER))
    parser.add_argument(
        "--reuse-exchange-rate",
        action="store_true",
        help=(
            "convert at the rate this county's existing dataset was built with, instead of "
            "today's. For CI, so that rebuilding can be byte-compared: everything here is "
            "published in euro and most chambers price in lei, so without this the output "
            "moves whenever the euro does and a diff proves nothing either way."
        ),
    )
    args = parser.parse_args()
    county = args.county

    # Whichever edition exists, not a year assumed in common. The Ploiești chamber published
    # nothing for 2026, so Prahova's grid is the 2025 one and sits beside six that are not.
    editions = sorted(ROOT.glob(f"data/ghid-teren-{COUNTY_TO_CHAMBER[county]}-*.json"))
    if not editions:
        raise SystemExit(f"no grid imported for {county}; run import_ghid.py first")
    grid = json.loads(editions[-1].read_text(encoding="utf-8"))
    grid_year = int(grid["period"])
    areas = load(ROOT / "data" / f"fond-funciar-{county.lower()}-{AREA_YEAR}.json")
    intra = intravilan_prices(grid)
    extra = extravilan_prices(grid)
    # Everything downstream is in euro, so a chamber that prices in lei is converted here
    # rather than leaving two units in one dataset.
    #
    # Which makes this file move with the euro, and CI byte-compares it. Those two facts are
    # incompatible: a rerun on a different day differs in the fourth significant figure of
    # every locality in every lei-priced county, which is not a regression and cannot be told
    # apart from one. `--reuse-exchange-rate` pins the rate to whatever the committed dataset
    # was built at, so the comparison tests the parsing and the arithmetic — which is what it
    # was meant to test — and leaves the rate to the steps that are not diffed.
    out_path = ROOT / "data" / f"valoare-teren-{county.lower()}-{grid_year}.json"
    if args.reuse_exchange_rate and out_path.exists():
        previous = json.loads(out_path.read_text(encoding="utf-8"))["assumptions"]
        ron_per_eur, fx_date = previous["ronPerEur"], previous["exchangeRateDate"]
    else:
        ron_per_eur, fx_date = exchange_rate()
    to_eur = (1 / ron_per_eur) if grid["currency"] == "RON" else 1.0

    rows: list[dict] = []
    unmatched: list[str] = []
    for record in areas["localities"]:
        # The register and the grid disagree about â, and both are already flattened, so the
        # lookup has to forgive an `a` against an `i` — see `ai_equal` in import_ghid.
        key = resolve(key_of(strip_rank(record["name"])), intra) or ""
        # Only the intravilan price is required. A study that prints no extravilan grid for a
        # locality — Alba does not, for two communes and most of its towns — still prices its
        # building land, and dropping the locality over the missing half would lose the more
        # valuable half with it. The unpriced categories stay unpriced.
        if key not in intra:
            unmatched.append(f"{record['name']} ({record['siruta']})")
            continue

        parts = [value * to_eur for value in intra[key]["parts"].values()]
        legs = {
            "low": min(parts),
            "central": statistics.fmean(parts),
            "high": max(parts),
        }

        def valued_at(areas: dict[str, float], forest_ha: float, legs: dict = legs, key: str = key):
            """These hectares at this locality's published prices.

            Run twice — once over every hectare in the register, once over the privately
            owned ones — because the taxable base has to be the *same valuation* on *fewer
            hectares*, not a second valuation that could drift from the first. A copy of this
            arithmetic would be a copy of every rounding and every missing-price rule in it.
            """
            built_ha = areas.get(INTRAVILAN_CATEGORY, 0.0)
            intravilan = {k: built_ha * M2_PER_HA * v for k, v in legs.items()}
            # Everything not built-up is valued outside the town, category by category.
            extravilan = 0.0
            priced_ha = 0.0
            by_code: dict[str, float] = {}
            forest_price = extra.get(key, {}).get(FOREST_CATEGORY)
            forest_value = 0.0
            if forest_ha and forest_price is not None:
                forest_value = forest_ha * M2_PER_HA * forest_price * to_eur
                extravilan += forest_value
                by_code[FOREST_CATEGORY] = forest_value
                priced_ha += forest_ha
            for code in EXTRAVILAN_CATEGORIES:
                if code == INTRAVILAN_CATEGORY:
                    continue
                hectares = areas.get(code, 0.0)
                price = extra.get(key, {}).get(code)
                price = price * to_eur if price is not None else None
                if hectares and price is not None:
                    extravilan += hectares * M2_PER_HA * price
                    by_code[code] = by_code.get(code, 0.0) + hectares * M2_PER_HA * price
                    priced_ha += hectares
            return built_ha, intravilan, extravilan, by_code, priced_ha, forest_value

        built_ha, intravilan_value, extravilan_value, by_code, priced_ha, forest_value = valued_at(
            record["byCategory"], record["forestHa"]
        )
        # The taxable base: art. 456 (1) a) does not tax land in the public domain, and a
        # quarter of Romania by area is in it. Same prices, private hectares only.
        (
            private_built_ha,
            taxable_intravilan,
            taxable_extravilan,
            taxable_by_code,
            _,
            _,
        ) = valued_at(record["byCategoryPrivate"], record["forestPrivateHa"])

        rows.append(
            {
                "siruta": record["siruta"],
                # The grid's spelling, not the register's. The land register shouts and
                # drops diacritics — MUNICIPIUL BACAU — while the notaries' study prints the
                # county roster's own Bacău. Same place, and only one of the two is a name.
                "name": intra[key].get("name") or strip_rank(record["name"]),
                "rank": intra[key]["rank"],
                "pricedBy": intra[key]["kind"],
                "parts": len(parts),
                "totalHa": record["totalHa"],
                "builtHa": round(built_ha, 2),
                "privateHa": record["privateHa"],
                "privateBuiltHa": round(private_built_ha, 2),
                "forestHa": record["forestHa"],
                "forestPrivateHa": record["forestPrivateHa"],
                "forestValueEur": round(forest_value),
                "pricedExtravilanHa": round(priced_ha, 2),
                # Six decimals, not two. The central figure is a mean of village prices,
                # and the app recomputes the value from this number rather than from the
                # mean itself — so a display rounding here becomes a real disagreement
                # between the page and the file it was checked against.
                "intravilanEurPerM2": {k: round(v, 6) for k, v in legs.items()},
                # Carried so the app can re-do this arithmetic under a different assumption
                # rather than only display the one made here. The intravilan share is the
                # parameter that moves the answer most, and a reader who cannot move it is
                # being shown a conclusion instead of a calculation.
                "areaHa": {k: v for k, v in record["byCategory"].items() if v},
                # The privately owned subset of the same hectares, carried for the same
                # reason: the browser recomputes the taxable base as the reader moves the
                # intravilan share, and it cannot do that from a total alone.
                "privateAreaHa": {k: v for k, v in record["byCategoryPrivate"].items() if v},
                # Forest is exported alongside the rest, not only used. The value builder
                # priced it and the page could not see it, so the browser's rent drifted five
                # per cent from the file it is checked against — which is exactly what the
                # parity test is for.
                "extravilanEurPerM2": {
                    code: round(extra[key][code] * to_eur, 6)
                    for code in [*EXTRAVILAN_CATEGORIES, FOREST_CATEGORY]
                    if extra.get(key, {}).get(code) is not None
                },
                "extravilanValueEur": round(extravilan_value),
                # The same total, split by cadastral code. Arable and pasture are surveyed
                # apart and yield apart, and forest has no measured yield at all, so the rent
                # builder needs to know which euro is which rather than one lump.
                "extravilanValueByCodeEur": {k: round(v) for k, v in by_code.items() if v},
                "landValueEur": {
                    k: round(intravilan_value[k] + extravilan_value) for k in legs
                },
                # What a land tax could actually reach. Not a share of the line above: the
                # public domain is concentrated in forest, roads and water, so the taxable
                # fraction of the *value* is much higher than the taxable fraction of the area.
                "taxableValueEur": {
                    k: round(taxable_intravilan[k] + taxable_extravilan) for k in legs
                },
                "taxableExtravilanValueEur": round(taxable_extravilan),
                "taxableExtravilanValueByCodeEur": {
                    k: round(v) for k, v in taxable_by_code.items() if v
                },
            }
        )

    if not rows:
        print(f"FATAL: nothing joined for {county}", file=sys.stderr)
        return 1

    totals = {
        band: sum(row["landValueEur"][band] for row in rows) for band in ("low", "central", "high")
    }
    # Named rather than asserted: the limitation below used to claim forest was excluded from
    # the value, and the only way that claim stays honest is to compute it every build.
    forest_value = sum(row["forestValueEur"] for row in rows)
    forest_share = forest_value / totals["central"] if totals["central"] else 0.0
    taxable = {
        band: sum(row["taxableValueEur"][band] for row in rows)
        for band in ("low", "central", "high")
    }
    built = sum(row["builtHa"] for row in rows)
    covered = sum(row["totalHa"] for row in rows)
    # Hectares that actually received a price, as against hectares belonging to a locality
    # this managed to match. The two are the same in most counties and are not in Hunedoara,
    # where the study prices agricultural land for its eleven circumscription seats and for
    # nobody else: fifty-four communes there carry building land and nothing else, so most of
    # the county's surface contributes zero to its land value. Reported rather than inferred,
    # because a county valued at a fifth of its neighbours reads as a finding about the county
    # until you know it is a fact about the document.
    # Forest is back in the denominator now that it can be priced. It was excluded while no
    # reader emitted a forest price, because then every county looked equally short and the
    # measure told nobody anything; with forest valued, an unpriced hectare is a real gap
    # again.
    priceable = sum(row["totalHa"] for row in rows)
    priced = sum(row["builtHa"] + row["pricedExtravilanHa"] for row in rows)

    share = len(rows) / len(areas["localities"]) if areas["localities"] else 0
    print(f"{county}: {len(rows)} din {len(areas['localities'])} localități legate "
          f"({100 * share:.1f}%)")
    if share < 0.9:
        print(f"FATAL: only {100 * share:.1f}% of the county valued; not writing", file=sys.stderr)
        return 1
    if unmatched:
        print(f"nelegate ({len(unmatched)}): {unmatched}")
    print(f"suprafață acoperită: {covered:,.0f} ha   curți-construcții: {built:,.0f} ha")
    for band in ("low", "central", "high"):
        print(f"  valoarea terenului, {band:<8}: {totals[band] / 1e9:8.2f} mld EUR")
    print(f"  din care impozabil (privat): {taxable['central'] / 1e9:8.2f} mld EUR "
          f"({100 * taxable['central'] / totals['central'] if totals['central'] else 0:.1f}%)")
    spread = totals["high"] / totals["low"] if totals["low"] else 0
    print(f"  raportul sus/jos: {spread:.1f}×")

    document = {
        "$schema": "../schema/valoare-teren.schema.json",
        "id": f"valoare-teren-{county.lower()}-{grid_year}",
        "title": (
            f"Valoarea terenului, județul {county}, "
            f"grila {grid_year} pe fondul funciar {AREA_YEAR}"
        ),
        "publisher": "romania-reforms",
        "counties": [county],
        "period": str(grid_year),
        "currency": "EUR",
        "provenance": {
            "source": f"unnpr-terenuri-{COUNTY_TO_CHAMBER[county]}-{grid_year}",
            "locator": (
                f"grila notarială {grid_year} × fondul funciar INS AGR101B {AREA_YEAR}, "
                "pe unitate administrativ-teritorială"
            ),
            "confidence": "derived",
            "note": (
                "valoare = suprafață_curți_construcții × preț_intravilan_CC + Σ "
                "suprafață_categorie × preț_extravilan_categorie. Prețul intravilan al unei "
                "comune nu este unul singur: grila publică un preț pe sat, respectiv pe zonă, "
                "fără suprafețe cu care să fie ponderate, așa că low/central/high sunt "
                "minimul, media neponderată și maximul prețurilor publicate."
            ),
        },
        "assumptions": {
            "sourceCurrency": grid["currency"],
            "ronPerEur": ron_per_eur,
            "exchangeRateDate": fx_date,
            "intravilanCategory": INTRAVILAN_CATEGORY,
            "areaYear": AREA_YEAR,
            "gridYear": grid_year,
            "weighting": "unweighted: villages and zones have no published areas",
        },
        "summary": {
            "localities": len(rows),
            "localitiesInRegister": len(areas["localities"]),
            # Named rather than forbidden, for the same reason the grid names its gaps: a
            # locality the study does not price cannot be valued, and dropping the county for
            # it would publish nothing about the rest. It is absent from the map, not zero on
            # it, which is the distinction that matters when the map is of land value.
            "unmatched": unmatched,
            "coverage": {
                "localitiesExpected": len(areas["localities"]),
                "localitiesValued": len(rows),
                "share": round(len(rows) / len(areas["localities"]), 4)
                if areas["localities"]
                else 0.0,
            },
            "coveredHa": round(covered, 2),
            "pricedHa": round(priced, 2),
            "priceableHa": round(priceable, 2),
            "builtHa": round(built, 2),
            "landValueEur": {band: round(value) for band, value in totals.items()},
            "taxableValueEur": {band: round(value) for band, value in taxable.items()},
            "taxableSharePercent": round(100 * taxable["central"] / totals["central"], 2)
            if totals["central"]
            else 0,
            "highToLowRatio": round(spread, 2),
        },
        "localities": rows,
        "limitations": [
            *(
                [
                    {
                        "id": "o-parte-din-suprafata-nu-are-pret",
                        "text": (
                            f"Doar {priced / priceable:.0%} din hectarele neîmpădurite ale "
                            "localităților evaluate au primit un preț; restul aparțin unor "
                            "categorii "
                            "pentru care studiul județului nu publică nicio valoare. "
                            "Hectarele fără preț intră cu zero, deci valoarea totală a "
                            "terenului este subevaluată, iar orice cotă calculată ca "
                            "impozit împărțit la valoare este supraevaluată în aceeași "
                            "măsură."
                        ),
                        "severity": "material",
                        "affects": ["valoare-teren", "renta", "captura"],
                    }
                ]
                if priceable and priced / priceable < 0.9
                else []
            ),
            {
                "id": "impartirea-intravilan-extravilan-e-presupusa",
                "text": (
                    "Fondul funciar nu spune ce este intravilan. Aici se presupune că "
                    "intravilanul este exact categoria curți-construcții, iar restul este "
                    "extravilan. Grădinile din sate sunt teren arabil în intravilan, deci "
                    "suprafața intravilană este subestimată, iar valoarea totală odată cu ea. "
                    "Este cel mai important parametru al acestui fișier."
                ),
                "severity": "blocking",
                "affects": ["valoare-teren", "impozit"],
            },
            {
                "id": "nu-exista-ponderi-pentru-sate-si-zone",
                "text": (
                    "Grila dă un preț pe sat și pe zonă, dar nici satele, nici zonele nu au "
                    "suprafețe publicate, deci nu există cu ce fi ponderate. De aceea fiecare "
                    "comună este evaluată de trei ori — la satul cel mai ieftin, la cel mai "
                    "scump și la media neponderată. Banda este rezultatul; punctul din mijloc "
                    "există doar ca să poată fi desenat. La orașe media este cea mai puțin de "
                    "încredere dintre cele trei: zona A este întotdeauna cea mai mică și cea "
                    "mai scumpă."
                ),
                "severity": "blocking",
                "affects": ["valoare-teren", "impozit"],
            },
            {
                "id": "anii-nu-coincid",
                "text": (
                    f"Suprafețele sunt din {AREA_YEAR}, prețurile din {grid_year}. Seria INS "
                    "pe localități s-a oprit în 2014 și nimic nu a înlocuit-o."
                ),
                "severity": "material",
                "affects": ["valoare-teren"],
            },
            {
                "id": "padurea-e-evaluata-din-alt-tabel",
                "text": (
                    f"Pădurea este evaluată, și anume {100 * forest_share:.0f}% din valoarea "
                    "terenului acestui județ. Prețul ei nu vine însă din grila pe metru pătrat, "
                    "ci din tabelul separat pe hectar pe care îl publică studiul, așa că "
                    "precizia lui este a acelui tabel: un preț pe județ sau pe zonă, nu pe sat. "
                    "Textul de aici a spus multă vreme că pădurea „este exclusă din valoare”, "
                    "ceea ce a încetat să fie adevărat în momentul în care a fost prețuită."
                ),
                "severity": "material",
                "affects": ["valoare-teren"],
            },
        ],
    }

    out = out_path
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

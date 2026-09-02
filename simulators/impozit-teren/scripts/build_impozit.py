"""Two taxes on the same hectares: the one the Fiscal Code levies, and one on land value.

This is the comparison the simulator exists to make. Both taxes are computed on exactly the
same land — the same localities, the same categories, the same hectares out of the INS land
register — so the difference between them is the rule, not the data.

    today   hectares × a figure from a table indexed on rank, zone and category
    LVT     hectares × price per square metre × a rate

Deliberately statutory against statutory, not against what councils actually collect.
Collections carry arrears, exemptions and enforcement, and comparing a modelled tax with a
collected one would attribute all three to the change of rule. The Fiscal Code's own
arithmetic is the honest counterfactual.

**Neither side is a number, and the reasons differ.** The land value is a band because the
grid publishes a price per village with no areas to weight them by. The Fiscal Code figure is
a band for three independent reasons stacked on top of each other:

    the statutory range   art. 465 (2) says 8 282–20 706 lei/ha and art. 465 (9) leaves the
                          choice to the local council — roughly 2,5× on its own
    the zone              A to D is a council decision, and no register of zones or of their
                          areas exists anywhere
    the rank              a commune's seat is rank IV and its other villages rank V

So `low` is the cheapest lawful reading — bottom of the range, zone D, the lower rank — and
`high` the dearest. Both are things a council could lawfully charge today. That the lawful
range is this wide is a finding about the current tax, not a weakness of this file.

The headline is the **revenue-neutral rate**: the percentage of land value that raises what
the Fiscal Code's midpoint raises. It is a ratio of two bands, so it is reported as one.

Usage:
    uv run python simulators/impozit-teren/scripts/build_impozit.py --county BC
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agricultural_yield import forest, measured, product_of  # noqa: E402
from built_yield import built as built_yield  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUILT_YIELD, BUILT_YIELD_SOURCE, _ = built_yield()
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
AREA_YEAR = 2014

# The euro reference rate, from the ECB rather than the BNR: the BNR's XML feed now answers
# with its own home page, and a source that has to be scraped out of a marketing page is not
# a source. The ECB publishes RON daily in a two-kilobyte file that has not moved in years.
# Legea nr. 351/2001 privind planul de amenajare a teritoriului național, anexa IV. The Fiscal
# Code uses ranks 0–V without defining them; this is where they are defined. Rank 0 is
# Bucharest and rank I these eleven municipalities. Everything below follows from rank: other
# municipalities are II, towns III, a commune's seat village IV, its other villages V.
RANK_I_MUNICIPALITIES = {
    "bacau", "brasov", "braila", "clujnapoca", "constanta", "craiova",
    "galati", "iasi", "oradea", "ploiesti", "timisoara",
}
BUCHAREST = "bucuresti"

COUNTY_TO_CHAMBER = {
    "B": "bucuresti",
    "IF": "ilfov",
    "CL": "calarasi",
    "GR": "giurgiu",
    "IL": "ialomita",
    "TR": "teleorman",
    "SV": "suceava",
    "BT": "botosani",
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
# The Fiscal Code's category names, folded onto the notaries' codes, for the intravilan
# table at art. 465 (4) and the extravilan table at art. 465 (7).
FISCAL_TO_NOTARY = {
    "Teren arabil": "A",
    "Pășune": "P+F",
    "Fâneață": "P+F",
    "Vie": "V+L",
    "Livadă": "V+L",
    "Teren cu apă": "AP",
    "Drumuri și căi ferate": "DR",
    "Teren neproductiv": "NP",
    "Teren cu construcții": "CC",
}
BANDS = ("low", "central", "high")
M2_PER_HA = 10_000

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_valoare_teren import exchange_rate, strip_rank  # noqa: E402
from import_ghid import key_of  # noqa: E402


def load(name: str) -> dict:
    path = ROOT / "data" / name
    if not path.exists():
        raise SystemExit(f"missing {path}; run its builder first")
    return json.loads(path.read_text(encoding="utf-8"))


def rank_of(name: str, roster_rank: str | None) -> tuple[str, str]:
    """The locality's rank under Legea 351/2001, as a low and a high reading.

    Towns have one rank. A commune does not: its seat is rank IV and its other villages are
    rank V, and there are no per-village areas to split the commune's hectares between them.
    Rather than pick, both readings are carried and become the ends of the band.
    """
    key = key_of(name)
    if key == BUCHAREST:
        return "0", "0"
    if roster_rank == "municipii":
        rank = "I" if key in RANK_I_MUNICIPALITIES else "II"
        return rank, rank
    if roster_rank == "orase":
        return "III", "III"
    return "V", "IV"


def fiscal_tax_ron(record: dict, code: dict, ranks: tuple[str, str]) -> dict[str, float]:
    """What the Fiscal Code would raise on these hectares, at its cheapest and dearest.

    Built-up land uses art. 465 (2) directly. Every other intravilan category would use
    (4) × (5) — but under the same assumption the value side makes, that curți-construcții is
    the intravilan and the rest is not, those categories are all extravilan here and go
    through (7) × art. 457 (6) instead.
    """
    zones = code["zones"]
    built_ha = record["byCategory"].get("CC", 0.0)
    per_band: dict[str, float] = {}

    for band in BANDS:
        # The cheapest lawful reading pairs the cheapest zone, the lower rank and the bottom
        # of the statutory range; the dearest pairs the opposite. Both are things a council
        # could lawfully charge.
        if band == "low":
            zone_choice, rank, pick = ["D"], ranks[0], "min"
        elif band == "high":
            zone_choice, rank, pick = ["A"], ranks[1], "max"
        else:
            zone_choice, rank, pick = zones, ranks[1], "mid"

        def cell(values: dict, pick: str = pick) -> float:
            """One cell of the Code, read at the end of the range this band asks for."""
            if pick == "mid":
                return (values["min"] + values["max"]) / 2
            return float(values[pick])

        built = statistics.fmean(
            cell(code["intravilanBuiltLeiPerHa"][zone][rank]) for zone in zone_choice
        )
        total = built_ha * built

        coefficients = code["zoneRankCoefficient"]
        for fiscal_name, notary_code in FISCAL_TO_NOTARY.items():
            if notary_code == "CC":
                continue
            hectares = record["byCategory"].get(notary_code, 0.0)
            if not hectares:
                continue
            match = next(
                (v for k, v in code["extravilanLeiPerHa"].items() if k.startswith(fiscal_name)),
                None,
            )
            if match is None:
                continue
            rate = cell(match)
            coefficient = statistics.fmean(coefficients[zone][rank] for zone in zone_choice)
            # Two register categories fold onto one notary code, so the hectares would be
            # counted twice if both Fiscal Code rows claimed them. The register's own split is
            # already lost by then, so the pair shares the land equally.
            share = sum(1 for c in FISCAL_TO_NOTARY.values() if c == notary_code)
            total += hectares / share * rate * coefficient
        per_band[band] = total
    return per_band


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", default="BC", choices=sorted(COUNTY_TO_CHAMBER))
    parser.add_argument("--rate", type=float, default=1.0, help="LVT rate, percent of land value")
    args = parser.parse_args()
    county = args.county

    code = load("cod-fiscal-teren-2026.json")
    areas = load(f"fond-funciar-{county.lower()}-{AREA_YEAR}.json")
    value = edition(f"valoare-teren-{county.lower()}-*.json")
    grid_year = int(value["period"])
    ron_per_eur, fx_date = exchange_rate()

    agri_yield, agri_source = measured(county)
    # Carried for the page, same as the general band above: the browser recomputes the rent
    # and has to use the yields Python used, per cadastral code, or the parity check fails.
    # `category`, not `code` — `code` is the Fiscal Code document a few lines above, and
    # shadowing it here made fiscal_tax_ron index a string and fail for every county.
    yield_by_code = {}
    for category in ("A", "P+F", "V+L", "AP", "DR", "NP"):
        band, _ = measured(county, product_of(category))
        if band:
            yield_by_code[category] = band
    forest_band, _ = forest(county)
    if forest_band:
        yield_by_code["PADURE"] = forest_band
    by_siruta = {row["siruta"]: row for row in value["localities"]}
    rows = []
    for record in areas["localities"]:
        valued = by_siruta.get(record["siruta"])
        if valued is None:
            continue
        ranks = rank_of(strip_rank(record["name"]), valued["rank"])
        fiscal = fiscal_tax_ron(record, code, ranks)
        land_value_ron = {b: valued["landValueEur"][b] * ron_per_eur for b in BANDS}
        # The agricultural half of the value, carried forward so the rent builder can put a
        # different yield on it. It does not vary across the bands: only the intravilan price
        # is published as a low/central/high spread, because only intravilan has villages and
        # zones whose weights are unknown. So one figure, and the intravilan part is whatever
        # is left of each band after it.
        extravilan_ron = valued["extravilanValueEur"] * ron_per_eur
        by_code_ron = {
            code: value * ron_per_eur
            for code, value in valued["extravilanValueByCodeEur"].items()
        }
        lvt = {b: land_value_ron[b] * args.rate / 100 for b in BANDS}
        rows.append(
            {
                "siruta": record["siruta"],
                "name": valued["name"],
                "rank": valued["rank"],
                "fiscalRank": {"low": ranks[0], "high": ranks[1]},
                "totalHa": record["totalHa"],
                "fiscalCodeRon": {b: round(fiscal[b]) for b in BANDS},
                "landValueRon": {b: round(land_value_ron[b]) for b in BANDS},
                "extravilanValueRon": round(extravilan_ron),
                "extravilanValueByCodeRon": {k: round(v) for k, v in by_code_ron.items()},
                "lvtRon": {b: round(lvt[b]) for b in BANDS},
                "effectiveRatePercent": {
                    b: round(100 * fiscal[b] / land_value_ron[b], 4) if land_value_ron[b] else None
                    for b in BANDS
                },
            }
        )

    if not rows:
        print(f"FATAL: nothing to compare for {county}", file=sys.stderr)
        return 1

    fiscal_total = {b: sum(r["fiscalCodeRon"][b] for r in rows) for b in BANDS}
    value_total = {b: sum(r["landValueRon"][b] for r in rows) for b in BANDS}
    # The headline. The midpoint of the lawful range against the midpoint of the value band;
    # the ends of the reported band pair the cheapest lawful tax with the dearest land and
    # vice versa, which is the widest honest reading rather than a flattering one.
    neutral = {
        "low": 100 * fiscal_total["low"] / value_total["high"],
        "central": 100 * fiscal_total["central"] / value_total["central"],
        "high": 100 * fiscal_total["high"] / value_total["low"],
    }

    print(f"{county}: {len(rows)} localități, curs BNR/BCE {ron_per_eur} RON/EUR ({fx_date})")
    print(f"{'':<26}{'low':>16}{'central':>16}{'high':>16}")
    for label, series in (
        ("impozit Cod fiscal (mil RON)", {b: fiscal_total[b] / 1e6 for b in BANDS}),
        ("valoarea terenului (mld RON)", {b: value_total[b] / 1e9 for b in BANDS}),
        (f"impozit pe valoare @{args.rate}% (mil RON)",
         {b: value_total[b] * args.rate / 100 / 1e6 for b in BANDS}),
    ):
        print(f"{label:<26}" + "".join(f"{series[b]:16,.1f}" for b in BANDS))
    print(f"{'cota neutră (%)':<26}" + "".join(f"{neutral[b]:16.3f}" for b in BANDS))

    document = {
        "$schema": "../schema/impozit.schema.json",
        "id": f"impozit-{county.lower()}-{grid_year}",
        "title": f"Impozitul pe teren azi și pe valoare, județul {county}, {grid_year}",
        "publisher": "romania-reforms",
        "counties": [county],
        "period": str(grid_year),
        "currency": "RON",
        "provenance": {
            "source": "cod-fiscal-teren-2026",
            "locator": (
                "Legea nr. 227/2015, art. 465 alin. (2), (4), (5), (7) și art. 457 alin. (6), "
                f"aplicate pe fondul funciar INS {AREA_YEAR} și pe grila notarială {grid_year}"
            ),
            "confidence": "derived",
            "note": (
                "Ambele impozite sunt calculate pe aceleași hectare. Impozitul din Codul "
                "fiscal este statutar, nu încasat: nu conține scutiri, restanțe sau grad de "
                "colectare. Banda lui vine din intervalul legal, din zonă și din rang, toate "
                "trei decizii locale nepublicate într-un registru național."
            ),
        },
        "assumptions": {
            "ronPerEur": ron_per_eur,
            "exchangeRateDate": fx_date,
            "lvtRatePercent": args.rate,
            "intravilanCategory": value["assumptions"]["intravilanCategory"],
            "rankSource": "Legea nr. 351/2001, anexa IV",
            # Carried here, though this file computes no rent, because the page does compute
            # rent and reads this file. The alternative was a constant in the browser that
            # nothing checked against the Python — which is the exact failure the parity test
            # exists to prevent.
            "agriculturalYieldPercent": agri_yield,
            "agriculturalYieldSource": agri_source,
            "yieldByCategoryPercent": yield_by_code,
            # The built-land band, carried here so the browser defaults its slider from the
            # derivation rather than from a number typed into the front end. A constant in
            # two languages is a constant that will disagree with itself.
            "builtYieldPercent": BUILT_YIELD,
            "builtYieldSource": BUILT_YIELD_SOURCE,
        },
        "summary": {
            "localities": len(rows),
            "fiscalCodeRon": {b: round(fiscal_total[b]) for b in BANDS},
            "landValueRon": {b: round(value_total[b]) for b in BANDS},
            "lvtRon": {b: round(value_total[b] * args.rate / 100) for b in BANDS},
            "revenueNeutralRatePercent": {b: round(neutral[b], 4) for b in BANDS},
            "lawfulRangeRatio": round(fiscal_total["high"] / fiscal_total["low"], 2),
        },
        "localities": rows,
        "limitations": [
            {
                "id": "impozitul-de-azi-e-si-el-o-banda",
                "text": (
                    "Impozitul „de azi” nu este un număr. Codul fiscal dă un interval de "
                    "aproximativ 2,5×, iar consiliul local alege din el; zona A–D este tot "
                    "decizie locală; iar o comună are satul de reședință la rangul IV și "
                    "celelalte sate la rangul V. Cele trei necunoscute se înmulțesc, așa că "
                    "raportul dintre citirea cea mai ieftină și cea mai scumpă permisă de lege "
                    "este de ordinul zecilor. Nu există un registru național al hotărârilor "
                    "consiliilor locale din care să se afle cifra reală."
                ),
                "severity": "blocking",
                "affects": ["impozit", "cota-neutra"],
            },
            {
                "id": "statutar-nu-incasat",
                "text": (
                    "Se compară statutar cu statutar. Impozitul calculat aici nu este ce "
                    "încasează primăriile: nu conține scutiri, restanțe și nici gradul de "
                    "colectare. Comparația cu încasările ar atribui schimbării de regulă și "
                    "efectele celor trei."
                ),
                "severity": "material",
                "affects": ["impozit"],
            },
            {
                "id": "cursul-muta-raspunsul",
                "text": (
                    f"Grila notarială este în euro, Codul fiscal în lei. Conversia folosește "
                    f"cursul de referință BCE din {fx_date} ({ron_per_eur} RON/EUR). Cota "
                    "neutră se mișcă direct proporțional cu el."
                ),
                "severity": "material",
                "affects": ["cota-neutra"],
            },
            {
                "id": "padurea-lipseste-din-ambele-parti",
                "text": (
                    "Pădurea este exclusă din valoare, pentru că studiile o evaluează pe "
                    "hectar într-un tabel separat. Este exclusă și din impozitul calculat, ca "
                    "cele două părți să stea pe aceleași hectare — dar Codul fiscal o "
                    "impozitează, deci impozitul de azi este subestimat cu partea ei."
                ),
                "severity": "material",
                "affects": ["impozit"],
            },
        ],
    }

    out = ROOT / "data" / f"impozit-{county.lower()}-{grid_year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

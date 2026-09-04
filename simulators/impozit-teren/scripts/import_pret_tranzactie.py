"""What a property actually sold for, on average, per county — money over things.

Two datasets in this directory each hold half of a price and neither can say it alone.
`import_transfer_imobiliar.py` reads the art. 111 tax and turns it into declared value: how much
money changed hands. `import_vanzari_imobile.py` reads ANCPI's registrations: how many things
changed hands. The quotient is the first average transaction price this repository has ever had
that comes from administrative records rather than from an advertisement.

    preț mediu declarat = (impozit ÷ partaj ÷ cotă) ÷ numărul de vânzări

**Why this fetches instead of reading two committed files.** The tax is filed per commune and
the file for one year is 450 KB; the repository has about half a megabyte of room left, so
committing a second and a third year to derive one small table would spend the remaining
headroom on an intermediate. This reads ANCPI from disk, fetches the tax for the matching year,
rolls it up to county in memory, and writes only the answer — forty-two rows.

**Three corrections the arithmetic needs, all of which push the same way.**

*The count is bigger than the taxed population.* ANCPI registers every sale; art. 111 (2)
exempts inheritances, donations between relatives to the third degree, and restitutions, which
are registered and pay nothing. Dividing by a count that includes them makes the average price
come out **too low**. The direction is known and the size is not, so it is stated rather than
corrected.

*The year is not a year.* ANCPI publishes seven to eleven months depending on the year while
budget execution is twelve. The counts are therefore scaled to twelve months before the
division, which assumes sales are spread evenly through the year — they are not, spring and
autumn are heavier — so `salesAnnualised` is marked as the estimate it is.

*The rate is a range.* 3% up to three years of ownership and 1% above, with no published mix,
so every price here is a band and never a point. The lower rate implies more value for the same
tax, so `high` is computed at 1%.

**And one thing this is not.** It is a price per *transaction*, not per square metre. Neither
source carries an area. A county whose sales are mostly flats and a county whose sales are
mostly field parcels will differ here for reasons that have nothing to do with what land costs.
The `withoutBuildings` share travels with each row so that difference is visible.

Usage:
    uv run python simulators/impozit-teren/scripts/import_pret_tranzactie.py
    uv run python simulators/impozit-teren/scripts/import_pret_tranzactie.py --year 2022
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import import_buget_uat as buget  # noqa: E402
import import_transfer_imobiliar as transfer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Below this many months a year is too thin to annualise: scaling five months by 12/5 is not an
# estimate of a year, it is one season with a multiplier on it.
MIN_MONTHS = 9

# And no year before ANCPI's 2018 reclassification, whatever its month count.
#
# The denominator here is `withBuildings + withoutBuildings`, which after 2018 is very nearly
# every registered sale. Before it, `apartamente` and `-` carried about 230 000 sales a year of
# their own — 111 028 apartments in 2017 against 20 in 2018, for the same country — so the pair
# misses a quarter of the market and the price it produces comes out some 40% too high. The two
# eras are not one series and this file will not straddle them.
MIN_YEAR = 2018

# A county registering fewer sales than this share of the national median, per inhabitant, is
# not a quiet property market — it is a county that does not file.
#
# The spread across the forty-two is 6,3 to 41,8 sales per thousand inhabitants and the middle
# is about twelve. Olt files 2,0 and Teleorman 2,4, and their own histories lurch — Olt reports
# 2 783 sales in 2018, 856 in 2019, 3 052 in 2022, 1 548 in 2023 — while their transfer tax sits
# squarely among their peers'. A denominator missing four fifths of its sales does not make the
# county expensive; it makes the quotient meaningless, and Olt came out as the dearest county in
# Romania at three times București before this guard existed.
MIN_SALES_PER_1000 = 4.0


def sales_document() -> dict:
    found = sorted((ROOT / "data").glob("vanzari-imobile-*.json"))
    if not found:
        raise SystemExit("vanzari-imobile is not built; run import_vanzari_imobile.py first")
    return json.loads(found[-1].read_text(encoding="utf-8"))


def usable_year(sales: dict, wanted: int | None) -> int:
    """The most recent year ANCPI covers well enough to annualise."""
    coverage: dict[int, int] = {}
    for county in sales["counties"]:
        for row in county["series"]:
            coverage[row["year"]] = max(coverage.get(row["year"], 0), row["monthsReported"])
    if wanted:
        if coverage.get(wanted, 0) < MIN_MONTHS:
            raise SystemExit(
                f"{wanted} has only {coverage.get(wanted, 0)} months of ANCPI data; "
                f"{MIN_MONTHS} is the floor for annualising"
            )
        if wanted < MIN_YEAR:
            raise SystemExit(
                f"{wanted} is before ANCPI's {MIN_YEAR} reclassification; the sales categories "
                "are not the same ones and the price would come out about 40% too high"
            )
        return wanted
    good = [
        year
        for year, months in coverage.items()
        if months >= MIN_MONTHS and year >= MIN_YEAR
    ]
    if not good:
        raise SystemExit("no year is both complete enough and after the reclassification")
    return max(good)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int)
    args = parser.parse_args()

    sales = sales_document()
    year = usable_year(sales, args.year)
    print(f"joining on {year}", file=sys.stderr)

    counts: dict[str, dict] = {}
    for county in sales["counties"]:
        for row in county["series"]:
            if row["year"] == year:
                counts[county["county"]] = {"name": county["name"], **row}

    # The tax, fetched and rolled up rather than committed. The quarantine runs first and on
    # the communes, not on the counties: Sector 5's impossible filing would otherwise be folded
    # into București and there would be nothing left to notice it by.
    uats = buget.roster()
    if len(uats) < 3000:
        raise SystemExit(f"only {len(uats)} UATs came back; refusing a partial roster")
    banked = transfer.receipts(uats, year)
    rows = [
        {
            "siruta": uat["siruta"],
            "name": uat["name"],
            "county": uat["county"],
            "localTaxRon": banked.get(uat["siruta"], 0.0),
        }
        for uat in uats
        if banked.get(uat["siruta"], 0.0) > 0
    ]
    suspects = transfer.quarantine(rows, {u["siruta"]: u["population"] or 0 for u in uats})
    rows = [r for r in rows if not r.pop("suspect", False)]

    tax_by_county: dict[str, float] = defaultdict(float)
    for row in rows:
        if row["county"]:
            tax_by_county[row["county"]] += row["localTaxRon"]

    # A county that lost a commune to the quarantine has lost part of its numerator with it.
    #
    # This is the general form of a specific problem: București's transfer tax reaches the
    # municipality, five of its six sectors file nothing at all, and the sixth files an
    # impossible number that the quarantine removes. What is left is a fraction of the city's
    # tax divided by all of the city's sales, and the capital came out as the *cheapest* place
    # in Romania to buy property. Excluding by the rule rather than by the name means the next
    # county this happens to is caught too.
    county_of = {uat["siruta"]: uat["county"] for uat in uats}
    incomplete = {county_of.get(s["siruta"]) for s in suspects} - {None}

    population: dict[str, int] = defaultdict(int)
    for uat in uats:
        if uat["county"] and uat["population"]:
            population[uat["county"]] += uat["population"]

    rate_min = transfer.RATE_MIN_PERCENT
    rate_max = transfer.RATE_MAX_PERCENT
    local_share = transfer.LOCAL_SHARE

    out_rows = []
    dropped = []
    for code in sorted(counts, key=lambda c: counts[c]["name"]):
        local = tax_by_county.get(code, 0.0)
        if local <= 0:
            continue
        record = counts[code]
        months = record["monthsReported"]
        reported = record["sales"].get("withBuildings", 0) + record["sales"].get(
            "withoutBuildings", 0
        )
        if not reported or not months:
            continue
        annualised = reported * 12 / months
        people = population.get(code, 0)
        per_thousand = 1000 * annualised / people if people else None
        if code in incomplete:
            dropped.append(
                {
                    "county": code,
                    "name": record["name"],
                    "reason": "numaratorul-e-incomplet",
                    "detail": (
                        "o primărie din județ a fost pusă în carantină, deci impozitul "
                        "județului nu este întreg"
                    ),
                }
            )
            continue
        if per_thousand is not None and per_thousand < MIN_SALES_PER_1000:
            dropped.append(
                {
                    "county": code,
                    "name": record["name"],
                    "reason": "prea-putine-vanzari-raportate",
                    "detail": (
                        f"{per_thousand:.1f} vânzări la mia de locuitori, sub pragul de "
                        f"{MIN_SALES_PER_1000}; numitorul nu descrie piața județului"
                    ),
                }
            )
            continue
        declared_low = local / local_share / (rate_max / 100)
        declared_high = local / local_share / (rate_min / 100)
        bare = record["sales"].get("withoutBuildings", 0)
        out_rows.append(
            {
                "county": code,
                "name": record["name"],
                "localTaxRon": round(local, 2),
                "monthsReported": months,
                "salesReported": reported,
                "salesAnnualised": round(annualised),
                "bareLandShare": round(bare / reported, 4) if reported else None,
                "salesPer1000": round(per_thousand, 2) if per_thousand is not None else None,
                "declaredValueRon": {
                    "low": round(declared_low, 2),
                    "high": round(declared_high, 2),
                },
                "pricePerSaleRon": {
                    "low": round(declared_low / annualised, 2),
                    "high": round(declared_high / annualised, 2),
                },
            }
        )

    if len(out_rows) < 35:
        raise SystemExit(f"only {len(out_rows)} counties survived; refusing to write")

    middle = sorted(r["pricePerSaleRon"]["high"] for r in out_rows)
    median_high = middle[len(middle) // 2]
    dearest = max(out_rows, key=lambda r: r["pricePerSaleRon"]["high"])
    cheapest = min(out_rows, key=lambda r: r["pricePerSaleRon"]["high"])

    document = {
        "$schema": "../schema/pret-tranzactie.schema.json",
        "id": f"pret-tranzactie-{year}",
        "title": f"Prețul mediu declarat pe tranzacție imobiliară, pe județe, {year}",
        "publisher": "romania-reforms",
        "period": str(year),
        "currency": "RON",
        "provenance": {
            "source": "transfer-imobiliar-si-vanzari-imobile",
            "locator": (
                f"impozitul art. 111 din execuția bugetară {year} pe UAT-uri "
                f"({buget.API}, cod funcțional {transfer.CODE}), agregat pe județ; "
                f"numărul vânzărilor din {sales['id']}, ANCPI"
            ),
            "confidence": "derived",
            "note": (
                "Impozitul este preluat ca atare; împărțirea la partaj, la cotă și la numărul "
                "de vânzări se face aici. Numărul vânzărilor este ridicat la douăsprezece luni "
                "înainte de împărțire, pentru că execuția bugetară este pe an întreg iar ANCPI "
                "publică mai puține luni."
            ),
        },
        "assumptions": {
            "localShare": local_share,
            "rateMinPercent": rate_min,
            "rateMaxPercent": rate_max,
            "minMonths": MIN_MONTHS,
            "minYear": MIN_YEAR,
            "minSalesPer1000": MIN_SALES_PER_1000,
            "salesCounted": "withBuildings + withoutBuildings",
            "note": (
                "Se numără vânzările cu și fără construcții, nu și apartamentele — care sunt o "
                "a doua axă de clasificare a acelorași dosare, nu o categorie în plus. "
                "„agricol” și „neagricol” sunt lăsate deoparte din același motiv."
            ),
        },
        "excluded": suspects,
        "droppedCounties": dropped,
        "summary": {
            "year": year,
            "counties": len(out_rows),
            "countiesDropped": len(dropped),
            "medianPricePerSaleRonAtOnePercent": median_high,
            "dearest": {"county": dearest["county"], "ron": dearest["pricePerSaleRon"]["high"]},
            "cheapest": {"county": cheapest["county"], "ron": cheapest["pricePerSaleRon"]["high"]},
        },
        "counties": out_rows,
        "limitations": [
            {
                "id": "numaratoarea-e-mai-larga-decat-impozitul",
                "severity": "blocking",
                "text": (
                    "ANCPI numără toate vânzările înregistrate, iar impozitul nu se datorează "
                    "la moșteniri, donații între rude până la gradul al III-lea și "
                    "reconstituiri de proprietate (art. 111 alin. (2)). Numitorul este deci mai "
                    "mare decât populația impozitată, iar prețul mediu de aici iese prea mic. "
                    "Direcția se cunoaște, mărimea nu."
                ),
                "affects": ["pret-tranzactie"],
            },
            {
                "id": "cota-efectiva-nu-se-publica",
                "severity": "blocking",
                "text": (
                    "Cota este 1% peste trei ani de deținere și 3% sub, iar amestecul nu se "
                    "publică. Fiecare preț este deci un interval de la simplu la triplu, nu o "
                    "cifră. Capătul „high” este cel la 1%, adică cel probabil mai apropiat de "
                    "adevăr acolo unde predomină revânzările."
                ),
                "affects": ["pret-tranzactie"],
            },
            {
                "id": "lunile-ridicate-la-douasprezece",
                "severity": "material",
                "text": (
                    "Numărul vânzărilor este înmulțit cu 12 împărțit la lunile raportate, ceea "
                    "ce presupune că vânzările se împart egal peste an. Nu se împart: "
                    "primăvara și toamna sunt mai grele. „salesReported” și „monthsReported” "
                    "sunt publicate alături, pentru cine vrea să refacă altfel."
                ),
                "affects": ["pret-tranzactie"],
            },
            {
                "id": "pe-tranzactie-nu-pe-metru",
                "severity": "material",
                "text": (
                    "Este un preț pe tranzacție, nu pe metru pătrat: niciuna dintre cele două "
                    "surse nu are suprafețe. Un județ care vinde apartamente și unul care vinde "
                    "tarlale ies diferit pentru motive care nu au legătură cu prețul "
                    "pământului. Cota vânzărilor fără construcții însoțește fiecare rând tocmai "
                    "ca diferența să se vadă."
                ),
                "affects": ["pret-tranzactie"],
            },
        ],
    }

    out = ROOT / "data" / f"pret-tranzactie-{year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(out_rows)} județe în {year}")
    print(f"  mediana prețului pe tranzacție, la cota de 1%: {median_high:,.0f} lei")
    print(f"  cel mai scump {dearest['name']}: {dearest['pricePerSaleRon']['high']:,.0f} lei")
    print(f"  cel mai ieftin {cheapest['name']}: {cheapest['pricePerSaleRon']['high']:,.0f} lei")
    print(f"Wrote {out.relative_to(ROOT.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

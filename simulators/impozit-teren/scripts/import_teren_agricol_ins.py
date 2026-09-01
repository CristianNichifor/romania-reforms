"""What farmland actually sold for, and what it actually rented for, from the same survey.

Everything else here is either administrative or an asking price. This is neither. INS runs an
annual survey of agricultural land — *Prețurile terenurilor agricole*, PTA — and reports it to
Eurostat as `apri_lprc` (purchase prices) and `apri_lrnt` (renting prices), by NUTS2 region,
from 2011. Those are transactions and tenancies, not offers and not minima.

Two things fall out of having both halves from one survey.

**A market reference for the grid.** The notaries' arable price against the INS transaction
price is a floor against a sale, which is the comparison the whole simulator invites and could
not previously make. The offer register can only say what was asked.

**A measured land yield, and two of them.** Rent divided by price is the return to holding
farmland. Arable and permanent grassland are surveyed separately and do not agree — about
**1,42%** for arable and **1,61%** for pasture and hayfield — so both are read and each
cadastral code takes the one that was measured on it. Reading only arable, as this did at
first, made pasture borrow a number measured on a different crop for no better reason than
that it came first in the table.

That gap is not a mistake in either place, and the file says so rather than quietly overriding
anything. The 3–7% band was anchored on a *residential gross rental yield* — a return on a
whole property, building included, in a town. This is a return on bare farmland let for a
season. They are different assets and there is no reason they should match; what is new is that
one of the two is now measured for the third of land value that is agricultural, and the other
remains assumed for the two thirds that is not.

Rents are per year and prices are per hectare, both in lei, so the ratio is a plain annual
yield with no conversion in it. The regional detail is NUTS2 — eight regions, not forty-two
counties — so a county takes its region's figure, which is stated on every row rather than
being invisible in the join.

Usage:
    uv run python simulators/impozit-teren/scripts/import_teren_agricol_ins.py [--refresh]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
REGIONS = ["RO", "RO11", "RO12", "RO21", "RO22", "RO31", "RO32", "RO41", "RO42"]
TABLES = {"price": ("apri_lprc", "NAC_HA"), "rent": ("apri_lrnt", "NAC_HA")}
# Which region each county sits in. The survey is regional and the rest of this simulator is
# not, so this is where the two granularities are reconciled — explicitly, and once.
COUNTY_REGION = {
    "BH": "RO11", "BN": "RO11", "CJ": "RO11", "MM": "RO11", "SM": "RO11", "SJ": "RO11",
    "AB": "RO12", "BV": "RO12", "CV": "RO12", "HR": "RO12", "MS": "RO12", "SB": "RO12",
    "BC": "RO21", "BT": "RO21", "IS": "RO21", "NT": "RO21", "SV": "RO21", "VS": "RO21",
    "BR": "RO22", "BZ": "RO22", "CT": "RO22", "GL": "RO22", "TL": "RO22", "VN": "RO22",
    "AG": "RO31", "CL": "RO31", "DB": "RO31", "GR": "RO31", "IL": "RO31",
    "PH": "RO31", "TR": "RO31",
    "B": "RO32", "IF": "RO32",
    "DJ": "RO41", "GJ": "RO41", "MH": "RO41", "OT": "RO41", "VL": "RO41",
    "AR": "RO42", "CS": "RO42", "HD": "RO42", "TM": "RO42",
}
# Arable and permanent grassland are surveyed apart and yield apart — 1,42% against 1,61% —
# so both are read. Reading only arable meant pasture and hayfield, which are a large share of
# Romanian farmland, borrowed a yield measured on a different crop for no reason other than
# that it was the first product in the table.
PRODUCTS = {"ARA": "teren arabil", "J0000": "pășuni și fânețe"}


def fetch(table: str, unit: str, refresh: bool) -> dict:
    cache = ROOT / "sources" / f"eurostat-{table}-ro.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    query = "&".join([f"geo={g}" for g in REGIONS])
    url = f"{API}/{table}?format=JSON&lang=EN&unit={unit}&{query}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(body, encoding="utf-8")
    return json.loads(body)


def unpack(document: dict, product: str) -> dict[str, dict[str, float]]:
    """A JSON-stat cube flattened to {region: {year: value}} for one product.

    JSON-stat stores its values against a single flat index, so the position has to be
    unravelled against the dimension sizes — the same arithmetic numpy would do, written out
    because one cube of nine regions does not justify the dependency.
    """
    ids, size, dim = document["id"], document["size"], document["dimension"]

    def index_of(name: str) -> dict[int, str]:
        return {position: key for key, position in dim[name]["category"]["index"].items()}

    regions, years = index_of("geo"), index_of("time")
    products = index_of("agriprod")
    where = {name: position for position, name in enumerate(ids)}

    def unravel(flat: int) -> list[int]:
        out = []
        for extent in reversed(size):
            out.append(flat % extent)
            flat //= extent
        return list(reversed(out))

    found: dict[str, dict[str, float]] = {}
    for key, value in document["value"].items():
        position = unravel(int(key))
        if products[position[where["agriprod"]]] != product:
            continue
        region = regions[position[where["geo"]]]
        found.setdefault(region, {})[years[position[where["time"]]]] = float(value)
    return found


def main() -> int:
    refresh = "--refresh" in sys.argv
    raw = {
        kind: fetch(table, unit, refresh) for kind, (table, unit) in TABLES.items()
    }
    price = {p: unpack(raw["price"], p) for p in PRODUCTS}
    rent = {p: unpack(raw["rent"], p) for p in PRODUCTS}
    labels = raw["price"]["dimension"]["geo"]["category"]["label"]

    years = sorted({y for by_region in price.values() for s in by_region.values() for y in s})
    latest = max(y for y in years if price["ARA"].get("RO", {}).get(y))

    regions = []
    for code in REGIONS:
        rows = []
        for product in PRODUCTS:
            for year in years:
                p = price[product].get(code, {}).get(year)
                r = rent[product].get(code, {}).get(year)
                if p is None and r is None:
                    continue
                rows.append(
                    {
                        "product": product,
                        "year": year,
                        "priceRonPerHa": p,
                        "rentRonPerHa": r,
                        # The whole reason for reading both tables. None where either half is
                        # missing, rather than carried forward from a neighbouring year.
                        "yieldPercent": round(100 * r / p, 4) if p and r else None,
                    }
                )
        if not rows:
            continue
        regions.append(
            {
                "region": code,
                "name": labels[code],
                "counties": sorted(c for c, g in COUNTY_REGION.items() if g == code),
                "series": rows,
            }
        )

    def middle_of(product: str) -> tuple[float | None, int]:
        found = sorted(
            row["yieldPercent"]
            for region in regions
            if region["region"] != "RO"
            for row in region["series"]
            if row["product"] == product
            and row["yieldPercent"] is not None
            and row["year"] >= "2019"
        )
        return (found[len(found) // 2] if found else None), len(found)

    middle, count = middle_of("ARA")
    grass, grass_count = middle_of("J0000")

    document = {
        "$schema": "../schema/teren-agricol-ins.schema.json",
        "id": f"teren-agricol-ins-{latest}",
        "title": (
            "Prețul și arenda terenului arabil, pe regiuni de dezvoltare, "
            f"ancheta INS raportată la Eurostat, 2011–{latest}"
        ),
        "publisher": "romania-reforms",
        "counties": sorted(COUNTY_REGION),
        "period": latest,
        "currency": "RON",
        "provenance": {
            "source": "eurostat-apri-lprc-lrnt",
            "locator": (
                f"{API}/apri_lprc și {API}/apri_lrnt, unit=NAC_HA, "
                f"agriprod={'+'.join(PRODUCTS)}, "
                "geo=RO + cele opt regiuni NUTS2; sursa primară este ancheta INS "
                "„Prețurile terenurilor agricole” (PTA)"
            ),
            "confidence": "verbatim",
            "note": (
                "Prețurile și arendele sunt preluate ca atare; singurul calcul este "
                "randamentul = arendă ÷ preț, ambele în lei/ha și pe același an."
            ),
        },
        "summary": {
            "regions": len(regions),
            "firstYear": years[0],
            "lastYear": latest,
            "nationalPriceRonPerHa": price["ARA"]["RO"][latest],
            "nationalRentRonPerHa": rent["ARA"].get("RO", {}).get(latest),
            "nationalYieldPercent": (
                round(100 * rent["ARA"]["RO"][latest] / price["ARA"]["RO"][latest], 4)
                if rent["ARA"].get("RO", {}).get(latest)
                else None
            ),
            "regionalYieldMedianPercent": middle,
            "regionalYieldObservations": count,
            "grasslandYieldMedianPercent": grass,
            "grasslandYieldObservations": grass_count,
        },
        "regions": regions,
        "limitations": [
            {
                "id": "regiuni-nu-judete",
                "text": (
                    "Ancheta este publicată pe cele opt regiuni NUTS2, nu pe județe. Un județ "
                    "primește cifra regiunii sale, deci diferențele dintre județele aceleiași "
                    "regiuni nu apar deloc — Iașiul și Vasluiul au aceeași valoare aici."
                ),
                "severity": "material",
                "affects": ["teren-agricol-ins", "multiplu-piata"],
            },
            {
                "id": "doar-arabil",
                "text": (
                    "Se citește doar terenul arabil. Pășunile, viile și livezile au prețuri "
                    "proprii în aceeași sursă, dar randamentul măsurat aici este al arabilului "
                    "și nu se transferă automat asupra celorlalte categorii."
                ),
                "severity": "material",
                "affects": ["teren-agricol-ins"],
            },
            {
                "id": "randamentul-agricol-nu-e-cel-rezidential",
                "text": (
                    "Randamentul măsurat aici — arendă ÷ preț, aproximativ 1,4–1,6% — este al "
                    "terenului agricol închiriat pentru un sezon. Banda de 3–7% folosită în "
                    "build_renta.py provine dintr-un randament brut rezidențial, adică al unei "
                    "proprietăți întregi, cu clădire cu tot, dintr-un oraș. Sunt active "
                    "diferite; cifra de aici nu o înlocuiește pe cealaltă pentru "
                    "curți-construcții, care rămân nemăsurate."
                ),
                "severity": "blocking",
                "affects": ["teren-agricol-ins", "renta"],
            },
            {
                "id": "media-nu-mediana",
                "text": (
                    "Ancheta raportează prețuri medii, iar barometrul ofertelor raportează "
                    "mediane. Pe o distribuție asimetrică la dreapta media depășește mediana, "
                    "ceea ce explică o parte din diferența dintre cele două referințe de piață "
                    "și înseamnă că multiplii calculați față de ele nu sunt direct comparabili."
                ),
                "severity": "material",
                "affects": ["teren-agricol-ins", "multiplu-piata"],
            },
        ],
    }

    out = ROOT / "data" / f"teren-agricol-ins-{latest}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = document["summary"]
    print(
        f"{latest}: preț {summary['nationalPriceRonPerHa']:,.0f} lei/ha, "
        f"arendă {summary['nationalRentRonPerHa']:,.0f} lei/ha, "
        f"randament {summary['nationalYieldPercent']:.2f}%"
    )
    print(
        f"randament regional median (2019–{latest}): arabil {middle:.2f}% (n={count}), "
        f"pășuni/fânețe {grass:.2f}% (n={grass_count})"
    )
    print(f"Wrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

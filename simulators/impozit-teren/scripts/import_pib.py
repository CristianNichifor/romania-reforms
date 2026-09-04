"""The denominator. What the economy produced, nationally and per county, year by year.

Every other number in this simulator is a stock or a levy in lei, and lei do not travel. "A
land value tax at 1% raises 34 mld lei" is a sentence nobody can weigh: it is either most of
the health budget or a rounding error, and which one it is depends entirely on how big the
economy is. Divided by GDP it becomes a share, and a share is arguable — against what other
countries raise from property, against what the local budgets already cost, against what the
same tax would have been worth ten years ago.

**Two series, because the page has two scopes.** With every county selected the denominator is
the country; with one county selected it has to be that county, or the page divides one
county's land by the whole country's output and prints a number an order of magnitude too
small. Eurostat carries both: `nama_10_gdp` for the country and `nama_10r_3gdp` at NUTS 3,
which for Romania is exactly the forty-two counties.

**Regional GDP is where output is booked, not where it is produced.** This is the reason the
county ratios need reading with care and the reason it is a limitation rather than a footnote.
A company's value added is counted where the unit that made it is registered, so București —
two per cent of the country by area — carries close to a quarter of its GDP. Its land tax over
its GDP therefore looks small, and every county whose firms are registered in the capital looks
large. The land is where it is; the accounting is not.

**Both currencies, because the rest of the simulator is bilingual in money.** The grids price
in euro and the taxes come out in lei, so the ratio has to be computable without dragging an
exchange rate through it: lei over lei, euro over euro, each pair from the same Eurostat row.

Not wired into CI. Eurostat revises national accounts on its own calendar — 2023 moved twice
while this repository was being written — so a byte diff here would fail for the one reason
that is not a regression. `import_avere_teren.py` is not in CI for the same reason. The file is
committed; re-running this is a decision somebody makes, not something a build does.

Usage:
    uv run python simulators/impozit-teren/scripts/import_pib.py
    uv run python simulators/impozit-teren/scripts/import_pib.py --from-year 2010
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"

# Where the series starts. Not the whole history Eurostat holds: the tax base on the page is
# priced from grids published in 2024, 2025 and 2026, and dividing today's land by the GDP of
# 2001 answers a question nobody asked. Ten years is enough to show the ratio falling as the
# economy grows past a stock of land that is valued once.
FROM_YEAR = 2015

# NUTS 3 is the county, one for one, so this is a translation and not a mapping. Written out
# rather than derived from the labels: Eurostat spells Brașov with a cedilla-comma that no
# normalisation in this repository agrees on, and a county silently dropped from a denominator
# is the kind of error that shows up as a plausible ratio.
NUTS3 = {
    "RO111": "BH", "RO112": "BN", "RO113": "CJ", "RO114": "MM", "RO115": "SM", "RO116": "SJ",
    "RO121": "AB", "RO122": "BV", "RO123": "CV", "RO124": "HR", "RO125": "MS", "RO126": "SB",
    "RO211": "BC", "RO212": "BT", "RO213": "IS", "RO214": "NT", "RO215": "SV", "RO216": "VS",
    "RO221": "BR", "RO222": "BZ", "RO223": "CT", "RO224": "GL", "RO225": "TL", "RO226": "VN",
    "RO311": "AG", "RO312": "CL", "RO313": "DB", "RO314": "GR", "RO315": "IL", "RO316": "PH",
    "RO317": "TR",
    "RO321": "B", "RO322": "IF",
    "RO411": "DJ", "RO412": "GJ", "RO413": "MH", "RO414": "OT", "RO415": "VL",
    "RO421": "AR", "RO422": "CS", "RO423": "HD", "RO424": "TM",
}

COUNTY_NAMES = {
    "AB": "Alba", "AG": "Argeș", "AR": "Arad", "B": "București", "BC": "Bacău", "BH": "Bihor",
    "BN": "Bistrița-Năsăud", "BR": "Brăila", "BT": "Botoșani", "BV": "Brașov", "BZ": "Buzău",
    "CJ": "Cluj", "CL": "Călărași", "CS": "Caraș-Severin", "CT": "Constanța", "CV": "Covasna",
    "DB": "Dâmbovița", "DJ": "Dolj", "GJ": "Gorj", "GL": "Galați", "GR": "Giurgiu",
    "HD": "Hunedoara", "HR": "Harghita", "IF": "Ilfov", "IL": "Ialomița", "IS": "Iași",
    "MH": "Mehedinți", "MM": "Maramureș", "MS": "Mureș", "NT": "Neamț", "OT": "Olt",
    "PH": "Prahova", "SB": "Sibiu", "SJ": "Sălaj", "SM": "Satu Mare", "SV": "Suceava",
    "TL": "Tulcea", "TM": "Timiș", "TR": "Teleorman", "VL": "Vâlcea", "VN": "Vrancea",
    "VS": "Vaslui",
}


def fetch(dataset: str, params: dict[str, str | list[str]]) -> dict:
    query = []
    for key, value in params.items():
        for item in value if isinstance(value, list) else [value]:
            query.append(f"{key}={item}")
    url = f"{API}/{dataset}?{'&'.join(query)}&format=JSON&lang=EN"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        return json.loads(response.read())


def cells(document: dict) -> list[tuple[dict, float]]:
    """A JSON-stat cube flattened to (coordinates, value). Same shape as import_avere_teren."""
    if "value" not in document:
        raise SystemExit("Eurostat returned no values; the query is wrong")
    dimensions = document["dimension"]
    names = list(dimensions.keys())
    size = document["size"]
    reverse = {
        name: {position: code for code, position in dimensions[name]["category"]["index"].items()}
        for name in names
    }
    out = []
    for flat, value in document["value"].items():
        remainder = int(flat)
        coordinates = {}
        for index, name in enumerate(names):
            stride = 1
            for later in range(index + 1, len(names)):
                stride *= size[later]
            coordinates[name] = reverse[name][remainder // stride]
            remainder %= stride
        out.append((coordinates, value))
    return out


def series(document: dict, key: str, from_year: int) -> dict[str, dict[int, float]]:
    """Eurostat's cube, folded to {geo: {year: value}} and cut at the first year worth having."""
    found: dict[str, dict[int, float]] = {}
    for coordinates, value in cells(document):
        year = int(coordinates["time"])
        if year < from_year:
            continue
        found.setdefault(coordinates[key], {})[year] = value
    return found


def paired(lei: dict[int, float], euro: dict[int, float]) -> list[dict]:
    """Only years where both currencies are published.

    A year with lei and no euro would render as a ratio in one scope of the page and a blank in
    the other, for a reason the reader has no way to see. Dropping it is the honest half.
    """
    return [
        {"year": year, "gdpMron": round(lei[year], 1), "gdpMeur": round(euro[year], 1)}
        for year in sorted(set(lei) & set(euro))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=FROM_YEAR)
    args = parser.parse_args()

    national_lei = fetch("nama_10_gdp", {"unit": "CP_MNAC", "na_item": "B1GQ", "geo": "RO"})
    national_eur = fetch("nama_10_gdp", {"unit": "CP_MEUR", "na_item": "B1GQ", "geo": "RO"})
    regional_lei = fetch("nama_10r_3gdp", {"unit": "MIO_NAC", "geo": sorted(NUTS3)})
    regional_eur = fetch("nama_10r_3gdp", {"unit": "MIO_EUR", "geo": sorted(NUTS3)})

    national = paired(
        series(national_lei, "geo", args.from_year).get("RO", {}),
        series(national_eur, "geo", args.from_year).get("RO", {}),
    )
    if not national:
        print("FATAL: no national GDP came back", file=sys.stderr)
        return 1

    by_county_lei = series(regional_lei, "geo", args.from_year)
    by_county_eur = series(regional_eur, "geo", args.from_year)
    regions = []
    for nuts, county in sorted(NUTS3.items(), key=lambda pair: pair[1]):
        rows = paired(by_county_lei.get(nuts, {}), by_county_eur.get(nuts, {}))
        if not rows:
            continue
        regions.append(
            {
                "county": county,
                "nuts3": nuts,
                "name": COUNTY_NAMES[county],
                "series": rows,
            }
        )
    # Forty-two or the county view is lying somewhere. A missing county would not fail loudly:
    # the page would fall back to the national denominator and print a ratio that is wrong by
    # a factor of thirty, with nothing on screen to say which county it happened to.
    if len(regions) != len(NUTS3):
        missing = sorted(set(NUTS3.values()) - {r["county"] for r in regions})
        print(f"FATAL: {len(missing)} counties have no GDP series: {missing}", file=sys.stderr)
        return 1

    national_latest = national[-1]["year"]
    county_latest = max(row["year"] for region in regions for row in region["series"])

    print(f"PIB România {national_latest}: {national[-1]['gdpMron'] / 1e3:,.0f} mld lei "
          f"({national[-1]['gdpMeur'] / 1e3:,.0f} mld EUR)")
    print(f"{len(regions)} județe, ultimul an regional {county_latest}")
    share = sum(
        row["gdpMron"]
        for region in regions
        for row in region["series"]
        if row["year"] == county_latest
    )
    reference = next((r["gdpMron"] for r in national if r["year"] == county_latest), None)
    if reference:
        print(f"suma județelor / PIB național în {county_latest}: {share / reference:.3f}")

    document = {
        "$schema": "../schema/pib.schema.json",
        "id": f"pib-{national_latest}",
        "title": f"Produsul intern brut, România și cele {len(regions)} de județe, "
                 f"{args.from_year}–{national_latest}",
        "publisher": "Eurostat",
        "counties": sorted(NUTS3.values()),
        "period": f"{args.from_year}-{national_latest}",
        "currency": "RON",
        "provenance": {
            "source": "eurostat-nama_10_gdp",
            "locator": (
                f"nama_10_gdp, B1GQ, unitățile CP_MNAC și CP_MEUR, geo=RO, anii "
                f"{args.from_year}–{national_latest}; pe județe din nama_10r_3gdp, unitățile "
                f"MIO_NAC și MIO_EUR, cele {len(regions)} regiuni NUTS 3 ale României"
            ),
            "confidence": "verbatim",
            "note": (
                "Sumele sunt preluate ca atare, în milioane, în unitatea în care le publică "
                "Eurostat. Nu se calculează nimic aici: raportul dintre impozit și PIB se face "
                "în pagină, pe anul ales de cititor."
            ),
        },
        "assumptions": {
            "fromYear": args.from_year,
            "nationalLatestYear": national_latest,
            "countyLatestYear": county_latest,
            "note": (
                "PIB-ul județean se publică cu un an întârziere față de cel național, deci "
                "ultimul an nu este același în cele două serii."
            ),
        },
        "summary": {
            "years": len(national),
            "counties": len(regions),
        },
        "series": national,
        "regions": regions,
        "limitations": [
            {
                "id": "pib-judetean-e-unde-se-inregistreaza",
                "text": (
                    "PIB-ul județean măsoară unde este înregistrată unitatea care produce "
                    "valoarea adăugată, nu unde stă pământul. Bucureștiul, 0,2% din suprafața "
                    "țării, adună aproape un sfert din PIB pentru că acolo își au sediul "
                    "firmele care lucrează în tot restul țării. Raportul impozit/PIB iese deci "
                    "mic în București și mare în județele ai căror agenți economici sunt "
                    "înregistrați în capitală. Comparațiile între județe se citesc cu asta în "
                    "minte; cea națională nu e afectată."
                ),
                "severity": "material",
                "affects": ["pib", "impozit-teren"],
            },
            {
                "id": "baza-e-din-grila-de-azi-numitorul-e-anul-ales",
                "text": (
                    "Terenul este prețuit din grila notarială în vigoare, o singură ediție. "
                    "Schimbarea anului PIB mută numitorul, nu și valoarea pământului: "
                    "„1,4% din PIB-ul lui 2015” înseamnă cât ar fi cântărit în economia de "
                    "atunci un impozit pe terenul de azi, nu cât ar fi adus în 2015."
                ),
                "severity": "material",
                "affects": ["pib", "impozit-teren"],
            },
            {
                "id": "pib-judetean-ramane-in-urma",
                "text": (
                    "Seria pe județe se oprește cu un an înaintea celei naționale. Pentru "
                    "ultimul an există numitor național, dar nu și județean."
                ),
                "severity": "note",
                "affects": ["pib"],
            },
            {
                "id": "conturile-nationale-se-revizuiesc",
                "text": (
                    "Conturile naționale se revizuiesc după publicare, iar anii recenți se "
                    "schimbă cu câteva zecimi la fiecare rundă. Fișierul este o fotografie a "
                    "seriei la data extragerii, nu o serie definitivă — de aceea importul "
                    "acesta nu este verificat prin diff în CI, cum nu este nici cel al "
                    "conturilor de avere."
                ),
                "severity": "note",
                "affects": ["pib"],
            },
        ],
    }

    out = ROOT / "data" / f"pib-{national_latest}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

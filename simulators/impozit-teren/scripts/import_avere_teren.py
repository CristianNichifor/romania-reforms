"""What other countries say their land is worth, so this one's total can be checked.

The headline here — every hectare in Romania, priced from the notaries' grids — has never had
anything to sit beside it. "Is 324 mld EUR plausible?" was a question the repository could not
answer, and the honest reflex is to assume a number built from administrative minima must be
too low. This file exists to test that reflex rather than repeat it.

**ESA 2010 makes land a balance-sheet item.** `nama_10_nfa_bs` carries asset `AN.211 Land` at
current replacement cost, and a handful of member states compile it. Divided by GDP it becomes
a ratio that survives the difference between a French hectare and a Slovak one, and that is the
only form in which the comparison means anything.

**Two things make this a weak instrument, and both are reported rather than smoothed over.**

* **Nine countries.** Land is optional in the ESA transmission programme and most members skip
  it — Romania included, which is why this is a benchmark and not a source. Nine is a median
  computed on nine numbers.
* **The peer group decides the answer.** Western Europe sits near 1,6–3,0× GDP and the
  post-2004 members near 0,9–1,2×, so "the EU median" can be made to imply anything between
  310 and 520 mld EUR for Romania. Both groups are therefore published, split on EU accession
  rather than on anything chosen after seeing the result, and neither is called the answer.

**Sector matters and is easy to get wrong.** `S14_S15` is households only and is what most
countries report; `S1` is the whole economy and is the only basis comparable with a total that
counts state forest and company land. This file reads `S1`. An earlier pass of this comparison
used the household series, found Romania's dwellings stock anomalously small relative to GDP
(0,31 against a 1,33 EU average, alongside Poland's 0,29), and would have drawn a confident
conclusion from what is really a compilation difference in a *different* asset.

Usage:
    uv run python simulators/impozit-teren/scripts/import_avere_teren.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor/romania-reforms)"
YEAR = 2023

# Split on EU accession, decided before the numbers were seen. Any grouping drawn after
# looking at the ratios would be a grouping chosen to produce a conclusion.
JOINED_2004_OR_LATER = {"BG", "CY", "CZ", "EE", "HR", "HU", "LT", "LV", "MT", "PL", "RO", "SI", "SK"}
AGGREGATES = {"EU27_2020", "EA19", "EA20", "EA21", "EU28"}


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
    """A JSON-stat cube flattened to (coordinates, value), which is the only shape worth having."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=YEAR)
    args = parser.parse_args()
    year = str(args.year)

    land = fetch(
        "nama_10_nfa_bs",
        {"unit": "CP_MEUR", "sector": "S1", "asset10": "N211N", "time": year},
    )
    gdp = fetch("nama_10_gdp", {"unit": "CP_MEUR", "na_item": "B1GQ", "time": year})

    product = {c["geo"]: v for c, v in cells(gdp) if c["geo"] not in AGGREGATES}
    rows = []
    for coordinates, value in cells(land):
        geo = coordinates["geo"]
        if geo in AGGREGATES or geo not in product or not product[geo]:
            continue
        rows.append(
            {
                "geo": geo,
                "landMeur": round(value, 1),
                "gdpMeur": round(product[geo], 1),
                "landOverGdp": round(value / product[geo], 4),
                "group": "est" if geo in JOINED_2004_OR_LATER else "vest",
            }
        )
    rows.sort(key=lambda row: -row["landOverGdp"])
    if len(rows) < 5:
        print(f"FATAL: only {len(rows)} countries report land for {year}", file=sys.stderr)
        return 1

    romania_gdp = product.get("RO")
    if not romania_gdp:
        print("FATAL: no Romanian GDP for the benchmark year", file=sys.stderr)
        return 1

    def summarise(group: str | None) -> dict:
        chosen = [r["landOverGdp"] for r in rows if group is None or r["group"] == group]
        if not chosen:
            return {}
        median = statistics.median(chosen)
        return {
            "countries": len(chosen),
            "medianLandOverGdp": round(median, 4),
            "impliedRomaniaEur": round(median * romania_gdp * 1e6),
        }

    groups = {"toate": summarise(None), "est": summarise("est"), "vest": summarise("vest")}
    for name, found in groups.items():
        if found:
            print(
                f"{name:6} {found['countries']:2} țări, mediana {found['medianLandOverGdp']:.2f}× PIB"
                f" → {found['impliedRomaniaEur'] / 1e9:6.0f} mld EUR pentru România"
            )
    print(f"\nPIB România {year}: {romania_gdp / 1000:,.0f} mld EUR")

    document = {
        "$schema": "../schema/avere-teren.schema.json",
        "id": f"avere-teren-{year}",
        "title": f"Valoarea terenului în conturile naționale, pe țări, {year}",
        "publisher": "Eurostat",
        "counties": ["RO"],
        "period": year,
        "currency": "EUR",
        "provenance": {
            "source": "eurostat-nama_10_nfa_bs",
            "locator": (
                f"nama_10_nfa_bs, activ AN.211 „Land”, sector S1 (toată economia), "
                f"unit CP_MEUR, anul {year}; PIB din nama_10_gdp, B1GQ"
            ),
            "confidence": "verbatim",
            "note": (
                "Sumele sunt preluate ca atare din conturile naționale. Raportul la PIB este "
                "calculat aici. Sectorul S1 este toată economia, singura bază comparabilă cu un "
                "total care cuprinde și pădurea statului și terenul firmelor; seria pe "
                "gospodării (S14_S15) acoperă mai multe țări, dar nu același lucru."
            ),
        },
        "assumptions": {
            "benchmarkYear": year,
            "romaniaGdpEur": round(romania_gdp * 1e6),
            "grouping": "aderare la UE: „est” = 2004 sau mai târziu, „vest” = înainte",
        },
        "summary": {
            "countries": len(rows),
            "groups": groups,
        },
        "localities": rows,
        "limitations": [
            {
                "id": "noua-tari-nu-sunt-o-distributie",
                "text": (
                    f"Doar {len(rows)} țări compilează valoarea terenului în conturile "
                    "naționale — activul este opțional în programul de transmisie ESA, iar "
                    "România nu îl raportează deloc. O mediană pe atâtea observații este un "
                    "reper, nu o distribuție, și nu suportă un interval de încredere."
                ),
                "severity": "blocking",
                "affects": ["avere-teren", "valoare-nationala"],
            },
            {
                "id": "grupul-de-comparatie-decide-raspunsul",
                "text": (
                    "Europa de Vest stă la 1,6–3,0× PIB, iar statele intrate în UE după 2004 "
                    "la 0,9–1,2×. „Mediana europeană” poate deci să însemne pentru România "
                    "orice între 310 și 520 mld EUR. Ambele grupuri sunt publicate, împărțite "
                    "după anul aderării — un criteriu ales înainte de a vedea cifrele — și "
                    "niciunul nu este numit răspunsul."
                ),
                "severity": "blocking",
                "affects": ["avere-teren", "valoare-nationala"],
            },
            {
                "id": "conturile-nationale-evalueaza-altfel",
                "text": (
                    "Conturile naționale evaluează terenul la prețul curent de înlocuire, "
                    "estimat de fiecare institut de statistică cu metoda lui — de regulă "
                    "valoarea proprietății minus costul de reconstrucție a clădirii. Nu este "
                    "aceeași operațiune cu înmulțirea hectarelor cu un preț publicat pe "
                    "localitate, deci reperul spune dacă ordinul de mărime e credibil, nu dacă "
                    "cifra e corectă."
                ),
                "severity": "material",
                "affects": ["valoare-nationala"],
            },
        ],
    }

    out = ROOT / "data" / f"avere-teren-{year}.json"
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

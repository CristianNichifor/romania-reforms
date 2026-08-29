"""Import the fiscal series the pay law is denominated in.

    uv run --with requests python scripts/import_fiscal.py

Several articles of the draft cannot be evaluated without external fiscal data:

  Art. 9(4)   the reference value may not rise faster than nominal GDP
  Art. 36(3)  from 2028 the uplift is set by a target to cut the public wage bill
              by at least 1.5 percentage points of GDP between 2024 and 2031

Those are the two this script serves. Eurostat is used rather than the Ministry of
Finance portal because it publishes a stable machine-readable API, applies one
methodology (ESA 2010) across countries, and covers Denmark on the same basis — which
is what makes a Romania/Denmark comparison of *ratios* legitimate while a comparison
of levels would not be.

What Eurostat cannot give us is per-ordonator detail. The Article 21(2) ceiling is
measured per ordonator principal de credite, per funding source, and no open dataset
publishes personnel spend at that granularity. That gap is recorded in the output.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/fiscal/eurostat-compensation-2026-08.json"

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
GEOS = ["RO", "DK"]
YEARS = [str(y) for y in range(2015, 2025)]

# COFOG functions that map onto the draft's occupational families. The mapping is
# approximate and is declared as such in the output: COFOG classifies spending by
# purpose, the annexes classify posts by employer, and the two do not align exactly.
COFOG = {
    "TOTAL": ("Total", None),
    "GF01": ("General public services", "VIII-administratie"),
    "GF02": ("Defence", "VI-aparare-ordine-securitate"),
    "GF03": ("Public order and safety", "VI-aparare-ordine-securitate"),
    "GF07": ("Health", "II-sanatate-asistenta-sociala"),
    "GF09": ("Education", "I-invatamant"),
    "GF10": ("Social protection", "II-sanatate-asistenta-sociala"),
}


def fetch(dataset: str, **params) -> dict:
    pairs: list[tuple[str, str]] = [("format", "JSON")]
    for key, value in params.items():
        for item in value if isinstance(value, list) else [value]:
            pairs.append((key, item))
    url = f"{API}/{dataset}?{urllib.parse.urlencode(pairs)}"
    with urllib.request.urlopen(url, timeout=90) as response:  # noqa: S310
        return json.loads(response.read())


def unflatten(payload: dict) -> list[dict]:
    """JSON-stat stores one flat index. Expand it back into labelled records."""
    order, size = payload["id"], payload["size"]
    reverse = {
        key: {v: k for k, v in payload["dimension"][key]["category"]["index"].items()}
        for key in order
    }
    records = []
    for flat, value in payload["value"].items():
        n, coords = int(flat), []
        for dim_size in reversed(size):
            coords.append(n % dim_size)
            n //= dim_size
        coords.reverse()
        record = {key: reverse[key][coords[i]] for i, key in enumerate(order)}
        record["value"] = value
        records.append(record)
    return records


def series_from(records, geo, selector, series_id, label, unit, dims, locator):
    observations = sorted(
        (
            {"period": r["time"], "value": r["value"]}
            for r in records
            if r["geo"] == geo and selector(r)
        ),
        key=lambda o: o["period"],
    )
    return {
        "id": series_id,
        "label": label,
        "geo": geo,
        "unit": unit,
        "dims": dims,
        "observations": observations,
        "provenance": {
            "source": "eurostat",
            "locator": locator,
            "confidence": "verbatim",
        },
    }


def main() -> None:
    print("fetching gov_10a_exp (compensation of employees) ...")
    exp = unflatten(
        fetch(
            "gov_10a_exp",
            geo=GEOS,
            na_item="D1",
            sector="S13",
            unit="PC_GDP",
            cofog99=list(COFOG),
            time=YEARS,
        )
    )

    print("fetching gov_10a_exp in national currency (the envelope baseline) ...")
    # Percentages of GDP make the structural point; envelope mode needs the money itself,
    # and needs it split the same way, so the two views cannot drift apart.
    cash = unflatten(
        fetch("gov_10a_exp", geo=GEOS, na_item="D1", sector="S13", unit="MIO_NAC",
              cofog99=list(COFOG), time=YEARS)
    )

    print("fetching nama_10_gdp (nominal GDP, national currency) ...")
    gdp = unflatten(
        fetch("nama_10_gdp", geo=GEOS, na_item="B1GQ", unit="CP_MNAC", time=YEARS)
    )

    series = []
    for geo in GEOS:
        for code, (name, family) in COFOG.items():
            dims = {"sector": "S13", "naItem": "D1", "cofog": code}
            if family:
                dims["family"] = family
            entry = series_from(
                exp,
                geo,
                lambda r, c=code: r["cofog99"] == c,
                f"d1-{code.lower()}-pc-gdp-{geo.lower()}",
                f"Compensation of employees, general government, {name} ({geo})",
                "PC_GDP",
                dims,
                f"Eurostat gov_10a_exp, S13/D1/{code}/PC_GDP, geo={geo}",
            )
            if entry["observations"]:
                series.append(entry)

        for code, (name, family) in COFOG.items():
            dims = {"sector": "S13", "naItem": "D1", "cofog": code, "measure": "cash"}
            if family:
                dims["family"] = family
            entry = series_from(
                cash, geo, lambda r, c=code: r["cofog99"] == c,
                f"d1-{code.lower()}-mnac-{geo.lower()}",
                f"Cheltuiala de personal, {name}, milioane monedă națională ({geo})",
                "CP_MNAC", dims,
                f"Eurostat gov_10a_exp, S13/D1/{code}/MIO_NAC, geo={geo}",
            )
            if entry["observations"]:
                series.append(entry)

        entry = series_from(
            gdp,
            geo,
            lambda r: True,
            f"gdp-nominal-{geo.lower()}",
            f"Gross domestic product at current prices, national currency ({geo})",
            "CP_MNAC",
            {"naItem": "B1GQ"},
            f"Eurostat nama_10_gdp, B1GQ/CP_MNAC, geo={geo}",
        )
        if entry["observations"]:
            series.append(entry)

    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "eurostat-compensation-2026-08",
        "title": "Public-sector compensation of employees and nominal GDP, Romania and Denmark",
        "publisher": "Eurostat",
        "methodology": "ESA 2010",
        "retrieved": date.today().isoformat(),
        "query": {
            "endpoint": API,
            "datasets": ["gov_10a_exp", "nama_10_gdp"],
            "geo": GEOS,
            "time": [YEARS[0], YEARS[-1]],
            "note": "Re-run scripts/import_fiscal.py to refresh. Eurostat revises back series, so the retrieved date is part of the identity of this document.",
        },
        "provenance": {
            "source": "eurostat",
            "locator": "gov_10a_exp and nama_10_gdp, retrieved via the dissemination API",
            "confidence": "verbatim",
        },
        "series": series,
        "limitations": [
            {
                "id": "cofog-nu-e-familie-ocupationala",
                "text": "COFOG clasifica cheltuiala dupa scop, iar anexele legii clasifica posturile dupa angajator. Corespondenta functie COFOG -> familie ocupationala din campul dims.family este orientativa, nu o echivalenta. Invatamantul privat finantat public intra la GF09 fara sa fie personal bugetar, iar personalul administrativ al unui spital intra la GF07 desi e salarizat pe Anexa VIII.",
                "affects": ["aggregate"],
                "severity": "material",
            },
            {
                "id": "granularitate-lipsa-pe-ordonator",
                "text": "Eurostat nu coboara sub nivelul functiei COFOG, deci acest document nu poate spune nimic despre plafonul de 20%, care se masoara pe ordonator principal de credite si pe sursa de finantare. Granularitatea aceea exista insa in alta parte: executiile bugetare pe entitate raportoare, in data/fiscal/plafon-sporuri.json. Limitarea priveste acest set de date, nu intrebarea.",
                "affects": ["capUtilisation", "aggregate"],
                "severity": "note",
            },
            {
                "id": "comparabilitate-institutionala",
                "text": "Ponderile pe functii nu sunt direct comparabile intre tari pentru ca granitele institutionale difera. 'Ordine publica si siguranta' include in Romania jandarmeria, politia locala si sistemul penitenciar; protectia sociala e in Danemarca preponderent municipala si prestata de personal angajat public, in Romania in mare parte transferuri banesti. Diferentele de pondere descriu structuri diferite ale statului, nu neaparat niveluri diferite de salarizare.",
                "affects": ["structure", "aggregate"],
                "severity": "material",
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(series)} series")
    # Two TOTAL series exist per country - a share of GDP and the cash bill - and keying
    # only on geo kept whichever came last, printing millions of lei labelled "% of GDP".
    total = {
        s["geo"]: s
        for s in series
        if s["dims"].get("cofog") == "TOTAL" and s["unit"] == "PC_GDP"
    }
    for geo, entry in sorted(total.items()):
        last = entry["observations"][-1]
        print(f"  {geo} compensation of employees {last['period']}: {last['value']}% of GDP")


if __name__ == "__main__":
    main()

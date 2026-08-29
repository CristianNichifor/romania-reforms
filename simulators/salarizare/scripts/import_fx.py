"""Import ECB reference exchange rates, so cross-currency comparison has a citable rate.

    uv run python scripts/import_fx.py

Writes data/fiscal/ecb-fx.json.

The rate is stored, dated and sourced rather than written into the app as a constant.
Anyone disputing a converted figure can see which day's rate produced it and re-run this
to get another.

A market rate is not purchasing power. Converting a Danish salary into lei at 0,70 says
what it would buy *in Romania* only if Danish and Romanian prices were the same, and they
are not. The conversion answers "how large is this number in a unit I know", which is a
fair question; it does not answer "is this person better off", which needs price levels.
That distinction is carried in the document's limitations so the UI can print it beside
every converted figure.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/fiscal/ecb-fx.json"

API = "https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A"
CURRENCIES = ["DKK", "RON"]


def latest(currency: str) -> tuple[str, float]:
    url = f"{API.format(cur=currency)}?lastNObservations=1&format=csvdata"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        rows = list(csv.DictReader(io.StringIO(response.read().decode())))
    if not rows:
        raise SystemExit(f"no observation returned for {currency}")
    row = rows[-1]
    return row["TIME_PERIOD"], float(row["OBS_VALUE"])


def main() -> None:
    rates: dict[str, tuple[str, float]] = {}
    for currency in CURRENCIES:
        period, value = latest(currency)
        rates[currency] = (period, value)
        print(f"EUR/{currency} = {value} ({period})")

    # Both legs are quoted against the euro, so the cross rate is one divided by the
    # other. Deriving it here rather than in the app keeps a single definition.
    dkk_period, dkk = rates["DKK"]
    ron_period, ron = rates["RON"]
    cross = ron / dkk
    print(f"1 DKK = {cross:.6f} RON")

    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "ecb-fx",
        "title": "Cursuri de referință BCE",
        "publisher": "Banca Centrală Europeană",
        "methodology": "ECB reference exchange rates, 14:15 CET",
        "retrieved": max(dkk_period, ron_period),
        "query": {
            "endpoint": API.format(cur="<currency>"),
            "series": [f"D.{c}.EUR.SP00.A" for c in CURRENCIES],
            "note": "Re-run scripts/import_fx.py to refresh.",
        },
        "provenance": {
            "source": "ecb-exr",
            "locator": "ECB Data Portal, dataset EXR, daily reference rates",
            "confidence": "verbatim",
        },
        "series": [
            {
                "id": "eur-dkk",
                "label": "Coroane daneze pentru un euro",
                "geo": "DK",
                "unit": "RATE",
                "dims": {"base": "EUR", "quote": "DKK"},
                "observations": [{"period": dkk_period, "value": dkk}],
                "provenance": {"source": "ecb-exr", "locator": "EXR.D.DKK.EUR.SP00.A", "confidence": "verbatim"},
            },
            {
                "id": "eur-ron",
                "label": "Lei pentru un euro",
                "geo": "RO",
                "unit": "RATE",
                "dims": {"base": "EUR", "quote": "RON"},
                "observations": [{"period": ron_period, "value": ron}],
                "provenance": {"source": "ecb-exr", "locator": "EXR.D.RON.EUR.SP00.A", "confidence": "verbatim"},
            },
            {
                "id": "dkk-ron",
                "label": "Lei pentru o coroană daneză",
                "geo": "RO",
                "unit": "RATE",
                "dims": {"base": "DKK", "quote": "RON"},
                "observations": [{"period": max(dkk_period, ron_period), "value": round(cross, 6)}],
                "provenance": {
                    "source": "ecb-exr",
                    "locator": "EXR.D.RON.EUR.SP00.A ÷ EXR.D.DKK.EUR.SP00.A",
                    "confidence": "derived",
                    "note": "Ambele cotate față de euro, deci cursul încrucișat este raportul lor.",
                },
            },
        ],
        "limitations": [
            {
                "id": "curs-nu-e-putere-de-cumparare",
                "text": "Cursul de schimb spune cât de mare este un număr într-o monedă cunoscută, nu cât cumpără. Un salariu danez convertit în lei la 0,70 ar cumpăra în România cât arată cifra doar dacă prețurile ar fi identice în cele două țări, ceea ce nu e cazul. Pentru „o duce mai bine?” e nevoie de paritatea puterii de cumpărare, care este o altă serie și o altă întrebare.",
                "affects": ["gross", "net", "aggregate"],
                "severity": "material",
            },
            {
                "id": "curs-de-o-zi",
                "text": "Este cursul de referință al unei singure zile. Coroana daneză este legată de euro într-o bandă îngustă, deci raportul DKK/RON se mișcă practic doar cât se mișcă leul față de euro — dar se mișcă.",
                "affects": ["gross", "net"],
                "severity": "note",
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

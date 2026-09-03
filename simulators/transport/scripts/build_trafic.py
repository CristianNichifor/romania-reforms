"""Traffic volumes on Romania's busiest roads, and what 2+1 would cost on them.

Every other question in this repository could be answered from OpenStreetMap. This one could
not: OSM has no traffic volumes, and without them "which sectors deserve a third lane" is a
question you can only answer by asserting an answer. CNAIR's *recensământ general de
circulație* is the natural source and is not published as data — the 2020 round was postponed
to 2022 by the pandemic, and the next one started in April 2026 and runs to November.

The way in is the Environmental Noise Directive. Article 7 of 2002/49/EC obliges member states
to map noise along every road carrying **more than three million vehicles a year**, and to
report the geometry with its traffic flow attached. Romania's return is published as open data
by the Ministry of Environment, and `annualTrafficFlow` on each section is exactly the number
CNAIR's census would have given — obtained because a noise directive forced its publication.

**What that inclusion rule means for this model.** Three million vehicles a year is an AADT of
8 219, so the dataset is the busy end of the network by construction: 299 sections, 3 941 km,
none below 8 245 vehicles a day. It cannot say anything about a quiet DN, and it does not need
to — a road nobody drives on does not need a third lane. What it does mean is that every count
here is the number of kilometres **among the busy ones**, never a national total.

**Why 2+1 rather than a motorway.** A 2+1 road gives each direction an overtaking lane in
alternation behind a central barrier, and reaches close to motorway safety at a fraction of
the cost. Romania has essentially none, so there is no Romanian price to read: the anchors are
Irish, which is legitimate here for the same reason Danish bus practice is legitimate
elsewhere in this repository — the network being priced does not exist yet, so a domestic
operating figure for it cannot exist either.

Output:
    data/trafic.json     AADT distribution, 2+1 candidate kilometres by band, and cost

Usage:
    uv run python -m scripts.build_trafic            # from the cached download
    uv run python -m scripts.build_trafic --refetch  # pull the GeoPackage again
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "trafic.json"
INPUTS = ROOT / "data" / "trafic-inputs.json"
CACHE = ROOT / "data" / "reports" / "major-roads.gpkg"

SOURCE_URL: Final[str] = (
    "https://data.gov.ro/dataset/03731237-07c7-4b83-a968-4a32f9758114/resource/"
    "30f7eb95-a89c-4a5d-8490-90bb9fe8165e/download/majorroadsource299_outsideagg.gpkg"
)
SOURCE_TITLE: Final[str] = (
    "Drumurile principale din România din afara aglomerărilor (art. 7, Directiva 2002/49/CE), "
    "Ministerul Mediului, Apelor și Pădurilor, versiune 2024, publicat pe data.gov.ro"
)
LAYER: Final[str] = "MajorRoadSource"
DAYS: Final[int] = 365

# A motorway already has the lanes. Sections whose code starts with A are excluded from the
# 2+1 programme rather than filtered out of the traffic picture, because their volumes are
# what make the case for the roads feeding them.
MOTORWAY_PREFIX: Final[str] = "A"


def fetch(path: Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
        path.write_bytes(response.read())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refetch", action="store_true", help="download the GeoPackage again")
    args = parser.parse_args(argv)

    if args.refetch or not CACHE.exists():
        if not args.refetch and not CACHE.exists():
            print(f"  not cached; run with --refetch to download {SOURCE_URL}", file=sys.stderr)
            return 1
        print("  downloading the major-roads GeoPackage...")
        fetch()

    import geopandas as gpd
    import numpy as np

    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))["items"]
    bands = json.loads(INPUTS.read_text(encoding="utf-8"))["bands"]
    ron_per_eur = inputs["ronPerEur"]["value"]
    widen_eur = inputs["twoPlusOneWidenEurPerKm"]["value"]
    upgrade_eur = inputs["twoPlusOneUpgradeEurPerKm"]["value"]

    roads = gpd.read_file(CACHE, layer=LAYER, engine="pyogrio")
    roads["aadt"] = roads["annualTrafficFlow"] / DAYS
    roads["km"] = roads["length"] / 1000.0
    roads["isMotorway"] = roads["roadNationalCode"].str.startswith(MOTORWAY_PREFIX)

    total_km = float(roads["km"].sum())
    weighted = float((roads["aadt"] * roads["km"]).sum() / total_km)
    print(f"  {len(roads)} sections, {total_km:,.0f} km, km-weighted AADT {weighted:,.0f}")

    national = roads[~roads["isMotorway"]]
    by_band = {}
    for band in bands:
        low, high = band["from"], band.get("to")
        selected = national[
            (national["aadt"] >= low) & ((high is None) | (national["aadt"] < (high or np.inf)))
        ]
        km = float(selected["km"].sum())
        by_band[band["id"]] = {
            "fromAadt": low,
            "toAadt": high,
            "sections": int(len(selected)),
            "km": round(km, 1),
            "verdict": band["verdict"],
            "costRon": round(km * widen_eur * ron_per_eur) if band["twoPlusOne"] else None,
        }
        print(
            f"  {band['id']:<12} AADT {low:>6,}{'+' if high is None else f'-{high:,}':>8}  "
            f"{len(selected):>3} sections  {km:>7,.1f} km  {band['verdict']}"
        )

    programme_km = sum(t["km"] for t in by_band.values() if t["costRon"] is not None)
    programme_ron = sum(t["costRon"] or 0 for t in by_band.values())

    document = {
        "$schema": "../schema/trafic.schema.json",
        "id": "trafic",
        "title": "Traficul pe drumurile principale, și unde ar merita banda a treia",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "end-major-roads-2024",
            "locator": SOURCE_TITLE,
            "confidence": "verbatim",
            "note": (
                "Fluxul anual de vehicule este citit din câmpul annualTrafficFlow al fiecărei "
                "secțiuni, așa cum a fost raportat de România sub Directiva 2002/49/CE. MZA "
                "este acel flux împărțit la 365."
            ),
        },
        "source": {"url": SOURCE_URL, "layer": LAYER, "title": SOURCE_TITLE},
        "network": {
            "sections": int(len(roads)),
            "km": round(total_km, 1),
            "minAadt": int(roads["aadt"].min()),
            "medianAadt": int(roads["aadt"].median()),
            "p90Aadt": int(roads["aadt"].quantile(0.9)),
            "maxAadt": int(roads["aadt"].max()),
            "kmWeightedAadt": int(weighted),
            "motorwayKm": round(float(roads.loc[roads["isMotorway"], "km"].sum()), 1),
        },
        "byBand": by_band,
        "programme": {
            "km": round(programme_km, 1),
            "costRon": programme_ron,
            "costEur": round(programme_ron / ron_per_eur),
            "eurPerKm": widen_eur,
            "upgradeOnlyEurPerKm": upgrade_eur,
        },
        "limitations": [
            {
                "id": "doar-drumurile-aglomerate",
                "text": (
                    "Setul conține DOAR drumurile care depășesc trei milioane de vehicule pe "
                    f"an, adică o MZA de 8.219 — pragul din articolul 7 al directivei. Sunt "
                    f"{len(roads)} de secțiuni și {total_km:,.0f} km, iar cea mai puțin "
                    f"circulată are {int(roads['aadt'].min()):,} de vehicule pe zi. Deci orice "
                    "cifră de aici este „dintre drumurile aglomerate”, niciodată un total "
                    "național. Pentru banda a treia asta nu deranjează — un drum pe care nu "
                    "circulă nimeni nu are nevoie de ea — dar pentru orice altceva, da."
                ).replace(",", "."),
                "severity": "material",
                "affects": ["trafic"],
            },
            {
                "id": "pretul-benzii-a-treia-e-strain",
                "text": (
                    "România nu are practic drumuri 2+1, deci nu există preț românesc de citit. "
                    "Reperele sunt irlandeze: circa 4,1 milioane de euro pe kilometru pentru un "
                    "drum 2+1 construit de la zero și până la 400.000 de euro pe kilometru "
                    "pentru transformarea unui drum destul de lat. Drumurile naționale "
                    "românești au de regulă 7 metri, prea puțin pentru a doua variantă fără "
                    "lărgire, așa că modelul folosește o valoare intermediară, presupusă. Este "
                    "cel mai slab element al acestui calcul. Folosirea unui reper străin este "
                    "însă corectă aici din același motiv pentru care se folosesc cifre daneze "
                    "la autobuze: rețeaua evaluată nu există încă, deci o cifră românească de "
                    "exploatare pentru ea nu poate exista."
                ),
                "severity": "material",
                "affects": ["trafic"],
            },
            {
                "id": "mza-nu-spune-varful",
                "text": (
                    "Media zilnică anuală ascunde vârful. Un drum cu MZA de 12.000 uniform și "
                    "unul cu 12.000 concentrat în două ore de vineri seara cer lucruri "
                    "diferite, iar al doilea este cazul obișnuit pe drumurile de ieșire din "
                    "orașe. Datele raportate sub directivă nu conțin distribuția orară, deci "
                    "clasificarea de aici este pe medie."
                ),
                "severity": "material",
                "affects": ["trafic"],
            },
            {
                "id": "sectiunile-nu-sunt-legate-de-model",
                "text": (
                    "Secțiunile sunt geometrii proprii, în EPSG:3035, nelegate încă de graful "
                    "rutier al acestui simulator. Deci traficul nu ponderează încă beneficiul "
                    "centurilor din data/ocoliri.json — care rămâne calculat pe perechi de "
                    "reședințe, nu pe vehicule. Legătura este următorul pas și este ceea ce ar "
                    "transforma ambele modele dintr-o listă de costuri într-o comparație de "
                    "rentabilitate."
                ),
                "severity": "blocking",
                "affects": ["trafic", "ocoliri"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"\n2+1 programme: {programme_km:,.0f} km, {programme_ron / 1e9:.1f} md lei "
        f"({programme_ron / ron_per_eur / 1e9:.1f} md euro)"
    )
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The signed speed limit of every intercity road, as map geometry.

`measure_limits.py` reduces Romania's `maxspeed` tags to eight numbers — one per road class —
and those numbers drive the whole speed model. This exports the same measurement *unreduced*,
so a reader can see where the limits actually are instead of taking the averages on trust.

It should make the model's central finding visible rather than merely stated: below motorway
the open-road limit is essentially the national 90 on every class, and what separates a trunk
road from a communal one is how much of its length drops to 50 inside a village. On the map
that is a 90 threading into 50 at every settlement, over and over, the length of the country.

**Untagged is a band, never a default.** Between a quarter and a half of the classes here carry
no `maxspeed` in OSM — 26% of secondary, 44% of tertiary. Those roads still have a legal limit;
what is missing is a mapper's record of it. Painting them at an assumed 90 would manufacture
exactly the fact the layer exists to show, so they are drawn in their own neutral colour and
the legend says what that colour means.

**What this is a map of.** OSM tags, not the Romanian road code. A tag can be wrong, stale, or
absent, and `RO:urban` and friends are treated as untagged rather than resolved to a number —
the same rule `measure_limits.py` applies, and for the same reason: resolving them would be
assuming the thing being measured. The parser is imported from that module rather than
reimplemented, so the map and the model can never disagree about what a tag means.

**Dissolved by value, not kept per way.** Every segment sharing a limit becomes one geometry,
which is what makes a national layer small enough to ship — a dozen features instead of three
hundred thousand. Nothing downstream needs a way's identity; this layer is drawn, not routed.

Output:
    data/road-speeds.geojson   one feature per signed value, plus one for untagged (kmh -1)
    data/road-speeds.json      km per band, provenance, limitations

Usage:
    uv run python -m scripts.export_speed_limits
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PBF = ADMINISTRATIV / "data" / "raw" / "romania-latest.osm.pbf"
GEOJSON_OUT = ROOT / "data" / "road-speeds.geojson"
SUMMARY_OUT = ROOT / "data" / "road-speeds.json"

# The intercity network. Residential and unclassified are left out deliberately: together they
# are 112 000 km at 38-41% coverage, they would triple the file, and they are streets rather
# than roads between places — the thing this simulator routes buses over stops at tertiary.
CLASSES: Final[tuple[str, ...]] = ("motorway", "trunk", "primary", "secondary", "tertiary")

# Matches administrativ's county-roads layer, which draws the same classes. A speed layer that
# generalised differently from the road layer beneath it would show limits sliding off their
# own roads at every bend.
SIMPLIFY_M: Final[float] = 150.0

CRS_WGS84: Final[str] = "EPSG:4326"
CRS_STEREO70: Final[str] = "EPSG:3844"

# Four decimals is about 11 m of latitude and 8 m of longitude at 45°N — an order of magnitude
# finer than the 150 m simplification above, so it costs no visible accuracy and takes roughly
# a fifth off the file. Five decimals would be storing precision the geometry does not have.
COORD_DECIMALS: Final[int] = 4

UNTAGGED: Final[str] = "untagged"


def round_coords(value):
    """Round a nested coordinate structure in place-ish, without importing administrativ."""
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (int, float)):
            return [round(float(v), COORD_DECIMALS) for v in value]
        return [round_coords(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    if not PBF.exists():
        print(
            f"Missing {PBF}.\nRun administrativ's fetch with --with-roads first.",
            file=sys.stderr,
        )
        return 1

    import geopandas as gpd

    from scripts.measure_limits import parse_maxspeed

    selector = ",".join(f"'{c}'" for c in CLASSES)
    print(f"Reading {', '.join(CLASSES)} from {PBF.name}...")
    roads = gpd.read_file(
        PBF,
        layer="lines",
        columns=["highway", "other_tags"],
        where=f"highway IN ({selector})",
        engine="pyogrio",
    )
    if roads.crs is None:
        roads = roads.set_crs(CRS_WGS84)
    roads = roads.to_crs(CRS_STEREO70)
    print(f"  {len(roads):,} ways")

    limits = np.array([parse_maxspeed(t) for t in roads["other_tags"]])
    # `maxspeed=0` is a broken tag, not a road nobody may drive on. Left in, it would paint
    # itself as the slowest band on the map — a lie in the most visible direction — so it
    # joins the untagged, which is what it actually is.
    limits[limits <= 0] = float("nan")
    # A float NaN cannot be a dissolve key, and rounding keeps 89,9 from becoming its own
    # band; the signed values in Romania are all multiples of ten anyway.
    roads["band"] = [UNTAGGED if math.isnan(v) else str(int(round(v))) for v in limits]

    lengths_km = roads.geometry.length / 1000.0
    by_band = (
        lengths_km.groupby(roads["band"]).sum().sort_values(ascending=False).round(1).to_dict()
    )

    print("Dissolving by signed value...")
    dissolved = roads[["band", "geometry"]].dissolve(by="band", as_index=False)
    dissolved["geometry"] = dissolved.geometry.simplify(SIMPLIFY_M)
    dissolved = dissolved.to_crs(CRS_WGS84)

    features = []
    for row in dissolved.itertuples():
        features.append(
            {
                "type": "Feature",
                "properties": {
                    # -1 for untagged, matching rail-lines.geojson and the guard in
                    # paint.railLinePaint. Not null: a MapLibre comparison against null is a
                    # different code path in every expression that touches it, and not 0,
                    # which would fall through and paint untagged roads as the slowest band —
                    # a lie in the most visible direction. -1 cannot be mistaken for a limit
                    # and the paint expression tests it explicitly.
                    "kmh": -1 if row.band == UNTAGGED else int(row.band),
                    "km": by_band.get(row.band, 0.0),
                },
                "geometry": {
                    "type": row.geometry.geom_type,
                    "coordinates": round_coords(row.geometry.__geo_interface__["coordinates"]),
                },
            }
        )
    # Untagged last, then ascending, so the legend and the file read in the same order.
    features.sort(key=lambda f: (f["properties"]["kmh"] < 0, f["properties"]["kmh"]))

    GEOJSON_OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )

    total_km = float(lengths_km.sum())
    tagged_km = float(lengths_km[roads["band"] != UNTAGGED].sum())
    summary = {
        "$schema": "../schema/road-speeds.schema.json",
        "id": "road-speeds",
        "title": "Limitele de viteză semnalizate, pe porțiuni de drum",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "openstreetmap-maxspeed",
            "locator": (
                "eticheta maxspeed din other_tags, extrasul romania-latest.osm.pbf, "
                "clasele motorway, trunk, primary, secondary, tertiary"
            ),
            "confidence": "verbatim",
            "note": (
                "Valorile sunt citite din etichete, fără ajustare, cu același parser ca "
                "scripts/measure_limits.py. Geometria este dizolvată pe valoare și "
                "simplificată la 150 m pentru afișare."
            ),
        },
        "classes": list(CLASSES),
        "simplifyM": SIMPLIFY_M,
        "totalKm": round(total_km, 1),
        "taggedKm": round(tagged_km, 1),
        "coverage": round(tagged_km / total_km, 4) if total_km else 0.0,
        "kmByBand": {k: v for k, v in sorted(by_band.items(), key=lambda kv: -kv[1])},
        "limitations": [
            {
                "id": "eticheta-nu-e-codul-rutier",
                "text": (
                    "Este o hartă a ETICHETELOR din OpenStreetMap, nu a codului rutier. O "
                    "etichetă poate lipsi, poate fi veche sau greșită, iar valorile "
                    "nenumerice — RO:urban, walk, none — sunt tratate ca netichetate, nu "
                    "convertite într-un număr. Un drum netichetat are totuși o limită legală: "
                    "90 în afara localității, 50 înăuntru. Ce lipsește este consemnarea ei."
                ),
                "severity": "material",
                "affects": ["road-speeds"],
            },
            {
                "id": "acoperirea-scade-cu-clasa",
                "text": (
                    f"Acoperirea pe ansamblul acestor clase este de "
                    f"{tagged_km / total_km:.0%} din kilometri, dar scade rapid cu clasa: 96% "
                    "pe autostradă, 84% pe drum expres, 88% pe principal, 74% pe secundar și "
                    "56% pe terțiar. Deci porțiunile netichetate nu sunt împrăștiate uniform — "
                    "sunt concentrate pe drumurile mici, exact acolo unde modelul are cea mai "
                    "mare nevoie de ele. Banda „netichetat” se desenează separat tocmai ca "
                    "această concentrare să se vadă, nu să fie acoperită cu o presupunere."
                ),
                "severity": "material",
                "affects": ["road-speeds"],
            },
            {
                "id": "dizolvat-pe-valoare",
                "text": (
                    "Segmentele care au aceeași limită sunt unite într-o singură geometrie, ca "
                    "stratul să încapă în câteva sute de kilobytes în loc de zeci de megabytes. "
                    "Se pierde identitatea fiecărui drum: harta poate spune CE limită are o "
                    "porțiune, nu care este numărul drumului. Stratul este de desenat, nu de "
                    "rutat — rutarea folosește data/road_time.parquet."
                ),
                "severity": "note",
                "affects": ["road-speeds"],
            },
        ],
    }
    SUMMARY_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    size_mb = GEOJSON_OUT.stat().st_size / 1_048_576
    print(f"\n{len(features)} bands over {total_km:,.0f} km, {tagged_km / total_km:.0%} tagged")
    for feature in features:
        kmh, km = feature["properties"]["kmh"], feature["properties"]["km"]
        label = "untagged" if kmh < 0 else f"{kmh} km/h"
        print(f"  {label:>12}  {km:>9,.0f} km  {km / total_km:>5.1%}")
    print(f"\nWrote {GEOJSON_OUT.name} ({size_mb:.2f} MB) and {SUMMARY_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

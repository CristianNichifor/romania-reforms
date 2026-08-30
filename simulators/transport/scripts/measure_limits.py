"""Measure Romania's signed speed limits per road class, from OSM.

The speed table used to be a column of judgement calls. This replaces its inputs with a
measurement, and leaves only the physics as assumption.

What it finds, and why it is the interesting part: on every class below motorway the
**open-road** limit is essentially the national 90 km/h. Trunk, primary, secondary and
tertiary roads are not signed differently from each other out in the country. What separates
them is how much of their length runs **inside a locality**, where the limit is 50:

    trunk        32% of its length          primary       50%
    secondary    59%                        tertiary      80%
    unclassified 95%                        residential  100%

So a DN is not slow because it is a worse road. It is slow because a third of it threads
through the villages it connects. That is a fact about Romanian settlement geography rather
than about asphalt, and it is measured here rather than guessed.

`maxspeed` is not promoted to a column by GDAL's OSM driver — it lives in the `other_tags`
hstore, which is why this parses rather than reads it. Non-numeric values (`RO:urban`,
`walk`, `none`) are counted as untagged rather than mapped to a number: mapping them would
be assuming the thing this script exists to measure.

Everything is **length-weighted**. Counting ways instead would over-weight villages badly,
because a village segment is short and numerous while a rural stretch is long and single —
per-way, trunk's median limit reads 50 km/h; per-kilometre it reads 90.

Output:
    data/road-limits.json    per class: km, coverage, in-locality share, open-road mean

Usage:
    uv run python -m scripts.measure_limits
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "road-limits.json"

# Kept in step with scripts/speeds.ROUTING_CLASSES and administrativ's ROUTING_CLASSES.
CLASSES = (
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "road",
)

# The limit at or below which a road is taken to be inside a locality. Romanian law sets 50
# inside built-up areas (OUG 195/2002 art. 49), so a segment signed 50 or less is one the
# legislator considers urban, whatever OSM calls its class.
LOCALITY_KMH = 50.0

# Below this share of tagged length a class's measurement is not worth trusting on its own.
MIN_COVERAGE = 0.30

TAG = re.compile(r'"maxspeed"=>"([^"]+)"')


def parse_maxspeed(other_tags: object) -> float:
    """Numeric km/h from an hstore blob, or NaN.

    `RO:urban`, `walk`, `none` and friends return NaN deliberately. They carry real meaning,
    but resolving them to a number is exactly the assumption this measurement replaces.
    """
    if not isinstance(other_tags, str):
        return float("nan")
    found = TAG.search(other_tags)
    if not found:
        return float("nan")
    value = found.group(1).strip()
    return float(value) if value.isdigit() else float("nan")


def summarise(limits: np.ndarray, lengths: np.ndarray) -> dict:
    """Length-weighted picture of one class."""
    total_km = float(lengths.sum()) / 1000
    tagged = np.isfinite(limits)
    tagged_km = float(lengths[tagged].sum()) / 1000
    if tagged_km == 0:
        return {"km": round(total_km, 1), "coverage": 0.0, "usable": False}

    lim, ln = limits[tagged], lengths[tagged]
    inside = lim <= LOCALITY_KMH
    open_km = float(ln[~inside].sum())
    coverage = tagged_km / total_km if total_km else 0.0

    return {
        "km": round(total_km, 1),
        "km_tagged": round(tagged_km, 1),
        "coverage": round(coverage, 3),
        "usable": coverage >= MIN_COVERAGE,
        "locality_share": round(float(ln[inside].sum()) / float(ln.sum()), 4),
        "open_road_kmh": round(float((lim[~inside] * ln[~inside]).sum() / open_km), 1)
        if open_km
        else None,
        "locality_kmh": round(float((lim[inside] * ln[inside]).sum() / float(ln[inside].sum())), 1)
        if inside.any()
        else None,
        "mean_kmh": round(float((lim * ln).sum() / float(ln.sum())), 1),
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd

    pbf = ADMINISTRATIV / "data/raw/romania-latest.osm.pbf"
    if not pbf.exists():
        raise SystemExit(
            f"Missing {pbf}. Run, in simulators/administrativ: "
            "uv run python -m pipeline.fetch --with-roads"
        )

    where = "highway IN (" + ",".join(f"'{c}'" for c in CLASSES) + ")"
    print("Reading the OSM extract...")
    roads = gpd.read_file(
        pbf, layer="lines", columns=["highway", "other_tags"], where=where, engine="pyogrio"
    )
    if roads.crs is None:
        roads = roads.set_crs("EPSG:4326")
    # Stereo70: lengths in metres, which is what length-weighting needs.
    roads = roads.to_crs("EPSG:3844")

    print(f"Parsing maxspeed from {len(roads):,} features...")
    limits = np.array([parse_maxspeed(t) for t in roads["other_tags"]])
    lengths = roads.length.to_numpy()
    highway = roads["highway"].to_numpy()

    classes = {}
    for name in CLASSES:
        pick = highway == name
        if not pick.any():
            continue
        classes[name] = summarise(limits[pick], lengths[pick])

    document = {
        "$schema": "../schema/road-limits.schema.json",
        "id": "road-limits",
        "title": "Limitele de viteză semnalizate, pe clasă de drum",
        "publisher": "OpenStreetMap contributors",
        "period": "2026",
        "provenance": {
            "source": "osm-geofabrik-romania",
            "locator": (
                "eticheta maxspeed din extrasul Geofabrik romania-latest.osm.pbf, "
                "ponderată cu lungimea segmentelor"
            ),
            "confidence": "derived",
            "note": (
                "Măsurat, nu presupus. Valorile netextuale (RO:urban, walk, none) sunt tratate "
                "ca nemarcate. Un drum sub 30% acoperire nu este folosit singur."
            ),
        },
        "localityThresholdKmh": LOCALITY_KMH,
        "classes": classes,
        "limitations": [
            {
                "id": "acoperire-inegala",
                "text": (
                    "Acoperirea etichetei maxspeed diferă mult între clase: peste 84% pe "
                    "autostradă și drumuri naționale, sub 40% pe drumurile comunale și "
                    "rezidențiale. Media pe o clasă slab acoperită descrie segmentele "
                    "etichetate, nu neapărat clasa."
                ),
                "severity": "material",
                "affects": ["speeds", "travel_time"],
            },
            {
                "id": "limita-nu-e-viteza",
                "text": (
                    "O limită semnalizată este un maxim legal, nu viteza realizată. Curbele, "
                    "intersecțiile, starea carosabilului și traficul o reduc; conversia se "
                    "face în scripts/speeds.py și este o presupunere separată."
                ),
                "severity": "material",
                "affects": ["travel_time"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'class':14} {'km':>9} {'cover':>7} {'in-loc':>7} {'open':>7} {'mean':>7}")
    for name, c in classes.items():
        if not c.get("usable"):
            print(f"{name:14} {c['km']:>9,.0f} {c['coverage']:>6.0%}  (below {MIN_COVERAGE:.0%})")
            continue
        print(
            f"{name:14} {c['km']:>9,.0f} {c['coverage']:>6.0%} {c['locality_share']:>6.0%} "
            f"{c['open_road_kmh'] or 0:>7.1f} {c['mean_kmh']:>7.1f}"
        )
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

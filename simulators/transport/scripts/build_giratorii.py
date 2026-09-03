"""At-grade junctions between named roads, and what converting them would cost.

The fourth of the road questions, and the one where the measurement is easiest and the
interpretation hardest. Finding where two national or county roads cross is geometry. Deciding
which of those crossings wants a roundabout is engineering this repository cannot do.

So what this produces is a **candidate set with an upper bound on it**, not a programme. Every
figure here should be read as "at most this many", and the traffic split is what turns it into
something a reader can act on: a crossing on a road carrying twenty thousand vehicles a day is
a different proposition from one where two county roads meet in a field.

**Why converted junctions vanish rather than being counted.** A roundabout is mapped as its own
circular way, so the two roads no longer touch each other — they touch the loop. That means an
already-converted junction simply does not appear as an intersection, and the count is
naturally of what remains. Only 49 of the crossings found sit near an existing roundabout way,
which is the residue of geometry rather than a meaningful figure.

**What a roundabout is not always the answer to.** Some of these crossings want traffic
signals, some want grade separation, some want nothing because they carry a hundred vehicles a
day, and some already have signals this model cannot see. Nothing here distinguishes them.

Output:
    data/giratorii.json    junction candidates, split by measured traffic, and cost

Usage:
    uv run python -m scripts.build_giratorii
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PBF = ADMINISTRATIV / "data" / "raw" / "romania-latest.osm.pbf"
TRAFFIC = ROOT / "data" / "reports" / "major-roads.gpkg"
OUT = ROOT / "data" / "giratorii.json"
INPUTS = ROOT / "data" / "giratorii-inputs.json"

CLASSES: Final[tuple[str, ...]] = ("trunk", "primary", "secondary")
CRS: Final[str] = "EPSG:3844"

# One junction is often mapped as several nodes — a dual carriageway crossing another road
# produces two, a staggered crossroads three. Points within this of each other are the same
# junction; wider would merge genuinely separate junctions in a town centre.
CLUSTER_M: Final[float] = 20.0

# How close an existing roundabout way must be for a crossing to count as already converted.
ROUNDABOUT_M: Final[float] = 60.0

# Traffic is inherited the same way the bypasses do it.
MATCH_M: Final[float] = 100.0
DAYS: Final[int] = 365

REF = re.compile(r'"ref"=>"([^"]+)"')
ROUNDABOUT_TAG: Final[str] = '"junction"=>"roundabout"'


def road_ref(tags: object) -> str | None:
    """The road number, e.g. DN1 or DJ105. `ref` lives in the hstore like `maxspeed` does.

    A way carrying two numbers — a DN that is also a European route — lists both; the first is
    taken, because concurrency is not a junction and counting E-numbers separately would invent
    crossings wherever a road changed its European designation.
    """
    if not isinstance(tags, str):
        return None
    found = REF.search(tags)
    return found.group(1).split(";")[0].strip() if found else None


def junction_points(geometry):
    """Points from an intersection result, ignoring shared carriageway.

    Two roads that run concurrently intersect in a LINE, not a point. That is one road wearing
    two numbers, not a junction, so only the ends of such a stretch are taken — those are where
    the roads actually part company.
    """
    from shapely.geometry import (
        GeometryCollection,
        LineString,
        MultiLineString,
        MultiPoint,
        Point,
    )

    found, stack = [], [geometry]
    while stack:
        part = stack.pop()
        if part.is_empty:
            continue
        if isinstance(part, Point):
            found.append(part)
        elif isinstance(part, (LineString, MultiLineString)):
            boundary = part.boundary
            found.extend(Point(p.x, p.y) for p in getattr(boundary, "geoms", []))
        elif isinstance(part, (MultiPoint, GeometryCollection)):
            stack.extend(part.geoms)
    return found


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    if not PBF.exists():
        print(f"Missing {PBF}. Run administrativ's fetch with --with-roads.", file=sys.stderr)
        return 1

    import geopandas as gpd

    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))["items"]
    lei_each = inputs["roundaboutLeiEach"]["value"]

    selector = ",".join(f"'{c}'" for c in CLASSES)
    print(f"Reading {', '.join(CLASSES)}...")
    roads = (
        gpd.read_file(
            PBF,
            layer="lines",
            columns=["highway", "other_tags"],
            where=f"highway IN ({selector})",
            engine="pyogrio",
        )
        .set_crs("EPSG:4326")
        .to_crs(CRS)
    )
    tags = roads["other_tags"].fillna("")
    roads["ref"] = [road_ref(t) for t in roads["other_tags"]]
    roads["isRoundabout"] = tags.str.contains(ROUNDABOUT_TAG, regex=False)

    existing = roads[roads["isRoundabout"]]
    named = roads[roads["ref"].notna() & ~roads["isRoundabout"]]
    dissolved = named.dissolve(by="ref", as_index=False)[["ref", "geometry"]]
    print(f"  {len(dissolved):,} distinct road numbers, {len(existing):,} roundabout ways")

    index = dissolved.sindex
    points = []
    for row in dissolved.itertuples():
        for other in index.query(row.geometry, predicate="intersects"):
            if dissolved["ref"].iloc[other] <= row.ref:
                continue
            points.extend(
                junction_points(row.geometry.intersection(dissolved.geometry.iloc[other]))
            )
    print(f"  {len(points):,} raw crossing points")

    blobs = gpd.GeoSeries(points, crs=CRS).buffer(CLUSTER_M).union_all()
    clusters = list(blobs.geoms) if blobs.geom_type == "MultiPolygon" else [blobs]
    junctions = gpd.GeoDataFrame(geometry=[c.centroid for c in clusters], crs=CRS)
    converted = junctions.geometry.intersects(existing.geometry.buffer(ROUNDABOUT_M).union_all())
    remaining = junctions[~converted].reset_index(drop=True)
    print(f"  {len(junctions):,} distinct junctions, {int(converted.sum()):,} already converted")

    busy = 0
    if TRAFFIC.exists():
        end = gpd.read_file(TRAFFIC, layer="MajorRoadSource", engine="pyogrio").to_crs(CRS)
        end["aadt"] = end["annualTrafficFlow"] / DAYS
        near = gpd.sjoin_nearest(
            remaining, end[["aadt", "geometry"]], how="left", max_distance=MATCH_M
        )
        near = near.groupby(level=0)["aadt"].max()
        busy = int(near.notna().sum())
    print(f"  {busy:,} of {len(remaining):,} sit on a road with measured traffic")

    document = {
        "$schema": "../schema/giratorii.schema.json",
        "id": "giratorii",
        "title": "Intersecțiile la nivel dintre drumurile numerotate, și cât ar costa girațiile",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "openstreetmap-plus-contracte",
            "locator": (
                "intersecții geometrice între drumuri cu numere diferite din "
                "romania-latest.osm.pbf, clasele trunk, primary și secondary; preț unitar din "
                "contractul pentru sensul giratoriu DN6 x DJ680 la Lugoj, 2026"
            ),
            "confidence": "derived",
            "note": (
                "Se numără traversări geometrice, nu proiecte. O intersecție deja transformată "
                "nu apare, pentru că girația se cartografiază ca inel propriu și drumurile nu "
                "se mai ating între ele."
            ),
        },
        "junctions": {
            "roadNumbers": int(len(dissolved)),
            "rawPoints": int(len(points)),
            "distinct": int(len(junctions)),
            "alreadyRoundabout": int(converted.sum()),
            "remaining": int(len(remaining)),
            "onMeasuredTraffic": busy,
            "existingRoundaboutWays": int(len(existing)),
            "clusterM": CLUSTER_M,
        },
        "cost": {
            "leiEach": lei_each,
            "allRemainingRon": round(len(remaining) * lei_each),
            "onMeasuredTrafficRon": round(busy * lei_each),
        },
        "limitations": [
            {
                "id": "candidati-nu-program",
                "text": (
                    f"Cele {len(remaining):,} de intersecții sunt CANDIDAȚI, nu un program. "
                    "Unele cer semaforizare, altele pasaj denivelat, multe nu cer nimic pentru "
                    "că pe ele trec o sută de vehicule pe zi, iar unele au deja semafoare pe "
                    "care modelul nu le vede. Nimic de aici nu le deosebește. Cifra trebuie "
                    "citită ca „cel mult atâtea”, iar împărțirea după trafic este singura care "
                    "o apropie de un program."
                ).replace(",", "."),
                "severity": "blocking",
                "affects": ["giratorii"],
            },
            {
                "id": "pretul-unitar-variaza-de-zece-ori",
                "text": (
                    "Prețul unitar este cel mai slab element. Reperul folosit este girația de "
                    "la Lugoj, DN6 cu DJ680, 3,74 milioane de lei în 2026 — o intersecție "
                    "obișnuită de drum național cu drum județean. Dar intervalul real merge de "
                    "la circa 1,5 milioane pentru una mică pe drum județean până la peste 40 "
                    "de milioane pentru DN7 cu DN76 la Deva, care include mult mai mult decât "
                    "inelul. Compoziția contează mai mult decât media, iar acest model nu o "
                    "cunoaște."
                ),
                "severity": "material",
                "affects": ["giratorii"],
            },
            {
                "id": "intersectia-geometrica-nu-e-intersectie-rutiera",
                "text": (
                    "Se intersectează geometrii, nu se citesc noduri. Două drumuri care trec "
                    "unul peste altul printr-un pasaj apar ca o încrucișare, deși nu se "
                    "întâlnesc. La clasele folosite aici pasajele sunt rare, dar există, iar "
                    "numărul este cu atât mai mult un prag de sus."
                ),
                "severity": "material",
                "affects": ["giratorii"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"\n  all {len(remaining):,} candidates: {len(remaining) * lei_each / 1e9:.1f} md lei; "
        f"the {busy:,} on measured roads: {busy * lei_each / 1e9:.1f} md lei"
    )
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

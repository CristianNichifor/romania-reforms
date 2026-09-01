"""The shapes the land values are painted on.

Everything in this simulator is keyed by SIRUTA, and so is the boundary file another simulator
in this repository already built and validated — `administrativ` joins 3 186 UAT polygons to
their attributes on exactly that code and refuses to build if a single one fails to match. So
the map is a join, not a project, and this file is deliberately thin: it emits geometry and the
key, and nothing else.

**No values are baked in.** The page recomputes land value as the reader moves the intravilan
share, the price band and the rest; a choropleth carrying pre-computed numbers would freeze at
whatever the assumptions were when this ran, and quietly disagree with the figures printed
beside it. The browser colours the polygons from the same `evaluate()` that produces the
totals, through maplibre's feature state, so the map and the numbers cannot drift apart.

**The feature id is the SIRUTA**, not a row number. `administrativ` exports its shapes with a
positional id and joins by index, which works there and would be a trap here: this simulator
publishes counties one at a time, so any index is a property of which counties happened to be
built, and a map keyed on it would silently repaint the wrong communes the moment a fifteenth
county landed.

**Only the counties that have a grid.** Painting all 3 186 UATs would mean 2 000 of them
rendered as "no data", which is a fair picture of coverage but a 3 MB download to say it. The
county borders come separately and cover the whole country, so what is missing still shows —
as an empty outline rather than as a grey polygon.

Geometry is simplified to about a hundred metres. That is far below anything a national
choropleth resolves and it roughly halves the file.

Usage:
    uv run --with geopandas python simulators/impozit-teren/scripts/build_harta.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BOUNDARIES = REPO / "simulators" / "administrativ" / "data" / "processed" / "uat_geometry.gpkg"
COUNTY_LINES = REPO / "dist" / "administrativ" / "data" / "counties.geojson"
# About 100 m in degrees. A national choropleth resolves nothing finer, and the coastline and
# the Danube keep their shape at this tolerance.
TOLERANCE = 0.001
# maplibre keys feature state on numbers, and a county code is a string. A fixed, alphabetical
# list gives each county a stable integer id — stable being the load-bearing word, since the
# ids are baked into the shipped file and looked up by the browser at paint time.
ORDER = [
    "AB", "AG", "AR", "B", "BC", "BH", "BN", "BR", "BT", "BV", "BZ", "CJ", "CL", "CS", "CT",
    "CV", "DB", "DJ", "GJ", "GL", "GR", "HD", "HR", "IF", "IL", "IS", "MH", "MM", "MS", "NT",
    "OT", "PH", "SB", "SJ", "SM", "SV", "TL", "TM", "TR", "VL", "VN", "VS",
]


def round_coordinates(node):
    """Coordinates to five decimals, which is about a metre.

    Full float precision is seventeen significant digits of a number that means nothing below
    the metre, and it tripled the file: 3,6 MB of mostly noise for 1 128 communes.
    """
    if isinstance(node, list):
        return [round_coordinates(x) for x in node]
    if isinstance(node, float):
        return round(node, 5)
    if isinstance(node, dict):
        return {k: round_coordinates(v) for k, v in node.items()}
    return node


def counties_with_values() -> set[str]:
    """The counties actually read from a grid.

    The national estimate is deliberately named `valoare-nationala-*` and not
    `valoare-teren-nationala-*`, so it does not answer this glob. It lists all forty-two
    counties; had it matched, this would have asked for every UAT in Romania — 3 186 polygons
    instead of 1 611, and two thousand communes painted as though a study had priced them.
    """
    found = set()
    for path in (ROOT / "data").glob("valoare-teren-*.json"):
        found.update(json.loads(path.read_text(encoding="utf-8"))["counties"])
    return found


def main() -> int:
    if not BOUNDARIES.exists():
        raise SystemExit(
            f"missing {BOUNDARIES}\n"
            "Run the administrativ pipeline's geometry step first; this simulator borrows its "
            "boundaries rather than fetching a second copy."
        )
    wanted = counties_with_values()
    if not wanted:
        raise SystemExit("no valoare-teren-*.json; run build_valoare_teren.py first")

    shapes = gpd.read_file(BOUNDARIES)
    shapes = shapes[shapes["county_code"].isin(wanted)].copy()
    if shapes.empty:
        raise SystemExit(f"no boundaries matched {sorted(wanted)}")
    shapes = shapes.to_crs(4326)
    shapes["geometry"] = shapes.geometry.simplify(TOLERANCE, preserve_topology=True)

    shapes = shapes[["siruta", "name_uat", "county_code", "geometry"]]
    features = json.loads(shapes.to_json())["features"]
    for feature in features:
        properties = feature["properties"]
        # The SIRUTA as an integer, because maplibre's feature state keys on numbers and
        # silently misses when a string id is looked up with a number.
        feature["id"] = int(properties["siruta"])
        feature["properties"] = {
            "siruta": str(properties["siruta"]),
            "name": properties["name_uat"],
            "county": properties["county_code"],
        }
        feature["geometry"] = round_coordinates(feature["geometry"])

    out = ROOT / "data" / "harta-uat.geojson"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )

    # The whole country's county borders, so the counties with no grid are visible as gaps
    # rather than absent. Copied rather than rebuilt: administrativ already validated them.
    if COUNTY_LINES.exists():
        borders = ROOT / "data" / "harta-judete.geojson"
        borders.write_text(COUNTY_LINES.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Wrote {borders.relative_to(REPO)}")

    # County outlines as *polygons*, for the half of the country that has no grid.
    #
    # The border file above is lines, which can only ever draw a gap. The national estimate
    # gives those counties a value, and a value wants a fill — but at county resolution and
    # not finer, because that is the resolution the estimate actually has. Painting a predicted
    # county commune by commune would dress a single regression coefficient up as local
    # knowledge. The visible difference between a mosaic and a flat shape is the point: it is
    # the difference in evidence, drawn.
    whole = gpd.read_file(BOUNDARIES).to_crs(4326)
    whole = whole.dissolve(by="county_code")[["geometry"]].reset_index()
    # Coarser than the communes, because a county outline is read at national zoom and its
    # detail is never the thing being looked at.
    whole["geometry"] = whole.geometry.simplify(TOLERANCE * 3, preserve_topology=True)
    county_features = json.loads(whole.to_json())["features"]
    for feature in county_features:
        code = feature["properties"]["county_code"]
        feature["id"] = ORDER.index(code) if code in ORDER else len(ORDER)
        feature["properties"] = {"county": code}
        feature["geometry"] = round_coordinates(feature["geometry"])
    shapes_out = ROOT / "data" / "harta-judete-poligon.geojson"
    shapes_out.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": county_features}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    print(
        f"{len(county_features)} poligoane de județ, "
        f"{shapes_out.stat().st_size / 1e6:.2f} MB -> {shapes_out.name}"
    )

    covered = {f["properties"]["county"] for f in features}
    print(f"{len(features)} UAT-uri din {len(covered)} județe: {' '.join(sorted(covered))}")
    print(f"{out.stat().st_size / 1e6:.2f} MB")
    print(f"Wrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

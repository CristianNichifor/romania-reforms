"""The shapes the map paints, and whether they join to the values.

A choropleth fails quietly. If a tenth of the communes stop matching their polygons the page
still renders, still looks like a map of Romania, and is simply wrong in places nobody can spot
without knowing the country. So the join is asserted rather than trusted, in both directions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "data"


@pytest.fixture(scope="module")
def shapes() -> dict:
    path = DATA / "harta-uat.geojson"
    if not path.exists():
        pytest.skip("harta-uat.geojson is not built")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def valued() -> dict[str, str]:
    """Every locality with a land value, to the county that priced it."""
    found: dict[str, str] = {}
    for path in sorted(DATA.glob("valoare-teren-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for row in document["localities"]:
            found[row["siruta"]] = document["counties"][0]
    return found


def test_every_valued_locality_has_a_shape(shapes, valued):
    """The direction that matters: a priced commune with no polygon is invisible on the map."""
    if not valued:
        pytest.skip("no county is built")
    ids = {feature["id"] for feature in shapes["features"]}
    missing = sorted(siruta for siruta in valued if int(siruta) not in ids)
    assert missing == [], missing


def test_feature_ids_are_integers(shapes):
    """maplibre keys feature state on numbers and misses silently against a string.

    Worth a test precisely because the failure is invisible: `setFeatureState` with an id the
    source does not have throws nothing, paints nothing, and leaves a map that looks finished.
    """
    for feature in shapes["features"]:
        assert isinstance(feature["id"], int)
        assert str(feature["id"]) == feature["properties"]["siruta"]


def test_the_unpainted_shapes_are_the_named_gaps(shapes, valued):
    """Shapes without a value are the communes their county's study does not price.

    They are supposed to exist — Hunedoara prices extravilan for eleven seats and Iași leaves
    five communes out — and they are supposed to be few. A large number here would mean the
    join is broken rather than that the documents are short.
    """
    if not valued:
        pytest.skip("no county is built")
    unpainted = [f for f in shapes["features"] if str(f["id"]) not in valued]
    assert len(unpainted) < len(shapes["features"]) * 0.15


def test_only_built_counties_are_shipped(shapes, valued):
    """Painting all 3 186 UATs would be a 3 MB download to say "no data" 2 000 times."""
    if not valued:
        pytest.skip("no county is built")
    built = set(valued.values())
    on_map = {f["properties"]["county"] for f in shapes["features"]}
    assert on_map == built


def test_the_file_stays_small_enough_to_ship(shapes):
    """Simplified to about a hundred metres and rounded to five decimals, for a reason."""
    size = (DATA / "harta-uat.geojson").stat().st_size
    assert size < 6_000_000, f"{size / 1e6:.1f} MB is too much to hand a browser"


def test_county_borders_cover_the_whole_country(shapes):
    """The missing counties have to be visible as empty outlines, not absent."""
    path = DATA / "harta-judete.geojson"
    if not path.exists():
        pytest.skip("harta-judete.geojson is not built")
    borders = json.loads(path.read_text(encoding="utf-8"))
    named = {
        side
        for feature in borders["features"]
        for key in ("leftcode", "rightcode")
        if (side := feature["properties"].get(key))
    }
    # Every county in the country, not only the fourteen with a grid — that is the point.
    assert len(named) >= 40


@pytest.fixture(scope="module")
def county_shapes() -> dict:
    path = DATA / "harta-judete-poligon.geojson"
    if not path.exists():
        pytest.skip("harta-judete-poligon.geojson is not built")
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_county_in_the_country_has_a_polygon(county_shapes):
    """All 42, not only the read ones — the polygons exist to paint the *unread* ones."""
    codes = {f["properties"]["county"] for f in county_shapes["features"]}
    assert len(codes) == 42, sorted(codes)


def test_county_ids_are_integers_and_unique(county_shapes):
    """Same trap as the communes, one level up.

    maplibre keys feature state on numbers. A county code is a string, so the builder assigns
    each one a position in a fixed alphabetical list — fixed being the point, because the ids
    are baked into the shipped file and looked up by the browser at paint time. Duplicates
    would silently paint two counties the same colour.
    """
    ids = [f["id"] for f in county_shapes["features"]]
    assert all(isinstance(i, int) for i in ids)
    assert len(set(ids)) == len(ids)


def test_the_estimated_counties_all_have_a_shape_to_paint(county_shapes):
    """Every county the national estimate predicts must be paintable, or it is invisible.

    This was written when nineteen counties had no grid: if one of them had no polygon the map
    would look complete and simply omit it, which is the failure mode the commune-level version
    of this test was written for.

    Every county is read now, so there is nothing left to predict and nothing for this to check.
    It stays because the set is not permanently empty — a chamber that stops publishing puts a
    county back into it — and an assertion that the set is non-empty would now fail for the
    best possible reason.
    """
    path = DATA / "valoare-nationala-2026.json"
    if not path.exists():
        pytest.skip("the national estimate is not built")
    national = json.loads(path.read_text(encoding="utf-8"))
    drawable = {f["properties"]["county"] for f in county_shapes["features"]}
    predicted = {
        row["county"] for row in national["counties_valued"] if row["basis"] == "predicted"
    }
    assert predicted <= drawable


def test_the_county_polygons_stay_small(county_shapes):
    """Coarser than the communes on purpose: a county outline is read at national zoom."""
    size = (DATA / "harta-judete-poligon.geojson").stat().st_size
    assert size < 1_500_000, f"{size / 1e6:.1f} MB for 42 outlines is too much"

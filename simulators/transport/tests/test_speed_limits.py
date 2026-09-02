"""Tests for the signed-speed-limit layer.

The layer's whole value is that it shows where the limits are instead of reducing them to
eight class averages. That makes two things load-bearing: the untagged quarter must stay
visibly untagged, and the two values Romania actually signs — 50 through villages, 90 on the
open road — must survive as the dominant bands rather than being smoothed into each other.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GEOJSON = ROOT / "data" / "road-speeds.geojson"
SUMMARY = ROOT / "data" / "road-speeds.json"


@pytest.fixture(scope="module")
def summary() -> dict:
    if not SUMMARY.exists():
        pytest.skip("speed limits not built")
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def layer() -> dict:
    if not GEOJSON.exists():
        pytest.skip("speed limits not built")
    return json.loads(GEOJSON.read_text(encoding="utf-8"))


def test_the_untagged_share_is_reported_not_hidden(summary):
    """A quarter of these kilometres carry no maxspeed. If coverage ever reads as 1,0 the
    untagged roads have been filled with an assumption, which is the one thing this layer
    must never do."""
    assert 0.5 < summary["coverage"] < 0.95
    assert summary["taggedKm"] < summary["totalKm"]
    assert "untagged" in summary["kmByBand"]
    assert summary["kmByBand"]["untagged"] > 0


def test_fifty_and_ninety_dominate(summary):
    """The model's central finding, as data: below motorway the open-road limit is the
    national 90 and what differs is how much of a road runs at 50 through villages. If some
    other value ever came top, either OSM changed radically or the parser broke."""
    tagged = {k: v for k, v in summary["kmByBand"].items() if k != "untagged"}
    top_two = sorted(tagged, key=lambda k: -tagged[k])[:2]
    assert set(top_two) == {"50", "90"}
    assert tagged["50"] > tagged["90"], "villages should out-length the open road"


def test_untagged_is_a_negative_sentinel_never_zero(layer):
    """-1 with an explicit guard in the paint expression. A 0 would fall through the step and
    paint 21 000 km as the slowest roads in the country — a false finding, drawn boldly."""
    values = [f["properties"]["kmh"] for f in layer["features"]]
    assert -1 in values
    assert 0 not in values
    for value in values:
        assert value == -1 or value >= 5, value


def test_every_band_carries_its_length(layer):
    """So a reader can weigh a colour by how much road is in it rather than by how much of the
    screen it happens to cover."""
    for feature in layer["features"]:
        assert feature["properties"]["km"] >= 0
        assert feature["geometry"]["type"] in ("LineString", "MultiLineString")


def test_the_bands_are_ordered_with_untagged_last(layer):
    """The legend reads fastest-first and the file reads ascending; both put absence at the
    end rather than mixed in among the numbers."""
    values = [f["properties"]["kmh"] for f in layer["features"]]
    tagged = [v for v in values if v >= 0]
    assert tagged == sorted(tagged)
    assert values[-1] == -1


def test_it_says_the_tag_is_not_the_road_code(summary):
    """The caveat that stops the layer being read as a legal map. A missing tag is a missing
    record, not a missing limit."""
    ids = {limitation["id"] for limitation in summary["limitations"]}
    assert "eticheta-nu-e-codul-rutier" in ids
    assert "acoperirea-scade-cu-clasa" in ids


def test_it_covers_the_classes_the_model_routes_over(summary):
    """Residential and unclassified are excluded on purpose — 112 000 km of streets at 38-41%
    coverage. If the class list ever shrinks below the intercity network the layer stops
    describing the thing the buses drive on."""
    assert set(summary["classes"]) >= {"motorway", "trunk", "primary", "secondary", "tertiary"}
    assert summary["totalKm"] > 70_000

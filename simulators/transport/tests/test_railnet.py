"""Tests for the rail network build.

The geometry stages need a 1 GB OSM extract and are exercised by running the script. What is
tested here is everything that decides *which* geometry counts — the tag parsing and the county
seat rule — because those are the places a silent wrong answer would come from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_railnet import _tags, pick_county_seats

ROOT = Path(__file__).resolve().parents[1]


def _frame(rows):
    pandas = pytest.importorskip("pandas")
    return pandas.DataFrame(rows)


def test_tags_parses_the_hstore():
    parsed = _tags('"usage"=>"main","maxspeed"=>"100","electrified"=>"contact_line"')
    assert parsed["usage"] == "main"
    assert parsed["maxspeed"] == "100"


def test_tags_survives_an_untagged_way():
    """GDAL hands back NaN, not None, for a way with no other tags.

    This crashed the first national build. A float is not a string and the regex says so.
    """
    assert _tags(float("nan")) == {}
    assert _tags(None) == {}
    assert _tags("") == {}


def test_county_seat_is_the_most_populous_uat_in_its_county():
    seats = _frame(
        [
            {"siruta": 1, "county_code": "CJ", "name_uat": "CLUJ-NAPOCA"},
            {"siruta": 2, "county_code": "CJ", "name_uat": "TURDA"},
            {"siruta": 3, "county_code": "AB", "name_uat": "ALBA IULIA"},
        ]
    )
    chosen = pick_county_seats(seats, {1: 286_598, 2: 43_500, 3: 63_536})
    assert list(chosen["name_uat"]) == ["ALBA IULIA", "CLUJ-NAPOCA"]


def test_exactly_one_seat_per_county():
    seats = _frame(
        [{"siruta": i, "county_code": c, "name_uat": f"U{i}"} for i, c in enumerate("AABBCC")]
    )
    chosen = pick_county_seats(seats, {i: 100 + i for i in range(6)})
    assert len(chosen) == len(set(chosen["county_code"])) == 3


def test_a_broken_population_join_fails_loudly():
    """A join that matched nothing must stop the build, not elect the first row of each county.

    The uats.geojson join matched 0 of 3 186 earlier in this project and rendered a plausible
    grey map. The guard is the lesson from that.
    """
    seats = _frame([{"siruta": i, "county_code": "CJ", "name_uat": f"U{i}"} for i in range(20)])
    with pytest.raises(SystemExit, match="bad join"):
        pick_county_seats(seats, {})


def test_the_published_network_declares_a_speed_for_every_condition():
    """A condition class priced without a declared speed could be priced at any speed."""
    document = json.loads((ROOT / "data" / "railnet.json").read_text(encoding="utf-8"))
    assert len(document["conditions"]) >= 2
    for name, entry in document["conditions"].items():
        assert entry["commercialKmh"] > 0, name
        assert entry["medianPairMin"] > 0, name


def test_rehabilitation_is_faster_than_the_track_as_it_stands():
    document = json.loads((ROOT / "data" / "railnet.json").read_text(encoding="utf-8"))
    conditions = document["conditions"]
    assert conditions["rehabilitated"]["medianPairMin"] < conditions["as_is"]["medianPairMin"]


def test_the_station_to_seat_residual_is_published():
    """Rail that requires a bus to reach it must say so in the artefact, not only in prose."""
    document = json.loads((ROOT / "data" / "railnet.json").read_text(encoding="utf-8"))
    seats = document["seats"]
    assert seats["withinWalkOfStation"] <= seats["considered"]
    assert {limitation["id"] for limitation in document["limitations"]} >= {"gara-nu-e-satul"}

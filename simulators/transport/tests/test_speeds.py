"""Tests for the assumed speed table.

These are the weakest numbers in L0 — every one of them is `assumed` — so the tests here
check the table's shape and internal consistency rather than its truth. Its truth is what
Task 6's one-county gate is for.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.speeds import (
    EFFECTIVE_KMH,
    FALLBACK_KMH,
    ROUTING_CLASSES,
    speeds_for_classes,
)


def test_every_routable_class_has_a_speed():
    """A class the router will traverse but the table does not price gets the fallback
    silently, which is how a whole road category ends up quietly wrong."""
    missing = [c for c in ROUTING_CLASSES if c not in EFFECTIVE_KMH]
    assert missing == [], missing


def test_speeds_are_ordered_by_road_class():
    """A motorway that models slower than a residential street means the table was edited
    without being read."""
    assert EFFECTIVE_KMH["motorway"] > EFFECTIVE_KMH["trunk"]
    assert EFFECTIVE_KMH["trunk"] >= EFFECTIVE_KMH["primary"]
    assert EFFECTIVE_KMH["primary"] > EFFECTIVE_KMH["secondary"]
    assert EFFECTIVE_KMH["secondary"] > EFFECTIVE_KMH["tertiary"]
    assert EFFECTIVE_KMH["tertiary"] > EFFECTIVE_KMH["residential"]


def test_no_speed_exceeds_the_legal_limit():
    """OUG 195/2002 caps cars at 130 km/h on motorways and 90 on other roads outside
    localities. An effective speed above the legal limit is not a modelling choice."""
    assert EFFECTIVE_KMH["motorway"] <= 130
    for name, kmh in EFFECTIVE_KMH.items():
        if name.startswith("motorway"):
            continue
        assert kmh <= 90, (name, kmh)


def test_a_link_is_never_faster_than_the_road_it_serves():
    for base in ("motorway", "trunk", "primary", "secondary", "tertiary"):
        assert EFFECTIVE_KMH[f"{base}_link"] <= EFFECTIVE_KMH[base], base


def test_it_maps_an_array_of_classes_to_speeds():
    got = speeds_for_classes(np.array(["motorway", "residential", "tertiary"]))
    assert got.tolist() == [
        EFFECTIVE_KMH["motorway"],
        EFFECTIVE_KMH["residential"],
        EFFECTIVE_KMH["tertiary"],
    ]


def test_an_unknown_class_falls_back_rather_than_crashing():
    """OSM adds highway values without asking. An unknown class must route slowly, not
    raise — a crash here would fail the whole national build on one odd way."""
    got = speeds_for_classes(np.array(["motorway", "some_new_osm_value"]))
    assert got[1] == FALLBACK_KMH


def test_the_fallback_is_pessimistic():
    """If the fallback were fast, an unrecognised class would silently become a shortcut."""
    assert min(EFFECTIVE_KMH.values()) >= FALLBACK_KMH


def test_missing_classes_fall_back_too():
    got = speeds_for_classes(np.array([None, "motorway"], dtype=object))
    assert got[0] == FALLBACK_KMH


def test_it_returns_floats_not_ints():
    """The caller divides by these. Integer division would silently truncate travel time."""
    assert speeds_for_classes(np.array(["motorway"])).dtype == np.float64


def test_it_handles_an_empty_array():
    assert speeds_for_classes(np.array([], dtype=object)).shape == (0,)


def test_every_speed_is_positive():
    """A zero would divide by zero and produce an infinite travel time on a real road."""
    assert all(kmh > 0 for kmh in EFFECTIVE_KMH.values())
    assert FALLBACK_KMH > 0


def test_the_provenance_note_names_the_gate():
    """The table is assumed, and the only thing that makes it defensible is the county
    check. If that sentence goes missing, so does the reason to trust any of this."""
    from scripts.speeds import SPEED_PROVENANCE

    assert SPEED_PROVENANCE["confidence"] == "assumed"
    assert "OUG 195/2002" in SPEED_PROVENANCE["locator"]


@pytest.mark.parametrize("kmh", EFFECTIVE_KMH.values())
def test_no_speed_is_absurdly_low(kmh):
    """Below 15 km/h a road is not a road; that would be a typo, not a slow lane."""
    assert kmh >= 15

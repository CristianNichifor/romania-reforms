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


def test_the_provenance_says_derived_and_still_names_the_law():
    """The limits are measured now, so the table is derived rather than assumed — but the
    legal ceilings are still law, and the note must keep saying that nothing here has been
    checked against a recorded journey."""
    from scripts.speeds import SPEED_PROVENANCE

    assert SPEED_PROVENANCE["confidence"] == "derived"
    assert "OUG 195/2002" in SPEED_PROVENANCE["locator"]
    assert "verificat" in SPEED_PROVENANCE["note"]


def test_a_bus_is_never_faster_than_a_car():
    """Lower legal ceiling and gentler acceleration. If a bus ever models faster, a cap or a
    rate has been entered the wrong way round."""
    from scripts.speeds import ROUTING_CLASSES, effective_kmh

    car, bus = effective_kmh("car"), effective_kmh("bus")
    for name in ROUTING_CLASSES:
        assert bus[name] <= car[name] + 1e-9, name


def test_the_bus_penalty_lands_on_fast_roads_not_slow_ones():
    """A result worth pinning: below trunk the road's geometry binds, not the vehicle, so a
    bus and a car converge. If this inverts, the ceilings are being applied everywhere
    instead of only where they bite."""
    from scripts.speeds import effective_kmh

    car, bus = effective_kmh("car"), effective_kmh("bus")
    assert car["motorway"] - bus["motorway"] > 10
    assert car["tertiary"] - bus["tertiary"] < 2


def test_more_locality_means_slower_all_else_equal():
    """The mechanism the model rests on: below motorway the open-road limit is the same 90
    on every class, so what makes a communal road slow is how much of it is inside a village.

    Stated as a property of the model rather than of the real classes, because the real
    classes differ in a second way too — see the test below."""
    from scripts.speeds import VEHICLES, _class_speed

    def at(share):
        return _class_speed(
            {"usable": True, "locality_share": share, "open_road_kmh": 90.0, "locality_kmh": 50.0},
            "secondary",
            VEHICLES["car"],
        )

    speeds = [at(s) for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert speeds == sorted(speeds, reverse=True), speeds


def test_a_rural_lane_is_signed_lower_than_a_town_street():
    """Why `unclassified` models slower than `residential` despite being *less* of it inside
    a locality: the in-locality limit is not constant either. A rural lane averages under 40
    where a town street averages 47, because villages sign 30 zones and towns sign 50.

    This surprised me, so it is pinned. It is also the reason the test above is written
    against the model rather than against the measured classes."""
    from scripts.speeds import EFFECTIVE_KMH, load_limits

    measured = load_limits()["classes"]
    unclassified, residential = measured["unclassified"], measured["residential"]
    assert unclassified["locality_share"] < residential["locality_share"]
    assert unclassified["locality_kmh"] < residential["locality_kmh"]
    assert EFFECTIVE_KMH["unclassified"] < EFFECTIVE_KMH["residential"]


def test_a_class_the_measurement_cannot_support_falls_back():
    """living_street is tagged on a quarter of its length. A mean over that is not a
    measurement of the class, so it takes the pessimistic fallback rather than pretending."""
    from scripts.speeds import EFFECTIVE_KMH, FALLBACK_KMH, load_limits

    measured = load_limits()["classes"]
    for name, m in measured.items():
        if not m.get("usable"):
            assert EFFECTIVE_KMH[name] == FALLBACK_KMH, name


def test_no_transition_loss_when_the_limit_does_not_change():
    """A motorway has no localities to brake for. If this returned anything but zero the
    loss term would be charging every road for a village it never enters."""
    from scripts.speeds import VEHICLES, _transition_loss_s

    assert _transition_loss_s(25.0, 25.0, VEHICLES["car"]) == 0.0
    assert _transition_loss_s(25.0, 30.0, VEHICLES["car"]) == 0.0


def test_a_gentler_vehicle_loses_more_at_every_village():
    """The physics, in the direction it must go: a bus takes longer to stop and longer to
    get going, so each locality costs it more than it costs a car."""
    from scripts.speeds import VEHICLES, _transition_loss_s

    car = _transition_loss_s(25.0, 13.9, VEHICLES["car"])
    bus = _transition_loss_s(25.0, 13.9, VEHICLES["bus"])
    assert bus > car > 0


def test_the_transition_loss_is_small_next_to_the_crawl():
    """Worth knowing and worth pinning: a village costs a few seconds of braking and a
    minute of crawling. If this ever inverts, the accel rates are wrong by an order."""
    from scripts.speeds import VEHICLES, _transition_loss_s

    braking = _transition_loss_s(25.0, 13.9, VEHICLES["bus"])
    crawling = 1500 / 13.9 - 1500 / 25.0  # 1,5 km of village at 50 instead of 90
    assert braking < crawling / 5


def test_an_unknown_vehicle_is_rejected():
    from scripts.speeds import effective_kmh

    with pytest.raises(ValueError, match="unknown vehicle"):
        effective_kmh("tram")


def test_a_link_never_outruns_the_road_it_serves():
    from scripts.speeds import EFFECTIVE_KMH

    for base in ("motorway", "trunk", "primary", "secondary", "tertiary"):
        assert EFFECTIVE_KMH[f"{base}_link"] <= max(EFFECTIVE_KMH[base], 60.0), base


@pytest.mark.parametrize("kmh", EFFECTIVE_KMH.values())
def test_no_speed_is_absurdly_low(kmh):
    """Below 15 km/h a road is not a road; that would be a typo, not a slow lane."""
    assert kmh >= 15

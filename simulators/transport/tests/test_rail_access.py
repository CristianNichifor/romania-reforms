"""Tests for offering the train as an alternative to the bus.

The mode choice has to be an *output* — the faster of two journeys — and never an assumption
about who rides what. Most of these hold that line, and the rest hold the walk-only rule that
decides who is offered a train at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_access import (
    STATION_WALK_KM,
    load_rail_access,
    rail_journey_min,
    train_headway_min,
    walk_min,
)

ROOT = Path(__file__).resolve().parents[1]

NEAR = {"station_km": 1.0, "seat_station_km": 0.5, "rail_km": 60.0}


def test_a_walk_is_longer_than_the_straight_line():
    """Streets are not crow-flies. A walk timed on the straight line would flatter rail."""
    assert walk_min(1.0) > 1.0 / 4.5 * 60


def test_the_journey_is_walk_train_walk():
    minutes = rail_journey_min(NEAR, rail_kmh=60.0, wait=10.0)
    expected = walk_min(1.0) + 10.0 + 60.0 / 60.0 * 60 + walk_min(0.5)
    assert minutes == pytest.approx(expected)


def test_a_far_station_means_no_train():
    """A commune whose station is five kilometres off is not served by the line passing it."""
    far = {**NEAR, "station_km": STATION_WALK_KM + 0.1}
    assert rail_journey_min(far, 60.0, 10.0) is None


def test_a_far_station_at_the_county_seat_also_means_no_train():
    """The condition at the destination end removes a whole county at once, which is the right
    and slightly brutal answer for the five seats whose station sits outside the town."""
    far_seat = {**NEAR, "seat_station_km": STATION_WALK_KM + 0.1}
    assert rail_journey_min(far_seat, 60.0, 10.0) is None


def test_no_rail_path_means_no_train():
    assert rail_journey_min({**NEAR, "rail_km": None}, 60.0, 10.0) is None
    assert rail_journey_min({}, 60.0, 10.0) is None


def test_headway_falls_as_service_rises():
    assert train_headway_min(10, 16) > train_headway_min(20, 16)
    assert train_headway_min(20, 16) == pytest.approx(48.0)


def test_nonsense_service_is_refused():
    with pytest.raises(ValueError):
        train_headway_min(0, 16)
    with pytest.raises(ValueError):
        train_headway_min(20, 0)


def test_missing_rail_build_yields_the_bus_only_simulator():
    """Setting the rail layer aside must return exactly the road model — the property the
    design document asked for, and the only way to measure what rail actually changes."""
    assert load_rail_access(ROOT / "data" / "does-not-exist.parquet") == {}


class TestPublished:
    """Against the built artefact."""

    @staticmethod
    def _doc() -> dict:
        path = ROOT / "data" / "access.json"
        if not path.exists():
            pytest.skip("access not built")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_rail_is_reported_beside_the_bus_figures_not_folded_into_them(self):
        summary = self._doc()["summary"]
        assert "medianPulsedMin" in summary
        assert "medianBestPulsedMin" in summary["rail"]

    def test_taking_the_train_never_makes_a_journey_longer(self):
        """`best` is a minimum over the two, so it cannot exceed either. If it ever did, the
        mode choice would be picking the slower option somewhere."""
        for row in self._doc()["uats"]:
            assert row["bestPulsedMin"] <= row["pulsedMin"] + 1e-9, row["name"]
            if row["railPulsedMin"] is not None:
                assert row["bestPulsedMin"] <= row["railPulsedMin"] + 1e-9, row["name"]

    def test_the_mode_flag_agrees_with_the_times(self):
        for row in self._doc()["uats"]:
            faster = row["railPulsedMin"] is not None and row["railPulsedMin"] < row["pulsedMin"]
            assert row["mode"] == ("rail" if faster else "bus"), row["name"]

    def test_rail_helps_a_minority_and_the_artefact_says_so(self):
        """The shape of the result is the result: few places, large gains. A model claiming
        rail served most of the country would be describing a different country."""
        rail = self._doc()["summary"]["rail"]
        total = self._doc()["summary"]["uats"]
        assert 0 < rail["uatsFasterByRail"] < total / 2
        assert rail["uatsFasterByRail"] <= rail["uatsWithOption"]

    def test_the_walk_only_rule_and_the_missing_cost_are_declared(self):
        ids = {limitation["id"] for limitation in self._doc()["limitations"]}
        assert "trenul-doar-pe-jos" in ids
        assert "trenul-nu-schimba-costul" in ids


def test_a_nan_from_parquet_is_not_a_journey():
    """Regression. A None written into a float column returns from parquet as NaN, and every
    comparison against NaN is False — so an unreachable UAT passed both the None check and the
    distance check, produced a NaN journey, and that NaN then won a min() against a real time.
    Caught by the published-artefact test, not by the unit tests, which is the uncomfortable
    part: nothing in the arithmetic looked wrong."""
    nan = float("nan")
    assert rail_journey_min({**NEAR, "rail_km": nan}, 60.0, 10.0) is None
    assert rail_journey_min({**NEAR, "station_km": nan}, 60.0, 10.0) is None
    assert rail_journey_min({**NEAR, "seat_station_km": nan}, 60.0, 10.0) is None


def _route(serves, km=10.0):
    return {"serves": list(serves), "oneWayKm": km, "tier": "T3"}


def test_a_route_is_only_releasable_if_every_commune_prefers_the_train():
    """The structural point. A feeder serves its whole branch, so one village with a station
    on a branch of eight releases nothing — the bus still runs for the other seven."""
    from scripts.build_access import rail_displacement

    mode = {"a": "rail", "b": "bus", "c": "rail", "d": "rail"}
    out = rail_displacement([_route("ab"), _route("cd")], mode)
    assert out["routesFullyRailServed"] == 1
    assert out["routesPartlyRailServed"] == 1
    assert out["displaceableKmShare"] == pytest.approx(0.5)


def test_a_route_nobody_prefers_the_train_on_is_untouched():
    from scripts.build_access import rail_displacement

    out = rail_displacement([_route("ab")], {"a": "bus", "b": "bus"})
    assert out["routesUntouched"] == 1
    assert out["displaceableKmShare"] == 0.0


def test_a_route_with_no_known_communes_is_skipped_not_counted_as_releasable():
    """An empty `serves` intersection must not read as 'all of them prefer the train', which
    is what `all([])` would give — vacuous truth quietly releasing a route that serves people
    the access model never scored."""
    from scripts.build_access import rail_displacement

    out = rail_displacement([_route("xy")], {"a": "rail"})
    assert out["routesFullyRailServed"] == 0
    assert out["displaceableKmShare"] == 0.0


def test_a_route_without_a_length_does_not_crash_the_bound():
    """One route in the network has no length; it must not take the arithmetic with it."""
    from scripts.build_access import rail_displacement

    out = rail_displacement([{"serves": ["a"], "oneWayKm": None}], {"a": "rail"})
    assert out["routesFullyRailServed"] == 1


def test_the_published_bound_is_small_and_stated():
    """If rail ever appeared to release most of the network, something structural broke."""
    path = ROOT / "data" / "access.json"
    if not path.exists():
        pytest.skip("access not built")
    rail = json.loads(path.read_text(encoding="utf-8"))["summary"]["rail"]
    assert 0 < rail["displaceableKmShare"] < 0.25
    assert rail["routesUntouched"] > rail["routesFullyRailServed"]

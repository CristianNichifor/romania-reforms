"""Tests for the service rule.

Every UAT gets a published timetable. What population changes is how many departures and
where they sit in the day — never whether they can be relied on. Several tests here exist
only to stop that being softened later.
"""

from __future__ import annotations

import dataclasses

import pytest

from scripts.tiers import (
    DAY_PROFILE,
    PERIODS,
    TIERS,
    Service,
    classify,
    service_for,
)


def test_the_three_classes_are_ordered_by_population():
    assert TIERS["basic"].max_population < TIERS["feeder"].max_population


def test_a_small_commune_gets_the_basic_class():
    assert classify(population=800, is_hub=False) == "basic"


def test_a_mid_sized_commune_gets_the_feeder_class():
    assert classify(population=3_000, is_hub=False) == "feeder"


def test_a_large_commune_gets_the_trunk_class():
    assert classify(population=8_000, is_hub=False) == "trunk"


def test_a_hub_is_always_trunk_whatever_its_population():
    """42 of the 249 hubs are communes, the smallest at 1 882 people. A centre that twelve
    UATs feed into needs trunk service regardless of how few people live in it."""
    assert classify(population=1_882, is_hub=True) == "trunk"


def test_the_boundaries_land_on_the_documented_side():
    """Exactly at a threshold, the larger class applies. Pinned because an off-by-one here
    silently moves hundreds of UATs between service levels."""
    assert classify(population=TIERS["basic"].max_population, is_hub=False) == "basic"
    assert classify(population=TIERS["basic"].max_population + 1, is_hub=False) == "feeder"
    assert classify(population=TIERS["feeder"].max_population, is_hub=False) == "feeder"
    assert classify(population=TIERS["feeder"].max_population + 1, is_hub=False) == "trunk"


def test_every_class_runs_a_fixed_published_service():
    """The line in the sand. If any class ever reports that it is not fixed, the flex tier
    has come back and §4 of the design document has been reversed without saying so."""
    for name, tier in TIERS.items():
        assert tier.fixed is True, name


def test_every_class_gets_at_least_one_departure_every_weekday():
    """A published timetable with no departures is not a service."""
    for name in TIERS:
        service = service_for(name)
        assert sum(service.departures.values()) > 0, name


def test_a_smaller_class_never_gets_more_departures():
    basic = sum(service_for("basic").departures.values())
    feeder = sum(service_for("feeder").departures.values())
    trunk = sum(service_for("trunk").departures.values())
    assert basic < feeder < trunk


def test_the_smallest_class_is_placed_on_the_peaks():
    """Four departures spread evenly through the day serve nobody. The point of a small
    service is that it is timed to school and work, so all of it sits in the peaks."""
    service = service_for("basic")
    assert service.departures["am_peak"] > 0
    assert service.departures["pm_peak"] > 0
    assert service.departures["midday"] == 0
    assert service.departures["evening"] == 0


def test_the_trunk_class_runs_across_the_whole_day():
    """A hub with hourly service in the peaks and nothing at midday is not a pulse."""
    service = service_for("trunk")
    for period in ("am_peak", "midday", "pm_peak", "evening"):
        assert service.departures[period] > 0, period


def test_the_day_profile_covers_the_service_day_without_overlap():
    hours = sum(DAY_PROFILE[p] for p in PERIODS)
    assert 14 <= hours <= 18, hours


def test_every_period_has_a_length():
    for period in PERIODS:
        assert DAY_PROFILE[period] > 0, period


def test_departures_are_declared_for_every_period():
    """A period missing from a class's departures would be read as zero by accident rather
    than by decision."""
    for name in TIERS:
        assert set(service_for(name).departures) == set(PERIODS), name


def test_a_bigger_class_gets_a_bigger_vehicle():
    assert service_for("basic").seats < service_for("feeder").seats
    assert service_for("feeder").seats < service_for("trunk").seats


def test_an_unknown_class_is_rejected():
    with pytest.raises(KeyError):
        service_for("flex")


def test_the_service_is_a_plain_value():
    """fleet.py consumes this and must not be able to mutate it back into tiers.py.

    The specific exception matters: a bare `Exception` would pass even if the assignment
    failed for some unrelated reason, which is the opposite of what this checks."""
    service = service_for("basic")
    assert isinstance(service, Service)
    with pytest.raises(dataclasses.FrozenInstanceError):
        service.seats = 99

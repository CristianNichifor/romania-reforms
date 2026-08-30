"""Tests for the fleet arithmetic.

Two numbers come out of the same sum and conflating them under-costs a transit system: the
peak vehicle requirement sizes the fleet and drives capital cost, while bus-hours drive
operating cost and drivers. Most of these tests exist to keep them apart.

A third mistake has its own tests below, because it was made: applying the spare ratio to a
route rather than to a network.
"""

from __future__ import annotations

import pytest

from scripts.fleet import (
    Resources,
    bus_hours,
    fleet_required,
    peak_vehicle_requirement,
    resources_for_route,
    vehicles_for_period,
)

DAY = {"am_peak": 3.0, "midday": 5.0, "pm_peak": 4.0, "evening": 4.0}


def test_one_vehicle_covers_a_round_trip_shorter_than_the_headway():
    """45 minutes of round trip on a 60-minute headway: the bus gets back before it is due
    out again."""
    assert vehicles_for_period(round_trip_min=45, layover_min=10, headway_min=60) == 1


def test_a_longer_round_trip_needs_a_second_vehicle():
    assert vehicles_for_period(round_trip_min=90, layover_min=10, headway_min=60) == 2


def test_the_cycle_rounds_up_to_a_whole_pulse():
    """A 65-minute cycle occupies two hourly intervals."""
    assert vehicles_for_period(round_trip_min=55, layover_min=10, headway_min=60) == 2


def test_an_exact_fit_does_not_buy_a_spare_vehicle():
    """50 + 10 = 60 exactly. An off-by-one here would over-buy a bus on every route."""
    assert vehicles_for_period(round_trip_min=50, layover_min=10, headway_min=60) == 1


def test_no_departures_means_no_vehicles():
    assert vehicles_for_period(round_trip_min=45, layover_min=10, headway_min=0) == 0


def test_the_peak_requirement_is_the_maximum_not_the_sum():
    """The classic under-costing: adding period counts would buy four buses where the same
    two serve morning and afternoon."""
    assert peak_vehicle_requirement({"am_peak": 2, "midday": 1, "pm_peak": 2}) == 2


def test_the_peak_requirement_of_nothing_is_nothing():
    assert peak_vehicle_requirement({}) == 0


def test_bus_hours_sum_across_every_period():
    """Unlike the fleet, hours accumulate: this is what drives drivers and fuel."""
    departures = {"am_peak": 2, "pm_peak": 2}
    hours = bus_hours(departures, round_trip_min=45, departures=departures)
    assert hours == pytest.approx(4 * 45 / 60)


def test_a_peaky_service_owns_more_buses_for_the_same_hours():
    """The ratio the design document asks to be displayed. Same total departures, different
    shape: the peaky one owns more buses to run identical hours."""
    peaky = resources_for_route(
        round_trip_min=60,
        layover_min=10,
        departures={"am_peak": 4, "midday": 0, "pm_peak": 4, "evening": 0},
        period_hours=DAY,
        km_round_trip=30.0,
    )
    flat = resources_for_route(
        round_trip_min=60,
        layover_min=10,
        departures={"am_peak": 2, "midday": 2, "pm_peak": 2, "evening": 2},
        period_hours=DAY,
        km_round_trip=30.0,
    )
    assert peaky.bus_hours == pytest.approx(flat.bus_hours)
    assert peaky.peak_vehicles > flat.peak_vehicles


def test_a_route_does_not_carry_a_fleet_at_all():
    """A fleet is not a property of a route. If `Resources` ever regains a fleet field, the
    spare ratio will start being applied route by route again — see the test below for what
    that costs."""
    assert not hasattr(
        resources_for_route(
            round_trip_min=45,
            layover_min=10,
            departures={"am_peak": 2},
            period_hours=DAY,
            km_round_trip=20.0,
        ),
        "fleet",
    )


def test_the_spare_ratio_is_applied_once_to_a_network():
    assert fleet_required(peak_vehicles=100, spare_ratio=0.15) == 115


def test_the_spare_ratio_rounds_up_to_a_whole_bus():
    """You cannot own a fifth of a bus."""
    assert fleet_required(peak_vehicles=10, spare_ratio=0.15) == 12


def test_applying_the_spare_per_route_would_buy_half_a_country_too_many():
    """The mistake, pinned with the real numbers that exposed it.

    Every feeder route needs one bus, and ceil(1 x 1.15) is 2 — a 100% margin from a 15%
    ratio. Across Romania's 2 895 feeder routes that was 6 809 buses against the 4 502 the
    ratio actually asks for: 2 307 too many, over half again as much fleet."""
    per_route = sum(fleet_required(1, 0.15) for _ in range(2_895))
    once = fleet_required(3_914, 0.15)
    assert per_route > once * 1.2
    assert once == 4_502


def test_a_spare_ratio_of_nothing_owns_exactly_the_peak():
    assert fleet_required(peak_vehicles=3_914, spare_ratio=0.0) == 3_914


def test_bus_km_follow_the_departures():
    result = resources_for_route(
        round_trip_min=45,
        layover_min=10,
        departures={"am_peak": 2, "pm_peak": 3},
        period_hours=DAY,
        km_round_trip=20.0,
    )
    assert result.bus_km == pytest.approx(5 * 20.0)


def test_a_route_with_no_service_costs_nothing():
    result = resources_for_route(
        round_trip_min=45,
        layover_min=10,
        departures={"am_peak": 0},
        period_hours=DAY,
        km_round_trip=20.0,
    )
    assert result.peak_vehicles == 0
    assert result.bus_hours == 0
    assert result.bus_km == 0


def test_the_idle_time_pulse_rounding_buys_is_reported():
    """A 65-minute cycle on an hourly pulse occupies two intervals, so the vehicle spends 55
    of every 120 minutes waiting. That slack is the real price of a clockface timetable.

    Note what it is *not*: padding does not buy an extra vehicle. Vehicles are
    ceil(cycle / headway) whether the cycle is padded or not."""
    result = resources_for_route(
        round_trip_min=55,
        layover_min=10,
        departures={"am_peak": 3},
        period_hours={"am_peak": 3.0},
        km_round_trip=25.0,
    )
    assert result.cycle_slack_min == pytest.approx(55.0)


def test_a_cycle_that_divides_the_headway_wastes_nothing():
    """50 + 10 = 60 exactly on an hourly pulse: never standing idle for want of an interval."""
    result = resources_for_route(
        round_trip_min=50,
        layover_min=10,
        departures={"am_peak": 3},
        period_hours={"am_peak": 3.0},
        km_round_trip=25.0,
    )
    assert result.cycle_slack_min == pytest.approx(0.0)


def test_a_real_feeder_needs_one_bus_and_a_long_one_needs_two():
    """Against the measured distribution: the median UAT is 22,6 minutes from its hub and
    the p90 is 44,6. Those must come out as one bus and two."""
    median = resources_for_route(
        round_trip_min=2 * 22.6,
        layover_min=10,
        departures={"am_peak": 2, "pm_peak": 2},
        period_hours=DAY,
        km_round_trip=30.0,
    )
    p90 = resources_for_route(
        round_trip_min=2 * 44.6,
        layover_min=10,
        departures={"am_peak": 2, "pm_peak": 2},
        period_hours=DAY,
        km_round_trip=60.0,
    )
    assert median.peak_vehicles == 1
    assert p90.peak_vehicles == 2


def test_resources_add_up_across_routes():
    """Hours, kilometres and peaks all add — two routes running at once need two buses,
    whatever either does off-peak."""
    a = Resources(peak_vehicles=2, bus_hours=10.0, bus_km=100.0, cycle_slack_min=0.0)
    b = Resources(peak_vehicles=1, bus_hours=5.0, bus_km=40.0, cycle_slack_min=55.0)
    total = a + b
    assert total.peak_vehicles == 3
    assert total.bus_hours == pytest.approx(15.0)
    assert total.bus_km == pytest.approx(140.0)
    assert total.cycle_slack_min == pytest.approx(55.0)


def test_a_sixteen_hour_vehicle_day_needs_two_duties():
    """The point the fleet count hides: a vehicle out from 06:00 to 22:00 cannot be one person,
    whatever it drives. EU 561/2006 caps daily driving at nine hours and a duty cannot span the
    whole service day."""
    from scripts.fleet import paid_driver_hours

    _, duties = paid_driver_hours(8.0, 16.0, 1.3, 13.0, 6.0, 9.0)
    assert duties == 2
    _, one = paid_driver_hours(8.0, 12.0, 1.3, 13.0, 6.0, 9.0)
    assert one == 1


def test_a_peak_only_route_costs_more_than_its_driving_hours():
    """Three hours of driving across a twelve-hour day, with a five-hour hole in the middle.
    Charging 3 x 1,3 made a peak-concentrated service look cheaper than it is."""
    from scripts.fleet import paid_driver_hours

    hours, _ = paid_driver_hours(3.0, 12.0, 1.3, 13.0, 6.0, 9.0)
    assert hours == 6.0
    assert hours > 3.0 * 1.3


def test_a_solidly_worked_day_falls_back_to_the_ratio():
    from scripts.fleet import paid_driver_hours

    hours, _ = paid_driver_hours(8.0, 10.0, 1.3, 13.0, 6.0, 9.0)
    assert hours == pytest.approx(8.0 * 1.3)


def test_the_span_is_first_departure_to_last():
    from scripts.tiers import duty_span_hours

    assert duty_span_hours({"am_peak": 2, "midday": 0, "pm_peak": 2, "evening": 0}) == 12
    assert duty_span_hours({"am_peak": 3, "midday": 5, "pm_peak": 4, "evening": 4}) == 16
    assert duty_span_hours({"am_peak": 0, "midday": 0, "pm_peak": 0, "evening": 0}) == 0

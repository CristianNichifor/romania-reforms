# Transport L1a — Service Tiers and Fleet Arithmetic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a UAT's population into a published service — a class, a vehicle, and departures placed across the day — and turn a route's duration into the vehicles, bus-hours and bus-km it costs.

**Architecture:** Two pure modules with no geometry and no I/O. `tiers.py` maps population to a service class and a day profile; `fleet.py` turns a round-trip duration into per-period vehicle counts, a peak vehicle requirement, and the resource vector `L2` will price. Both are testable against synthetic routes, which is why they are split from route generation (`L1b`) — that subsystem has its own risks and its own plan.

**Tech Stack:** Python 3.12, `uv`, `ruff`, `pytest`. No new dependencies: this is arithmetic.

---

## Context an engineer needs before starting

**Read first:** `docs/superpowers/specs/2026-08-29-transport-design.md` §4 (the service rule), §6 (pulse and fleet sizing). This plan implements those two sections and nothing else.

**The one thing that must not be softened.** Every UAT gets a **fixed, published** timetable. Nothing in this simulator is booked in advance. What varies with population is how many departures a place receives and where they sit in the day — never whether they can be relied on. An earlier draft of the spec made the smallest tier demand-responsive and it was rejected on the grounds that booking is a barrier falling hardest on exactly the people rural transit exists for. If you find yourself adding a "flex" class, stop and re-read §4.

**Fleet is sized by peak, not average.** This is the other thing the spec is emphatic about. Two numbers fall out of the same arithmetic and conflating them is the classic way to under-cost a transit system:

- **Peak vehicle requirement (PVR)** — the maximum concurrent vehicles across all periods. Sizes the fleet, so it drives CAPEX. A bus bought for the 07:00 peak stands idle at 11:00; that is not waste, it is what being able to serve a peak costs.
- **Bus-hours** — summed across every period. Drives OPEX and driver numbers.

They diverge, and their ratio is an output worth showing.

**Grounding, measured from the real data in this repository** (`data/hubs.json`, administrativ's `uat_geometry.gpkg`). Use these to sanity-check your work; they are why the default thresholds are what they are:

| | |
|---|---|
| non-hub UATs below 2 000 people | 887 (1,25 M people) |
| non-hub UATs 2 000–5 000 | 1 586 (4,96 M) |
| non-hub UATs above 5 000 | 464 (5,14 M) |
| hubs | 249, median population 12 534 |
| UAT → own-hub road time | median 22,6 min, p90 44,6 min |

A median 22,6-minute feeder journey means a ~45-minute round trip plus layover — one vehicle on a 60-minute pulse. At p90 it is ~90 minutes and needs two. Your arithmetic must reproduce that.

**Working directory:** repository root, `romania-reforms-transport/`. Branch `transport-design`.

**Commit messages are prose, not Conventional Commits.** Run `git log --oneline -10` and match.

---

## File Structure

| File | Responsibility |
|---|---|
| `simulators/transport/scripts/tiers.py` | Population → service class, vehicle, departures per period. The service rule, and nothing else. |
| `simulators/transport/scripts/fleet.py` | Round-trip duration + departures → per-period vehicles, PVR, bus-hours, bus-km. The arithmetic, and nothing else. |
| `simulators/transport/tests/test_tiers.py` | |
| `simulators/transport/tests/test_fleet.py` | |

`tiers.py` never sees a duration; `fleet.py` never sees a population. A reader disputing the service standard touches one file; a reader disputing the vehicle arithmetic touches the other. That boundary is the point.

---

### Task 1: The service rule

**Files:**
- Create: `simulators/transport/scripts/tiers.py`
- Create: `simulators/transport/tests/test_tiers.py`

- [ ] **Step 1: Write the failing tests**

Create `simulators/transport/tests/test_tiers.py`:

```python
"""Tests for the service rule.

Every UAT gets a published timetable. What population changes is how many departures and
where they sit in the day — never whether they can be relied on. Several tests here exist
only to stop that being softened later.
"""

from __future__ import annotations

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
    """fleet.py consumes this and must not be able to mutate it back into tiers.py."""
    service = service_for("basic")
    assert isinstance(service, Service)
    with pytest.raises(Exception):
        service.seats = 99
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_tiers.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.tiers'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/tiers.py`:

```python
"""The service rule: what a UAT's population entitles it to.

**Every UAT gets a published timetable.** What population changes is how many departures a
place receives and where they sit in the day. What it never changes is whether those
departures can be relied on — nothing here is booked in advance.

An earlier draft made the smallest tier demand-responsive, on the Danish flextrafik model,
because a clockface timetable to a 200-person village is ruinous. That was rejected. A public
system's first obligation is that it works without arrangement, and booking is a barrier that
falls hardest on exactly the population rural transit exists for: the elderly, people without
smartphones, people making unplanned trips. The cost objection is real and is answered by
**frequency**, not by responsiveness — a small commune does not need an hourly bus, it needs
four departures that always run.

The thresholds are inputs a reader may move. The structure — three classes, all fixed and
published — is not.

Grounded on the real distribution: of the 2 937 UATs that are not hubs, 887 fall below 2 000
people, 1 586 sit between 2 000 and 5 000, and 464 are above. The thresholds sit on those
breaks rather than on round numbers chosen for their roundness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# The service day, in hours per period. Weekend is deliberately absent: it is a separate
# profile in L1b, not a period of the weekday.
PERIODS: Final[tuple[str, ...]] = ("am_peak", "midday", "pm_peak", "evening")

DAY_PROFILE: Final[dict[str, float]] = {
    "am_peak": 3.0,   # 06:00-09:00
    "midday": 5.0,    # 09:00-14:00
    "pm_peak": 4.0,   # 14:00-18:00
    "evening": 4.0,   # 18:00-22:00
}


@dataclass(frozen=True)
class Tier:
    """A service class. `fixed` exists so that a flex tier cannot be added quietly."""

    name: str
    max_population: int
    fixed: bool


@dataclass(frozen=True)
class Service:
    """What a class actually runs: a vehicle, and departures placed across the day."""

    tier: str
    seats: int
    departures: dict[str, int]


TIERS: Final[dict[str, Tier]] = {
    "basic": Tier("basic", max_population=2_000, fixed=True),
    "feeder": Tier("feeder", max_population=5_000, fixed=True),
    # No ceiling: everything above the feeder threshold, and every hub.
    "trunk": Tier("trunk", max_population=2**31, fixed=True),
}

# Departures per period, one direction. All fixed, all published.
#
# `basic` is four a day and every one of them is on a peak. Four departures spread evenly
# through the day would serve nobody; timed to school and work they serve most of the trips
# a small commune actually makes.
SERVICES: Final[dict[str, Service]] = {
    "basic": Service(
        tier="basic",
        seats=20,
        departures={"am_peak": 2, "midday": 0, "pm_peak": 2, "evening": 0},
    ),
    "feeder": Service(
        tier="feeder",
        seats=40,
        departures={"am_peak": 3, "midday": 2, "pm_peak": 3, "evening": 1},
    ),
    # Hourly across the service day: the pulse the feeders are timed to meet.
    "trunk": Service(
        tier="trunk",
        seats=50,
        departures={"am_peak": 3, "midday": 5, "pm_peak": 4, "evening": 4},
    ),
}


def classify(population: int, is_hub: bool) -> str:
    """Which service class a UAT falls into.

    A hub is always trunk whatever its population. 42 of the 249 hubs are communes and the
    smallest has 1 882 people, but a centre that twelve UATs feed into carries their
    transfers, not only its own residents.
    """
    if is_hub:
        return "trunk"
    if population <= TIERS["basic"].max_population:
        return "basic"
    if population <= TIERS["feeder"].max_population:
        return "feeder"
    return "trunk"


def service_for(tier: str) -> Service:
    """The service a class runs. Raises on an unknown class rather than inventing one."""
    return SERVICES[tier]
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd simulators/transport && uv run pytest tests/test_tiers.py -q
```

Expected: all pass.

- [ ] **Step 5: Sanity-check the rule against the real data**

Not a test — a look. Run this and confirm the class mix is credible:

```bash
cd simulators/transport && uv run python -c "
import json, collections, geopandas as gpd
from scripts.tiers import classify
hub=json.load(open('data/hubs.json'))['hubOf']
u=gpd.read_file('../administrativ/data/processed/uat_geometry.gpkg', layer='uat')
mix=collections.Counter(classify(int(r.population), hub.get(r.siruta)==r.siruta) for r in u.itertuples())
print(mix)
"
```

Expected roughly: `basic` ~890, `feeder` ~1 590, `trunk` ~710 (464 large UATs plus 249 hubs, less overlap). If `basic` comes out near zero or over 2 000, a threshold is wrong.

- [ ] **Step 6: Lint and commit**

```bash
cd simulators/transport && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/tiers.py simulators/transport/tests/test_tiers.py
git commit -m "Give every UAT a published timetable, sized by population

Three classes, all fixed. What population changes is how many departures
a place gets and where they sit in the day; what it never changes is
whether they can be relied on.

The smallest class is four departures and all four are on a peak. Spread
evenly through the day they would serve nobody; timed to school and work
they cover most of the trips a small commune makes. That is the answer to
the cost objection that once motivated a book-ahead tier — frequency, not
responsiveness.

Thresholds sit on the real distribution rather than on round numbers: of
the 2.937 UATs that are not hubs, 887 fall below 2.000 people and 1.586
sit between 2.000 and 5.000. A hub is trunk whatever its population,
because 42 of the 249 are communes and the smallest has 1.882 people
while carrying twelve UATs' transfers."
```

Append the two trailer lines used across this branch (`Co-Authored-By:` and `Claude-Session:`); copy them from `git log -1 --format=%b`.

---

### Task 2: Fleet arithmetic

**Files:**
- Create: `simulators/transport/scripts/fleet.py`
- Create: `simulators/transport/tests/test_fleet.py`

- [ ] **Step 1: Write the failing tests**

Create `simulators/transport/tests/test_fleet.py`:

```python
"""Tests for the fleet arithmetic.

Two numbers come out of the same sum and conflating them under-costs a transit system: the
peak vehicle requirement sizes the fleet and drives capital cost, while bus-hours drive
operating cost and drivers. Most of these tests exist to keep them apart.
"""

from __future__ import annotations

import pytest

from scripts.fleet import (
    Resources,
    bus_hours,
    peak_vehicle_requirement,
    resources_for_route,
    vehicles_for_period,
)


def test_one_vehicle_covers_a_round_trip_shorter_than_the_headway():
    """45 minutes of round trip on a 60-minute headway: the bus gets back before it is due
    out again."""
    assert vehicles_for_period(round_trip_min=45, layover_min=10, headway_min=60) == 1


def test_a_longer_round_trip_needs_a_second_vehicle():
    """90 minutes plus layover cannot be covered by one bus on an hourly headway."""
    assert vehicles_for_period(round_trip_min=90, layover_min=10, headway_min=60) == 2


def test_the_cycle_rounds_up_to_a_whole_pulse():
    """Under a pulse the cycle must fit a whole number of intervals, so a 65-minute cycle
    occupies two. That rounding is what occasionally buys an extra vehicle, and the design
    document is explicit that it must be visible rather than absorbed."""
    assert vehicles_for_period(round_trip_min=55, layover_min=10, headway_min=60) == 2


def test_an_exact_fit_does_not_buy_a_spare_vehicle():
    """50 + 10 = 60 exactly. An off-by-one here would over-buy a bus on every route."""
    assert vehicles_for_period(round_trip_min=50, layover_min=10, headway_min=60) == 1


def test_no_departures_means_no_vehicles():
    assert vehicles_for_period(round_trip_min=45, layover_min=10, headway_min=0) == 0


def test_the_peak_requirement_is_the_maximum_not_the_sum():
    """The classic under-costing: adding period vehicle counts would buy four buses where
    the same two serve morning and afternoon."""
    assert peak_vehicle_requirement({"am_peak": 2, "midday": 1, "pm_peak": 2}) == 2


def test_the_peak_requirement_of_nothing_is_nothing():
    assert peak_vehicle_requirement({}) == 0


def test_bus_hours_sum_across_every_period():
    """Unlike the fleet, hours accumulate: this is what drives drivers and fuel."""
    hours = bus_hours({"am_peak": 2, "pm_peak": 2}, round_trip_min=45, departures={"am_peak": 2, "pm_peak": 2})
    assert hours == pytest.approx(4 * 45 / 60)


def test_a_peaky_service_costs_more_fleet_per_bus_hour_than_a_flat_one():
    """The ratio the design document asks to be displayed. Same total departures, different
    shape: the peaky one owns more buses to run the same hours."""
    peaky = resources_for_route(
        round_trip_min=60, layover_min=10, departures={"am_peak": 4, "midday": 0, "pm_peak": 4, "evening": 0},
        period_hours={"am_peak": 3.0, "midday": 5.0, "pm_peak": 4.0, "evening": 4.0},
        km_round_trip=30.0, spare_ratio=0.0,
    )
    flat = resources_for_route(
        round_trip_min=60, layover_min=10, departures={"am_peak": 2, "midday": 2, "pm_peak": 2, "evening": 2},
        period_hours={"am_peak": 3.0, "midday": 5.0, "pm_peak": 4.0, "evening": 4.0},
        km_round_trip=30.0, spare_ratio=0.0,
    )
    assert peaky.bus_hours == pytest.approx(flat.bus_hours)
    assert peaky.fleet > flat.fleet


def test_the_spare_ratio_is_applied_to_the_peak_not_to_the_hours():
    """Spares exist so a breakdown does not cancel a published departure. They are vehicles,
    not driving time, so they must not inflate operating cost."""
    without = resources_for_route(
        round_trip_min=45, layover_min=10, departures={"am_peak": 2, "pm_peak": 2},
        period_hours={"am_peak": 3.0, "pm_peak": 4.0}, km_round_trip=20.0, spare_ratio=0.0,
    )
    with_spare = resources_for_route(
        round_trip_min=45, layover_min=10, departures={"am_peak": 2, "pm_peak": 2},
        period_hours={"am_peak": 3.0, "pm_peak": 4.0}, km_round_trip=20.0, spare_ratio=0.2,
    )
    assert with_spare.fleet > without.fleet
    assert with_spare.bus_hours == pytest.approx(without.bus_hours)
    assert with_spare.bus_km == pytest.approx(without.bus_km)


def test_the_spare_ratio_always_rounds_up_to_a_whole_bus():
    """You cannot own a fifth of a bus. Rounding down would make the spare ratio vanish on
    every small route, which is most of them."""
    result = resources_for_route(
        round_trip_min=45, layover_min=10, departures={"am_peak": 1},
        period_hours={"am_peak": 3.0}, km_round_trip=20.0, spare_ratio=0.1,
    )
    assert result.fleet == 2


def test_bus_km_follow_the_departures():
    result = resources_for_route(
        round_trip_min=45, layover_min=10, departures={"am_peak": 2, "pm_peak": 3},
        period_hours={"am_peak": 3.0, "pm_peak": 4.0}, km_round_trip=20.0, spare_ratio=0.0,
    )
    assert result.bus_km == pytest.approx(5 * 20.0)


def test_a_route_with_no_service_costs_nothing():
    result = resources_for_route(
        round_trip_min=45, layover_min=10, departures={"am_peak": 0},
        period_hours={"am_peak": 3.0}, km_round_trip=20.0, spare_ratio=0.2,
    )
    assert result.fleet == 0 and result.bus_hours == 0 and result.bus_km == 0


def test_the_idle_time_pulse_rounding_buys_is_reported():
    """A 65-minute cycle on an hourly pulse occupies two intervals, so the vehicle spends 55
    of every 120 minutes waiting. That slack is the real price of a clockface timetable and
    the design document requires it visible rather than absorbed.

    Note what it is *not*: padding does not buy an extra vehicle. Vehicles are
    ceil(cycle / headway) whether the cycle is padded or not, because padded/headway is that
    same ceiling. An earlier draft claimed otherwise and was wrong."""
    result = resources_for_route(
        round_trip_min=55, layover_min=10, departures={"am_peak": 3},
        period_hours={"am_peak": 3.0}, km_round_trip=25.0, spare_ratio=0.0,
    )
    assert result.cycle_slack_min == pytest.approx(55.0)


def test_a_cycle_that_divides_the_headway_wastes_nothing():
    """50 + 10 = 60 exactly on an hourly pulse: the bus is never standing idle for want of a
    whole interval. If this reports slack, the padding arithmetic is off by a rounding."""
    result = resources_for_route(
        round_trip_min=50, layover_min=10, departures={"am_peak": 3},
        period_hours={"am_peak": 3.0}, km_round_trip=25.0, spare_ratio=0.0,
    )
    assert result.cycle_slack_min == pytest.approx(0.0)


def test_a_real_feeder_needs_one_bus_and_a_long_one_needs_two():
    """Against the measured distribution: the median UAT is 22,6 minutes from its hub and
    the p90 is 44,6. Those must come out as one bus and two."""
    median = resources_for_route(
        round_trip_min=2 * 22.6, layover_min=10, departures={"am_peak": 2, "pm_peak": 2},
        period_hours={"am_peak": 3.0, "pm_peak": 4.0}, km_round_trip=30.0, spare_ratio=0.0,
    )
    p90 = resources_for_route(
        round_trip_min=2 * 44.6, layover_min=10, departures={"am_peak": 2, "pm_peak": 2},
        period_hours={"am_peak": 3.0, "pm_peak": 4.0}, km_round_trip=60.0, spare_ratio=0.0,
    )
    assert median.fleet == 1
    assert p90.fleet == 2


def test_resources_add_up_across_routes():
    """A network is the sum of its routes for hours and km — but the fleet is the sum of
    peaks, because two routes running at once need two buses even off-peak."""
    a = Resources(fleet=2, peak_vehicles=2, bus_hours=10.0, bus_km=100.0, cycle_slack_min=0.0)
    b = Resources(fleet=1, peak_vehicles=1, bus_hours=5.0, bus_km=40.0, cycle_slack_min=55.0)
    total = a + b
    assert total.fleet == 3
    assert total.bus_hours == pytest.approx(15.0)
    assert total.bus_km == pytest.approx(140.0)
    assert total.cycle_slack_min == pytest.approx(55.0)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd simulators/transport && uv run pytest tests/test_fleet.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.fleet'`.

- [ ] **Step 3: Write the implementation**

Create `simulators/transport/scripts/fleet.py`:

```python
"""Vehicles, hours and kilometres for a route, period by period.

Two numbers come out of the same arithmetic and conflating them is the classic way to
under-cost a transit system:

- **Peak vehicle requirement** — the maximum concurrent vehicles across the day. This sizes
  the fleet and therefore the capital cost. A bus bought for the 07:00 peak stands in the
  depot at 11:00; that is not waste, it is what being able to serve a peak costs, and a
  system owning only its average fleet cannot serve a peak at all.
- **Bus-hours** — summed across every period. These drive operating cost and driver numbers.

They diverge, and the ratio between them is itself worth showing: a peaky service carries a
high fleet cost per bus-hour, a flat one a low one. A reader flattening the day profile can
watch operating cost rise while capital cost falls, which is the actual trade an authority
faces.

**Spares are vehicles, not driving time.** A bus under repair cannot run a published
departure, so a system owning exactly its peak requirement will cancel service routinely. The
spare ratio therefore lifts the fleet and must never touch the hours.

This module knows nothing about geography or population. It takes a duration and a count of
departures. That boundary is deliberate: a reader disputing the service standard argues with
`tiers.py`, and a reader disputing the vehicle arithmetic argues with this.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

# Minutes a vehicle stands at the end of a run before starting back: driver relief, recovery
# from a late arrival, and — at a hub — the dwell that lets a feeder meet the trunk.
DEFAULT_LAYOVER_MIN: Final[float] = 10.0


@dataclass(frozen=True)
class Resources:
    """What one route, or a whole network, costs in vehicles, time and distance."""

    fleet: int
    peak_vehicles: int
    bus_hours: float
    bus_km: float
    cycle_slack_min: float

    def __add__(self, other: Resources) -> Resources:
        """Hours and kilometres add. So does the fleet — two routes running at the same time
        need two buses, whatever either does off-peak."""
        return Resources(
            fleet=self.fleet + other.fleet,
            peak_vehicles=self.peak_vehicles + other.peak_vehicles,
            bus_hours=self.bus_hours + other.bus_hours,
            bus_km=self.bus_km + other.bus_km,
            cycle_slack_min=self.cycle_slack_min + other.cycle_slack_min,
        )


def vehicles_for_period(round_trip_min: float, layover_min: float, headway_min: float) -> int:
    """Vehicles needed to hold a headway, with the cycle rounded up to a whole pulse.

    Under a pulse the cycle must occupy a whole number of intervals, so a 65-minute cycle on
    an hourly headway occupies two. That rounding sometimes buys a vehicle, and the design
    document requires it to be visible rather than absorbed — see `pulse_penalty` below.
    """
    if headway_min <= 0:
        return 0
    cycle = round_trip_min + layover_min
    return max(1, math.ceil(cycle / headway_min))


def cycle_slack(round_trip_min: float, layover_min: float, headway_min: float) -> float:
    """Minutes a vehicle stands idle because the cycle does not fill a whole pulse.

    This is what clockface running actually costs, and it is not what an earlier draft
    claimed. Padding does **not** buy an extra vehicle: vehicles are `ceil(cycle / headway)`
    whether the cycle is padded or not, because the padded cycle divided by the headway is
    that same ceiling. What padding buys is waiting — a 65-minute cycle on an hourly pulse
    occupies two intervals and leaves the bus standing for 55 of every 120 minutes.

    Reporting it as idle minutes is both true and more useful than a vehicle count: it says
    how much of the fleet's paid time the timetable's shape is spending on nothing.
    """
    if headway_min <= 0:
        return 0.0
    cycle = round_trip_min + layover_min
    padded = math.ceil(cycle / headway_min) * headway_min
    return padded - cycle


def peak_vehicle_requirement(per_period: dict[str, int]) -> int:
    """The maximum, never the sum. Adding period counts would buy four buses where the same
    two serve both the morning and the afternoon."""
    return max(per_period.values(), default=0)


def bus_hours(
    per_period: dict[str, int], round_trip_min: float, departures: dict[str, int]
) -> float:
    """Driving time across the whole day. Unlike the fleet, this accumulates."""
    total_departures = sum(departures.values())
    return total_departures * round_trip_min / 60.0


def resources_for_route(
    round_trip_min: float,
    layover_min: float,
    departures: dict[str, int],
    period_hours: dict[str, float],
    km_round_trip: float,
    spare_ratio: float,
) -> Resources:
    """Everything one route costs, from its duration and its published departures."""
    if sum(departures.values()) == 0:
        return Resources(0, 0, 0.0, 0.0, 0)

    per_period: dict[str, int] = {}
    slack = 0.0
    for period, count in departures.items():
        if count <= 0:
            per_period[period] = 0
            continue
        hours = period_hours.get(period, 0.0)
        headway = (hours * 60.0 / count) if hours > 0 else 0.0
        per_period[period] = vehicles_for_period(round_trip_min, layover_min, headway)
        # The worst period's slack, not the sum: it describes the shape of the cycle against
        # the pulse, and adding it across periods would count the same standing bus twice.
        slack = max(slack, cycle_slack(round_trip_min, layover_min, headway))

    peak = peak_vehicle_requirement(per_period)
    return Resources(
        fleet=math.ceil(peak * (1 + spare_ratio)),
        peak_vehicles=peak,
        bus_hours=bus_hours(per_period, round_trip_min, departures),
        bus_km=sum(departures.values()) * km_round_trip,
        cycle_slack_min=slack,
    )
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd simulators/transport && uv run pytest tests/test_fleet.py -q
```

Expected: all pass.

- [ ] **Step 5: Whole suite, lint, commit**

```bash
cd simulators/transport && PYTHONHASHSEED=0 uv run pytest -q && uv run ruff check scripts tests && uv run ruff format --check scripts tests
cd "$(git rev-parse --show-toplevel)"
git add simulators/transport/scripts/fleet.py simulators/transport/tests/test_fleet.py
git commit -m "Size the fleet by the peak, and the hours by the day

Two numbers come out of one sum and conflating them under-costs a transit
system. The peak vehicle requirement sizes the fleet and drives capital
cost; bus-hours sum across every period and drive operating cost and
drivers. A peaky service owns more buses to run the same hours, and that
ratio is an output rather than an accident.

Spares lift the fleet and never the hours. A bus in the workshop cannot
run a published departure, so a system owning exactly its peak will
cancel service; a spare is a vehicle, not driving time.

Clockface running is priced as the idle minutes it actually costs. An
earlier draft said the rounding buys an extra vehicle; it does not —
vehicles are ceil(cycle/headway) whether the cycle is padded or not,
because the padded cycle over the headway is that same ceiling. What
padding buys is waiting, and a 65-minute cycle on an hourly pulse leaves
the bus standing 55 minutes in every 120."
```

---

## Self-Review

**Spec coverage.** §4 (the service rule, three fixed classes, thresholds as inputs) is Task 1. §6 (pulse, PVR, spare ratio, the visible rounding penalty) is Task 2. The day profile that §4 introduces is in Task 1 and consumed by Task 2.

**Deliberately out of scope, and why.** Route generation, corridor merging, and the 42 UATs that cannot reach their own hub by road are `L1b` — a separate subsystem with its own determinism risks, and one that needs geometry these two modules are defined to avoid. Cost in lei is `L2`; this plan stops at the resource vector because that is exactly what `L2` consumes. Rail is `LR`.

**Grounding rather than invention.** Every threshold and expectation in this plan is measured from data in the repository: the population bands from `uat_geometry.gpkg` against `hubs.json`, the one-bus/two-bus expectation from the measured 22,6-minute median and 44,6-minute p90 UAT-to-hub times. `test_a_real_feeder_needs_one_bus_and_a_long_one_needs_two` exists so the arithmetic is checked against the country rather than only against itself.

**A correction this plan makes to the spec.** Design document §6 says that rounding the cycle up to a whole pulse "sometimes buys an extra vehicle". **It does not.** Vehicles are `ceil(cycle / headway)` with or without padding, because the padded cycle divided by the headway is that same ceiling — checked numerically before this plan was committed. What padding buys is **idle time**: a 65-minute cycle on an hourly pulse occupies two intervals and leaves the vehicle standing 55 minutes in every 120, 46% of its paid time.

The first draft of this plan carried the error forward into a `pulse_penalty` function whose leading term was also dead code — `ceil(x) - ceil(x - 1e-9)` is always zero. Both are replaced by `cycle_slack`, which reports the minutes. §6 of the spec should be corrected to match; it is the reason to read this paragraph before writing `L2`, because a cost model that expects a vehicle count from this field will find minutes.

**Remaining weak point.** `cycle_slack` takes the *worst* period rather than summing across periods, on the reasoning that slack describes the shape of a cycle against the pulse and adding it would count the same standing bus more than once. That is a judgement, not an identity, and it is the thing in this plan most worth arguing with.

**Type consistency.** `Service.departures` is `dict[str, int]` keyed by `PERIODS`, and `resources_for_route` takes `departures` and `period_hours` on those same keys. `Resources` is returned by `resources_for_route` and added by `__add__`. `classify` returns a key of `TIERS`, which `service_for` accepts.

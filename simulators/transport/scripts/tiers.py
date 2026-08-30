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

# When each period starts and ends on the clock. The profile gives lengths; a duty needs
# times, because what decides how many drivers a vehicle needs is not how long it runs but how
# far apart its first and last departures are.
PERIOD_CLOCK: Final[dict[str, tuple[float, float]]] = {
    "am_peak": (6.0, 9.0),
    "midday": (9.0, 14.0),
    "pm_peak": (14.0, 18.0),
    "evening": (18.0, 22.0),
}

DAY_PROFILE: Final[dict[str, float]] = {
    "am_peak": 3.0,  # 06:00-09:00
    "midday": 5.0,  # 09:00-14:00
    "pm_peak": 4.0,  # 14:00-18:00
    "evening": 4.0,  # 18:00-22:00
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


def duty_span_hours(departures: dict[str, int]) -> float:
    """Hours from the first departure of the day to the last.

    Four departures placed on the peaks is a twelve-hour day, not a three-hour one, and the
    day is what has to be staffed.
    """
    live = [p for p, count in departures.items() if count > 0]
    if not live:
        return 0.0
    start = min(PERIOD_CLOCK[p][0] for p in live if p in PERIOD_CLOCK)
    end = max(PERIOD_CLOCK[p][1] for p in live if p in PERIOD_CLOCK)
    return max(0.0, end - start)

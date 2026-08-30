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
    """What one route, or a whole network, costs in vehicles, time and distance.

    There is deliberately no `fleet` here. A fleet is not a property of a route: spares are a
    depot float covering many routes, and applying a ratio route by route buys one for every
    village shuttle. Use `fleet_required` on a network total — see its docstring for what
    that mistake cost when it was made.
    """

    peak_vehicles: int
    bus_hours: float
    bus_km: float
    cycle_slack_min: float

    def __add__(self, other: Resources) -> Resources:
        """Hours and kilometres add, and so do peak vehicles — two routes running at the same
        time need two buses, whatever either does off-peak."""
        return Resources(
            peak_vehicles=self.peak_vehicles + other.peak_vehicles,
            bus_hours=self.bus_hours + other.bus_hours,
            bus_km=self.bus_km + other.bus_km,
            cycle_slack_min=self.cycle_slack_min + other.cycle_slack_min,
        )


def fleet_required(peak_vehicles: int, spare_ratio: float) -> int:
    """Buses to own, so that a vehicle in the workshop does not cancel a departure.

    **Applied once, to a network total.** Applying it per route and rounding up buys a spare
    for every single-bus service: `ceil(1 x 1.15)` is 2, a 100% margin from a 15% ratio.
    Measured on the real country the difference was 6 809 buses against 4 502 — 2 307 too
    many, over half again as much fleet as the ratio asks for.

    Spares are a depot float. One workshop bus covers many routes, which is the whole reason
    the ratio is a fraction rather than a per-service allowance.
    """
    return math.ceil(peak_vehicles * (1 + spare_ratio))


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
) -> Resources:
    """Everything one route costs, from its duration and its published departures.

    No spare ratio: see `fleet_required`. A route's peak is a real quantity; a route's share
    of the workshop float is not.
    """
    if sum(departures.values()) == 0:
        return Resources(0, 0.0, 0.0, 0.0)

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

    return Resources(
        peak_vehicles=peak_vehicle_requirement(per_period),
        bus_hours=bus_hours(per_period, round_trip_min, departures),
        bus_km=sum(departures.values()) * km_round_trip,
        cycle_slack_min=slack,
    )

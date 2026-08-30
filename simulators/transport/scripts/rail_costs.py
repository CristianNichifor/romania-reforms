"""Train-km and train-hours into lei, and what a minute of journey time costs to buy.

Same split as `costs.py`, for the same reason: operating cost scales with what the trains do,
capital with how many must exist and how much track was renewed to let them.

- **per train-km** — track access (TUI), traction energy, rolling-stock maintenance.
- **per train-hour** — the crew.
- **per unit-year** — the train itself, annualised.
- **per route-km, once** — rehabilitation, annualised over the life of the renewal.

**Three of the big numbers here are Romanian and verbatim**, which the road model never managed:
CFR publishes its access tariff in the network statement, and both the rolling stock and the
rehabilitation contracts are public procurements with signed values. Where the bus model has to
reason from a European benchmark and a wage ratio, this can read the price off a contract.

**The tariff already knows about track condition.** CFR bands its network A to D by the weighted
mean of maximum permitted speed *including permanent restrictions*, and charges 3,45 lei/train-km
on the best band against 1,48 on the worst. So a worn line is cheaper to run on and slower — the
tariff pays you to accept the restriction. That is a genuine and slightly perverse property of
the system, and it means rehabilitation must buy back more in time than it adds in tariff.

**What this is for.** §8 of the design document claims the cheapest new transit capacity in
Romania may be track already lying in the ground. `cost_per_passenger_hour_saved` turns that
into a number, and the answer can be compared against the cheapest thing the bus network can do
with the same money — which is not more buses, but coordinating the timetable it already runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from scripts.rail_speeds import class_commercial_kmh

ROOT = Path(__file__).resolve().parents[1]
RAIL_COST_INPUTS = ROOT / "data" / "rail-cost-inputs.json"

# Same operating year as the road model, so the two can be added.
WEEKDAYS_PER_YEAR: Final[int] = 250

# Trains per weekday on a reference regional service. Lives here rather than in a build script
# because two consumers need it: the cost model prices this many trains, and the access model
# derives from it the headway a passenger waits. Two copies would let the service that is priced
# drift away from the service that is timetabled, with nothing to say so.
REFERENCE_TRAINS_PER_WEEKDAY: Final[int] = 20

# CFR's own line bands, from Anexa 25.a art. 6, keyed by the upper bound of the speed regime.
# Bands rather than a curve because that is how the tariff is actually written: a line at
# 91 km/h and one at 120 pay the same access charge.
LINE_CLASS_BANDS: Final[tuple[tuple[float, str], ...]] = (
    (50.0, "D"),
    (90.0, "C"),
    (120.0, "B"),
    (160.0, "A"),
)


def line_class(line_kmh: float) -> str:
    """CFR line class for a signed speed.

    Anything above the top band is still class A: 160 km/h is the ceiling of the tariff table,
    not of physics, and a faster line does not fall off the end into free access.
    """
    for ceiling, name in LINE_CLASS_BANDS:
        if line_kmh <= ceiling:
            return name
    return "A"


@dataclass(frozen=True)
class RailPrices:
    """Unit prices, resolved into the four rates the model needs."""

    per_train_hour: float
    tui_by_class: dict[str, float]
    energy_per_km: float
    maintenance_per_unit_year: float
    unit_price: float
    unit_life_years: float
    rehabilitation_per_km: float
    rehabilitation_life_years: float
    seats: int


@dataclass(frozen=True)
class RailCost:
    """A year of rail cost, in lei, kept in the pieces it was built from."""

    crew_ron: float
    access_ron: float
    energy_ron: float
    maintenance_ron: float
    capital_ron: float
    infrastructure_ron: float

    @property
    def operating_ron(self) -> float:
        return self.crew_ron + self.access_ron + self.energy_ron + self.maintenance_ron

    @property
    def total_ron(self) -> float:
        return self.operating_ron + self.capital_ron + self.infrastructure_ron


def load_rail_prices(path: Path = RAIL_COST_INPUTS) -> RailPrices:
    """Resolve the data file into rates."""
    document = json.loads(path.read_text(encoding="utf-8"))
    item = {name: entry["value"] for name, entry in document["items"].items()}

    employer_monthly = item["driverGrossMonthly"] * (1 + item["employerContributionRate"])
    per_paid_hour = employer_monthly / item["crewPaidHoursMonth"]
    per_train_hour = per_paid_hour * item["platformToPaidRatio"] * item["trainCrewSize"]

    # The tonnage modulation, applied once: TUI = Tsn x [1 + (gross - Tmin) x Ft], plus the
    # electrification element for an electric train.
    modulation = 1 + (item["emuGrossTonnes"] - item["tuiTminTonnes"]) * item["tuiFt"]
    tui = {
        name: item[f"tuiTsnClass{name}"] * modulation + item["tuiTtse"]
        for name in ("A", "B", "C", "D")
    }

    return RailPrices(
        per_train_hour=per_train_hour,
        tui_by_class=tui,
        energy_per_km=item["energyKwhPerKm"] * item["energyPriceRonKwh"],
        maintenance_per_unit_year=item["emuMaintenanceRonYear"],
        unit_price=item["emuPriceRon"],
        unit_life_years=item["emuLifeYears"],
        rehabilitation_per_km=item["rehabilitationRonPerKm"],
        rehabilitation_life_years=item["rehabilitationLifeYears"],
        seats=int(item["emuSeats"]),
    )


def annual_rail_cost(
    train_km_per_weekday: float,
    train_hours_per_weekday: float,
    units: int,
    prices: RailPrices,
    line_kmh: float,
    rehabilitated_km: float = 0.0,
    weekdays: int = WEEKDAYS_PER_YEAR,
) -> RailCost:
    """A year of cost for a service, and for any track renewed to run it."""
    access_rate = prices.tui_by_class[line_class(line_kmh)]
    return RailCost(
        crew_ron=train_hours_per_weekday * weekdays * prices.per_train_hour,
        access_ron=train_km_per_weekday * weekdays * access_rate,
        energy_ron=train_km_per_weekday * weekdays * prices.energy_per_km,
        maintenance_ron=units * prices.maintenance_per_unit_year,
        capital_ron=units * prices.unit_price / prices.unit_life_years,
        infrastructure_ron=(
            rehabilitated_km * prices.rehabilitation_per_km / prices.rehabilitation_life_years
        ),
    )


def cost_per_passenger_hour_saved(
    line_km: float,
    trains_per_weekday: int,
    passengers_per_train: int,
    prices: RailPrices,
    weekdays: int = WEEKDAYS_PER_YEAR,
) -> dict[str, float]:
    """What an hour of passenger time costs to buy by rehabilitating a line.

    The comparison §8 asks for. Renewal moves a line from the speed its condition permits to the
    speed its alignment permits, which saves every passenger on every train a slice of time, for
    ever. Against that stands the annualised cost of the renewal *plus* the higher access tariff
    the better line attracts — CFR charges more for good track, so the tariff partly claws back
    what the renewal buys.

    Returned per passenger-hour so it can be set beside anything else that buys time.
    """
    if line_km <= 0 or trains_per_weekday <= 0 or passengers_per_train <= 0:
        raise ValueError("line length, service and loading must all be positive")

    slow = class_commercial_kmh("as_is")
    fast = class_commercial_kmh("rehabilitated")
    hours_saved_per_trip = line_km / slow - line_km / fast
    passenger_hours = hours_saved_per_trip * trains_per_weekday * passengers_per_train * weekdays

    annual_capital = line_km * prices.rehabilitation_per_km / prices.rehabilitation_life_years
    # The renewed line moves up a band, so the access charge rises with it.
    train_km = line_km * trains_per_weekday * weekdays
    extra_access = train_km * (
        prices.tui_by_class[line_class(fast)] - prices.tui_by_class[line_class(slow)]
    )

    total = annual_capital + extra_access
    return {
        "hoursSavedPerTrip": hours_saved_per_trip,
        "passengerHoursPerYear": passenger_hours,
        "annualCapitalRon": annual_capital,
        "extraAccessRon": extra_access,
        "ronPerPassengerHour": total / passenger_hours,
    }

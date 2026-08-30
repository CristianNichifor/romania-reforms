"""Bus-hours and bus-km into lei.

Pure arithmetic over `data/cost-inputs.json`. No geography, no service standard, no network —
a reader disputing the price of a driver-hour argues here and with the data file; one disputing
how many hours there are argues with `fleet.py`; one disputing the standard that generates them
argues with `tiers.py`. None of them has to accept the others to make their case.

**The split that matters.** Operating cost scales with what the buses do; capital cost scales
with how many of them must exist. They are driven by different numbers and behave differently
under every lever a reader can pull:

- **per paid driver-hour** — the driver, who is staffed against the vehicle's DAY rather than
  its driving: a bus out from 06:00 to 22:00 needs two duties however little it moves.
- **per bus-km** — fuel, tyres, the parts that wear.
- **per vehicle-year** — insurance and depot, owed whether the bus moves or not.
- **capital** — the vehicles themselves, annualised over their life.

Flatten a peaky timetable and operating cost rises while capital falls. Fold them into one
figure per bus-hour and that trade disappears, which is how a transit system gets costed wrong
in a way nobody can see.

**A driver is paid for more hours than the bus runs.** Sign-on, breaks and deadhead mean paid
hours exceed platform hours by the `platformToPaidRatio`; costing a driver at bus-hours alone
would understate the largest single line by roughly a third.

**This module produces cost, not subsidy.** What comes out here is what the service costs to
run. Fares and the residual public contribution are a separate layer — `build_fares.py` and
`data/fares.json` — deliberately downstream of this one, because the cost of running a bus does
not depend on what is charged to sit in it. Quoting a figure from this file as a subsidy is a
category error; the subsidy is in `fares.json`, and it is smaller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
COST_INPUTS = ROOT / "data" / "cost-inputs.json"

WEEKDAYS_PER_YEAR: Final[int] = 250


@dataclass(frozen=True)
class Prices:
    """Unit prices, resolved from the data file into the four rates the model needs."""

    per_bus_hour: float
    per_paid_hour: float
    per_bus_km_by_class: dict[str, float]
    per_vehicle_year: float
    admin_share: float
    vehicle_price: dict[str, float]
    vehicle_life_years: float


@dataclass(frozen=True)
class Cost:
    """A year of network cost, in lei, kept in the pieces it was built from."""

    driver_ron: float
    running_ron: float
    standing_ron: float
    admin_ron: float
    capital_ron: float

    @property
    def operating_ron(self) -> float:
        """What the service costs to run for a year, before buying anything."""
        return self.driver_ron + self.running_ron + self.standing_ron + self.admin_ron

    @property
    def total_ron(self) -> float:
        return self.operating_ron + self.capital_ron

    def __add__(self, other: Cost) -> Cost:
        return Cost(
            driver_ron=self.driver_ron + other.driver_ron,
            running_ron=self.running_ron + other.running_ron,
            standing_ron=self.standing_ron + other.standing_ron,
            admin_ron=self.admin_ron + other.admin_ron,
            capital_ron=self.capital_ron + other.capital_ron,
        )


def maintenance_per_km(item: dict[str, float]) -> float:
    """Maintenance in lei per km, wage-adjusted from a European benchmark.

    This repository simulates a network that does not exist, so a Romanian operating figure for
    it cannot exist either. The benchmark is therefore the starting point rather than a
    fallback — but it may not be imported whole. Maintenance is roughly half labour and half
    parts, and only the labour half is cheaper in Romania: a bearing costs what a bearing costs.

    Discounting the entire figure by the wage ratio is precisely the error made earlier against
    the driver-share benchmark, where a Western European share was taken at face value and
    turned out to be about twice the wage-adjusted expectation. Split, then adjust one half.
    """
    labour = item["maintenanceLabourShare"]
    adjusted_eur = item["maintenanceEurPerKm"] * (
        labour * item["maintenanceWageRatio"] + (1 - labour)
    )
    return adjusted_eur * item["ronPerEur"]


def load_prices(path: Path = COST_INPUTS) -> Prices:
    """Resolve the data file into rates.

    The driver rate is the one derived figure: a monthly gross wage becomes a cost per
    *bus*-hour only after employer contributions and the platform-to-paid ratio, and both
    steps are easy to forget.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    item = {name: entry["value"] for name, entry in document["items"].items()}
    vehicles = document["vehicles"]

    employer_monthly = item["driverGrossMonthly"] * (1 + item["employerContributionRate"])
    per_paid_hour = employer_monthly / item["driverPaidHoursMonth"]
    per_bus_hour = per_paid_hour * item["platformToPaidRatio"]

    maintenance = maintenance_per_km(item)
    per_km = {
        name: (spec["dieselPer100Km"] / 100) * item["dieselPricePerLitre"]
        + maintenance
        + item["tyresPerKm"]
        for name, spec in vehicles.items()
    }

    return Prices(
        per_bus_hour=per_bus_hour,
        per_paid_hour=per_paid_hour,
        per_bus_km_by_class=per_km,
        per_vehicle_year=item["insurancePerVehicleYear"]
        + item["depotPerVehicleYear"]
        + item["roadTaxPerVehicleYear"],
        admin_share=item["adminOverheadShare"],
        vehicle_price={name: spec["priceRon"] for name, spec in vehicles.items()},
        vehicle_life_years=item["vehicleLifeYears"],
    )


def annual_cost(
    paid_driver_hours_per_weekday: float,
    bus_km_per_weekday_by_class: dict[str, float],
    fleet_by_class: dict[str, int],
    prices: Prices,
    weekdays: int = WEEKDAYS_PER_YEAR,
) -> Cost:
    """A year of cost from a weekday's operation and the fleet that runs it.

    Kilometres come per class because a 20-seat minibus and a 50-seat coach do not burn the
    same fuel over the same road, and the classes differ by nearly a factor of two.

    The driver line takes PAID hours — see `fleet.paid_driver_hours`. Passing bus-hours here
    understates it, because the dead time a peak timetable creates is real and someone is
    employed across it.
    """
    # PAID hours, not bus-hours. A vehicle out from 06:00 to 22:00 needs two duties whatever
    # it drives, and a peak-only route buys three hours of driving across a twelve-hour day.
    # Billing bus-hours charged nothing for either.
    driver = paid_driver_hours_per_weekday * weekdays * prices.per_paid_hour
    running = sum(
        km * weekdays * prices.per_bus_km_by_class[name]
        for name, km in bus_km_per_weekday_by_class.items()
    )
    fleet = sum(fleet_by_class.values())
    standing = fleet * prices.per_vehicle_year
    admin = (driver + running + standing) * prices.admin_share
    capital = sum(
        count * prices.vehicle_price[name] / prices.vehicle_life_years
        for name, count in fleet_by_class.items()
    )
    return Cost(
        driver_ron=driver,
        running_ron=running,
        standing_ron=standing,
        admin_ron=admin,
        capital_ron=capital,
    )

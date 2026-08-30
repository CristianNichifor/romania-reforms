"""Ticket revenue, and the subsidy that is left over.

Everything else in this simulator computes what the service **costs**. This is the file that
turns that into what it would cost the **public budget**, which is the number a finance ministry
actually argues about — and the two differ by whatever passengers pay.

**Why the recovery ratio is an output and not an input.** The obvious shortcut is to assume a
farebox recovery ratio and multiply: Denmark's Movia covers about half its turnover from tickets,
so take half. That is circular. It says *subsidy = cost × (1 − r)* and adds no information the
cost model did not already hold — the answer would move only when the cost moved, and the
benchmark could never disagree with it. So revenue is built from a fare and a quantity, and the
recovery ratio falls out afterwards, where Movia can be used to check it.

**The quantity is the weak half, and it is weak in a specific way.** There is no demand model
here. Passenger-kilometres come from the capacity the network offers multiplied by an assumed
load factor, which means this can tell you what a given service would earn and cannot tell you
whether anyone would ride it. Two consequences worth stating plainly rather than burying:

- The network can never be overcrowded and can never show unmet demand. A route nobody boards
  and a route nobody fits on look identical at the same average load.
- Revenue is exactly proportional to the load factor. Over the plausible 15–30% band the
  recovery ratio runs from a third to two thirds, so `sensitivity()` reports the whole band and
  the central case is offered as one row of it rather than as the answer.

**Fares are Romanian and sourced; the load factor cannot be.** County councils publish a tariff
per passenger-kilometre — Botoșani at 0,31 lei, Vaslui at 0,405 ex-VAT. No Romanian source can
give the occupancy of a service that does not exist, which is exactly the asymmetry this whole
repository keeps running into: the price of a thing is public, the behaviour of a thing that was
never built is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
FARE_INPUTS = ROOT / "data" / "fare-inputs.json"

WEEKDAYS_PER_YEAR: Final[int] = 250


@dataclass(frozen=True)
class FarePrices:
    """What a passenger pays, and how full the bus is."""

    fare_per_passenger_km: float
    load_factor: float
    load_factor_low: float
    load_factor_high: float
    mean_seats: float


@dataclass(frozen=True)
class Farebox:
    """A year of revenue against a year of operating cost."""

    passenger_km: float
    revenue_ron: float
    operating_ron: float

    @property
    def subsidy_ron(self) -> float:
        """What the public budget carries once tickets are counted.

        Clamped at zero: a service earning more than it costs needs no subsidy, and a negative
        subsidy is a surplus, which is a different claim and should not be smuggled in as one.
        """
        return max(0.0, self.operating_ron - self.revenue_ron)

    @property
    def recovery(self) -> float:
        """Share of operating cost covered by tickets. Compare against Movia's ~0,50."""
        return self.revenue_ron / self.operating_ron if self.operating_ron else 0.0


def load_fare_prices(path: Path = FARE_INPUTS) -> FarePrices:
    document = json.loads(path.read_text(encoding="utf-8"))
    item = {name: entry["value"] for name, entry in document["items"].items()}
    return FarePrices(
        fare_per_passenger_km=item["farePerPassengerKm"],
        load_factor=item["loadFactor"],
        load_factor_low=item["loadFactorLow"],
        load_factor_high=item["loadFactorHigh"],
        mean_seats=item["meanSeats"],
    )


def farebox(
    bus_km_per_year: float,
    operating_ron: float,
    prices: FarePrices,
    load_factor: float | None = None,
) -> Farebox:
    """Revenue and subsidy for one load factor.

    Seat-kilometres are bus-kilometres times seats; passenger-kilometres are that times how
    full the bus is. The fare is per passenger-kilometre, so a long journey pays more than a
    short one — which is how Romanian county tariffs are actually written.
    """
    if bus_km_per_year < 0 or operating_ron < 0:
        raise ValueError("bus-km and operating cost must both be non-negative")
    share = prices.load_factor if load_factor is None else load_factor
    if not 0 < share <= 1:
        raise ValueError(f"load factor must sit in (0, 1]; got {share}")

    passenger_km = bus_km_per_year * prices.mean_seats * share
    return Farebox(
        passenger_km=passenger_km,
        revenue_ron=passenger_km * prices.fare_per_passenger_km,
        operating_ron=operating_ron,
    )


def sensitivity(
    bus_km_per_year: float,
    operating_ron: float,
    prices: FarePrices,
    steps: int = 4,
) -> list[dict[str, float]]:
    """The whole plausible load-factor band, not just the central case.

    Published as a band because the band is the finding: a single recovery ratio quoted from an
    assumed occupancy would read as a measurement, and this one moves by a factor of two across
    assumptions nobody can currently rule out.
    """
    if steps < 2:
        raise ValueError("a band needs at least two points")
    low, high = prices.load_factor_low, prices.load_factor_high
    rows = []
    for index in range(steps):
        share = low + (high - low) * index / (steps - 1)
        result = farebox(bus_km_per_year, operating_ron, prices, load_factor=share)
        rows.append(
            {
                "loadFactor": round(share, 3),
                "passengerKm": result.passenger_km,
                "revenueRon": result.revenue_ron,
                "subsidyRon": result.subsidy_ron,
                "recovery": result.recovery,
            }
        )
    return rows

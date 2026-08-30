"""Tests for the cost engine.

Operating cost scales with what the buses do; capital cost scales with how many must exist.
Most of these tests exist to keep those apart, and to keep the arithmetic honest about a
driver being paid for more hours than the bus is moving.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.costs import Cost, Prices, annual_cost, load_prices

ROOT = Path(__file__).resolve().parents[1]
COST = ROOT / "data" / "cost.json"

PRICES = Prices(
    per_bus_hour=50.0,
    per_bus_km_by_class={"basic": 2.0, "feeder": 3.0, "trunk": 4.0},
    per_vehicle_year=10_000.0,
    admin_share=0.10,
    vehicle_price={"basic": 100_000.0, "feeder": 200_000.0, "trunk": 300_000.0},
    vehicle_life_years=10.0,
)


def test_the_driver_line_follows_hours_not_kilometres():
    """A driver is paid for time. If this ever scaled with distance, a slow route through
    villages would cost less than a fast one over the same hours."""
    cost = annual_cost(100.0, {"basic": 0.0}, {"basic": 0}, PRICES, weekdays=10)
    assert cost.driver_ron == pytest.approx(100 * 10 * 50.0)


def test_the_running_line_is_priced_per_class():
    """A 20-seat minibus and a 50-seat coach do not burn the same fuel over the same road —
    nearly a factor of two apart. One blended rate would misprice both."""
    cost = annual_cost(0.0, {"basic": 100.0, "trunk": 100.0}, {}, PRICES, weekdays=1)
    assert cost.running_ron == pytest.approx(100 * 2.0 + 100 * 4.0)


def test_standing_cost_is_owed_whether_the_bus_moves_or_not():
    """Insurance and depot are per vehicle-year. A bus parked all winter still costs them."""
    cost = annual_cost(0.0, {}, {"feeder": 3}, PRICES, weekdays=250)
    assert cost.standing_ron == pytest.approx(3 * 10_000.0)


def test_capital_is_annualised_over_the_vehicle_life():
    cost = annual_cost(0.0, {}, {"trunk": 10}, PRICES, weekdays=250)
    assert cost.capital_ron == pytest.approx(10 * 300_000.0 / 10.0)


def test_capital_is_not_part_of_operating():
    """Buying a bus is not running it. Folding the two would make a fleet renewal look like
    an operating overspend, and hide the trade a reader is entitled to see."""
    cost = annual_cost(10.0, {"basic": 10.0}, {"basic": 1}, PRICES, weekdays=1)
    assert cost.operating_ron + cost.capital_ron == pytest.approx(cost.total_ron)
    assert cost.capital_ron > 0
    assert cost.operating_ron != cost.total_ron


def test_administration_is_charged_on_the_direct_cost_only():
    """Overhead is a share of what the service costs to run, not of what the buses cost to
    buy — and not of itself."""
    cost = annual_cost(10.0, {"basic": 10.0}, {"basic": 1}, PRICES, weekdays=1)
    direct = cost.driver_ron + cost.running_ron + cost.standing_ron
    assert cost.admin_ron == pytest.approx(direct * 0.10)


def test_costs_add_across_parts_of_a_network():
    a = Cost(1.0, 2.0, 3.0, 4.0, 5.0)
    b = Cost(10.0, 20.0, 30.0, 40.0, 50.0)
    assert (a + b).total_ron == pytest.approx(a.total_ron + b.total_ron)
    assert (a + b).driver_ron == pytest.approx(11.0)


def test_a_network_that_runs_nothing_costs_nothing():
    assert annual_cost(0.0, {}, {}, PRICES, weekdays=250).total_ron == 0.0


def test_the_driver_rate_includes_contributions_and_unpaid_platform_time():
    """The two steps easiest to forget. A gross wage is not an employer cost, and a bus-hour
    is not a paid hour — sign-on, breaks and deadhead mean the driver is paid for more time
    than the bus is moving, so costing at bus-hours alone understates the largest line."""
    real = load_prices()
    inputs = json.loads((ROOT / "data" / "cost-inputs.json").read_text(encoding="utf-8"))["items"]
    naive = inputs["driverGrossMonthly"]["value"] / inputs["driverPaidHoursMonth"]["value"]
    assert real.per_bus_hour > naive * inputs["platformToPaidRatio"]["value"] * 0.99
    assert real.per_bus_hour > naive


def test_every_price_carries_its_own_confidence():
    """The point of the data file: a reader disputing one figure argues with one row. A line
    item without a confidence is a number with nowhere to attach a dispute."""
    document = json.loads((ROOT / "data" / "cost-inputs.json").read_text(encoding="utf-8"))
    for name, entry in document["items"].items():
        assert entry["confidence"] in ("verbatim", "derived", "assumed"), name
    for name, entry in document["vehicles"].items():
        assert entry["confidence"] in ("verbatim", "derived", "assumed"), name


def test_the_file_admits_that_nothing_is_sourced():
    """Load-bearing. If this ever passes silently because someone removed the caveat rather
    than sourcing the numbers, the whole document starts reading as though it were cited."""
    document = json.loads((ROOT / "data" / "cost-inputs.json").read_text(encoding="utf-8"))
    assert document["provenance"]["confidence"] == "assumed"
    ids = {limitation["id"] for limitation in document["limitations"]}
    assert "niciun-pret-nu-este-citat" in ids


@pytest.fixture(scope="module")
def built() -> dict:
    if not COST.exists():
        pytest.skip("cost not built")
    return json.loads(COST.read_text(encoding="utf-8"))


def test_the_totals_add_up(built):
    annual = built["annualRon"]
    parts = annual["driver"] + annual["running"] + annual["standing"] + annual["admin"]
    assert annual["operating"] == pytest.approx(parts, rel=1e-6)
    assert annual["total"] == pytest.approx(annual["operating"] + annual["capital"], rel=1e-6)


def test_the_ledger_carries_both_columns(built):
    """Neither number is quotable alone. That is the whole design."""
    ledger = built["ledgerRon"]
    assert ledger["transportCost"] > 0
    assert ledger["administrativeSaving"] > 0
    assert ledger["netAgainstAdministrativeSaving"] == pytest.approx(
        ledger["administrativeSaving"] - ledger["transportCost"]
    )


def test_it_is_declared_a_cost_and_not_a_subsidy(built):
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "cost-nu-subventie" in ids
    assert "preturile-nu-sunt-citate" in ids


def test_the_failing_sanity_checks_are_declared(built):
    """Three checks against how bus operations behave do not pass: the driver share, the cost
    per kilometre and the commercial speed. They are declared rather than tuned away, and if
    someone fixes the model these limitations should go with the fix."""
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "viteza-comerciala-prea-mare" in ids
    assert "structura-costului-nu-seamana-cu-realitatea" in ids

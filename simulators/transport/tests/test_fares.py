"""Tests for the farebox.

The recurring hazard in this file is circularity: it is very easy to write a subsidy model whose
answer is the benchmark it claims to be checked against. Several of these exist to keep the
benchmark on the output side of the calculation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.fares import FarePrices, farebox, load_fare_prices, sensitivity

ROOT = Path(__file__).resolve().parents[1]

PRICES = FarePrices(
    fare_per_passenger_km=0.40,
    load_factor=0.25,
    load_factor_low=0.10,
    load_factor_high=0.50,
    mean_seats=40.0,
)


def test_revenue_is_capacity_times_occupancy_times_fare():
    result = farebox(1_000_000.0, 1.0, PRICES)
    assert result.passenger_km == pytest.approx(1_000_000 * 40 * 0.25)
    assert result.revenue_ron == pytest.approx(1_000_000 * 40 * 0.25 * 0.40)


def test_subsidy_is_what_tickets_do_not_cover():
    result = farebox(1_000.0, 100_000.0, PRICES)
    assert result.subsidy_ron == pytest.approx(100_000.0 - result.revenue_ron)


def test_a_service_that_more_than_pays_for_itself_needs_no_subsidy():
    """Not a negative subsidy. A surplus is a different claim and must not arrive disguised."""
    result = farebox(1_000_000.0, 1_000.0, PRICES)
    assert result.revenue_ron > result.operating_ron
    assert result.subsidy_ron == 0.0


def test_recovery_scales_with_occupancy_and_nothing_else_does_the_work():
    """Double the load, double the revenue. This linearity is the model's honest weakness —
    it is also why the band is published, so nobody reads one recovery ratio as measured."""
    half = farebox(1_000.0, 1.0, PRICES, load_factor=0.10)
    full = farebox(1_000.0, 1.0, PRICES, load_factor=0.20)
    assert full.revenue_ron == pytest.approx(2 * half.revenue_ron)


def test_an_impossible_load_factor_is_refused():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="load factor"):
            farebox(1_000.0, 1.0, PRICES, load_factor=bad)


def test_negative_inputs_are_refused():
    with pytest.raises(ValueError):
        farebox(-1.0, 1.0, PRICES)
    with pytest.raises(ValueError):
        farebox(1.0, -1.0, PRICES)


def test_the_band_spans_the_declared_range_and_rises():
    rows = sensitivity(1_000_000.0, 1_000_000.0, PRICES, steps=5)
    assert rows[0]["loadFactor"] == pytest.approx(PRICES.load_factor_low)
    assert rows[-1]["loadFactor"] == pytest.approx(PRICES.load_factor_high)
    recoveries = [row["recovery"] for row in rows]
    assert recoveries == sorted(recoveries)


def test_a_band_needs_more_than_one_point():
    with pytest.raises(ValueError, match="at least two"):
        sensitivity(1.0, 1.0, PRICES, steps=1)


def test_the_fare_is_sourced_and_the_load_factor_is_not():
    """The asymmetry this level is built around: a published tariff exists, an occupancy for a
    service that was never built cannot. If the load factor were ever marked as anything but
    assumed, the model would be claiming to know something nobody does."""
    document = json.loads((ROOT / "data" / "fare-inputs.json").read_text(encoding="utf-8"))
    assert document["items"]["farePerPassengerKm"]["confidence"] == "derived"
    assert document["items"]["loadFactor"]["confidence"] == "assumed"


def test_the_danish_benchmark_is_not_an_input():
    """Load-bearing. If Movia's ratio ever became an input, the subsidy would be cost times a
    constant and the check would be checking itself. It may appear only under `benchmarks`."""
    document = json.loads((ROOT / "data" / "fare-inputs.json").read_text(encoding="utf-8"))
    assert "moviaFareboxRecovery" in document["benchmarks"]
    for name in document["items"]:
        assert "movia" not in name.lower(), name
        assert "recovery" not in name.lower(), name


def test_the_published_result_ships_a_band_not_a_number():
    document = json.loads((ROOT / "data" / "fares.json").read_text(encoding="utf-8"))
    assert len(document["band"]) >= 2
    lows = [row["recovery"] for row in document["band"]]
    assert max(lows) > min(lows) * 1.5, "a band this narrow is not reporting the uncertainty"


def test_the_published_result_declares_that_occupancy_decides_it():
    document = json.loads((ROOT / "data" / "fares.json").read_text(encoding="utf-8"))
    blocking = {
        limitation["id"]
        for limitation in document["limitations"]
        if limitation["severity"] == "blocking"
    }
    assert "gradul-de-ocupare-decide-tot" in blocking
    assert "cererea-nu-raspunde-la-tarif" in blocking


def test_the_model_lands_near_danish_practice():
    """A check, not a target. Both inputs were fixed from other sources before this ran."""
    document = json.loads((ROOT / "data" / "fares.json").read_text(encoding="utf-8"))
    assert document["benchmark"]["withinBand"] is True


def test_real_prices_load():
    prices = load_fare_prices()
    assert prices.fare_per_passenger_km > 0
    assert 0 < prices.load_factor_low < prices.load_factor < prices.load_factor_high <= 1

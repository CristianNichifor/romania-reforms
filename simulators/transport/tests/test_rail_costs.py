"""Tests for the rail cost engine.

Most of these hold apart things that would be easy to fold together and wrong to: operating
against capital, the access tariff against the track it is charged for, and the price of a
minute against the claim that one mode could replace another.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.rail_costs import (
    annual_rail_cost,
    cost_per_passenger_hour_saved,
    line_class,
    load_rail_prices,
)

ROOT = Path(__file__).resolve().parents[1]


def test_line_class_matches_cfr_bands():
    """CFR's bands from Anexa 25.a art. 6, including both edges of each."""
    assert line_class(40.0) == "D"
    assert line_class(50.0) == "D"
    assert line_class(51.0) == "C"
    assert line_class(90.0) == "C"
    assert line_class(91.0) == "B"
    assert line_class(120.0) == "B"
    assert line_class(121.0) == "A"
    assert line_class(160.0) == "A"


def test_a_line_faster_than_the_tariff_table_is_still_class_a():
    """A line above 160 must not fall off the end of the table into free access."""
    assert line_class(200.0) == "A"


def test_better_track_costs_more_to_use():
    """The tariff is monotone in line class, which is what makes renewal partly self-taxing.

    If this ever inverted, rehabilitation would look cheaper than it is, because the model
    would be crediting it with an access saving that CFR does not give.
    """
    prices = load_rail_prices()
    tui = prices.tui_by_class
    assert tui["A"] > tui["B"] > tui["C"] > tui["D"]


def test_operating_and_capital_stay_apart():
    """Rolling stock is owned, not run. Folding it into the running cost would hide the trade
    between a peaky timetable and a large fleet, exactly as it would on the road side."""
    prices = load_rail_prices()
    cost = annual_rail_cost(2000.0, 44.0, 6, prices, line_kmh=80.0)
    assert cost.capital_ron > 0
    assert cost.operating_ron == pytest.approx(
        cost.crew_ron + cost.access_ron + cost.energy_ron + cost.maintenance_ron
    )
    assert cost.total_ron > cost.operating_ron


def test_running_no_trains_still_costs_the_fleet():
    """A fleet parked all year still depreciates. Zero service must not mean zero cost."""
    prices = load_rail_prices()
    cost = annual_rail_cost(0.0, 0.0, 6, prices, line_kmh=80.0)
    assert cost.access_ron == 0
    assert cost.energy_ron == 0
    assert cost.capital_ron > 0


def test_rehabilitation_on_a_busier_line_is_cheaper_per_hour():
    """Fixed capital spread over more passengers must fall per passenger-hour."""
    prices = load_rail_prices()
    quiet = cost_per_passenger_hour_saved(100.0, 10, 50, prices)
    busy = cost_per_passenger_hour_saved(100.0, 40, 150, prices)
    assert busy["ronPerPassengerHour"] < quiet["ronPerPassengerHour"]


def test_length_cancels_out_of_the_unit_cost():
    """Both the capital and the time saved scale with line length, so the price of an hour
    must not depend on how long a line was chosen for the illustration."""
    prices = load_rail_prices()
    short = cost_per_passenger_hour_saved(50.0, 20, 96, prices)
    long = cost_per_passenger_hour_saved(200.0, 20, 96, prices)
    assert short["ronPerPassengerHour"] == pytest.approx(long["ronPerPassengerHour"], rel=0.02)


def test_rehabilitation_pays_more_access_not_less():
    """Renewal moves the line up a band, so the tariff takes some of the gain back."""
    prices = load_rail_prices()
    saved = cost_per_passenger_hour_saved(100.0, 20, 96, prices)
    assert saved["extraAccessRon"] > 0


def test_nonsense_service_is_refused():
    prices = load_rail_prices()
    for args in ((0.0, 20, 96), (100.0, 0, 96), (100.0, 20, 0)):
        with pytest.raises(ValueError):
            cost_per_passenger_hour_saved(*args, prices)


def test_the_published_comparison_keeps_pulsing_free():
    """Pulsing moves departure times, not buses. The day that stops being zero in the
    artefact, the comparison it anchors has quietly changed meaning."""
    document = json.loads((ROOT / "data" / "rail-cost.json").read_text(encoding="utf-8"))
    assert document["againstPulsing"]["pulseCapitalRon"] == 0
    assert document["againstPulsing"]["equivalentRailSpendRon"] > 0


def test_the_comparison_admits_it_is_not_the_same_passengers():
    """A unit-cost comparison read as a substitution claim would be a real distortion, so the
    artefact has to keep carrying the caveat next to the number."""
    document = json.loads((ROOT / "data" / "rail-cost.json").read_text(encoding="utf-8"))
    ids = {limitation["id"] for limitation in document["limitations"]}
    assert "compara-preturi-unitare-nu-aceiasi-calatori" in ids
    assert "incarcarea-decide-rezultatul" in ids


def test_the_big_rail_inputs_are_sourced():
    """The point of the rail side: unlike the road model, these came off documents."""
    document = json.loads((ROOT / "data" / "rail-cost-inputs.json").read_text(encoding="utf-8"))
    items = document["items"]
    for name in ("tuiTsnClassC", "tuiTtse", "emuPriceRon", "rehabilitationRonPerKm"):
        assert items[name]["confidence"] == "verbatim", name

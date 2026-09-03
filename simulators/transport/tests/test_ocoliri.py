"""Tests for the bypass programme.

The whole model is one measured length times two unit numbers, which makes it easy to get a
huge answer and never notice. €35 md is larger than the entire twelve-year bus programme, so
these tests exist mostly to keep the arithmetic honest and the caveats attached.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "data" / "ocoliri.json"
INPUTS = ROOT / "data" / "ocoliri-inputs.json"


@pytest.fixture(scope="module")
def built() -> dict:
    if not BUILT.exists():
        pytest.skip("bypasses not built")
    return json.loads(BUILT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inputs() -> dict:
    return json.loads(INPUTS.read_text(encoding="utf-8"))["items"]


def test_a_bypass_is_longer_than_the_street_it_replaces(built):
    """It arcs around the settlement and ties back to the road at both ends. If this ever
    inverted, someone had swapped the factor for its reciprocal and the country would look a
    third cheaper to fix than it is."""
    for tally in built["byThreshold"].values():
        if tally["crossings"] == 0:
            continue
        assert tally["bypassKm"] > tally["throughTownKm"]


def test_raising_the_threshold_can_only_shrink_the_programme(built):
    """A longer minimum crossing is a strict subset. Monotonic in every column — if it were
    not, the merge is double-counting somewhere."""
    tallies = sorted(built["byThreshold"].items(), key=lambda kv: int(kv[0]))
    for (_, smaller), (_, larger) in zip(tallies, tallies[1:], strict=False):
        assert larger["crossings"] <= smaller["crossings"]
        assert larger["throughTownKm"] <= smaller["throughTownKm"]
        assert larger["costRon"] <= smaller["costRon"]


def test_the_cost_is_the_length_times_the_price(built, inputs):
    """No hidden factor. The model is deliberately this simple, and the test says so."""
    price = inputs["bypassLeiPerKm"]["value"]
    for tally in built["byThreshold"].values():
        assert tally["costRon"] == pytest.approx(tally["bypassKm"] * price, rel=1e-3)


def test_the_crossings_are_a_subset_of_the_in_locality_road(built):
    """Every crossing is made of road that was signed at 50. The merged total cannot exceed
    the length it was merged from."""
    network = built["network"]
    assert built["byThreshold"]["200"]["throughTownKm"] <= network["throughLocalityKm"] + 1
    assert network["throughLocalityKm"] < network["totalKm"]
    # The finding that motivates the whole programme, held to the measurement it came from.
    assert 0.25 < network["throughLocalityShare"] < 0.55


def test_the_median_crossing_looks_like_a_romanian_village(built):
    """A sanity check with teeth. A median crossing of 100 m would mean the merge is
    fragmenting; 20 km would mean it is joining settlements across the countryside between
    them. Either failure produces a plausible total from nonsense parts."""
    median = built["byThreshold"]["500"]["medianCrossingM"]
    assert 800 <= median <= 5_000, median


def test_the_threshold_is_declared_as_a_choice(built):
    """The count is a function of where the line is drawn, and the document has to say so —
    2 781 quoted without "at 500 m" is not a finding."""
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "numarul-e-un-prag-nu-o-descoperire" in ids
    assert str(built["defaultThresholdM"]) in json.dumps(built["limitations"], ensure_ascii=False)
    assert len(built["byThreshold"]) >= 3, "one threshold alone hides the sensitivity"


def test_it_says_the_price_rests_on_a_single_contract(built):
    """The largest weakness, and the one most likely to be forgotten once the number is
    quoted. Metropolitan rings are a different product, not the same product priced higher."""
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "un-singur-contract-de-referinta" in ids
    assert "pretul-de-contract-nu-e-costul-total" in ids


def test_the_missing_benefit_is_blocking(built):
    """A cost with no benefit beside it is half an answer, and the half a decision-maker
    cannot use. It stays blocking until the journey-time coupling exists."""
    by_id = {limitation["id"]: limitation for limitation in built["limitations"]}
    assert by_id["nu-e-inca-legat-de-timpii-de-parcurs"]["severity"] == "blocking"


def test_the_programme_is_reported_against_something(built):
    """Scale is the thing a reader cannot judge alone. 175 md lei means nothing until it sits
    beside a number from the same repository — here, that the bus programme is far smaller."""
    cost = ROOT / "data" / "cost.json"
    if not cost.exists():
        pytest.skip("cost not built")
    annual = json.loads(cost.read_text(encoding="utf-8"))["annualRon"]["total"]
    assert built["headline"]["costRon"] > annual, (
        "if bypasses ever cost less than one year of running the buses, check the price"
    )

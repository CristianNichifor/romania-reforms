"""The asking-price barometer, and the multiple derived from it.

The point of these is not that the arithmetic divides. It is that the two blocking limitations
survive — asking prices are not transaction prices, and farmland is not house plots — because
the moment either is dropped the multiple starts looking like a market calibration of the whole
simulator, which it is not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "data"
BANDS = ("low", "central", "high")


def load(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        pytest.skip(f"{name} is not built")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def asked() -> dict:
    return load("pret-cerut-agricol-2026.json")


@pytest.fixture(scope="module")
def multiple() -> dict:
    return load("multiplu-piata-2026.json")


def test_the_asking_prices_say_they_are_asking_prices(asked):
    """Blocking, not a note: the whole file is misread if this caveat travels separately."""
    blocking = {x["id"] for x in asked["limitations"] if x["severity"] == "blocking"}
    assert "preturi-cerute-nu-de-tranzactionare" in blocking
    assert "doar-teren-agricol-extravilan" in blocking


def test_every_band_is_ordered(asked):
    """p25 ≤ median ≤ p75, on every row and both units, or the percentiles were mislabelled."""
    for county in asked["prices"]:
        for unit in ("ronPerHa", "eurPerM2"):
            band = county[unit]
            assert band["low"] <= band["central"] <= band["high"], county["county"]
        for local in county["localities"]:
            for unit in ("ronPerHa", "eurPerM2"):
                band = local[unit]
                assert band["low"] <= band["central"] <= band["high"], local["siruta"]


def test_the_two_units_are_the_same_number(asked):
    """EUR/m² is RON/ha ÷ 10 000 — a unit change, not a currency conversion.

    Named because it looks like one: the figure goes from tens of thousands to fractions of a
    unit, which is exactly what a RON→EUR conversion would also do, and getting those two
    confused would move every price by a factor of five and still look plausible.
    """
    for county in asked["prices"]:
        for band in BANDS:
            assert county["eurPerM2"][band] == pytest.approx(
                county["ronPerHa"][band] / 10_000, rel=1e-6
            )


def test_sirutas_are_the_key_the_rest_of_the_repository_joins_on(asked):
    """A locality without a SIRUTA cannot be joined to anything and must not be published."""
    for county in asked["prices"]:
        for local in county["localities"]:
            assert local["siruta"].isdigit()
            assert local["offers"] >= asked["summary"]["minOffersPerLocality"]


def test_no_county_is_published_on_too_few_offers(asked):
    floor = asked["summary"]["minOffersPerCounty"]
    assert all(county["offers"] >= floor for county in asked["prices"])


def test_the_multiple_is_the_division_it_claims_to_be(multiple):
    """Absolute tolerance, because the stored multiple is rounded to three decimals.

    A relative tolerance fails on the small ones for no reason: 0,212 against 0,21226 is half
    of the last printed digit, which is what rounding to three decimals means, and no
    tolerance tighter than that can hold for a ratio that is allowed to be under one.
    """
    for row in multiple["counties_compared"]:
        for band in BANDS:
            assert row["multiple"][band] == pytest.approx(
                row["askedRonPerHa"][band] / row["gridMedianRonPerHa"], abs=5e-4
            )


def test_a_thin_grid_is_marked_rather_than_dropped(multiple):
    """The rule, not a census of who currently fails it.

    This used to assert that at least one county was too thin to compare, which was true while
    Hunedoara priced extravilan for eleven town seats and nobody else. Reading the two rows its
    tables carry for every commune — "Centre de Comuna" and "Sate" — took that county from 17%
    of its hectares priced to 98%, and no county is thin any more. The mechanism is what needs
    guarding: a county below the threshold must be marked rather than quietly dropped, because
    a county missing from a comparison reads as having nothing to compare.
    """
    for row in multiple["counties_compared"]:
        assert row["comparable"] == (row["gridShare"] >= 0.5)


def test_the_headline_multiple_uses_only_comparable_counties(multiple):
    usable = [r for r in multiple["counties_compared"] if r["comparable"]]
    assert multiple["summary"]["comparableCounties"] == len(usable)
    assert usable


def test_the_grid_is_not_far_below_the_asking_price(multiple):
    """The finding, pinned: for farmland the notaries' floor is roughly the asking price.

    A wide range rather than a tight one — this is asserting that the multiple is of order one
    and not of order ten, which is the claim the file actually makes. If a future grid or a
    future barometer moves it outside this, the number is worth looking at rather than
    quietly re-publishing.
    """
    central = multiple["summary"]["countyMultiple"]["central"]
    assert 0.5 < central < 3.0
    same_place = multiple["summary"]["localityMultiple"]
    if same_place:
        assert 0.5 < same_place["central"] < 3.0


def test_some_counties_price_above_the_market(multiple):
    """The part that is easy to lose: the floor is not always below."""
    below = multiple["summary"]["countiesBelowParity"]
    assert below
    for county in below:
        row = next(r for r in multiple["counties_compared"] if r["county"] == county)
        assert row["multiple"]["central"] < 1


def test_the_multiple_does_not_claim_to_cover_building_land(multiple):
    blocking = {x["id"] for x in multiple["limitations"] if x["severity"] == "blocking"}
    assert "doar-arabil-extravilan" in blocking
    assert "cerut-contra-administrativ" in blocking


def test_matched_localities_are_matched_on_both_sides(multiple, asked):
    """Every per-UAT pair must exist in the barometer under the same SIRUTA."""
    known = {
        local["siruta"]
        for county in asked["prices"]
        for local in county["localities"]
    }
    seen = 0
    for row in multiple["counties_compared"]:
        for pair in row["localities"]:
            assert pair["siruta"] in known
            seen += 1
    assert seen >= multiple["summary"]["matchedLocalities"]


def test_building_land_is_calibrated_separately_by_kind_of_place():
    """The finding this file exists to stop being averaged away.

    For its whole life this builder said it could not calibrate curți-construcții, which is 68%
    of the simulator's land value. It can now, and the answer is not one number: against the
    notaries' price the median asking price is about parity in municipalities and more than
    twice that in communes. A single national multiple describes neither, so if the three ever
    collapse toward each other that is a change in the grid worth noticing rather than a tidier
    dataset.
    """
    found = load("multiplu-piata-2026.json")["summary"].get("buildingLand")
    if not found:
        pytest.skip("anunturi-teren is not built, so building land is not calibrated")
    ranks = found["byRank"]
    for kind in ("municipii", "orase", "comune"):
        assert kind in ranks, f"{kind} missing from the split"
    assert (
        ranks["municipii"]["medianMultiple"]
        < ranks["orase"]["medianMultiple"]
        < ranks["comune"]["medianMultiple"]
    ), f"the grid no longer tracks the market better in cities than in communes: {ranks}"


def test_the_two_building_land_aggregates_answer_different_questions():
    """Median over localities against mean weighted by value, and they must not be conflated.

    Two thirds of the building-land value sits in twenty cities where the grid is close to
    right, so the value-weighted figure — the one a revenue argument needs — has to come out
    below the median over localities, which is the one a fairness argument needs. Equal would
    mean the weighting had stopped doing anything.
    """
    found = load("multiplu-piata-2026.json")["summary"].get("buildingLand")
    if not found:
        pytest.skip("anunturi-teren is not built")
    assert found["valueWeightedMultiple"] < found["medianMultiple"]
    assert found["localities"] >= 50

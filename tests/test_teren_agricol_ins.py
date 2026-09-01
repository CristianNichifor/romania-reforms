"""The INS survey, and the yield it measures.

The reason this file exists is one number. `build_renta.py` turns a stock of land value into a
flow of land rent by assuming a yield of 3–7%, and for agricultural land that assumption can now
be checked against a survey that measures both halves — what a hectare sold for and what a
hectare rented for, same institution, same year. It comes out near 1,5%.

So these tests guard the measurement and the distinction at once: that the yield is what it
claims to be, and that the file keeps saying it does not licence anyone to apply it to the
land under houses, which nothing measures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "data"


def latest(prefix: str) -> dict:
    found = sorted(DATA.glob(f"{prefix}-*.json"))
    if not found:
        pytest.skip(f"{prefix} is not built")
    return json.loads(found[-1].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def survey() -> dict:
    return latest("teren-agricol-ins")


@pytest.fixture(scope="module")
def multiple() -> dict:
    return latest("multiplu-piata")


def test_the_yield_is_rent_over_price(survey):
    """Both legs are lei per hectare per year, so the ratio is a yield with no conversion."""
    checked = 0
    for region in survey["regions"]:
        for row in region["series"]:
            if row["priceRonPerHa"] and row["rentRonPerHa"]:
                assert row["yieldPercent"] == pytest.approx(
                    100 * row["rentRonPerHa"] / row["priceRonPerHa"], abs=1e-3
                )
                checked += 1
    assert checked > 20


def test_a_missing_half_leaves_the_yield_empty(survey):
    """Not carried forward from a neighbouring year, which would invent a measurement."""
    for region in survey["regions"]:
        for row in region["series"]:
            if not (row["priceRonPerHa"] and row["rentRonPerHa"]):
                assert row["yieldPercent"] is None


def test_the_measured_yield_is_far_below_the_assumed_band(survey):
    """The finding, pinned.

    `build_renta.py` assumes 3–7%. Farmland measures near 1,5%, which is not a rounding
    difference — it is a factor of three, and it moves what share of the rent a tax is said to
    take. Asserted as a range rather than a point so a new year of survey data does not fail
    the suite, but tightly enough that the two bands cannot quietly meet.
    """
    measured = survey["summary"]["regionalYieldMedianPercent"]
    assert measured is not None
    assert 0.5 < measured < 2.5
    assert measured < 3.0, "if farmland ever yields 3%, build_renta's band stops being wrong"


def test_every_county_is_mapped_to_exactly_one_region(survey):
    seen: dict[str, str] = {}
    for region in survey["regions"]:
        if region["region"] == "RO":
            assert region["counties"] == []
            continue
        for county in region["counties"]:
            assert county not in seen, county
            seen[county] = region["region"]
    assert len(seen) == 42


def test_the_national_row_carries_no_counties(survey):
    """RO is the country, not a region; giving it counties would double-count every one."""
    national = [r for r in survey["regions"] if r["region"] == "RO"]
    assert len(national) == 1
    assert national[0]["counties"] == []


def test_the_survey_does_not_licence_a_yield_for_building_land(survey):
    blocking = {x["id"] for x in survey["limitations"] if x["severity"] == "blocking"}
    assert "randamentul-agricol-nu-e-cel-rezidential" in blocking


def test_both_market_references_are_reported_separately(multiple):
    """Asking and paid are different numbers about different things; never one blended figure."""
    assert multiple["summary"]["countyMultipleVsPaid"] is not None
    assert multiple["summary"]["countyMultiple"]["central"] is not None
    ids = {x["id"] for x in multiple["limitations"]}
    assert "cele-doua-referinte-nu-sunt-comparabile-intre-ele" in ids


def test_the_paid_multiple_is_the_division_it_claims_to_be(multiple):
    for row in multiple["counties_compared"]:
        if row["multipleVsPaid"] is None:
            continue
        assert row["multipleVsPaid"] == pytest.approx(
            row["paidRonPerHa"] / row["gridMedianRonPerHa"], abs=5e-4
        )


def test_counties_in_one_region_share_a_paid_price(multiple):
    """The regional limitation, made visible: Iași and Neamț cannot differ here, and don't."""
    by_region: dict[str, set[float]] = {}
    for row in multiple["counties_compared"]:
        if row["surveyRegion"] and row["paidRonPerHa"]:
            by_region.setdefault(row["surveyRegion"], set()).add(row["paidRonPerHa"])
    assert by_region
    for region, prices in by_region.items():
        assert len(prices) == 1, region


def test_the_grid_is_below_the_transaction_price_almost_everywhere(multiple):
    """Against sales rather than offers, the floor is a floor — with Iași the near-exception."""
    below = multiple["summary"]["countiesBelowParityVsPaid"]
    comparable = [r for r in multiple["counties_compared"] if r["comparable"]]
    assert len(below) < len(comparable) / 2
    central = multiple["summary"]["countyMultipleVsPaid"]
    assert 1.0 < central < 4.0

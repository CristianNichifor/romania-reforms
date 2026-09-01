"""The timber harvest, and the forest yield built from it.

Forest was the last big category resting on a borrowed number: 11% of the land value in this
simulator, earning whatever arable earned, because nobody leases woodland by the year and there
was no rent to measure. It now has a yield of its own, derived from two published series — what
was cut and what standing timber sold for — and one declared parameter.

These guard the arithmetic and, more importantly, the denominator: the first version divided a
county's forest value by *all* its forest hectares including the ones that never got a price,
which put Hunedoara's yield at 15,6%.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "data"
BANDS = ("low", "central", "high")


def latest(prefix: str) -> dict:
    found = sorted(DATA.glob(f"{prefix}-*.json"))
    if not found:
        pytest.skip(f"{prefix} is not built")
    return json.loads(found[-1].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def harvest() -> dict:
    return latest("lemn-recoltat")


@pytest.fixture(scope="module")
def yields() -> dict:
    return latest("randament-padure")


def test_the_harvest_matches_what_ins_announced(harvest):
    """19,41 million cubic metres in 2025, which INS put out in a press release.

    An outside number, and the reason for one: the parse walks malformed HTML — TEMPO closes
    its cells with `</td align='right'>` — so "it returned something" is not evidence it
    returned the right thing.
    """
    total = harvest["summary"]["harvestM3"]
    assert 15e6 < total < 25e6
    assert harvest["summary"]["counties"] >= 40


def test_harvest_per_hectare_is_the_division_it_claims(harvest):
    for row in harvest["counties_measured"]:
        if row["m3PerHaPerYear"] is None:
            continue
        assert row["m3PerHaPerYear"] == pytest.approx(
            row["harvestM3"] / row["forestHa"], rel=1e-3
        )
        # A Romanian county cuts between a fraction of a cubic metre and about ten per
        # hectare; outside that the area and the volume are not about the same forest.
        assert 0.1 < row["m3PerHaPerYear"] < 12


def test_the_forested_counties_cut_the_most(harvest):
    """Harghita and Suceava against Brăila — the ordering is a sanity check on the join."""
    per_ha = {r["county"]: r["m3PerHaPerYear"] for r in harvest["counties_measured"]}
    if not {"HR", "BR"} <= per_ha.keys():
        pytest.skip("counties not built")
    assert per_ha["HR"] > per_ha["BR"]


def test_the_yield_is_rent_over_value(yields):
    a = yields["assumptions"]
    for row in yields["counties_measured"]:
        rent = {
            "low": row["m3PerHaPerYear"] * a["stumpageLeiPerM3"]["low"]
            * (1 - a["ownerCostShare"]["low"]),
            "central": row["m3PerHaPerYear"] * a["stumpageLeiPerM3"]["central"]
            * (1 - a["ownerCostShare"]["central"]),
            "high": row["m3PerHaPerYear"] * a["stumpageLeiPerM3"]["high"]
            * (1 - a["ownerCostShare"]["high"]),
        }
        for band in BANDS:
            assert row["rentRonPerHaPerYear"][band] == pytest.approx(rent[band], abs=0.01)
            assert row["yieldPercent"][band] == pytest.approx(
                100 * rent[band] / row["forestValueRonPerHa"], abs=1e-3
            )


def test_only_priced_hectares_are_in_the_denominator(yields):
    """The Hunedoara bug, pinned.

    Dividing a county's forest value by every forest hectare it has, priced or not, made
    Hunedoara — which prices forest for eleven town seats and nobody else — look like land
    worth 2 434 lei a hectare yielding 15,6%. Every row now carries what share of its county's
    forest actually got a price, and no row may claim a value per hectare that is absurd.
    """
    for row in yields["counties_measured"]:
        assert 0 < row["forestShareOfCountyPriced"] <= 1
        assert 3_000 < row["forestValueRonPerHa"] < 200_000, row["county"]
        assert row["yieldPercent"]["central"] < 8, row["county"]


def test_forest_earns_more_than_arable(yields):
    """The result, and it is a result rather than an input.

    Both sides were assumed until now — forest borrowed arable's band outright. Forest coming
    out above farmland is plausible for an illiquid asset with lumpy income and a rotation
    measured in decades, but it is worth failing on if it ever inverts, because that would
    mean one of the two derivations moved a long way.
    """
    forest = yields["summary"]["yieldPercent"]["central"]
    arable = yields["summary"]["arableYieldPercentForComparison"]
    assert forest > arable
    assert 1.0 < forest < 5.0


def test_the_band_is_paired_to_widen(yields):
    band = yields["summary"]["yieldPercent"]
    assert band["low"] < band["central"] < band["high"]


def test_it_says_the_cost_share_is_a_parameter(yields):
    blocking = {x["id"] for x in yields["limitations"] if x["severity"] == "blocking"}
    assert "costurile-proprietarului-sunt-parametru" in blocking
    assert yields["provenance"]["confidence"] == "derived"


def test_the_national_price_limitation_is_declared(yields):
    ids = {x["id"] for x in yields["limitations"]}
    assert "pretul-e-national-nu-judetean" in ids
    assert "romsilva-e-padurea-statului" in ids


def test_the_rent_builder_uses_the_forest_band(yields):
    """The point of the exercise: forest must no longer borrow arable's yield."""
    for path in sorted(DATA.glob("renta-*.json")):
        rent = json.loads(path.read_text(encoding="utf-8"))
        bands = rent["assumptions"]["yieldByCategoryPercent"]
        if "PADURE" not in bands or "A" not in bands:
            continue
        county = rent["counties"][0]
        row = next(
            (r for r in yields["counties_measured"] if r["county"] == county), None
        )
        if row is None:
            continue
        assert bands["PADURE"] == row["yieldPercent"], county
        assert bands["PADURE"] != bands["A"], county

"""The derived yield for building land.

This is the only number in the simulator that is neither read from a document nor measured from
a survey — it is solved for. So the tests are mostly about the arithmetic staying honest: that
the identity holds, that the band is paired the way that widens it rather than the way that
cancels it, and that the file never stops saying it is a derivation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "data"
BANDS = ("low", "central", "high")


@pytest.fixture(scope="module")
def derived() -> dict:
    path = DATA / "randament-teren-construit-2026.json"
    if not path.exists():
        pytest.skip("randament-teren-construit is not built")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_identity_holds(derived):
    """r = y_net − δ·(1 − λ), with the ends paired to widen rather than to cancel."""
    a, s = derived["assumptions"], derived["summary"]
    share = {b: s["landSharePercent"][b] / 100 for b in BANDS}
    worst, best = max(a["depreciationPercent"].values()), min(a["depreciationPercent"].values())
    assert s["derivedYieldPercent"]["low"] == pytest.approx(
        a["netYieldPercent"]["low"] - worst * (1 - share["low"]), abs=5e-4
    )
    assert s["derivedYieldPercent"]["central"] == pytest.approx(
        a["netYieldPercent"]["central"] - a["depreciationPercent"]["central"]
        * (1 - share["central"]),
        abs=5e-4,
    )
    assert s["derivedYieldPercent"]["high"] == pytest.approx(
        a["netYieldPercent"]["high"] - best * (1 - share["high"]), abs=5e-4
    )


def test_the_band_is_a_band(derived):
    """It collapsed to 2,52–2,42 once, from pairing each input's own "low" together.

    That reads as precision and is arithmetic: a thin property yield and slow depreciation push
    the answer in opposite directions, so taking both "low" ends cancels them. The band has to
    be wide enough to be worth reporting, which is what this asserts.
    """
    band = derived["summary"]["derivedYieldPercent"]
    assert band["low"] < band["central"] < band["high"]
    assert band["high"] - band["low"] > 0.5


def test_net_is_below_gross(derived):
    a = derived["assumptions"]
    for band in BANDS:
        assert a["netYieldPercent"][band] == pytest.approx(
            a["grossYieldPercent"] * (1 - a["operatingCostShare"][band]), abs=1e-3
        )
        assert a["netYieldPercent"][band] < a["grossYieldPercent"]


def test_depreciation_is_the_reciprocal_of_the_legal_life(derived):
    """HG 2139/2004 gives the life in years; the rate is one over it and nothing else."""
    a = derived["assumptions"]
    for band in BANDS:
        assert a["depreciationPercent"][band] == pytest.approx(
            100 / a["buildingLifeYears"][band], abs=1e-3
        )
    assert 40 <= min(a["buildingLifeYears"].values())
    assert max(a["buildingLifeYears"].values()) <= 60


def test_the_land_share_is_small_and_that_is_the_finding(derived):
    """Around 6% at a plot four times the floor — an order of magnitude, not a decimal.

    Romanian construction costs what construction costs and Romanian land, outside the cities
    with no grid, does not. If this ever climbs past 20% the derivation's conclusion changes
    and should be looked at rather than re-published.
    """
    share = derived["summary"]["landSharePercent"]
    assert share["low"] < share["central"] < share["high"]
    assert 2 < share["central"] < 20


def test_the_derived_band_sits_below_the_assumed_one(derived):
    """The point of the exercise, pinned.

    The assumed 3–7% was anchored on a residential *property* yield with no arithmetic between
    it and land. Doing the arithmetic moves the answer down far enough that the two bands
    barely overlap — the derived ceiling is about the assumed floor.
    """
    got = derived["summary"]["derivedYieldPercent"]
    assumed = derived["summary"]["assumedYieldPercent"]
    assert got["central"] < assumed["central"]
    assert got["high"] <= assumed["central"]


def test_it_never_stops_saying_it_is_a_derivation(derived):
    assert derived["provenance"]["confidence"] == "derived"
    blocking = {x["id"] for x in derived["limitations"] if x["severity"] == "blocking"}
    assert "nu-e-masuratoare-ci-deducere" in blocking


def test_the_sample_is_declared_as_poor_counties(derived):
    """Biased low, and the file has to say so: no grid exists for București, Cluj or Timiș."""
    ids = {x["id"] for x in derived["limitations"]}
    assert "esantion-de-judete-sarace" in ids
    assert set(derived["counties"]) <= {"HD", "MS", "HR", "IS"}
    assert derived["summary"]["pairs"] >= 100


def test_urban_and_rural_are_reported_apart(derived):
    """Pooling them answers a question nobody asked.

    Building land in a village and in the centre of Iași differ by an order of magnitude in
    land share — about 6% against a third — and 97% of the sampled rows are villages while most
    of the country's building-land value is towns. A single median over rows is dominated by
    the rows, not by the value.
    """
    s = derived["summary"]
    assert s["urbanLandSharePercent"] is not None
    assert s["ruralLandSharePercent"] is not None
    assert s["urbanLandSharePercent"]["central"] > s["ruralLandSharePercent"]["central"]
    assert s["urbanPairs"] + s["ruralPairs"] == s["pairs"]


def test_the_urban_correction_does_not_rescue_the_assumed_band(derived):
    """The bias was real and the conclusion survives it, which is the point of measuring it.

    Adding Iași — the most valuable land in the fourteen counties — raises the derived yield
    from about 2,5% to about 2,7%. That is a correction, not a rescue: the assumed band starts
    at 3%, and the urban figure is still below it.
    """
    urban = derived["summary"]["urbanDerivedYieldPercent"]
    assumed = derived["summary"]["assumedYieldPercent"]
    assert urban is not None
    assert urban["central"] > derived["summary"]["ruralDerivedYieldPercent"]["central"]
    assert urban["central"] < assumed["low"]


def test_every_county_contributes_real_pairs(derived):
    """Eight, not twenty.

    A county that contributes only its zoned towns has few rows by nature — Iași has five
    towns and four zones and yields eleven pairs. Demanding twenty would have excluded the one
    county in the sample where land is expensive, which is the county the sample most needed.
    """
    total = sum(row["pairs"] for row in derived["counties_measured"])
    assert total == derived["summary"]["pairs"]
    for row in derived["counties_measured"]:
        assert row["pairs"] >= 8
        assert 0 < row["landSharePercent"]["central"] < 50

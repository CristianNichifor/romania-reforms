"""Tests for the regional prosecution variant.

This file proposes something the paper does not, so the tests are aimed first at keeping that
visible: a variant that stops announcing itself as a variant is the most damaging failure
available here. After that they check the merge conserves what went into it, that the region
membership is the same one the appellate-court variant uses rather than a second opinion, and
that the inversion this tier turns on is reported rather than smoothed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REGIUNI = ROOT / "simulators/justitie/data/parchete-regiuni.json"
CURTI = ROOT / "simulators/justitie/data/curti-apel-regiuni.json"
COMASARE = ROOT / "simulators/justitie/data/parchete-comasare.json"


@pytest.fixture(scope="module")
def variant() -> dict:
    if not REGIUNI.exists():
        pytest.skip("regional prosecution variant not built")
    return json.loads(REGIUNI.read_text(encoding="utf-8"))


def test_it_says_it_is_not_the_paper(variant):
    """The paper keeps fifteen appellate prosecution offices. Presenting eight as its proposal
    would be inventing policy on its behalf."""
    assert variant["variantOfPaper"] is True
    blocking = {x["id"] for x in variant["limitations"] if x["severity"] == "blocking"}
    assert "regiunile-nu-sunt-in-lucrare" in blocking


def test_the_merge_conserves_volume_and_prosecutors(variant):
    assert sum(r["volume"] for r in variant["regions"]) == variant["summary"]["totalVolume"]
    assert sum(o["volume"] for o in variant["offices"]) == variant["summary"]["totalVolume"]
    assert sum(r["prosecutors"] for r in variant["regions"]) == (
        variant["summary"]["totalProsecutors"]
    )
    assert sum(r["officesBefore"] for r in variant["regions"]) == len(variant["offices"])


def test_every_office_lands_in_exactly_one_region(variant):
    regions = {r["region"] for r in variant["regions"]}
    assert len(regions) == 8
    for office in variant["offices"]:
        assert office["region"] in regions, office["office"]
    for region in variant["regions"]:
        members = [o for o in variant["offices"] if o["region"] == region["region"]]
        assert len(members) == region["officesBefore"], region["region"]
        assert region["volume"] == sum(o["volume"] for o in members)


def test_the_regions_are_the_ones_the_courts_use(variant):
    """Two different eight-region maps in one repository would be worse than none. The court
    variant is the source; this must not have drifted from it."""
    if not CURTI.exists():
        pytest.skip("appellate variant not built")
    curti = json.loads(CURTI.read_text(encoding="utf-8"))
    assert {r["region"] for r in variant["regions"]} == {r["region"] for r in curti["regions"]}
    by_name = {r["region"]: r for r in curti["regions"]}
    for region in variant["regions"]:
        assert region["counties"] == by_name[region["region"]]["counties"], region["region"]
        assert region["seatCounty"] == by_name[region["region"]]["seatCounty"]


def test_merging_narrows_the_spread_but_only_somewhat(variant):
    """Reported honestly: this tier is already far more even than the county tier was, so the
    merger has much less to do and the page must not imply otherwise."""
    before, after = variant["summary"]["spreadBefore"], variant["summary"]["spreadAfter"]
    assert after["maxOverMin"] < before["maxOverMin"]
    # Nothing like the county merger's 14,4 -> 3,2. If this tier ever started that uneven, the
    # claim in the module docstring would need rewriting rather than the test relaxing.
    assert before["maxOverMin"] < 10


def test_the_inversion_is_reported(variant):
    """The office with the most cases has the lightest load. That is the finding, and it is
    about staffing rather than geography, so merging cannot fix it."""
    summary = variant["summary"]
    assert summary["loadRunsBackwards"] is True
    assert summary["biggestToday"] == summary["lightestToday"]
    assert summary["heaviestTodayPerProsecutor"] > summary["biggestTodayPerProsecutor"]
    biggest = next(o for o in variant["offices"] if o["office"] == summary["biggestToday"])
    assert biggest["volume"] == max(o["volume"] for o in variant["offices"])


def test_merging_moves_boundaries_not_people(variant):
    ids = {x["id"] for x in variant["limitations"]}
    assert "comasarea-nu-muta-procurori" in ids
    assert "posturile-sunt-deduse-si-aici" in ids


def test_the_three_tiers_add_up_to_the_service(variant):
    """The point of the file is the whole shape, not one tier of it."""
    structure = variant["summary"]["structure"]
    assert structure["proposedCounty"] == 42
    assert structure["proposedRegional"] == 8
    assert structure["proposedTotal"] == 42 + 8 + 1
    assert structure["proposedTotal"] < structure["todayTotal"]
    if COMASARE.exists():
        comasare = json.loads(COMASARE.read_text(encoding="utf-8"))
        assert structure["proposedCounty"] == comasare["summary"]["officesAfter"]
        assert structure["todayLower"] == comasare["summary"]["officesBefore"]

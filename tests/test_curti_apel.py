"""Tests for the eight-region appellate variant.

This document models something the paper does not propose, so the first duty of these tests is
to make sure it can never be read as the paper's own. The second is the arithmetic: fewer
courts is the easy half of the claim, and the travel it costs is the half that gets dropped.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APEL = ROOT / "simulators/justitie/data/curti-apel-regiuni.json"


@pytest.fixture(scope="module")
def apel() -> dict:
    if not APEL.exists():
        pytest.skip("the appellate variant is not built")
    return json.loads(APEL.read_text(encoding="utf-8"))


def test_it_declares_itself_a_variant(apel):
    """The paper proposes ~15 — the number that already exists. Eight is the author's
    alternative, and a reader must not be able to mistake one for the other."""
    assert apel["variantOfPaper"] is True
    assert apel["provenance"]["confidence"] == "assumed"
    assert "nu-e-propunerea-lucrarii" in {x["id"] for x in apel["limitations"]}


def test_every_county_lands_in_exactly_one_region(apel):
    """Derived from boundary geometry rather than typed, so the partition is the check."""
    seen = collections.Counter()
    for region in apel["regions"]:
        for county in region["counties"]:
            seen[county] += 1
    assert len(seen) == 42, len(seen)
    assert set(seen.values()) == {1}, [c for c, n in seen.items() if n > 1]


def test_the_regions_reproduce_the_statutory_composition(apel):
    """Legea 315/2004 fixes the eight regions at 5, 7, 6, 4, 6, 6, 6 and 2 counties.

    Nothing here enters that; it falls out of polygonising the published boundary lines. If the
    sizes ever stop matching, the derivation has drifted from the law it should reproduce.
    """
    sizes = sorted(len(r["counties"]) for r in apel["regions"])
    assert sizes == [2, 4, 5, 6, 6, 6, 6, 7], sizes


def test_the_region_names_are_distinct(apel):
    """Names come from probing either side of each boundary line and taking a majority. Two
    regions sharing a name is exactly what a mislabelled probe would produce."""
    names = [r["region"] for r in apel["regions"]]
    assert len(set(names)) == 8, names


def test_each_seat_is_the_busiest_court_in_its_region(apel):
    """The stated rule, checked rather than trusted: the seat keeps the work because it already
    carries the most of it."""
    for region in apel["regions"]:
        assert region["seatCounty"] in region["counties"], region["region"]
        assert region["courtsToday"] == len(region["absorbs"]) + 1


def test_consolidation_adds_up(apel):
    summary = apel["summary"]
    assert summary["today"] == 15
    assert summary["variant"] == 8
    assert summary["absorbed"] == sum(len(r["absorbs"]) for r in apel["regions"])
    assert summary["today"] - summary["variant"] == summary["absorbed"]


def test_the_travel_cost_is_carried_beside_the_saving(apel):
    """Eight courts is the attractive half. This is the other half, and it is large: no county
    can come out nearer, because the eight seats are a subset of the fifteen."""
    summary = apel["summary"]
    assert summary["meanMetresToRegionSeat"] > summary["meanMetresToNearestToday"]
    nearer = [
        c["county"]
        for c in apel["counties"]
        if c["metresToRegionSeat"] < c["metresToNearestToday"]
    ]
    assert nearer == [], nearer
    assert 0 < summary["countiesTravellingFurther"] <= summary["countiesCompared"]


def test_the_caseload_attribution_is_declared_unsound(apel):
    """Circuit membership is not published in this repository, so a court's volume is credited
    to the region its seat sits in. Where a circuit crosses a region line that is wrong, and
    the file says so rather than presenting the split as a measurement."""
    blocking = {x["id"] for x in apel["limitations"] if x["severity"] == "blocking"}
    assert "circumscriptiile-nu-sunt-publicate-aici" in blocking


# --- the cross-region question ---------------------------------------------------------------
#
# The county tier routes across county lines because nothing requires a citizen to drive past a
# nearer courthouse. Asked one tier up, the same question has an uncomfortable answer, and these
# tests exist so the answer stays reported rather than quietly dropped.


def test_the_detour_is_computed_against_the_nearest_of_the_eight(apel):
    for county in apel["counties"]:
        assert county["metresToNearestRegionSeat"] <= county["metresToRegionSeat"]
        assert county["detourMetres"] == (
            county["metresToRegionSeat"] - county["metresToNearestRegionSeat"]
        )
        assert county["nearerAnotherRegion"] == (county["nearestRegion"] != county["region"])
        # A county nearest its own seat has no detour, by construction.
        if not county["nearerAnotherRegion"]:
            assert county["detourMetres"] == 0


def test_counties_sent_past_a_nearer_seat_are_counted(apel):
    sent = [c for c in apel["counties"] if c["nearerAnotherRegion"]]
    assert apel["summary"]["countiesNearerAnotherRegion"] == len(sent)
    assert sent, "if this ever became empty the limitation claiming a trade-off is stale"
    worst = max(sent, key=lambda c: c["detourMetres"])
    assert apel["summary"]["worstDetour"]["county"] == worst["county"]
    assert apel["summary"]["worstDetour"]["detourMetres"] == worst["detourMetres"]


def test_the_trade_between_a_legal_geography_and_a_shorter_drive_is_declared(apel):
    """The development regions are statutory. Routing a county to its nearest seat instead means
    not having regions, which is a decision the data can inform and cannot make."""
    assert "regiunile-nu-sunt-cele-mai-apropiate-sedii" in {
        x["id"] for x in apel["limitations"]
    }


def test_the_nearest_region_is_one_of_the_eight(apel):
    names = {r["region"] for r in apel["regions"]}
    for county in apel["counties"]:
        assert county["nearestRegion"] in names


def test_the_missing_circumscriptions_name_the_document_that_would_close_them(apel):
    """A blocking caveat that says only "not published" is unfalsifiable and unactionable.

    This one was re-examined after the identical claim turned out to be wrong for prosecution —
    there, the office's territory was its court's, and HG 1217/2023 had it all along. Here it
    held: the decision arondates only judecatorii, and the CSM annexes list courts flat and
    alphabetically without grouping them under a court of appeal. So the caveat stays blocking,
    but it now names the source that would close it rather than implying none exists.
    """
    caveat = next(
        x for x in apel["limitations"] if x["id"] == "circumscriptiile-nu-sunt-publicate-aici"
    )
    assert caveat["severity"] == "blocking"
    assert "304/2022" in caveat["text"], "the caveat must name the document it is missing"
    assert "HG 1217/2023" in caveat["text"], "and say which sources were checked"

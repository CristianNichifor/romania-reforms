"""Tests for the bypass prioritisation.

The point of this file is that a programme is an order, not a total. Most of these tests guard
the two things that would quietly turn a ranking back into a wish list: the curve must be
sorted cheapest-first, and the unit must keep saying it is capital per ANNUAL hour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "data" / "prioritate.json"


@pytest.fixture(scope="module")
def built() -> dict:
    if not BUILT.exists():
        pytest.skip("prioritisation not built")
    return json.loads(BUILT.read_text(encoding="utf-8"))


def test_the_curve_is_cheapest_first(built):
    """Otherwise it is not a priority order, and 'the first 100 crossings buy a quarter of the
    benefit' stops being true."""
    curve = built["curve"]
    for earlier, later in zip(curve, curve[1:], strict=False):
        assert later["benefitShare"] > earlier["benefitShare"]
        assert later["crossings"] >= earlier["crossings"]
        assert later["costRon"] >= earlier["costRon"]
        # Cheapest first means the marginal crossing only ever gets worse.
        assert later["worstRonPerVehicleHour"] >= earlier["worstRonPerVehicleHour"]


def test_prioritising_beats_building_everything(built):
    """The finding. If the early crossings did not buy disproportionate benefit, there would be
    no argument for an order and the honest advice would be 'all or nothing'."""
    first = built["curve"][0]
    last = built["curve"][-1]
    cost_share = first["costRon"] / last["costRon"]
    assert cost_share < first["benefitShare"], (
        "the cheapest quarter of the benefit should cost less than a quarter of the money"
    )


def test_a_bypass_always_saves_time_for_the_vehicles_on_it(built):
    """Every ranked crossing must have positive hours saved: the arc around is longer, but it
    is fast enough to win. A zero or negative entry means the lengthening factor and the speeds
    have drifted into contradiction."""
    assert built["ranked"]["vehicleHoursYear"] > 0
    for entry in built["top"]:
        assert entry["vehicleHoursYear"] > 0
        assert entry["ronPerVehicleHour"] > 0


def test_the_speeds_are_effective_not_legal(built):
    """A bypass delivers what the road runs at, not what the sign says. If these ever read 50
    and 90 exactly, someone has swapped the measured regime for the legal one and every saving
    here is overstated."""
    speeds = built["speeds"]
    assert speeds["insideKmh"] < 50, speeds
    assert speeds["openKmh"] < 90, speeds
    assert speeds["openKmh"] > speeds["insideKmh"]


def test_the_unit_explains_itself(built):
    """Capital lei per annual vehicle-hour is easy to mistake for lei per hour, which is off by
    the appraisal period — a factor of thirty."""
    unit = built["unit"]
    assert "AN" in unit["what"] or "an" in unit["what"]
    assert unit["howToCompare"]
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "nu-se-aplica-o-valoare-a-timpului" in ids


def test_the_unmatched_crossings_are_bounded_not_ignored(built):
    """The join covers a minority of crossings, and the reason matters: the directive reports
    everything above its threshold, so an absent crossing is quiet rather than unknown."""
    join = built["join"]
    assert join["matched"] < join["crossings"]
    assert join["endThresholdAadt"] > 8_000
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "doar-traversarile-cu-trafic-masurat" in ids


def test_it_says_safety_is_missing(built):
    """Safety is the main reason bypasses get built, and this model cannot see it. A ranking on
    travel time alone systematically undervalues the smallest villages."""
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "beneficiul-e-doar-timpul-soferilor" in ids

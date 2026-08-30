"""The rail speed model is calibrated at both ends; these hold both ends still."""

from __future__ import annotations

import pytest

from scripts import rail_speeds as rs


def test_as_is_reproduces_the_observed_national_average():
    """`as_is` on the measured line speed must return the figure it was calibrated against.

    This is the point of deriving the condition penalty as a residual rather than assuming it:
    the class cannot drift away from the only published number in the model.
    """
    assert rs.class_commercial_kmh("as_is") == pytest.approx(rs.OBSERVED_COMMERCIAL_KMH)


def test_rehabilitation_is_worth_more_than_a_third_again():
    """The headline claim: renewal buys a large speed gain without moving a single curve."""
    gain = rs.class_commercial_kmh("rehabilitated") / rs.class_commercial_kmh("as_is")
    assert gain > 1.3


def test_condition_penalty_is_a_real_penalty_not_a_rounding_artefact():
    """If the residual ever reached 1, the model would be claiming Romanian track is sound."""
    assert 0.4 < rs.condition_factor() < 0.9


def test_stopping_costs_time():
    """A service that stops every 5 km must be slower than one stopping every 20."""
    frequent = rs.commercial_kmh(88.0, stop_spacing_km=5.0)
    sparse = rs.commercial_kmh(88.0, stop_spacing_km=20.0)
    assert frequent < sparse


def test_commercial_speed_never_exceeds_line_speed():
    """A train cannot average more than the track permits, whatever the stopping pattern."""
    for spacing in (2.0, 10.0, 50.0, 200.0):
        assert rs.commercial_kmh(88.0, stop_spacing_km=spacing) < 88.0


def test_loco_hauled_is_slower_than_an_emu():
    """Worse acceleration and longer dwell must show up as a slower service."""
    emu = rs.commercial_kmh(88.0, stock="regional_emu")
    loco = rs.commercial_kmh(88.0, stock="loco_hauled")
    assert loco < emu


def test_rehabilitated_is_capped_by_the_alignment():
    """A line signed far above Danish practice must not be priced above that ceiling."""
    absurd = rs.class_commercial_kmh("rehabilitated", line_kmh=300.0)
    capped = rs.class_commercial_kmh("rehabilitated", line_kmh=rs.DANISH_REGIONAL_CEILING_KMH)
    assert absurd == pytest.approx(capped)


def test_unknown_condition_and_stock_are_refused():
    """A typo must fail loudly rather than silently selecting a default speed."""
    with pytest.raises(ValueError, match="unknown condition"):
        rs.class_commercial_kmh("modernised")
    with pytest.raises(ValueError, match="unknown rolling stock"):
        rs.commercial_kmh(88.0, stock="steam")


def test_nonsense_inputs_are_refused():
    with pytest.raises(ValueError):
        rs.commercial_kmh(0.0)
    with pytest.raises(ValueError):
        rs.commercial_kmh(88.0, stop_spacing_km=0.0)


def test_the_timetable_is_not_an_input():
    """The provenance must keep saying why Mersul Trenurilor is excluded.

    This is documentation held in place by a test on purpose: the reasoning inverted once
    already this project, and the note is the only place it is written down next to the number.
    """
    assert "Mersul" in rs.RAIL_SPEED_PROVENANCE["note"]
    assert rs.RAIL_SPEED_PROVENANCE["confidence"] == "derived"

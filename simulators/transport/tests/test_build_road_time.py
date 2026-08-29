"""Tests for the seat-to-seat travel-time build.

The expensive part of this script is administrativ's, already tested over there. What is
tested here is the part L0 owns: that the output is shaped right, that unreachable pairs are
reported rather than dropped, and that the artefact is deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
ADMINISTRATIV = ROOT / "simulators/administrativ"
sys.path.insert(0, str(ADMINISTRATIV))

from scripts.build_road_time import (  # noqa: E402
    SEARCH_LIMIT_S,
    plausibility,
    time_table,
)


def test_it_pairs_every_edge_with_a_time():
    pairs = [("1", "2"), ("2", "3")]
    seconds = np.array([600.0, 1200.0])
    table = time_table(pairs, seconds)
    assert list(table["a_siruta"]) == ["1", "2"]
    assert list(table["road_s"]) == [600.0, 1200.0]


def test_it_is_sorted_so_the_artefact_is_byte_reproducible():
    """Same inputs must give the same file. Parquet is byte-reproducible; dict ordering is
    not, so the sort is what makes the determinism check in CI meaningful."""
    pairs = [("9", "1"), ("2", "3")]
    table = time_table(pairs, np.array([10.0, 20.0]))
    assert list(table["a_siruta"]) == ["2", "9"]


def test_it_carries_minutes_as_well_as_seconds():
    """The whole point of L0 is that a reader thinks in minutes. Rounding once, here, stops
    four consumers rounding differently."""
    table = time_table([("1", "2")], np.array([630.0]))
    assert table["road_min"].iloc[0] == pytest.approx(10.5)


def test_an_unreachable_pair_survives_as_infinity_rather_than_vanishing():
    """A dropped row is a commune with no journey that nobody counted. It must reach the
    report as infinity and be counted there, not disappear between the two."""
    table = time_table([("1", "2")], np.array([np.inf]))
    assert len(table) == 1
    assert np.isinf(table["road_s"].iloc[0])


def test_plausibility_flags_a_time_that_beats_the_motorway():
    """No pair of adjacent commune seats is reachable at 130 km/h door to door. If one is,
    the speed table or the snapping is wrong."""
    fast = plausibility(distance_m=np.array([50_000.0]), seconds=np.array([600.0]))
    assert fast["implausible"] == 1


def test_plausibility_accepts_an_ordinary_pair():
    ok = plausibility(distance_m=np.array([20_000.0]), seconds=np.array([1_500.0]))
    assert ok["implausible"] == 0
    assert ok["median_kmh"] == pytest.approx(48.0)


def test_plausibility_ignores_unreachable_pairs():
    """An infinite time has no implied speed; including it would make the median useless."""
    mixed = plausibility(
        distance_m=np.array([20_000.0, 30_000.0]),
        seconds=np.array([1_500.0, np.inf]),
    )
    assert mixed["implausible"] == 0
    assert mixed["median_kmh"] == pytest.approx(48.0)


def test_the_search_limit_covers_the_distance_limit():
    """Administrativ bounds its search at 60 km. At the slowest class in the table that is
    well over an hour, so a limit shorter than that would silently drop real neighbours."""
    assert SEARCH_LIMIT_S >= 60_000 / (20.0 / 3.6)

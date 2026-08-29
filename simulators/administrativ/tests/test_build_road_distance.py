"""Tests for the road graph's weighting.

The graph is built from ten million vertices by a hand-rolled hashing trick, so it is not
something to change casually. These tests pin the two things a caller depends on: that the
default weight is still length, and that a supplied speed produces seconds.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

from pipeline.build_geometry import Report
from pipeline.build_road_distance import build_graph
from pipeline.constants import CRS_STEREO70


def two_roads() -> gpd.GeoDataFrame:
    """Two straight 1 000 m segments meeting end to end, in projected metres."""
    return gpd.GeoDataFrame(
        {"highway": ["motorway", "residential"]},
        geometry=[
            LineString([(0.0, 0.0), (1000.0, 0.0)]),
            LineString([(1000.0, 0.0), (2000.0, 0.0)]),
        ],
        crs=CRS_STEREO70,
    )


def test_the_default_weight_is_still_length_in_metres():
    """Administrativ's whole model reads this graph. If the default changed, every region
    boundary in the country would move and the parity fixtures would be the only warning."""
    graph, _, _, _ = build_graph(two_roads(), Report())
    assert graph.sum() == pytest.approx(2 * 2000.0)  # two segments, stored both directions


def test_a_speed_turns_the_weight_into_seconds():
    """1 000 m at 100 km/h is 36 s; 1 000 m at 50 km/h is 72 s."""
    speed = np.array([100.0, 50.0])
    graph, _, _, _ = build_graph(two_roads(), Report(), speed_kmh=speed)
    assert graph.sum() == pytest.approx(2 * (36.0 + 72.0))


def test_the_speed_applies_per_feature_not_globally():
    """The two segments must not share one speed — that would flatten the whole table."""
    speed = np.array([100.0, 50.0])
    graph, _, _, _ = build_graph(two_roads(), Report(), speed_kmh=speed)
    weights = sorted(graph.tocoo().data.tolist())
    assert weights == pytest.approx([36.0, 36.0, 72.0, 72.0])


def test_a_multi_vertex_line_splits_its_time_across_segments():
    """A road digitised as many short segments must total the same time as one long one."""
    roads = gpd.GeoDataFrame(
        {"highway": ["motorway"]},
        geometry=[LineString([(0.0, 0.0), (500.0, 0.0), (1000.0, 0.0)])],
        crs=CRS_STEREO70,
    )
    graph, _, _, _ = build_graph(roads, Report(), speed_kmh=np.array([100.0]))
    assert graph.sum() == pytest.approx(2 * 36.0)


def test_a_wrong_length_speed_array_is_rejected():
    """Passing one speed for the wrong number of features would silently misprice roads
    through numpy broadcasting rather than failing."""
    with pytest.raises(ValueError, match="one speed per road feature"):
        build_graph(two_roads(), Report(), speed_kmh=np.array([100.0]))


def test_zero_length_segments_do_not_become_infinite_time():
    """Snapping collapses near-duplicate vertices; a self-loop must be dropped, not divided."""
    roads = gpd.GeoDataFrame(
        {"highway": ["residential"]},
        geometry=[LineString([(0.0, 0.0), (0.1, 0.0), (1000.0, 0.0)])],
        crs=CRS_STEREO70,
    )
    graph, _, _, _ = build_graph(roads, Report(), speed_kmh=np.array([50.0]))
    assert np.isfinite(graph.tocoo().data).all()

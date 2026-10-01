"""Bounded synthetic pipeline-to-model tests, not a national-data certificate.

Eight 2 km squares form a road-connected chain crossing a county boundary. All six
loader inputs are materialised in a temporary directory. National assertions remain
in test_reference_model.py under the explicit full_data marker.
"""

from __future__ import annotations

import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from pipeline import reference_model as model
from pipeline.constants import CRS_STEREO70, RADIUS_GRID_M


@pytest.fixture
def processed_fixture(tmp_path, monkeypatch):
    ids = [str(i) for i in range(1, 9)]
    population = [20000, 1000, 1000, 10000, 20000, 1000, 1000, 10000]
    geometry = gpd.GeoDataFrame(
        {
            "siruta": ids,
            "name_uat": [f"Synthetic {s}" for s in ids],
            "county_code": ["XX"] * 4 + ["YY"] * 4,
            "population": population,
            "natlevname": ["Oras", "Comuna", "Comuna", "Oras"] * 2,
            "geometry": [box(i * 2000, 0, (i + 1) * 2000, 2000) for i in range(8)],
        },
        crs=CRS_STEREO70,
    )
    geometry.to_file(tmp_path / "uat_geometry.gpkg", layer="uat")
    gpd.GeoDataFrame(
        {"siruta": ids, "geometry": [Point(i * 2000 + 1000, 1000) for i in range(8)]},
        crs=CRS_STEREO70,
    ).to_file(tmp_path / "uat_seats.gpkg", layer="seat")
    pd.DataFrame(
        {
            "a_siruta": ids[:-1],
            "b_siruta": ids[1:],
            "shared_border_m": [2000.0] * 7,
            "traversable": [True] * 7,
        }
    ).to_parquet(tmp_path / "adjacency.parquet")
    pd.DataFrame(
        {
            "a_siruta": ids[:-1],
            "b_siruta": ids[1:],
            "road_m": [2000.0] * 7,
            "straight_m": [2000.0] * 7,
        }
    ).to_parquet(tmp_path / "road_distance.parquet")
    pd.DataFrame(
        {"siruta": ids, "operating_ron": [1000.0] * 8, "administrative_ron": [100.0] * 8}
    ).to_parquet(tmp_path / "finance.parquet")
    rows = []
    for radius in RADIUS_GRID_M:
        for a in (0, 3, 4, 7):
            for b in range(8):
                if a != b and a // 4 == b // 4 and abs(a - b) * 2000 <= radius:
                    rows.append((radius, ids[a], ids[b], 1.0, True))
    pd.DataFrame(
        rows,
        columns=["radius_m", "absorber_siruta", "uat_siruta", "overlap_fraction", "seat_inside"],
    ).to_parquet(tmp_path / "candidacy.parquet")
    monkeypatch.setattr(model, "PROCESSED_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize("target", [0, 25000, 50000])
def test_pipeline_fixture_runs_every_model_phase(processed_fixture, target):
    data = model.load_data()
    original = copy.deepcopy(data)
    params = model.Params(n_min=1, p_target=target, min_compactness=0)
    result, summary = model.run(data, params)
    assert data == original, "the reference model must not mutate its inputs"
    assert summary["uats"] == 8
    assert summary["unassigned"] == 0
    members = [m for group in result.members.values() for m in group]
    assert sorted(members) == sorted(data.population)
    for seat, group in result.members.items():
        assert seat in group
        assert model._is_connected(data, group)
        assert len({data.county[m] for m in group}) == 1
    assert summary["savings_admin_ron"] == (8 - summary["regions"]) * 100
    assert summary["savings_operating_ron"] == (8 - summary["regions"]) * 1000
    again, again_summary = model.run(data, params)
    assert again == result
    assert again_summary == summary


def test_connected_counties_cannot_merge_even_under_large_target(processed_fixture):
    result, summary = model.run(
        model.load_data(), model.Params(n_min=1, p_target=50000, min_compactness=0)
    )
    assert {seat: sorted(members) for seat, members in result.members.items()} == {
        "1": ["1", "2", "3", "4"],
        "5": ["5", "6", "7", "8"],
    }
    assert summary["regions"] == 2
    assert summary["savings_admin_ron"] == 600


@pytest.mark.parametrize(
    "name",
    [
        "uat_geometry.gpkg",
        "uat_seats.gpkg",
        "adjacency.parquet",
        "road_distance.parquet",
        "candidacy.parquet",
        "finance.parquet",
    ],
)
def test_loader_refuses_each_missing_input(processed_fixture, name):
    (processed_fixture / name).unlink()
    with pytest.raises(SystemExit, match=f"Missing .*{name}"):
        model.load_data()

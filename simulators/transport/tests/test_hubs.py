"""Tests for the frozen hub assignment.

This file is the transport engine's only input from the administrative simulator, so what
matters is that it covers everything, that it is internally consistent, and that it cannot
drift out from under this simulator without saying so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUBS = ROOT / "data" / "hubs.json"


@pytest.fixture(scope="module")
def hubs() -> dict:
    if not HUBS.exists():
        pytest.skip("hub assignment not exported")
    return json.loads(HUBS.read_text(encoding="utf-8"))


def test_every_uat_has_exactly_one_hub(hubs):
    """A UAT missing here is a settlement with no route, and a settlement with no route is a
    cost nobody counted — which flatters every figure built on top."""
    assert len(hubs["hubOf"]) == hubs["summary"]["uats"] == 3186


def test_every_hub_is_itself_a_uat_in_the_map(hubs):
    """A hub that is not in the map is a route terminating at a place the model does not
    know, which would fail later and further from the cause."""
    known = set(hubs["hubOf"])
    unknown = sorted({h for h in hubs["hubOf"].values() if h not in known})
    assert unknown == [], unknown[:10]


def test_a_hub_serves_itself(hubs):
    """A centre must belong to its own region. If one does not, the accretion assigned it
    away and the map has a centre nobody is attached to."""
    wrong = [h for h in set(hubs["hubOf"].values()) if hubs["hubOf"][h] != h]
    assert wrong == [], wrong[:10]


def test_the_summary_matches_the_map(hubs):
    """A summary that disagrees with its own rows would still read as an answer."""
    hub_ids = set(hubs["hubOf"].values())
    assert hubs["summary"]["hubs"] == len(hub_ids)
    counts = sorted(sum(1 for v in hubs["hubOf"].values() if v == h) for h in hub_ids)
    assert hubs["summary"]["membersMin"] == counts[0]
    assert hubs["summary"]["membersMax"] == counts[-1]
    assert hubs["summary"]["membersMedian"] == counts[len(counts) // 2]


def test_the_scenario_still_matches_administrativs_defaults():
    """The drift guard. This simulator freezes administrativ's defaults by value, so if a
    default moves upstream every route here changes with nothing in the diff to show it.

    Failing is not necessarily a bug — it may be a deliberate upstream change — but it must
    be noticed and the export re-run, rather than discovered as a shifted cost months later.
    """
    import sys

    sys.path.insert(0, str(ROOT.parent / "administrativ"))
    try:
        from pipeline.reference_model import Params
    except ImportError:
        pytest.skip("administrativ pipeline not importable")

    from scripts.export_hubs import SCENARIO

    defaults = Params()
    for key, value in SCENARIO.items():
        assert getattr(defaults, key) == value, (
            f"administrativ's default for {key} is now {getattr(defaults, key)}, "
            f"not the {value} this export was frozen at — re-run scripts/export_hubs.py"
        )


def test_the_recorded_scenario_is_the_one_in_the_file(hubs):
    """The parameters in the document must be the parameters the script would use, or the
    file is describing a scenario it was not produced by."""
    from scripts.export_hubs import SCENARIO

    assert hubs["scenario"] == SCENARIO


def test_the_consolidation_actually_consolidates(hubs):
    """Fewer centres than UATs, or this is not a consolidation scenario at all."""
    assert hubs["summary"]["hubs"] < hubs["summary"]["uats"]
    assert 0 < hubs["summary"]["reductionPct"] < 100


def test_the_savings_travel_with_the_map(hubs):
    """Both columns of the ledger in one place. Consolidation is argued as a saving; this
    simulator exists to price what it costs in travel, and quoting either alone is the
    thing the design document set out to stop."""
    assert hubs["savingsRon"]["administrative"] > 0
    assert hubs["savingsRon"]["operating"] > 0


def test_a_singleton_hub_is_reported_not_hidden(hubs):
    """A hub serving only itself has no feeder route to run. The count is small and the
    number must be visible, because those are the places a network plan quietly skips."""
    hub_ids = set(hubs["hubOf"].values())
    singletons = sum(1 for h in hub_ids if sum(1 for v in hubs["hubOf"].values() if v == h) == 1)
    assert hubs["summary"]["singletonHubs"] == singletons


def test_the_limitation_about_one_scenario_is_declared(hubs):
    ids = {limitation["id"] for limitation in hubs["limitations"]}
    assert "un-singur-scenariu" in ids

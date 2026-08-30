"""Tests for the caseload each proposed court would carry.

The first version of this routing silently dropped 14% of the national caseload — every
Bucharest sector among it — because the government decision and the CSM register spell ten
courts differently and an unmatched court was treated as dormant. Nothing failed; the totals
just came out smaller. Most of these tests exist because of that: they check that every case is
accounted for, that "dormant" means one named court rather than "we could not find it", and
that the population split is measured rather than assumed away.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INCARCATURA = ROOT / "simulators/justitie/data/incarcatura-noua.json"
LOCATED = ROOT / "simulators/justitie/data/instante-localizate-2025.json"


@pytest.fixture(scope="module")
def load() -> dict:
    if not INCARCATURA.exists():
        pytest.skip("court caseload not built")
    return json.loads(INCARCATURA.read_text(encoding="utf-8"))


def test_every_case_in_the_register_is_routed(load):
    """The regression that motivated this file. If a court fails to match, its volume must not
    quietly vanish: routed volume has to equal the national level-one volume exactly."""
    summary = load["summary"]
    assert summary["routedVolume"] == summary["nationalLevelOneVolume"]


def test_routed_volume_arrives_somewhere(load):
    """Every routed case either lands at a seat or is counted as unreachable. Nothing else."""
    summary = load["summary"]
    landed = sum(c["lowerVolume"] for c in load["courts"])
    assert landed + summary["unreachableVolume"] == pytest.approx(
        summary["routedVolume"], abs=len(load["courts"])
    )


def test_dormant_means_one_named_court_not_a_failed_lookup(load):
    """'Dormant' is an assertion about the world and must stay expensive to claim."""
    dormant = load["summary"]["dormantCourts"]
    assert len(dormant) == 1
    assert "nsur" in dormant[0]


def test_the_two_levels_are_kept_apart_and_add_up(load):
    for court in load["courts"]:
        assert court["volume"] == court["lowerVolume"] + court["upperVolume"], court["name"]
    summary = load["summary"]
    assert summary["totalVolume"] == sum(c["volume"] for c in load["courts"])
    assert summary["tribunalVolume"] == sum(c["upperVolume"] for c in load["courts"])


def test_how_much_rests_on_the_population_split_is_reported(load):
    """The split is an assumption; the honest move is to measure its reach rather than defend
    it. Most of the volume must be assignment-invariant or the finding is modelling, not
    arithmetic."""
    summary = load["summary"]
    assert summary["invariantVolume"] + summary["splitVolume"] == summary["routedVolume"]
    assert summary["invariantShare"] == pytest.approx(
        summary["invariantVolume"] / summary["routedVolume"], rel=1e-2
    )
    assert summary["invariantShare"] > 0.5
    ids = {x["id"] for x in load["limitations"]}
    assert "dosarele-se-impart-dupa-populatie" in ids


def test_the_merger_tightens_the_middle(load):
    """The robust measure is where the evening-out shows; max/min is dominated by Bucharest."""
    today, after = load["summary"]["spreadToday"], load["summary"]["spreadAfter"]
    assert after["p90OverP10"] < today["p90OverP10"]
    assert after["min"] > today["min"]


def test_bucharest_stays_an_outlier(load):
    """The half that does not flatter the proposal, and it must not be droppable."""
    summary = load["summary"]
    busiest = max(load["courts"], key=lambda c: c["volume"])
    assert busiest["volume"] == summary["busiestVolume"]
    assert summary["busiestShareOfTotal"] > 0.1
    assert summary["spreadAfter"]["maxOverMin"] > 10


def test_caseload_per_head_is_far_more_even_than_volume(load):
    """The reason the remaining spread is the county map's rather than the merger's."""
    summary = load["summary"]
    assert summary["spreadPerCapita"]["p90OverP10"] < summary["spreadAfter"]["p90OverP10"]


def test_the_delta_is_counted_not_reassigned(load):
    """Sulina has no road to any seat. Forcing it onto one would invent an access route."""
    summary = load["summary"]
    assert summary["unreachableCommunes"] > 0
    assert summary["unreachableVolume"] > 0
    assert "delta-nu-are-drum" in {x["id"] for x in load["limitations"]}


def test_judges_are_a_size_not_an_establishment(load):
    if not LOCATED.exists():
        pytest.skip("court register not built")
    averages = json.loads(LOCATED.read_text(encoding="utf-8"))["nationalAverages"]["byTier"]
    judecatorie = next(t for t in averages if t["tier"] == "judecatorie")
    assert load["summary"]["loadPerJudge"] == judecatorie["perJudge"]
    for court in load["courts"]:
        assert court["judgesAtNationalLoad"] == pytest.approx(
            court["volume"] / judecatorie["perJudge"], rel=1e-2
        )
    assert "judecatorii-la-media-nationala" in {x["id"] for x in load["limitations"]}

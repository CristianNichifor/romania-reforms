"""Tests for the prosecution establishment against its caseload.

This file computes how many people are in the wrong place, which is the most misreadable number
the repository produces: it is one edit away from looking like a transfer list. The first test
is about that and is not negotiable.

The rest check the arithmetic cannot flatter itself — that the equalisation conserves headcount,
that each tier is levelled against its own mean rather than a pooled one that would describe
neither, and that the "recruit instead of transfer" finding is a real comparison rather than a
number chosen to be smaller than the vacancies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INCADRARE = ROOT / "simulators/justitie/data/parchete-incadrare.json"
PARCHETE = ROOT / "simulators/justitie/data/parchete-2025.json"
COMASARE = ROOT / "simulators/justitie/data/parchete-comasare.json"
REGIUNI = ROOT / "simulators/justitie/data/parchete-regiuni.json"


@pytest.fixture(scope="module")
def staffing() -> dict:
    if not INCADRARE.exists():
        pytest.skip("establishment analysis not built")
    return json.loads(INCADRARE.read_text(encoding="utf-8"))


def test_it_refuses_to_be_a_personnel_plan(staffing):
    """A prosecutor is not a unit of capacity. If this caveat ever stops being blocking, the
    page starts reading as a list of people to move, which it must never be."""
    assert staffing["variantOfPaper"] is True
    blocking = [x for x in staffing["limitations"] if x["severity"] == "blocking"]
    assert any(x["id"] == "nu-e-un-plan-de-personal" for x in blocking)


def test_equalisation_conserves_the_corps(staffing):
    """Nobody is created. Arrivals and departures may differ only by the rounding to whole
    people, and that drift is reported rather than hidden."""
    for tier in staffing["levels"]:
        assert sum(r["prosecutors"] for r in tier["rows"]) == tier["totalProsecutors"]
        assert sum(r["volume"] for r in tier["rows"]) == tier["totalVolume"]
        assert tier["netRoundingDrift"] == tier["arrivals"] - tier["departures"]
        assert abs(tier["netRoundingDrift"]) <= tier["offices"]


def test_each_row_is_its_own_arithmetic(staffing):
    for tier in staffing["levels"]:
        for row in tier["rows"]:
            assert row["delta"] == row["equalised"] - row["prosecutors"], row["name"]
            assert row["perProsecutor"] == pytest.approx(
                row["volume"] / row["prosecutors"], rel=1e-2
            )
            # An office with cases always keeps somebody in it.
            assert row["equalised"] >= 1


def test_each_tier_is_levelled_against_its_own_mean(staffing):
    """Pooling a county office and a regional one would produce a target that describes
    neither: they are different grades doing different work."""
    targets = [t["targetPerProsecutor"] for t in staffing["levels"]]
    assert len(set(targets)) == len(targets)
    for tier in staffing["levels"]:
        assert tier["targetPerProsecutor"] == pytest.approx(
            tier["totalVolume"] / tier["totalProsecutors"], rel=1e-2
        )


def test_the_rebalancing_is_smaller_than_the_vacancies(staffing):
    """The finding that makes this humane rather than brutal: the service is already short of
    more people than the rebalancing needs, so it could be done by recruitment placement."""
    if not PARCHETE.exists():
        pytest.skip("parchete-2025 not imported")
    parchete = json.loads(PARCHETE.read_text(encoding="utf-8"))
    summary = staffing["summary"]
    assert summary["vacantPosts"] == parchete["totals"]["vacant"]
    assert summary["vacanciesCoverArrivals"] is True
    assert summary["arrivals"] < summary["vacantPosts"]
    assert summary["arrivalsAsShareOfVacancies"] == pytest.approx(
        summary["arrivals"] / summary["vacantPosts"], rel=1e-2
    )
    assert "vacantele-nu-sunt-pe-parchet" in {x["id"] for x in staffing["limitations"]}


def test_the_summary_totals_the_tiers(staffing):
    summary = staffing["summary"]
    assert summary["arrivals"] == sum(t["arrivals"] for t in staffing["levels"])
    assert summary["departures"] == sum(t["departures"] for t in staffing["levels"])
    assert summary["totalProsecutors"] == sum(t["totalProsecutors"] for t in staffing["levels"])


def test_the_inversion_was_checked_against_its_best_objection(staffing):
    """A big office can look lightly loaded because its prosecutors do other work. The report's
    investigation-only column is the test for that, and the finding has to survive it."""
    summary = staffing["summary"]
    assert summary["inversionSurvivesInvestigationMeasure"] is True
    assert summary["investigationLoadHeaviest"] > summary["investigationLoadBiggest"]


def test_the_tiers_are_the_ones_built_elsewhere(staffing):
    """This reads the two proposed structures rather than restating them; if it ever drifted
    from them the numbers would be about a service that exists nowhere."""
    county = next(t for t in staffing["levels"] if t["offices"] == 42)
    regional = next(t for t in staffing["levels"] if t["offices"] == 8)
    if COMASARE.exists():
        comasare = json.loads(COMASARE.read_text(encoding="utf-8"))
        assert county["totalVolume"] == comasare["summary"]["totalVolume"]
        assert county["totalProsecutors"] == comasare["summary"]["totalProsecutors"]
    if REGIUNI.exists():
        regiuni = json.loads(REGIUNI.read_text(encoding="utf-8"))
        assert regional["totalVolume"] == regiuni["summary"]["totalVolume"]
        assert regional["totalProsecutors"] == regiuni["summary"]["totalProsecutors"]


def test_cases_are_not_claimed_to_be_equal_work(staffing):
    assert "dosarele-nu-sunt-egale" in {x["id"] for x in staffing["limitations"]}

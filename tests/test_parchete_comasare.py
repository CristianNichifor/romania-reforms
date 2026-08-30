"""Tests for the prosecution merger run on the CSM's published volumes.

This file reports the one finding in the repository that favours the paper, so the tests are
aimed at the ways it could be flattering by construction: a spread that narrows because an
office was dropped rather than because work evened out, a merged total that does not equal what
went into it, or a headline ratio computed on two extremes that the report itself prints as
oddities.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMASARE = ROOT / "simulators/justitie/data/parchete-comasare.json"
PARCHETE = ROOT / "simulators/justitie/data/parchete-2025.json"


@pytest.fixture(scope="module")
def merger() -> dict:
    if not COMASARE.exists():
        pytest.skip("prosecution merger not built")
    return json.loads(COMASARE.read_text(encoding="utf-8"))


def test_the_merger_lands_on_the_forty_two_offices_the_paper_proposes(merger):
    assert merger["summary"]["officesAfter"] == 42
    assert len(merger["merged"]) == 42
    assert len({o["county"] for o in merger["merged"]}) == 42


def test_no_case_is_created_or_lost_in_the_merge(merger):
    """Every merged office is exactly its two levels added together, and the national total is
    the sum of the offices."""
    total = 0
    for office in merger["merged"]:
        assert office["volume"] == office["lowerVolume"] + office["upperVolume"], office["county"]
        total += office["volume"]
    assert total == merger["summary"]["totalVolume"]
    assert sum(o["prosecutors"] for o in merger["merged"]) == merger["summary"]["totalProsecutors"]


def test_every_merged_office_has_someone_in_it(merger):
    for office in merger["merged"]:
        assert office["prosecutors"] > 0, office["county"]
        assert office["perProsecutor"] == pytest.approx(
            office["volume"] / office["prosecutors"], rel=1e-2
        )


def test_the_spread_narrows_on_both_measures(merger):
    """The headline. It must hold on the robust measure too, or it is an artefact of the two
    offices at the ends — and the report prints some very odd ends."""
    before, after = merger["summary"]["spreadBefore"], merger["summary"]["spreadAfter"]
    assert after["maxOverMin"] < before["maxOverMin"]
    assert after["p90OverP10"] < before["p90OverP10"]
    assert merger["summary"]["maxOverMinFalls"] == pytest.approx(
        before["maxOverMin"] - after["maxOverMin"], rel=1e-2
    )


def test_the_dormant_office_is_kept_but_not_counted_as_a_workload(merger):
    """Însurăței is printed with zeros across the row. Dropping it silently would narrow the
    spread for free; keeping it in the spread would divide by zero. It is excluded on purpose
    and the exclusion is declared."""
    summary = merger["summary"]
    assert summary["dormantOffices"], "the zero-row office should still be reported"
    assert summary["activeOfficesBefore"] == summary["officesBefore"] - len(
        summary["dormantOffices"]
    )
    assert summary["spreadBefore"]["min"] > 0
    ids = {x["id"] for x in merger["limitations"]}
    assert "un-parchet-fara-instanta" in ids


def test_consolidation_concentrates_as_well_as_evens(merger):
    """The finding cuts both ways and both halves have to survive: pooling Bucharest's offices
    puts a large share of the national caseload in one place."""
    summary = merger["summary"]
    assert 0 < summary["busiestShareOfTotal"] < 1
    busiest = next(o for o in merger["merged"] if o["county"] == summary["busiestCounty"])
    assert busiest["volume"] == summary["busiestVolume"]
    assert busiest["volume"] == max(o["volume"] for o in merger["merged"])
    heaviest = next(o for o in merger["merged"] if o["county"] == summary["heaviestCounty"])
    assert heaviest["perProsecutor"] == max(o["perProsecutor"] for o in merger["merged"])


def test_the_two_levels_are_not_pretended_to_be_the_same_case(merger):
    ids = {x["id"] for x in merger["limitations"]}
    assert "doua-feluri-de-dosare-adunate" in ids
    assert "dosare-de-solutionat-nu-munca-facuta" in ids


def test_merging_by_county_is_declared_as_the_papers_rule_not_a_choice(merger):
    """The court half of this simulator routes across county lines by distance. Prosecution
    cannot, and the reason has to stay visible or the two halves look inconsistent."""
    blocking = {x["id"] for x in merger["limitations"] if x["severity"] == "blocking"}
    assert "comasare-pe-judet-nu-pe-distanta" in blocking


def test_the_older_parchete_document_no_longer_claims_this_is_unmodelled(merger):
    """parchete-2025 carried a blocking limitation saying the redistribution was not computed.
    It is now, and a stale blocking caveat is its own kind of wrong answer."""
    if not PARCHETE.exists():
        pytest.skip("parchete-2025 not imported")
    parchete = json.loads(PARCHETE.read_text(encoding="utf-8"))
    ids = {x["id"] for x in parchete["limitations"]}
    assert "volumul-parchetelor-nu-e-modelat" not in ids
    assert "volumul-parchetelor-e-in-alta-parte" in ids

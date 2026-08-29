"""Tests for the two-reform comparison.

The failure to guard against is not arithmetic but false equivalence: one document is a
government bill and the other is this site author's paper, and a page that showed them as
peers would be lending the second the standing of the first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "simulators/justitie/data/pensii-comparatie.json"


@pytest.fixture(scope="module")
def comparison() -> dict:
    if not FILE.exists():
        pytest.skip("comparison not built")
    return json.loads(FILE.read_text(encoding="utf-8"))


def test_the_paper_is_marked_unpublished(comparison):
    assert comparison["published"] is False
    assert any(x["id"] == "lucrarea-nu-e-lege" for x in comparison["limitations"])


def test_the_bill_is_quoted_and_the_paper_is_too(comparison):
    assert comparison["bill"]["provenance"]["confidence"] == "verbatim"
    assert comparison["paper"]["provenance"]["confidence"] == "verbatim"
    assert "p. 58" in comparison["paper"]["provenance"]["locator"]


def test_the_sporuri_disagreement_is_named(comparison):
    """The two reforms move in opposite directions on the detail that decides the amount.
    If this ever stops being recorded, the comparison has lost its point."""
    assert any(d["id"] == "sporurile-in-baza" for d in comparison["disagreements"])


def test_the_paper_is_the_stricter_of_the_two(comparison):
    """Its flat cap sits below the bill's floor for every grade but the trainee.

    Recomputed rather than asserted in prose, so the claim cannot drift from the figures.
    """
    below = [r for r in comparison["byGrade"] if r["paperCapBelowBillFloor"]]
    assert len(below) >= 4, [r["grade"] for r in below]
    for row in comparison["byGrade"]:
        assert row["paperCapBelowBillFloor"] == (row["paperCapLei"] < row["billFloorLei"])


def test_the_cap_is_one_average_wage(comparison):
    wage = comparison["averageGrossWageLei"]
    assert 5_000 < wage < 20_000, wage
    for row in comparison["byGrade"]:
        assert abs(row["paperCapLei"] - wage) <= 1, row["grade"]


def test_it_does_not_claim_to_compute_the_paper_s_pension(comparison):
    """The paper's formula starts from a contributory pension nobody can compute from here,
    so only its cap is shown — and the document has to say that rather than imply a total."""
    ids = {x["id"] for x in comparison["limitations"]}
    assert "pensia-contributiva-nu-e-calculata" in ids

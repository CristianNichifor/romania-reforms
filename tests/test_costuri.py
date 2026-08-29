"""Tests for the judiciary's base wage bill.

Money is the part of a reform argument people quote without checking, so these recompute the
totals from their own parts rather than trusting a summary, and pin the two unknowns that
decide the answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COSTURI = ROOT / "simulators/justitie/data/costuri-2025.json"
GRADES = ROOT / "simulators/justitie/data/indemnizatii-2022.json"
COURTS = ROOT / "simulators/justitie/data/instante-localizate-2025.json"

MONTHS = 12


@pytest.fixture(scope="module")
def costuri() -> dict:
    if not COSTURI.exists():
        pytest.skip("costs not built")
    return json.loads(COSTURI.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grades() -> dict:
    if not GRADES.exists():
        pytest.skip("pay grades not imported")
    return json.loads(GRADES.read_text(encoding="utf-8"))


def test_every_court_tier_has_a_pay_grade(costuri, grades):
    """An unpriced tier costs zero, which reads as a finding rather than a hole."""
    for tier in ("iccj", "curte-de-apel", "tribunal", "judecatorie"):
        assert tier in costuri["monthlyLeiByTier"], tier
        assert costuri["monthlyLeiByTier"][tier] > 0, tier
    assert set(grades["tierToGrade"]) == set(costuri["monthlyLeiByTier"])


def test_the_total_is_the_sum_of_its_tiers(costuri):
    parts = sum(row["annualLei"] for row in costuri["today"]["byTier"])
    assert abs(parts - costuri["today"]["annualLei"]) <= len(costuri["today"]["byTier"])


def test_each_tier_recomputes_from_judges_and_pay(costuri):
    for row in costuri["today"]["byTier"]:
        expected = row["judges"] * row["monthlyLei"] * MONTHS
        assert abs(expected - row["annualLei"]) <= 1, row["tier"]


def test_the_grades_are_ordered_by_seniority_of_court(costuri):
    """A judecatorie judge cannot out-earn one at the Inalta Curte.

    Cheap to assert and it would catch a mis-parsed table, which is how this data arrives:
    scraped out of an HTML annex by row position.
    """
    pay = costuri["monthlyLeiByTier"]
    assert pay["iccj"] > pay["curte-de-apel"] > pay["tribunal"] > pay["judecatorie"]


def test_both_grade_readings_are_computed(costuri):
    """The paper does not say what grade a merged court's judges hold, and it decides a third
    of the answer. Neither reading may be dropped."""
    grades_used = {s["gradePaid"] for s in costuri["scenarios"]}
    assert grades_used == {"judecatorie", "tribunal"}, grades_used
    for target in {s["target"] for s in costuri["scenarios"]}:
        at_target = [s for s in costuri["scenarios"] if s["target"] == target]
        assert len(at_target) == 2, target


def test_the_answer_spans_a_saving_and_an_increase(costuri):
    """The point of the whole document: with the two unknowns open, consolidation's effect on
    the wage bill is not determined — it runs from money saved to money spent."""
    differences = [s["differenceLei"] for s in costuri["scenarios"]]
    assert min(differences) < 0 < max(differences), differences


def test_a_higher_caseload_target_needs_fewer_judges(costuri):
    for grade in ("judecatorie", "tribunal"):
        rows = sorted(
            (s for s in costuri["scenarios"] if s["gradePaid"] == grade),
            key=lambda s: s["target"],
        )
        needed = [s["judgesNeeded"] for s in rows]
        assert needed == sorted(needed, reverse=True), (grade, needed)


def test_the_two_blocking_gaps_are_declared(costuri):
    ids = {x["id"] for x in costuri["limitations"]}
    assert "gradul-instantei-comasate-nu-e-stabilit" in ids
    assert "doar-indemnizatia-de-baza" in ids
    blocking = {x["id"] for x in costuri["limitations"] if x["severity"] == "blocking"}
    assert len(blocking) >= 2, blocking

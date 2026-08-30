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


def test_at_the_papers_grade_the_answer_turns_on_the_caseload_target(costuri):
    """A claim this file made and this file now withdraws.

    It previously asserted that at tribunal grade every staffing target costs more than today.
    That was an artefact of counting judges by dividing caseload by volume — about 2.960 — when
    the CSM report prints 4.319 filled posts. Against the real current payroll, the tightest
    target still costs more, but the two looser ones save. The direction of the answer was
    being set by an understated baseline, not by the reform.

    So the assertion is now the honest one: the sign is not fixed, and it is the caseload target
    that decides it.
    """
    paper = [s for s in costuri["scenarios"] if s["isPaperGrade"]]
    assert paper, "no scenario is marked as the paper's grade"
    assert all(s["gradePaid"] == costuri["resolvedGrade"]["grade"] for s in paper)
    differences = [s["differenceLei"] for s in paper]
    assert min(differences) < 0 < max(differences), differences
    # And the ordering that must hold whatever the level: a tighter caseload target needs more
    # judges, so it cannot come out cheaper.
    ordered = sorted(paper, key=lambda s: s["target"])
    assert [s["differenceLei"] for s in ordered] == sorted(
        [s["differenceLei"] for s in ordered], reverse=True
    )


def test_today_is_priced_on_published_posts_not_derived_ones(costuri):
    """The correction itself, pinned so it cannot quietly revert.

    Filled posts are what the judiciary costs; the caseload-derived count is what a target would
    need. Mixing them made every "against today" difference subtract an establishment from a
    payroll.
    """
    by_tier = {row["tier"]: row for row in costuri["today"]["byTier"]}
    assert by_tier["iccj"]["judges"] > by_tier["iccj"]["judgesDerived"]
    total = sum(row["judges"] for row in costuri["today"]["byTier"])
    assert total == 4319, total
    # Level one must sit on the same basis, or the differences compare unlike things.
    assert costuri["today"]["levelOne"]["judges"] == (
        by_tier["tribunal"]["judges"] + by_tier["judecatorie"]["judges"]
    )


def test_the_counterfactual_grade_is_kept(costuri):
    """The cheaper reading stays in the file as a comparison. Deleting it would hide that the
    grade was ever a question, and hide how much of the answer it decides."""
    other = [s for s in costuri["scenarios"] if not s["isPaperGrade"]]
    assert other, "the counterfactual grade was dropped"
    assert min(s["differenceLei"] for s in other) < 0


def test_the_resolved_grade_is_cited_not_chosen(costuri):
    """It is read out of the paper, so it must carry a locator into the paper."""
    resolved = costuri["resolvedGrade"]
    assert resolved["grade"] == "tribunal"
    assert resolved["provenance"]["source"] == "reforma-sistem-judiciar-romania"
    assert resolved["provenance"]["confidence"] == "verbatim"
    assert "43" in resolved["provenance"]["locator"]


def test_a_higher_caseload_target_needs_fewer_judges(costuri):
    for grade in ("judecatorie", "tribunal"):
        rows = sorted(
            (s for s in costuri["scenarios"] if s["gradePaid"] == grade),
            key=lambda s: s["target"],
        )
        needed = [s["judgesNeeded"] for s in rows]
        assert needed == sorted(needed, reverse=True), (grade, needed)


def test_the_gaps_are_declared_at_the_right_weight(costuri):
    """Neither gap is blocking any more, and each stopped for its own reason.

    Sporuri stopped being unknowable when the pay simulator's execution data turned out to
    carry the courts' own ordonator principal. The merged court's grade stopped being open when
    the paper was read past the chapter this file was built from: it abolishes judecatoriile
    outright. Both caveats survive as material — one about scope, one about the transition —
    and both are asserted here so neither can quietly drift back to blocking or vanish.
    """
    ids = {x["id"] for x in costuri["limitations"]}
    assert "tranzitia-de-grad-nu-e-stabilita" in ids
    assert "doar-indemnizatia-de-baza" in ids
    weight = {x["id"]: x["severity"] for x in costuri["limitations"]}
    # Both former blocking gaps are now material: sporuri were measured, and the grade turned
    # out to be answered on two pages of the paper this file had already read.
    assert weight["tranzitia-de-grad-nu-e-stabilita"] == "material"
    assert weight["doar-indemnizatia-de-baza"] == "material"

"""Tests for the prosecution service's posts and cost.

The report prints the same staffing table twice — once for January, once for December — and
the level names also head two chapters hundreds of pages earlier. Both traps produced wrong
numbers before these checks existed, so the ones that pin the December figures are the point
of this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PARCHETE = ROOT / "simulators/justitie/data/parchete-2025.json"


@pytest.fixture(scope="module")
def parchete() -> dict:
    if not PARCHETE.exists():
        pytest.skip("prosecution offices not imported")
    return json.loads(PARCHETE.read_text(encoding="utf-8"))


def test_the_december_table_was_read_not_the_january_one(parchete):
    """January has 3.071 posts and December 3.052, in tables of identical shape.

    Anchoring on the table header alone lands on January. If this ever reads 3.071, the
    importer has drifted back to the wrong half of the chapter.
    """
    assert parchete["totals"]["posts"] == 3052, parchete["totals"]["posts"]
    assert parchete["totals"]["posts"] != 3071


def test_the_levels_sum_to_the_totals(parchete):
    levels = parchete["levels"]
    totals = parchete["totals"]
    assert sum(row["posts"] for row in levels) == totals["posts"]
    assert sum(row["vacant"] for row in levels) == totals["vacant"]
    assert sum(row["filled"] for row in levels) == totals["filled"]
    for row in levels:
        assert row["filled"] == row["posts"] - row["vacant"], row["level"]


def test_the_reports_own_disagreement_is_preserved(parchete):
    """The table leaves 2.287 filled; the prose says 2.293. Keeping both is the point — a
    source that disagrees with itself is a fact about the source, and silently choosing the
    number that adds up would hide it."""
    totals = parchete["totals"]
    assert totals["statedFilled"] != totals["filled"]
    assert abs(totals["statedFilled"] - totals["filled"]) < 20
    assert "raportul-nu-se-potriveste-cu-el-insusi" in {
        x["id"] for x in parchete["limitations"]
    }


def test_the_auxiliary_paragraph_also_fails_to_add_up(parchete):
    """1.353 filled plus 137 vacant is 1.490, not the 1.435 the same sentence gives. Asserted
    so that a future edition quietly fixing it does not go unnoticed."""
    aux = parchete["auxiliary"]
    assert aux["filled"] + aux["vacant"] != aux["posts"]


def test_the_wage_bill_recomputes_from_filled_posts(parchete):
    for row in parchete["levels"]:
        assert abs(row["filled"] * row["monthlyLei"] * 12 - row["annualLei"]) <= 1, row["level"]
    assert abs(
        sum(row["annualLei"] for row in parchete["levels"]) - parchete["totals"]["annualLei"]
    ) <= len(parchete["levels"])


def test_prosecutors_are_paid_under_judges_at_every_level(parchete):
    """A fact about the grid worth pinning: it would catch the two scales being swapped."""
    pay = {row["level"]: row["monthlyLei"] for row in parchete["levels"]}
    assert pay["piccj"] > pay["curte-de-apel"] > pay["tribunal"] > pay["judecatorie"]
    assert pay["piccj"] < 26_250, "PICCJ prosecutors must not out-earn ICCJ judges"


def test_the_merger_covers_only_the_two_bottom_levels(parchete):
    """7.3 folds judecatorie and tribunal offices into 42; it leaves the appellate level alone."""
    merger = parchete["merger"]
    levels = {row["level"]: row for row in parchete["levels"]}
    assert merger["posts"] == levels["tribunal"]["posts"] + levels["judecatorie"]["posts"]
    assert merger["filled"] == levels["tribunal"]["filled"] + levels["judecatorie"]["filled"]
    assert merger["proposedOffices"] == 42


def test_the_workload_points_at_where_it_is_now_modelled(parchete):
    """This file is still posts and cost only, but the redistribution it used to declare
    missing has been built in `parchete-comasare`.

    The caveat was blocking and is now a pointer, which is the change that matters: a blocking
    limitation left standing after the work is done is its own kind of wrong answer, telling a
    reader nothing can be said about something the page goes on to say.
    """
    ids = {x["id"] for x in parchete["limitations"]}
    assert "volumul-parchetelor-nu-e-modelat" not in ids
    pointer = next(x for x in parchete["limitations"] if x["id"] == "volumul-parchetelor-e-in-alta-parte")
    assert pointer["severity"] != "blocking"
    assert "parchete-comasare" in pointer["text"]
    assert "piccj-cuprinde-dna-si-diicot" in ids

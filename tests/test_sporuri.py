"""Tests for the courts' supplements, and the pension arithmetic that turns on them.

This document exists to retire a caveat that three other documents were carrying, and it
rewrites a published headline from a 31% cut to about 14%. A number that overturns an earlier
number has to be held to a higher standard than the one it replaces, so every check here
recomputes rather than reads, and the scope cross-check that proved which institution the data
covers is pinned as a test rather than left in a commit message.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPORURI = ROOT / "simulators/justitie/data/sporuri-2025.json"
PENSII = ROOT / "simulators/justitie/data/pensii-2025.json"
PLAFON = ROOT / "simulators/salarizare/data/fiscal/plafon-sporuri.json"


@pytest.fixture(scope="module")
def sporuri() -> dict:
    if not SPORURI.exists():
        pytest.skip("supplements not built")
    return json.loads(SPORURI.read_text(encoding="utf-8"))


def test_the_line_is_every_court_not_the_supreme_court_alone(sporuri):
    """The cross-check the whole document rests on.

    The ratio is read off the Inalta Curte's line, and if that line were only the supreme
    court — a bench of roughly a hundred — it would say nothing about the judiciary. It holds
    14.650 filled posts at about 14.000 lei a month each, which is a judges-and-grefieri
    payroll. Were this ever to resolve to a few hundred posts, the ratio would have quietly
    become a statement about one courthouse.
    """
    scope = sporuri["scope"]
    assert scope["filledPosts"] > 10_000, scope["filledPosts"]
    assert 8_000 < scope["baseMonthlyLeiPerPost"] < 25_000, scope["baseMonthlyLeiPerPost"]
    recomputed = scope["baseAnnualLei"] / scope["filledPosts"] / 12
    assert abs(recomputed - scope["baseMonthlyLeiPerPost"]) <= 1


def test_the_ratios_match_the_pay_simulator(sporuri):
    """Read across two simulators, so a change on the other side must not pass silently."""
    if not PLAFON.exists():
        pytest.skip("pay simulator's execution data not imported")
    series = json.loads(PLAFON.read_text(encoding="utf-8"))["series"]
    source = {
        s["dims"]["measure"]: s["observations"][0]["value"]
        for s in series
        if s["dims"].get("cui") == "4340587" and s["dims"]["kind"] == "entity"
    }
    assert source, "the courts' principal vanished from the execution data"
    for measure in ("narrow", "wide"):
        assert abs(source[measure] - sporuri["sporuri"][measure]) < 1e-4, measure


def test_wide_contains_narrow(sporuri):
    """Everything above base pay includes the two paragraphs called supplements."""
    assert sporuri["sporuri"]["wide"] >= sporuri["sporuri"]["narrow"]


def test_the_cap_verdict_follows_from_the_numbers(sporuri):
    """Being over the ceiling is the document's sharpest claim; it must not be asserted."""
    cap = sporuri["draftCap"]
    narrow = sporuri["sporuri"]["narrow"]
    assert cap["overCap"] == (narrow > cap["percent"] / 100)
    assert cap["gapPercentagePoints"] == round(100 * (narrow - cap["percent"] / 100), 1)


def test_widening_the_base_always_softens_the_cut(sporuri):
    """The direction the whole correction depends on.

    The bill cuts the rate and widens the base at once. Supplements are a positive share of
    base pay, so the second effect can only offset the first. If a reading ever came out
    harsher than the rate change alone, the arithmetic would have the sign wrong.
    """
    plain = sporuri["pension"]["reductionWithoutSporuriPercent"]
    for reading in sporuri["pension"]["readings"]:
        assert reading["reductionPercent"] < plain, reading["measure"]
        assert reading["reductionPercent"] > 0, reading["measure"]


def test_a_wider_definition_of_supplements_softens_it_further(sporuri):
    readings = {r["measure"]: r for r in sporuri["pension"]["readings"]}
    assert readings["wide"]["reductionPercent"] < readings["narrow"]["reductionPercent"]


def test_each_reading_recomputes_from_the_rates(sporuri):
    if not PENSII.exists():
        pytest.skip("the bill is not imported")
    bill = json.loads(PENSII.read_text(encoding="utf-8"))
    now = bill["current"]["percent"] / 100
    then = bill["proposed"]["percent"] / 100
    assert sporuri["pension"]["currentPercent"] == bill["current"]["percent"]
    assert sporuri["pension"]["proposedPercent"] == bill["proposed"]["percent"]
    for reading in sporuri["pension"]["readings"]:
        effective = then * (1 + reading["sporuriShare"])
        assert reading["effectivePercentOfIndemnity"] == round(100 * effective, 1)
        assert reading["reductionPercent"] == round(100 * (now - effective) / now, 1)


def test_the_published_headline_is_kept_for_comparison(sporuri):
    """The figure this replaces stays in the file. A correction that deletes what it corrects
    leaves a reader unable to tell that anything changed."""
    plain = sporuri["pension"]["reductionWithoutSporuriPercent"]
    now = sporuri["pension"]["currentPercent"]
    then = sporuri["pension"]["proposedPercent"]
    # Compared against the rounded value rather than through a tolerance: the stored figure is
    # rounded to one decimal, so the true error sits exactly on half a step and any tolerance
    # written as a bare "< 0.05" rejects the case it was written to accept.
    assert plain == round(100 * (now - then) / now, 1)


def test_the_scope_caveats_survive(sporuri):
    """The ratio is system-wide and the three definitions of a supplement do not coincide.
    Neither gap is closed by this document, and both change how its number reads."""
    ids = {x["id"] for x in sporuri["limitations"]}
    assert "raportul-e-pe-tot-personalul" in ids
    assert "trei-definitii-ale-sporurilor" in ids
    assert "media-pe-60-de-luni-nu-e-modelata" in ids
    assert "plafonul-net-nu-e-modelat" in ids


def test_ministerul_justitiei_is_declared_unusable(sporuri):
    """Its execution line rolls in the prison service while its headcount row does not, so the
    two disagree on perimeter. Declared rather than quietly skipped."""
    assert "ministerul-justitiei-nu-e-comparabil" in {x["id"] for x in sporuri["limitations"]}

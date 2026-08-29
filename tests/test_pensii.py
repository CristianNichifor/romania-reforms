"""Tests for the service pension comparison.

The risk here is not arithmetic, it is framing: four things change at once and the headline
number — 80% to 55% — describes only one of them. Every test below guards the parts that keep
that from being read as the whole.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PENSII = ROOT / "simulators/justitie/data/pensii-2025.json"
BILL = ROOT / "simulators/justitie/sources/lege-pensii-magistrati-2025.pdf"


@pytest.fixture(scope="module")
def pensii() -> dict:
    if not PENSII.exists():
        pytest.skip("pension rules not imported")
    return json.loads(PENSII.read_text(encoding="utf-8"))


def test_the_bill_travels_with_the_repository():
    assert BILL.exists(), "the pension bill is missing from sources/"


def test_the_bill_is_quoted_not_transcribed(pensii):
    """Its four numbers are read out of the PDF, so a different draft cannot be described by
    this file's prose while carrying other figures."""
    assert pensii["proposed"]["provenance"]["confidence"] == "verbatim"
    assert "art. 211" in pensii["proposed"]["provenance"]["locator"]


def test_the_rule_in_force_is_marked_derived(pensii):
    """The consolidated text of Legea 303/2022 is not in the repository — today's rule is
    described through what the bill replaces, and must not claim to be quoted."""
    assert pensii["current"]["provenance"]["confidence"] == "derived"


def test_all_four_changes_are_recorded(pensii):
    """Rate, seniority, base and cap. Dropping any one turns a structural change into a
    headline about a percentage."""
    current, proposed = pensii["current"], pensii["proposed"]
    assert proposed["percent"] < current["percent"]
    assert proposed["seniorityYears"] > current["seniorityYears"]
    assert proposed["netCapPercent"] < current["netCapPercent"]
    assert proposed["baseMonths"] > 1
    assert proposed["baseIncludesSporuri"] is True


def test_the_reduction_is_labelled_a_ceiling_not_an_estimate(pensii):
    """Computed on indemnity alone while the new base also counts sporuri, so the real cut is
    smaller by an unknown amount. If that caveat ever leaves, the number starts lying."""
    ids = {x["id"] for x in pensii["limitations"]}
    assert "sporurile-nu-sunt-publice" in ids
    blocking = {x["id"] for x in pensii["limitations"] if x["severity"] == "blocking"}
    assert "sporurile-nu-sunt-publice" in blocking


def test_the_reduction_matches_the_two_rates(pensii):
    current, proposed = pensii["current"]["percent"], pensii["proposed"]["percent"]
    expected = round(100 * (current - proposed) / current, 1)
    for row in pensii["byGrade"]:
        assert abs(row["reductionPercent"] - expected) < 0.2, row["grade"]


def test_it_does_not_claim_a_total_saving(pensii):
    """How many magistrates draw a service pension is not in the public data here, so the
    document compares rules and must not imply it has costed them."""
    ids = {x["id"] for x in pensii["limitations"]}
    assert "nu-stim-cati-pensionari" in ids
    assert "totalLei" not in json.dumps(pensii)

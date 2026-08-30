"""Tests for the paper's efficiency claim against its own cited source.

This is the most consequential thing the simulator says about the paper, so the checks are
aimed at the ways it could be unfair: a comparison against the wrong edition, a total that
quietly includes courts the report did not classify, or a headline that reads the report's
grades more harshly than the report does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EFICIENTA = ROOT / "simulators/justitie/data/eficienta-csm.json"


@pytest.fixture(scope="module")
def eficienta() -> dict:
    if not EFICIENTA.exists():
        pytest.skip("efficiency not imported")
    return json.loads(EFICIENTA.read_text(encoding="utf-8"))


def test_the_comparison_uses_the_edition_the_paper_cites(eficienta):
    """The paper's table names the CSM report of 2023. Comparing it against 2025 would be
    holding it to numbers published after it was written."""
    assert eficienta["comparison"]["citedYear"] == 2023
    assert any(y["year"] == 2023 for y in eficienta["years"])


def test_each_year_totals_its_own_grades(eficienta):
    for entry in eficienta["years"]:
        for tier in ("judecatorii", "tribunale"):
            grades = entry.get(tier)
            if not grades:
                continue
            assert grades["classified"] == (
                grades["veryEfficient"] + grades["efficient"] + grades["satisfactory"]
            ), (entry["year"], tier)
            assert grades["efficientOrBetter"] == grades["veryEfficient"] + grades["efficient"]


def test_no_court_is_classified_inefficient_in_either_year(eficienta):
    """The finding that most directly contradicts 'sute de instante subcritice': the lowest
    grade is empty in both editions, for both tiers."""
    for entry in eficienta["years"]:
        assert entry["judecatorii"]["inefficient"] == 0, entry["year"]
        if entry["tribunale"]:
            assert entry["tribunale"]["inefficient"] == 0, entry["year"]


def test_the_report_and_the_paper_disagree_by_an_order_of_magnitude(eficienta):
    """Stated as the arithmetic rather than as an accusation."""
    c = eficienta["comparison"]
    assert c["reportSaysEfficientOrBetter"] > 5 * c["paperSaysEfficient"]
    # And the paper's number is close to the top grade alone, which is the likely reading.
    assert abs(c["paperSaysEfficient"] - c["reportSaysVeryEfficient"]) <= 5


def test_the_paper_claim_is_quoted_with_a_locator(eficienta):
    claim = eficienta["paperClaim"]
    assert claim["provenance"]["confidence"] == "verbatim"
    assert "59" in claim["provenance"]["locator"]
    assert "20" in claim["text"]


def test_the_five_indicators_are_named(eficienta):
    codes = {i["code"] for i in eficienta["indicators"]}
    assert codes == {"E01", "E02", "E03", "E04", "E05"}


def test_efficiency_is_not_claimed_to_be_viability(eficienta):
    """The paper's real argument in 7.4 is about whether a six-judge court can specialise and
    survive a retirement. These indicators never measured that, in either direction."""
    ids = {x["id"] for x in eficienta["limitations"]}
    assert "eficienta-nu-e-viabilitate" in ids
    assert "gradele-pe-instanta-sunt-culori" in ids

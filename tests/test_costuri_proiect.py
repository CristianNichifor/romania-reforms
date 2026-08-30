"""Tests for the judiciary priced under the July 2026 pay draft.

The claim that carries weight here is comparative — the draft compresses the bench, and that
shrinks what the merged court's grade transition is worth. A comparison is easy to get
backwards, so every direction is asserted explicitly rather than assumed from the numbers that
happen to be in the file today.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROIECT = ROOT / "simulators/justitie/data/costuri-proiect-2026.json"
COSTURI = ROOT / "simulators/justitie/data/costuri-2025.json"
REGIME = ROOT / "simulators/salarizare/data/regimes/ro-draft-2026-07-16.json"

MONTHS = 12


@pytest.fixture(scope="module")
def proiect() -> dict:
    if not PROIECT.exists():
        pytest.skip("the draft costing is not built")
    return json.loads(PROIECT.read_text(encoding="utf-8"))


def test_every_tier_is_priced(proiect):
    """An unpriced tier costs zero, which reads as a finding rather than a hole."""
    tiers = {row["tier"] for row in proiect["byTier"]}
    assert tiers == {"iccj", "curte-de-apel", "tribunal", "judecatorie"}
    assert all(row["monthlyLei"] > 0 for row in proiect["byTier"])


def test_pay_is_the_coefficient_times_the_reference(proiect):
    """The whole document is one multiplication; if it does not reproduce, nothing else here
    means anything. Rounded up to the whole leu, as Art. 10 alin. (4) requires."""
    reference = proiect["referenceLei"]
    for row in proiect["byTier"]:
        assert row["monthlyLei"] == math.ceil(row["coefficient"] * reference)


def test_the_coefficients_are_the_draft_s_own(proiect):
    """Read across simulators, so a redrafted grid cannot pass through silently."""
    if not REGIME.exists():
        pytest.skip("the draft regime is not imported")
    regime = json.loads(REGIME.read_text(encoding="utf-8"))
    names = {
        "iccj": "Judecator cu grad de ICCJ",
        "curte-de-apel": "Judecător cu grad de curte de apel",
        "tribunal": "Judecător cu grad de tribunal",
        "judecatorie": "Judecător cu grad de judecătorie",
    }
    by_name = {p["name"]: p for p in regime["positions"]}
    assert proiect["referenceLei"] == regime["reference"]["amount"][-1]["value"]
    for row in proiect["byTier"]:
        position = by_name[names[row["tier"]]]
        top = next(
            v for v in position["variants"] if v.get("dims", {}).get("vechime") == "Peste 20 ani"
        )
        assert row["coefficient"] == top["value"], row["tier"]


def test_the_ranks_stay_in_order(proiect):
    """A judecatorie judge cannot out-earn one at the Inalta Curte under either regime."""
    pay = {row["tier"]: row["monthlyLei"] for row in proiect["byTier"]}
    assert pay["iccj"] > pay["curte-de-apel"] > pay["tribunal"] > pay["judecatorie"]


def test_the_draft_compresses_rather_than_lifts(proiect):
    """The document's headline, asserted in the direction it claims.

    The spread is top rank over bottom rank, which is a ratio and therefore immune to the two
    regimes being denominated in different years' money — the one comparison that survives the
    absence of a deflator.
    """
    spread = proiect["spread"]
    assert spread["compresses"] is True
    assert spread["draftRatio"] < spread["todayRatio"]
    # Compression here is two-sided: the top is cut and the bottom is raised.
    ratio = {row["tier"]: row["ratioToToday"] for row in proiect["byTier"]}
    assert ratio["iccj"] < 1 < ratio["judecatorie"]


def test_the_grade_gap_narrows_and_the_swing_follows_it(proiect):
    """Why compression matters for this simulator specifically.

    The paper settles which grade the merged court holds — it abolishes judecatoriile — so the
    gap no longer prices an ambiguity. It prices the transition: what it costs if judges
    arriving from an abolished judecatorie keep their grade for a while. A narrower gap is a
    cheaper transition, at every staffing target rather than only on average.
    """
    assert proiect["gradeIsResolved"] is True
    gap = proiect["gradeGap"]
    assert gap["narrows"] is True
    assert 0 < gap["draftMonthlyLei"] < gap["todayMonthlyLei"]
    assert proiect["gradeChoiceSwing"], "no staffing targets were compared"
    for swing in proiect["gradeChoiceSwing"]:
        assert 0 < swing["draftLei"] < swing["todayLei"], swing["target"]


def test_the_swing_is_the_gap_times_the_headcount(proiect):
    """Recomputed from the scenarios rather than trusted, since it is the number quoted."""
    for swing in proiect["gradeChoiceSwing"]:
        pair = {s["gradePaid"]: s for s in proiect["scenarios"] if s["target"] == swing["target"]}
        assert len(pair) == 2, swing["target"]
        expected = pair["tribunal"]["annualLei"] - pair["judecatorie"]["annualLei"]
        assert abs(expected - swing["draftLei"]) <= 1


def test_a_higher_caseload_target_needs_fewer_judges(proiect):
    for grade in ("judecatorie", "tribunal"):
        rows = sorted(
            (s for s in proiect["scenarios"] if s["gradePaid"] == grade), key=lambda s: s["target"]
        )
        needed = [s["judgesNeeded"] for s in rows]
        assert needed == sorted(needed, reverse=True), (grade, needed)


def test_the_headcount_is_the_one_the_rest_of_the_simulator_uses(proiect):
    """Same judges, different price. If the headcount drifted, the comparison would be
    measuring two different judiciaries and the ratios would be meaningless."""
    if not COSTURI.exists():
        pytest.skip("the current costing is not built")
    costuri = json.loads(COSTURI.read_text(encoding="utf-8"))
    today = {row["tier"]: row["judges"] for row in costuri["today"]["byTier"]}
    for row in proiect["byTier"]:
        assert row["judges"] == today[row["tier"]], row["tier"]
        assert row["todayMonthlyLei"] == costuri["monthlyLeiByTier"][row["tier"]]


def test_the_two_years_are_declared_incomparable_in_level(proiect):
    """No deflator is applied, so levels must not be read against each other. The caveat is
    what keeps the ratios honest, and it is the first thing a hurried reader would drop."""
    ids = {x["id"] for x in proiect["limitations"]}
    assert "ani-diferiti-fara-deflator" in ids
    assert "doar-judecatorii-sunt-evaluati" in ids
    # The grade is settled but the transition is not, and the gap is what that question costs.
    assert "tranzitia-de-grad-nu-e-stabilita" in ids
    assert "diferenta-tranzitorie-nu-e-modelata" in {
        x["id"] for x in proiect["limitations"] if x["severity"] == "blocking"
    }

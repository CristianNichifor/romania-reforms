"""Tests for the Danish comparison behind chapters 4 and 5.

This file contradicts the paper's single most quotable sentence, so the tests are aimed at the
ways *it* could be the one that is wrong: a density built from two different years, a ratio
that does not follow from its own inputs, a Romanian court count that drifted from the register,
or — worst — a headline that quietly presents "the paper's premises do not support its
conclusion" as "the paper's premises are false".

The two structural limits have their own tests, because the finding is only honest while they
are stated: the Danish counts are the paper's own, and only half the paper's criterion could be
measured at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DANEMARCA = ROOT / "simulators/justitie/data/danemarca-comparatie.json"
LOCATED = ROOT / "simulators/justitie/data/instante-localizate-2025.json"
CURTI = ROOT / "simulators/justitie/data/curti-apel-regiuni.json"


@pytest.fixture(scope="module")
def dk() -> dict:
    if not DANEMARCA.exists():
        pytest.skip("Danish comparison not built")
    return json.loads(DANEMARCA.read_text(encoding="utf-8"))


def test_both_populations_are_the_same_year(dk):
    """A density built from two different years compares nothing. The builder refuses it; this
    checks the refusal actually held."""
    pop = dk["population"]
    assert pop["year"] >= 2024
    assert pop["provenance"]["confidence"] == "verbatim"
    assert "tps00001" in pop["provenance"]["source"] or "eurostat" in pop["provenance"]["source"]


def test_the_implied_court_count_follows_from_the_densities(dk):
    first = dk["firstInstance"]
    pop = dk["population"]
    danish_density = pop["denmark"] / first["denmarkCourts"]
    assert first["denmarkPeoplePerCourt"] == pytest.approx(danish_density, rel=1e-3)
    assert first["impliedAtDanishDensity"] == pytest.approx(pop["romania"] / danish_density, rel=1e-3)
    assert first["actualOverImplied"] == pytest.approx(
        first["romaniaCourts"] / first["impliedAtDanishDensity"], rel=1e-2
    )


def test_the_paper_overstates_its_own_multiple(dk):
    """Stated as arithmetic, not as a verdict: at the paper's own Danish counts and Eurostat's
    populations, the multiple is materially below the three the chapter concludes with."""
    first = dk["firstInstance"]
    assert first["paperSaysMultiple"] == dk["paperClaim"]["multiple"]
    assert first["actualOverImplied"] < first["paperSaysMultiple"]
    # Materially below, not a rounding quibble.
    assert first["paperSaysMultiple"] - first["actualOverImplied"] > 0.5


def test_the_proposal_is_sparser_than_the_model_it_cites(dk):
    """The finding that matters most for the reform rather than for the paper: 42 first-instance
    courts is not convergence on Denmark, it is well past it."""
    first = dk["firstInstance"]
    assert first["proposedOverImplied"] < 1
    assert first["proposedCourts"] < first["impliedAtDanishDensity"]
    assert first["proposedPeoplePerCourt"] > first["denmarkPeoplePerCourt"]


def test_the_region_variant_is_the_one_near_danish_appellate_density(dk):
    appellate = dk["appellate"]
    if not CURTI.exists():
        pytest.skip("appellate variant not built")
    curti = json.loads(CURTI.read_text(encoding="utf-8"))
    assert appellate["regionVariantCourts"] == curti["summary"]["variant"]
    # Both are above Danish density, but the variant is much closer to it than the paper's 15.
    assert appellate["regionVariantOverImplied"] < appellate["actualOverImplied"]


def test_the_romanian_counts_come_from_the_register(dk):
    if not LOCATED.exists():
        pytest.skip("court register not built")
    courts = json.loads(LOCATED.read_text(encoding="utf-8"))["courts"]
    tiers: dict[str, int] = {}
    for court in courts:
        tiers[court["tier"]] = tiers.get(court["tier"], 0) + 1
    romania = dk["romania"]
    assert romania["firstInstance"] == tiers["judecatorie"]
    assert romania["tribunals"] == tiers["tribunal"]
    assert romania["appellate"] == tiers["curte-de-apel"]


def test_the_papers_own_romanian_figures_are_kept_separate(dk):
    """The paper's '180+' and the register's 175 are different facts and must not be merged
    into one number, or the page would be quietly correcting the document it quotes."""
    count = dk["selfCount"]
    assert count["paperFirstInstance"] != count["actualFirstInstance"]
    assert count["paperTribunals"] != count["actualTribunals"]
    # The '42 tribunale' appears to be counting towns rather than courts.
    assert count["paperTribunals"] == count["actualTribunalSites"]
    assert count["appellateAgrees"] is True


def test_the_two_structural_limits_are_blocking(dk):
    """Without both of these stated, the page would be claiming to have refuted Denmark's
    numbers and to have tested a criterion it only half tested."""
    blocking = {x["id"] for x in dk["limitations"] if x["severity"] == "blocking"}
    assert "volumul-de-cauze-nu-s-a-putut-masura" in blocking
    assert "cifrele-daneze-sunt-ale-lucrarii" in blocking


def test_density_is_not_presented_as_access(dk):
    """Denmark is a fifth of Romania's area. Equal courts per head is not equal travel, and the
    distance work lives elsewhere in this simulator."""
    ids = {x["id"] for x in dk["limitations"]}
    assert "densitatea-nu-e-acces" in ids
    assert "competentele-nu-sunt-aceleasi" in ids


def test_the_danish_structure_is_quoted_not_verified(dk):
    denmark = dk["denmark"]
    assert denmark["provenance"]["source"] == "reforma-sistem-judiciar-romania"
    assert denmark["provenance"]["confidence"] == "verbatim"
    assert "CEPEJ" in denmark["provenance"]["note"] or "domstol" in denmark["provenance"]["note"]

"""Tests for chapter 16's resource figures against the system they re-equip.

Three of the four findings here say the paper disagrees with itself, so the tests are aimed at
the ways *this* file could be the one that is wrong: an exchange rate that carries a conclusion,
a headcount costed at a floor nobody is actually paid, a building estimate divided by a site
count that quietly changed, and a "+50%" whose denominator is not what it claims to be.

The disagreements themselves are asserted only as arithmetic — that the numbers stand in the
relation the page reports — never as a verdict on the paper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESURSE = ROOT / "simulators/justitie/data/resurse-necesare.json"
PERSONAL = ROOT / "simulators/justitie/data/personal-2025.json"
PARCHETE = ROOT / "simulators/justitie/data/parchete-2025.json"
COSTURI = ROOT / "simulators/justitie/data/costuri-2025.json"

MONTHS = 12


@pytest.fixture(scope="module")
def resurse() -> dict:
    if not RESURSE.exists():
        pytest.skip("resources not imported")
    return json.loads(RESURSE.read_text(encoding="utf-8"))


def _load(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not imported")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_chapter_is_quoted_from_its_own_page(resurse):
    assert resurse["provenance"]["confidence"] == "verbatim"
    assert "16" in resurse["provenance"]["locator"]
    assert resurse["chapter"]["page"] == 63


def test_every_range_runs_low_to_high(resurse):
    """A backwards range would silently invert every per-site and per-year figure below."""
    chapter = resurse["chapter"]
    for key in ("digitalisationMillionEur", "buildingsMillionEur", "auxiliaryRecruits"):
        low, high = chapter[key]
        assert low < high, key


def test_the_exchange_rate_does_not_carry_the_argument(resurse):
    """The paper never dates its euros. If the year-end rate and the year's average differed
    enough to move a conclusion, the choice of date would be doing work the source cannot
    support — so the test is on the gap between them, not on the rate itself."""
    fx = resurse["exchangeRate"]
    assert fx["date"].startswith("2025-12")
    assert fx["provenance"]["confidence"] == "verbatim"
    drift = abs(fx["leiPerEur"] / fx["yearAverage"] - 1)
    assert drift < 0.05, f"year-end and year-average differ by {drift:.1%}"


def test_the_auxiliary_headcount_is_costed_above_base_pay(resurse):
    """Costing 4.000-6.000 people at bare base pay would manufacture the gap this page
    reports. The band has to be the grid uplifted by the sporuri actually paid, and the
    comparison has to use the dearest reading of it."""
    check = resurse["auxiliaryCheck"]
    band = check["band"]
    assert band["withSporuriLowMonthlyLei"] > band["baseLowMonthlyLei"]
    assert band["withSporuriHighMonthlyLei"] > band["baseHighMonthlyLei"]
    dearest = check["recruitsHigh"] * band["withSporuriHighMonthlyLei"] * MONTHS
    assert check["costOfRecruitsDearestLei"] == pytest.approx(dearest, rel=1e-6)
    # The finding survives its own most generous reading of the paper.
    assert check["moneyOverDearest"] > 1
    assert check["moneyOverCheapest"] > check["moneyOverDearest"]


def test_the_unexplained_remainder_is_the_dearest_reading(resurse):
    """It is a ceiling on what is unaccounted for, not a measure of waste: employer
    contributions, training and equipment are real costs the chapter simply does not list."""
    check = resurse["auxiliaryCheck"]
    assert check["unexplainedAnnualLei"] == pytest.approx(
        check["annualMoneyLei"] - check["costOfRecruitsDearestLei"], rel=1e-6
    )
    ids = {x["id"] for x in resurse["limitations"]}
    assert "costul-unui-post-e-doar-salariul" in ids


def test_the_vacancies_come_from_the_csm_report_not_from_here(resurse):
    personal, parchete = _load(PERSONAL), _load(PARCHETE)
    check = resurse["magistrateCheck"]
    assert check["judgesVacant"] == personal["judgesTotal"]["vacant"]
    assert check["prosecutorsVacant"] == parchete["totals"]["vacant"]
    assert check["bothVacant"] == check["judgesVacant"] + check["prosecutorsVacant"]


def test_both_readings_of_magistrat_are_reported(resurse):
    """The paper does not say whether 1.000 magistrates means judges or judges and
    prosecutors, and the two readings give opposite answers. Reporting only the damaging one
    would be the same sin the page accuses the paper of."""
    check = resurse["magistrateCheck"]
    assert check["coversJudgeVacancies"] is True
    assert check["coversBothVacancies"] is False
    assert check["shortfallIfBoth"] == check["bothVacant"] - check["recruits"]


def test_the_proposed_estate_is_smaller_than_todays(resurse):
    """Chapter 7 sends the judecatorii into the tribunals' buildings, so the site count has to
    fall. If it ever stopped falling, the per-site comparison would have no point."""
    check = resurse["buildingsCheck"]
    assert check["sitesProposed"] < check["sitesToday"]
    assert check["sitesClosed"] == check["sitesToday"] - check["sitesProposed"]
    assert check["perSiteProposedLowEur"] > check["perSiteTodayLowEur"]


def test_the_per_site_figures_are_the_budget_divided_by_the_sites(resurse):
    check = resurse["buildingsCheck"]
    million = 1_000_000
    assert check["perSiteTodayLowEur"] == pytest.approx(
        check["millionEurLow"] * million / check["sitesToday"], rel=1e-6
    )
    assert check["perSiteProposedHighEur"] == pytest.approx(
        check["millionEurHigh"] * million / check["sitesProposed"], rel=1e-6
    )


def test_the_total_is_measured_against_a_wage_bill_and_says_so(resurse):
    """'+50%' is the page's largest single claim, and its denominator is the courts' base
    payroll — not the justice budget, which is bigger. If that ever stopped being flagged as
    blocking, the number would read as something it is not."""
    costuri = _load(COSTURI)
    total = resurse["total"]
    assert total["basePayrollLei"] == costuri["reconciliation"]["executionBaseAnnualLei"]
    assert total["annualLowLei"] == pytest.approx(
        total["annualLowMillionEur"] * 1_000_000 * resurse["exchangeRate"]["leiPerEur"], rel=1e-6
    )
    assert total["shareOfBasePayrollLow"] == pytest.approx(
        total["annualLowLei"] / total["basePayrollLei"], rel=1e-3
    )
    assert total["shareOfBasePayrollLow"] <= total["shareOfBasePayrollHigh"]
    blocking = [x for x in resurse["limitations"] if x["severity"] == "blocking"]
    assert any(x["id"] == "salariile-nu-sunt-buget" for x in blocking)


def test_the_annual_total_only_spreads_what_the_chapter_dates(resurse):
    """The buildings line carries its own ten years; digitalisation carries none, and the
    horizon used for it is borrowed from the implementation plan. That is an assumption, and
    it has to stay declared."""
    ids = {x["id"] for x in resurse["limitations"]}
    assert "esalonarea-e-presupusa" in ids
    assert "euro-nedatati" in ids
    chapter, total = resurse["chapter"], resurse["total"]
    assert total["horizonYears"] == chapter["buildingsYears"]
    assert total["annualLowMillionEur"] > chapter["auxiliaryAnnualMillionEur"]

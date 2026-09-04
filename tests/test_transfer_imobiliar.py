"""The transfer tax, and the three ways a receipt turns into a wrong claim about prices.

This file exists because the dataset is one step away from being misused. It holds a tax, and
everybody wants a price; the step between them is a division by a rate nobody publishes and a
doubling under art. 111 (7), and each of those is a place to be quietly wrong by a factor of
three. So the tests guard the arithmetic, the quarantine that stops one broken filing being
59% of the country, and the order of magnitude of the answer against an independent series.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "simulators" / "impozit-teren" / "data"


def latest(prefix: str) -> dict:
    found = sorted(DATA.glob(f"{prefix}-*.json"))
    if not found:
        pytest.skip(f"{prefix} is not built")
    return json.loads(found[-1].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def transfers() -> dict:
    return latest("transfer-imobiliar")


def test_the_rates_are_the_ones_the_code_states(transfers):
    """3% up to three years, 1% above, half to the commune. All three are art. 111.

    Not a style check. Every figure anybody derives from this file is a division by one of
    these, so a typo here is a silent factor of three in the answer.
    """
    a = transfers["assumptions"]
    assert a["rateMinPercent"] == 1.0
    assert a["rateMaxPercent"] == 3.0
    assert a["localShare"] == 0.5
    assert "111" in a["legalBasis"]


def test_the_summary_is_the_rows(transfers):
    rows = transfers["uats"]
    assert transfers["summary"]["uatsReporting"] == len(rows)
    assert transfers["summary"]["localTaxRon"] == pytest.approx(
        sum(r["localTaxRon"] for r in rows), rel=1e-9
    )


def test_doubling_and_dividing_go_the_right_way(transfers):
    """The lower rate implies the larger turnover, which is easy to write backwards."""
    s = transfers["summary"]
    a = transfers["assumptions"]
    assert s["taxRon"] == pytest.approx(s["localTaxRon"] / a["localShare"], rel=1e-9)
    assert s["declaredValueRon"]["low"] == pytest.approx(
        s["taxRon"] / (a["rateMaxPercent"] / 100), rel=1e-9
    )
    assert s["declaredValueRon"]["high"] == pytest.approx(
        s["taxRon"] / (a["rateMinPercent"] / 100), rel=1e-9
    )
    assert s["declaredValueRon"]["low"] < s["declaredValueRon"]["high"]


def test_no_row_survives_the_threshold_it_was_filtered_by(transfers):
    """Whatever was excluded is gone from the rows and named in `excluded`."""
    excluded = {e["siruta"] for e in transfers["excluded"]}
    assert excluded, "nothing was quarantined; the Bucharest sector filing should still trip it"
    assert not (excluded & {r["siruta"] for r in transfers["uats"]})
    for entry in transfers["excluded"]:
        assert entry["timesMedian"] > transfers["assumptions"]["suspectMultipleOfMedian"]


def test_the_quarantined_filing_is_the_one_that_cannot_be_a_market(transfers):
    """A Bucharest sector filing more than the whole city is a filing, not a property market.

    Asserted on the shape rather than the name: what disqualifies it is that it is hundreds of
    times the median per inhabitant, not that it is Sector 5.
    """
    worst = max(transfers["excluded"], key=lambda e: e["timesMedian"])
    assert worst["timesMedian"] > 100
    assert worst["reportedLocalTaxRon"] > transfers["summary"]["localTaxRon"]


def test_no_single_commune_is_most_of_the_country(transfers):
    """The guard that makes the next broken filing visible instead of averaged in."""
    largest = transfers["summary"]["largestFiler"]
    assert largest is not None
    assert largest["shareOfCountry"] < 0.25


def test_every_receipt_is_positive(transfers):
    for row in transfers["uats"]:
        assert row["localTaxRon"] > 0
        assert row["level"] in {"uat", "county"}


def test_the_communes_are_the_same_communes_as_the_rest_of_the_project(transfers):
    """SIRUTA is the join key for the notary grids, the land register and the budgets.

    A transfer receipt that matches no commune elsewhere cannot be put beside a land value,
    which is the only reason to have imported it.
    """
    budgets = latest("buget-uat")
    known = {r["siruta"] for r in budgets["uats"]}
    rows = [r for r in transfers["uats"] if r["level"] == "uat"]
    matched = sum(1 for r in rows if r["siruta"] in known)
    assert matched / len(rows) > 0.95


def test_the_turnover_is_a_believable_share_of_the_economy(transfers):
    """An order-of-magnitude check against a series built from somewhere else entirely.

    Property changing hands is a few per cent of GDP in any economy that has a housing market.
    A factor-of-ten error in the rate, the doubling or the classification code would land
    outside this band, and nothing else in the file would notice.
    """
    gdp_doc = latest("pib")
    year = int(transfers["period"])
    gdp = next(
        (row["gdpMron"] * 1e6 for row in gdp_doc["series"] if row["year"] == year),
        None,
    )
    if gdp is None:
        pytest.skip(f"no GDP for {year}")
    low = transfers["summary"]["declaredValueRon"]["low"] / gdp
    high = transfers["summary"]["declaredValueRon"]["high"] / gdp
    assert 0.005 < low, f"declared turnover is {low:.2%} of GDP, implausibly small"
    assert high < 0.15, f"declared turnover is {high:.2%} of GDP, implausibly large"

"""The sales counts, and the two traps a reader will otherwise walk into.

This dataset exists to be a denominator, and both of its hazards are the kind that produce a
confident wrong number rather than an error. Its six categories read like a partition and are
not one; its years read like years and are seven, eight or eleven months. Each of those has a
test here, and each test asserts against the data rather than against the prose, so the caveat
cannot outlive the thing it warns about — or, worse, survive after ANCPI fixes it.
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
def sales() -> dict:
    return latest("vanzari-imobile")


def test_all_forty_two_counties_are_there(sales):
    """Forty-seven spellings fold onto forty-two codes, and a missing one is invisible."""
    codes = {county["county"] for county in sales["counties"]}
    assert len(codes) == 42
    assert sales["summary"]["counties"] == 42


def test_the_categories_do_not_reconcile(sales):
    """`agricol + neagricol` is not a decomposition of `fara constructii`, and that is measured.

    If this ever approaches 1, ANCPI has changed what it publishes and the blocking limitation
    saying the two axes are unrelated would have become false — which is exactly the moment a
    caveat is most dangerous, because nobody re-reads one that has been true for years.
    """
    ratio = sales["summary"]["agriculturalPlusNonAgriculturalOverWithoutBuildings"]
    assert ratio is not None
    assert ratio < 0.8, f"the categories now reconcile at {ratio}; re-read the limitation"


def test_no_year_pretends_to_be_twelve_months(sales):
    """Every row says how many months it was summed over, and none of them is a full year."""
    by_year = sales["assumptions"]["monthsByYear"]
    for county in sales["counties"]:
        for row in county["series"]:
            declared = by_year.get(str(row["year"]))
            assert declared is not None, f"year {row['year']} has no month list"
            assert row["monthsReported"] <= len(declared)
            assert 1 <= row["monthsReported"] <= 12


def test_the_month_lists_are_real_months(sales):
    for year, months in sales["assumptions"]["monthsByYear"].items():
        assert months == sorted(set(months))
        assert all(1 <= month <= 12 for month in months), year
        assert 1 <= len(months) <= 12


def test_counts_are_counts(sales):
    allowed = set(sales["assumptions"]["types"].values())
    for county in sales["counties"]:
        for row in county["series"]:
            assert row["sales"], f"{county['county']} {row['year']} has no categories"
            for name, value in row["sales"].items():
                assert name in allowed
                assert isinstance(value, int) and value >= 0


def test_bare_land_is_the_largest_category(sales):
    """`withoutBuildings` is the line this whole dataset was imported for.

    It should also be the biggest, because most registered sales in Romania are of land rather
    than of built property. If that stopped being true the dataset would still parse, and the
    reason to have imported it would have quietly gone.
    """
    counts = sales["summary"]["salesInFullestYear"]
    assert counts.get("withoutBuildings", 0) > counts.get("withBuildings", 0)
    assert counts.get("withoutBuildings", 0) > counts.get("apartments", 0)


def test_the_two_traps_are_declared_blocking(sales):
    severity = {limit["id"]: limit["severity"] for limit in sales["limitations"]}
    assert severity.get("categoriile-nu-se-aduna") == "blocking"
    assert severity.get("lunile-nu-fac-un-an") == "blocking"


def test_it_joins_to_the_transfer_tax(sales):
    """The point of importing this: the tax gives money, this gives things, together a price.

    Only the join is asserted here — that both datasets name counties the same way — because
    the years they cover need not overlap and the price itself belongs to whatever builds it.
    """
    transfers = latest("transfer-imobiliar")
    theirs = {row["county"] for row in transfers["uats"] if row.get("county")}
    ours = {county["county"] for county in sales["counties"]}
    assert theirs <= ours, f"transfer tax names counties this dataset lacks: {theirs - ours}"


@pytest.mark.full_data
def test_a_price_would_land_in_a_plausible_band(sales):
    """Real-data plausibility remains a separate, fail-closed certification."""
    assert_plausible_price(sales, latest("transfer-imobiliar"))


def assert_plausible_price(sales, transfers):
    """The same arithmetic serves the national assertion and bounded fixtures."""
    year = int(transfers["period"])
    counts = 0
    for county in sales["counties"]:
        for row in county["series"]:
            if row["year"] == year:
                counts += row["sales"].get("withoutBuildings", 0) + row["sales"].get(
                    "withBuildings", 0
                )
    assert counts > 0, f"no ANCPI counts for {year}; the sources do not overlap yet"
    tax = transfers["summary"]["taxRon"]
    low = tax / (transfers["assumptions"]["rateMaxPercent"] / 100) / counts
    high = tax / (transfers["assumptions"]["rateMinPercent"] / 100) / counts
    assert 10_000 < low, f"average declared price {low:,.0f} lei is implausibly small"
    assert high < 3_000_000, f"average declared price {high:,.0f} lei is implausibly large"


def price_fixture(year=2025, tax=200000):
    # Synthetic values only: 100 sales, 200k tax, 1–3% => 66,667–200,000 lei.
    return (
        {
            "counties": [
                {"series": [{"year": year, "sales": {"withoutBuildings": 60, "withBuildings": 40}}]}
            ]
        },
        {
            "period": "2025",
            "summary": {"taxRon": tax},
            "assumptions": {"rateMaxPercent": 3, "rateMinPercent": 1},
        },
    )


def test_price_arithmetic_with_bounded_overlapping_sources():
    assert_plausible_price(*price_fixture())


@pytest.mark.parametrize("tax", [2000, 20000000])
def test_price_arithmetic_rejects_order_of_magnitude_errors(tax):
    with pytest.raises(AssertionError, match="implausibly"):
        assert_plausible_price(*price_fixture(tax=tax))


def test_non_overlapping_sources_cannot_certify_a_price():
    with pytest.raises(AssertionError, match="no ANCPI counts for 2025"):
        assert_plausible_price(*price_fixture(year=2024))

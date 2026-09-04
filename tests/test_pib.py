"""The denominator, and the two ways it could quietly be wrong.

A ratio is the least self-checking number in this repository. `0,41% din PIB` looks equally
reasonable whether the divisor is the country's output, one county's, or last year's, and no
reader can tell which one it was from the figure itself. So the checks here are about the
divisor rather than about the tax: that every county the page can select has one, that the
forty-two add up to the country, and that the two currencies come from the same row rather than
from an exchange rate applied to one of them.
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
def gdp() -> dict:
    return latest("pib")


def test_every_county_the_page_offers_has_a_denominator(gdp):
    """The page's county list is discovered from `data/`, so the two have to agree.

    A county with a land value dataset and no GDP row renders a share-of-GDP box that falls
    back to the last year it does have — or, if it has none at all, to nothing — and neither
    failure says which county it happened to.
    """
    priced = {
        path.name.split("-")[2].upper()
        for path in DATA.glob("valoare-teren-*.json")
        if "nationala" not in path.name
    }
    assert priced, "no county has a land value dataset"
    with_gdp = {region["county"] for region in gdp["regions"]}
    assert priced <= with_gdp, f"no GDP for {sorted(priced - with_gdp)}"


def test_the_counties_add_up_to_the_country(gdp):
    """Within a per cent: what is left over is Extra-Regio, which belongs to no county."""
    year = gdp["assumptions"]["countyLatestYear"]
    counties = sum(
        row["gdpMron"]
        for region in gdp["regions"]
        for row in region["series"]
        if row["year"] == year
    )
    national = next(row["gdpMron"] for row in gdp["series"] if row["year"] == year)
    assert counties == pytest.approx(national, rel=0.01)


def test_nuts3_is_one_county_each(gdp):
    codes = [region["nuts3"] for region in gdp["regions"]]
    counties = [region["county"] for region in gdp["regions"]]
    assert len(set(codes)) == len(codes) == len(set(counties)) == len(counties)
    assert len(codes) == gdp["summary"]["counties"]


def test_both_currencies_come_from_the_same_row(gdp):
    """Lei over euro must land on the year's actual exchange rate, not on a fixed one.

    The point of carrying both is that a ratio never needs a rate applied to one side of it. If
    one currency had been derived from the other with a single rate, this ratio would be
    constant across eleven years instead of tracking the leu, which it does not.
    """
    rates = []
    for series in [gdp["series"]] + [region["series"] for region in gdp["regions"]]:
        for row in series:
            assert row["gdpMron"] > 0 and row["gdpMeur"] > 0
            rates.append(row["gdpMron"] / row["gdpMeur"])
    assert min(rates) > 4.0, "an implied rate below 4,0 lei/EUR is not a Romanian year here"
    assert max(rates) < 5.5, "an implied rate above 5,5 lei/EUR is not one either"
    assert max(rates) - min(rates) > 0.2, "the rate never moved, so one currency is derived"


def test_the_years_are_contiguous_and_start_where_the_file_says(gdp):
    first = gdp["assumptions"]["fromYear"]
    years = [row["year"] for row in gdp["series"]]
    assert years == list(range(first, gdp["assumptions"]["nationalLatestYear"] + 1))
    for region in gdp["regions"]:
        county_years = [row["year"] for row in region["series"]]
        assert county_years == sorted(set(county_years))
        assert county_years[0] == first


def test_the_county_series_may_lag_but_never_lead(gdp):
    """Regional accounts are published behind the national ones, never ahead of them."""
    national_latest = gdp["assumptions"]["nationalLatestYear"]
    county_latest = gdp["assumptions"]["countyLatestYear"]
    assert county_latest <= national_latest
    for region in gdp["regions"]:
        assert max(row["year"] for row in region["series"]) == county_latest


def test_the_registration_effect_is_declared(gdp):
    """Bucharest carries the value added of firms that work everywhere else.

    Without this stated, a reader comparing county ratios is comparing where companies are
    registered and believing they are comparing where land is. It is the one caveat that
    changes how the county view should be read, so it must be at least material.
    """
    found = {limit["id"]: limit for limit in gdp["limitations"]}
    stated = found.get("pib-judetean-e-unde-se-inregistreaza")
    assert stated is not None
    assert stated["severity"] in {"blocking", "material"}
    assert "impozit-teren" in stated["affects"]


def test_bucharest_is_the_outlier_the_limitation_describes(gdp):
    """Not a style check on the prose: the effect it warns about is measurable here.

    București is 0,2% of the country by area and books close to a quarter of its GDP. If that
    ever stopped being true the caveat would be describing a distortion that no longer exists,
    and the county ratios would deserve to be read straight.
    """
    year = gdp["assumptions"]["countyLatestYear"]
    at = lambda county: next(  # noqa: E731
        row["gdpMron"]
        for region in gdp["regions"]
        if region["county"] == county
        for row in region["series"]
        if row["year"] == year
    )
    national = next(row["gdpMron"] for row in gdp["series"] if row["year"] == year)
    assert at("B") / national > 0.2

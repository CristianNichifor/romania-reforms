"""The budget execution behind the self-financing map.

This file exists to answer one question the land data alone cannot: whether a land value tax
would cover what a commune actually spends. That makes the denominator load-bearing, and a
denominator that is wrong in the wrong direction turns a modest tax into an apparently
sufficient one.

Two things are pinned here. The national total has to stay in the range that local budgets
actually occupy — the first import produced 991 mld lei, five times reality, because three
Bucharest sectors file sums that are not budgets. And the exclusion that fixes it has to
stay visible: a filing set aside without being named is a number nobody can check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "simulators" / "impozit-teren" / "data"


@pytest.fixture(scope="module")
def budget() -> dict:
    path = DATA / "buget-uat-2025.json"
    if not path.exists():
        pytest.skip("buget-uat-2025.json is not built")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_country_is_covered(budget):
    """Every commune, not the ones that fitted in the first page of the roster."""
    assert budget["summary"]["uatsReporting"] > 3000
    sirutas = {row["siruta"] for row in budget["uats"]}
    assert len(sirutas) == len(budget["uats"]), "a SIRUTA code appears twice"


def test_local_spending_is_the_size_local_spending_is(budget):
    """Between 100 and 300 mld lei.

    Not a precise claim — it is a claim that the number is a Romanian local budget total at
    all. The import that included the three impossible filings produced 991 mld, and nothing
    in the file said so: every per-capita figure downstream would have been five times too
    small and still looked plausible.
    """
    total = budget["summary"]["spendingRon"] / 1e9
    assert 100 < total < 300, f"{total:.0f} mld lei is not what Romanian communes spend"


def test_what_was_thrown_out_is_named(budget):
    """The exclusion is data, not a silent filter."""
    excluded = budget["excluded"]
    assert excluded, "nothing was excluded; the rule that catches impossible filings is off"
    for row in excluded:
        assert row["name"]
        assert row["timesMedian"] > budget["assumptions"]["suspectMultipleOfMedian"]
    # And it is stated where a reader looks for caveats, at the severity it deserves.
    blocking = {x["id"] for x in budget["limitations"] if x.get("severity") == "blocking"}
    assert "raportari-imposibile-scoase" in blocking


def test_no_excluded_filing_survives_in_the_rows(budget):
    """A quarantined authority must not still be colouring a map."""
    thrown = {row["siruta"] for row in budget["excluded"]}
    kept = {row["siruta"] for row in budget["uats"]}
    assert not (thrown & kept)


def test_own_revenue_is_a_part_of_revenue(budget):
    """The split is a partition, not two independent sums."""
    for row in budget["uats"]:
        assert row["ownRevenueRon"] <= row["revenueRon"] + 0.01, row["name"]
    assert budget["summary"]["ownRevenueRon"] < budget["summary"]["revenueRon"]


def test_most_communes_live_on_money_they_did_not_raise(budget):
    """The finding the map is built on, stated as a test so it cannot quietly invert.

    If the median commune raised most of its own budget, "which communes could pay for
    themselves" would be a question with an obvious answer and the map would be pointless.
    """
    median = budget["summary"]["medianOwnShare"]
    assert median is not None
    assert median < 0.5, f"the median commune raises {median:.0%} of its budget itself"


def ratios(budget) -> list[float]:
    """A land value tax at 1% over what each commune spent, for every priced locality."""
    spending = {
        row["siruta"]: row["spendingRon"]
        for row in budget["uats"]
        if row["level"] == "uat" and row["spendingRon"] > 0
    }
    out = []
    for path in sorted(DATA.glob("impozit-*-2026.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for locality in document.get("localities", []):
            spent = spending.get(str(locality["siruta"]))
            lvt = (locality.get("lvtRon") or {}).get("central")
            if spent and lvt:
                out.append(lvt / spent)
    return sorted(out)


def test_every_priced_locality_has_a_budget_to_be_measured_against(budget):
    """The join is the whole point, so a silent drop would empty the map without a word."""
    spending = {row["siruta"] for row in budget["uats"] if row["level"] == "uat"}
    priced = {
        str(locality["siruta"])
        for path in DATA.glob("impozit-*-2026.json")
        for locality in json.loads(path.read_text(encoding="utf-8")).get("localities", [])
    }
    if not priced:
        pytest.skip("the tax files are not built")
    missing = priced - spending
    assert not missing, f"{len(missing)} priced localities have no budget row"


def test_a_one_percent_tax_does_not_pay_for_a_commune(budget):
    """The finding, pinned.

    At the rate the page opens on, the middle commune covers about an eighth of what it
    spends, and a handful clear 100%. Both halves matter: a median near zero would make the
    map pointless, and a median near one would mean this simulator had quietly started
    claiming a land tax could replace local government. If either end moves, it is because
    the data moved, and that should fail here rather than be discovered on the page.
    """
    values = ratios(budget)
    if not values:
        pytest.skip("the tax files are not built")
    median = values[len(values) // 2]
    assert 0.05 < median < 0.25, f"the median commune covers {median:.1%} of its spending"
    assert sum(1 for v in values if v >= 1) < len(values) * 0.02


def test_the_transfer_chapters_are_published(budget):
    """Which chapters count as somebody else's money is an editorial call, so it is in the file."""
    prefixes = budget["assumptions"]["transferPrefixes"]
    assert "04." in prefixes and "11." in prefixes
    assert all(p.endswith(".") for p in prefixes)

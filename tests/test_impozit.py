"""Tests for the Fiscal Code's tables and the comparison built on them.

These guard a claim rather than a parse: that a land value tax raising what Romania's land tax
raises today would sit around a fifth of a percent of land value. A figure like that gets
quoted without its band, so the band is what most of this file defends.

The Fiscal Code tables are checked against the text of the law, because a table read out of a
7 MB HTML page is exactly the kind of thing that can come back plausible and wrong — and two
of these tables were replaced with effect from 1 January 2026, so "it matched last year" is
not evidence either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "simulators/impozit-teren/data"
COUNTIES = ["BC", "NT", "AB", "IS", "SB", "CT", "TL", "PH", "MS", "HR", "VN", "DB", "BZ", "HD"]

def edition(prefix: str, county: str) -> dict:
    """The county's dataset, whichever year its chamber published.

    Named by glob rather than by a constant 2026: the Ploiești and Galați chambers published
    no 2026 study, so Prahova, Dâmbovița and Vrancea are 2025 documents sitting beside nine
    that are not. A hard-coded year did not fail here, it *skipped* — three counties quietly
    dropped out of the suite while it still reported all green.
    """
    found = sorted(DATA.glob(f"{prefix}-{county.lower()}-*.json"))
    if not found:
        pytest.skip(f"{prefix}-{county.lower()} is not built")
    return json.loads(found[-1].read_text(encoding="utf-8"))



def load(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        pytest.skip(f"{name} is not built")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def code() -> dict:
    return load("cod-fiscal-teren-2026.json")


@pytest.fixture(scope="module", params=COUNTIES)
def tax(request) -> dict:
    return edition("impozit", request.param)


def test_the_tables_say_what_the_law_says(code):
    """Spot values quoted from art. 465 as published, at both corners of the table.

    Reading the corners is the cheap version of reading all 24 cells: a row or column offset
    by one, or a range parsed backwards, moves them.
    """
    assert code["intravilanBuiltLeiPerHa"]["A"]["0"] == {"min": 8282, "max": 20706}
    assert code["intravilanBuiltLeiPerHa"]["D"]["V"] == {"min": 142, "max": 356}
    assert code["rankCoefficient"] == {
        "0": 8.0, "I": 5.0, "II": 4.0, "III": 3.0, "IV": 1.1, "V": 1.0
    }
    assert code["zoneRankCoefficient"]["A"]["0"] == 2.60
    assert code["zoneRankCoefficient"]["D"]["V"] == 0.90


def test_the_code_states_a_range_and_it_survives_as_one(code):
    """Article 465 (9) leaves the choice inside the range to the council.

    Collapsing a cell to one number would be a claim about the law that the law does not make,
    so the range has to reach the data intact — and be wide, which is the finding.
    """
    corner = code["intravilanBuiltLeiPerHa"]["A"]["0"]
    assert corner["max"] / corner["min"] > 2
    widths = [
        cell["max"] / cell["min"]
        for zone in code["intravilanBuiltLeiPerHa"].values()
        for cell in zone.values()
        if cell["min"]
    ]
    assert min(widths) > 1.5
    blocking = {x["id"] for x in code["limitations"] if x["severity"] == "blocking"}
    assert "codul-da-un-interval-nu-o-cota" in blocking
    assert "zonarea-e-decizie-locala" in blocking


def test_the_tax_falls_with_rank_and_with_zone(code):
    """The Code's whole logic in two orderings: central land dearer, big towns dearer.

    If either inverted, the zone and rank axes would have been read transposed — which is the
    likeliest silent failure in a table with both.
    """
    built = code["intravilanBuiltLeiPerHa"]
    for zone in ("A", "B", "C", "D"):
        by_rank = [built[zone][rank]["min"] for rank in code["ranks"]]
        assert by_rank == sorted(by_rank, reverse=True), zone
    for rank in code["ranks"]:
        by_zone = [built[zone][rank]["min"] for zone in ("A", "B", "C", "D")]
        assert by_zone == sorted(by_zone, reverse=True), rank


def test_both_taxes_stand_on_the_same_hectares(tax):
    """The comparison is only worth anything if the land underneath is identical."""
    county = tax["counties"][0]
    areas = load(f"fond-funciar-{county.lower()}-2014.json")
    assert tax["summary"]["localities"] <= areas["summary"]["localities"]
    assert sum(r["totalHa"] for r in tax["localities"]) <= areas["summary"]["totalHa"] * 1.001


def test_todays_tax_is_a_band_too_and_a_wide_one(tax):
    """The point that makes the comparison fair.

    It would be easy to present a modelled band against a single confident "what we pay now".
    The Code gives a range, the zone is a local decision and a commune spans two ranks, so
    today's tax is a band as well — and a wider one than the land value it is compared with.
    """
    summary = tax["summary"]
    fiscal = summary["fiscalCodeRon"]
    assert fiscal["low"] < fiscal["central"] < fiscal["high"]
    assert summary["lawfulRangeRatio"] > 2
    blocking = {x["id"] for x in tax["limitations"] if x["severity"] == "blocking"}
    assert "impozitul-de-azi-e-si-el-o-banda" in blocking


def test_the_revenue_neutral_rate_is_a_fraction_of_a_percent(tax):
    """The headline, pinned loosely enough to be about the finding and not the arithmetic.

    Both counties land near a fifth to a third of a percent centrally. The bound here is wide
    on purpose: what would matter is the claim moving by an order of magnitude, which is what
    a currency slip or a hectares-versus-square-metres slip would do.
    """
    neutral = tax["summary"]["revenueNeutralRatePercent"]
    assert 0 < neutral["low"] < neutral["central"] < neutral["high"]
    assert 0.01 < neutral["central"] < 3.0
    assert tax["provenance"]["confidence"] == "derived"


def test_a_commune_spans_two_ranks_and_a_town_does_not(tax):
    """Legea 351/2001: a commune's seat is rank IV, its other villages rank V.

    Towns have one rank each, so an unequal pair on a town would mean the rank rule leaked.
    """
    for row in tax["localities"]:
        low, high = row["fiscalRank"]["low"], row["fiscalRank"]["high"]
        if row["rank"] == "comune":
            assert (low, high) == ("V", "IV"), row["name"]
        else:
            assert low == high, row["name"]
    ranks = {row["fiscalRank"]["high"] for row in tax["localities"]}
    assert ranks & {"I", "II", "III"}


def test_the_exchange_rate_is_recorded_because_the_answer_moves_with_it(tax):
    """The grid is in euro and the Code in lei; the neutral rate scales with the conversion."""
    assumptions = tax["assumptions"]
    assert 3 < assumptions["ronPerEur"] < 8
    assert assumptions["exchangeRateDate"]
    ids = {x["id"] for x in tax["limitations"]}
    assert "cursul-muta-raspunsul" in ids
    assert "statutar-nu-incasat" in ids

"""Tests for the observed-journey validation.

Two jobs. The first is ordinary: the parser reads the county programme layouts correctly, and
does not invent a distance for the continuation rows that carry only times. The second is the
one that matters — keeping the speed check a *test* rather than a fit. The service-speed
factor was set before these observations existed, and the moment someone nudges it to close
the remaining 3,7% the repository loses its only independent check on travel time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.observed_journeys import Journey, parse_programme_line, summarise

ROOT = Path(__file__).resolve().parents[1]
OBSERVED = ROOT / "data" / "observed-journeys.json"
COST = ROOT / "data" / "cost.json"
INPUTS = ROOT / "data" / "cost-inputs.json"

# Real rows, one per county layout, kept verbatim so a parser change that breaks a county
# fails here rather than silently dropping that county's rows from the sample.
BRAILA = "01 01 001 BRAILA CHISCANI TUFESTI 41 8 10 1 7:00 8:20 8:25 9:45 1,2,3,4,5,6,7 002"
DOLJ = "01 001 Craiova DN6 Filiaşi 38 15 10 2 05:40 06:20 06:30 07:10 1,2,3,4,5,6,7"
CARAS = "01 00 001 BOCSA RESITA 25 32 Min 10 4 1 05:00 05:45 06:00 06:45 1,2,3,4,5,6,7"
SIBIU = "01 SB 001 SIBIU/ AUTOG. ŞELIMBĂR CISNĂDIE 15 21 23 4>23 5:15 5:40 6:00 6:25 1,2,3,4,5"


def test_it_reads_distance_and_both_directions():
    """One row books two runs over the same distance, and an operator often allows more time
    against the morning peak than for the evening. Taking only the outbound halves the sample
    and drops the slower direction."""
    journeys = parse_programme_line(BRAILA, "Brăila")
    assert len(journeys) == 2
    assert [j.km for j in journeys] == [41, 41]
    assert journeys[0].minutes == 80  # 7:00 -> 8:20
    assert journeys[1].minutes == 80  # 8:25 -> 9:45
    assert journeys[0].kmh == pytest.approx(30.75)


def test_a_unit_column_is_not_mistaken_for_a_place():
    """Caraş-Severin writes the journey time in its own column as "32 Min". Walking back to
    the last word would stop at "Min" and read the distance as 10 — the vehicle count."""
    journeys = parse_programme_line(CARAS, "Caraș-Severin")
    assert journeys[0].km == 25
    assert journeys[0].minutes == 45


def test_it_handles_the_layouts_that_differ_by_county():
    """Dolj has one fewer leading column than Brăila; Sibiu puts a "4>23" token between the
    distance and the times. The distance is found by position relative to the place names,
    not by column index, precisely so these do not each need their own parser."""
    assert parse_programme_line(DOLJ, "Dolj")[0].km == 38
    assert parse_programme_line(SIBIU, "Sibiu")[0].km == 15


def test_a_continuation_row_is_dropped_rather_than_guessed():
    """Most rows in a programme are further departures for the route named above, carrying
    times and no distance. Inheriting the distance from the row above would be a guess, and a
    wrong guess would be multiplied across every departure of that route."""
    assert parse_programme_line("6:00 6:25 6:45 7:10 6", "Sibiu") == []
    assert parse_programme_line("11:00 12:20 12:25 13:45 1,2,3,4,5,6,7", "Brăila") == []


def test_a_run_across_midnight_is_not_negative():
    """23:30 to 00:15 is 45 minutes, not minus 1 395."""
    journeys = parse_programme_line("01 01 001 BRAILA IANCA SUTESTI 20 1 1 1 23:30 00:15 1,2", "T")
    assert journeys[0].minutes == 45


def test_implausible_rows_are_refused():
    """A misparsed row produces a plausible-looking number, which is the dangerous kind. The
    bounds exist to make a parse error show up as a missing row rather than a fast one."""
    fast = "01 01 001 BRAILA IANCA SUTESTI 20 1 1 1 7:00 7:02 1,2"
    assert parse_programme_line(fast, "T") == []  # 600 km/h
    far = "01 01 001 BRAILA IANCA SUTESTI 300 1 1 1 7:00 9:00 1,2"
    assert parse_programme_line(far, "T") == []  # 300 km is an interurban coach


def test_the_summary_weights_by_kilometre():
    """Bus-hours is total distance over the speed that distance is covered at, so a 90 km
    route counts for more than a 10 km one. Averaging the per-route ratios weights them
    equally and drags the figure down toward the short village runs."""
    journeys = [Journey("A", km=90, minutes=90), Journey("A", km=10, minutes=30)]
    summary = summarise(journeys)
    assert summary["kmhWeighted"] == pytest.approx(100 / 2.0)  # 50,0
    assert summary["kmhMean"] == pytest.approx((60 + 20) / 2)  # 40,0 — the wrong answer
    assert summary["kmhWeighted"] != summary["kmhMean"]


@pytest.fixture(scope="module")
def observed() -> dict:
    if not OBSERVED.exists():
        pytest.skip("observations not built")
    return json.loads(OBSERVED.read_text(encoding="utf-8"))


def test_the_sample_is_real_and_spans_more_than_one_county(observed):
    """A single county's programme would measure that county's terrain, not Romania's."""
    assert observed["summary"]["count"] > 400
    assert len(observed["summary"]["byCounty"]) >= 5
    for source in observed["sources"]:
        assert source["url"].startswith("https://")
        assert source["title"]


def test_the_sample_declares_that_it_is_not_random(observed):
    """These are the routes that exist, and a route exists where the road is good. The
    limitation is load-bearing: without it the sample reads as a national measurement."""
    ids = {limitation["id"] for limitation in observed["limitations"]}
    assert "esantionul-e-al-traseelor-existente" in ids
    assert "sase-judete-dintre-care-patru-cantaresc" in ids


@pytest.fixture(scope="module")
def cost() -> dict:
    if not COST.exists():
        pytest.skip("cost not built")
    return json.loads(COST.read_text(encoding="utf-8"))


def test_the_model_speed_falls_inside_the_observed_range(cost, observed):
    """The check itself. If this fails, either the speed model moved or the sample did, and
    the answer is to find out which — not to adjust the factor until it passes again."""
    modelled = cost["speedCheck"]["modelledKmh"]
    summary = observed["summary"]
    assert summary["kmhP25"] <= modelled <= summary["kmhP75"]
    assert cost["speedCheck"]["tuned"] is False
    assert abs(modelled / summary["kmhWeighted"] - 1) < 0.15


def test_the_service_factor_was_not_tuned_to_close_the_gap():
    """The factor is 0,75 because that is what engineering judgement gave before any
    observation existed. Moving it to 0,78 would make the model match the observed mean
    exactly and would destroy the only independent test of travel time in this repository.

    If a future change genuinely justifies a different factor, this test should be deleted
    along with the claim in cost-inputs.json that it was never tuned — not quietly widened.
    """
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    assert inputs["items"]["serviceSpeedFactor"]["value"] == 0.75
    assert inputs["items"]["serviceSpeedFactor"]["confidence"] == "assumed"


def test_the_repository_no_longer_claims_speeds_were_never_checked(cost):
    """That claim was true for most of this project and is now false. It was carried in three
    places at once; leaving any of them behind would make the document contradict itself."""
    ids = {limitation["id"] for limitation in cost["limitations"]}
    assert "vitezele-nu-sunt-verificate" not in ids
    assert "vitezele-sunt-verificate-doar-in-ansamblu" in ids

    from scripts.speeds import SPEED_PROVENANCE

    assert "nu există astfel de date" not in SPEED_PROVENANCE["note"]

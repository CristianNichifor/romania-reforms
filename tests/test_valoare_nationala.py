"""The national estimate, and the line between what was read and what was guessed.

Every other dataset here is checked for being *right*. This one cannot be: nineteen of its
counties have no grid to check against, which is the entire reason it exists. So what is
checked instead is that it never stops saying which half is which — that a measured county
still equals its own grid to the leu, that a predicted county's band is the model's measured
error rather than a chosen one, and that the two counties nobody can predict are absent with a
reason attached rather than quietly summed in as small numbers.

The failure this guards against is specific and it is not arithmetic. It is a national total
that reads as a fact.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "simulators" / "impozit-teren" / "data"
BANDS = ("low", "central", "high")


@pytest.fixture(scope="module")
def national() -> dict:
    path = DATA / "valoare-nationala-2026.json"
    if not path.exists():
        pytest.skip("the national estimate is not built")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(national) -> list[dict]:
    return national["counties_valued"]


def test_every_county_says_whether_it_was_read_or_guessed(rows):
    """The load-bearing field. Without it the file is a national total and nothing else."""
    assert rows
    for row in rows:
        assert row["basis"] in {"measured", "predicted", "excluded"}


def test_an_excluded_county_has_no_number_and_no_zero(rows):
    """Null, never nought.

    A zero would sum correctly and read as "this land is worth nothing", which of a county in
    the capital region is the single most wrong sentence available. The absence has to be a
    hole in the data, not a small contribution to the total.

    București used to be here and is not any more: its chamber publishes on its own server
    rather than through unnpr.ro, and once that study was read the capital became measured.
    Ilfov stays — its largest town is inside the fitted range and its land market is not, being
    priced by a city that is not in the county.
    """
    # Empty now, and the test is kept rather than deleted. Both counties that were excluded —
    # București and Ilfov — turned out to be published by a chamber this repository was not
    # reading, so the mechanism went unused rather than wrong. The rule it encodes still has to
    # hold the day something else cannot be predicted: absent, with a reason, never a zero.
    excluded = [r for r in rows if r["basis"] == "excluded"]
    for row in excluded:
        assert row["landValueEur"] is None
        assert len(row["reason"]) > 20


def test_a_measured_county_is_its_own_grid_to_the_leu(rows):
    """The estimate must not re-estimate what was read.

    A model fitted on the measured counties will happily produce a number for them too, and
    using it would smooth the read counties towards the fit — making the file look more
    coherent than the evidence is, and quietly overwriting twenty-one parsed studies with a
    two-parameter regression.
    """
    for row in rows:
        if row["basis"] != "measured":
            continue
        found = sorted(DATA.glob(f"valoare-teren-{row['county'].lower()}-*.json"))
        assert found, row["county"]
        summary = json.loads(found[-1].read_text(encoding="utf-8"))["summary"]
        for band in BANDS:
            assert row["landValueEur"][band] == summary["landValueEur"][band]


def test_a_predicted_band_is_the_models_measured_error(rows, national):
    """low and high are the point estimate divided and multiplied by the leave-one-out error.

    Asserted because a band is the easiest thing in this repository to invent. If the width
    ever stops being the model's own out-of-sample error it stops meaning anything, and the
    only way to notice is to check that it still reconstructs.
    """
    factor = national["assumptions"]["builtLeaveOneOutErrorFactor"]
    transfer_error = national["assumptions"]["transferLeaveOneOutErrorFactor"]
    for row in rows:
        if row["basis"] != "predicted":
            continue
        built = row["builtValueEur"]
        parts = row["extravilanValueByCodeEur"]
        low = built / factor + sum(v / transfer_error[k] for k, v in parts.items())
        high = built * factor + sum(v * transfer_error[k] for k, v in parts.items())
        assert row["landValueEur"]["low"] == pytest.approx(low, rel=1e-6)
        assert row["landValueEur"]["high"] == pytest.approx(high, rel=1e-6)
        assert row["landValueEur"]["central"] == pytest.approx(
            built + sum(parts.values()), rel=1e-6
        )


def test_the_error_factors_are_above_one(national):
    """An error factor of exactly 1 is not a perfect model, it is a bug.

    It would mean every held-out county was predicted exactly, which for twenty-one counties
    and two parameters is impossible — so if it ever appears, the leave-one-out loop has
    started training on the county it is predicting.
    """
    assumptions = national["assumptions"]
    assert assumptions["builtLeaveOneOutErrorFactor"] > 1.0
    for code, factor in assumptions["transferLeaveOneOutErrorFactor"].items():
        assert factor > 1.0, code


def test_bigger_town_means_dearer_land(national):
    """The sign of the slope, which is the only thing about the fit that is not empirical.

    A negative slope would still produce a national total, and every downstream figure would
    still add up; it would simply mean the model had learned that land is cheap in cities. The
    arithmetic cannot catch that. This can.
    """
    assert national["assumptions"]["builtSlope"] > 0
    assert 0 < national["assumptions"]["builtR2"] < 1


def test_what_was_tried_and_rejected_is_still_in_the_file(national):
    """The discipline that makes the chosen predictor readable.

    Population is not an obvious choice until you know that the built share of the county gives
    an R² of 0,04 and that the NUTS2 region is worse than no predictor at all. Both are what a
    reader would otherwise assume had been used, so both have to survive in the output — a
    method section that lists only what worked is a method section that cannot be argued with.
    """
    rejected = national["assumptions"]["rejectedPredictors"]
    assert "builtShareOfCounty" in rejected
    assert "nuts2Region" in rejected
    for reason in rejected.values():
        assert any(ch.isdigit() for ch in reason), reason


def test_no_predicted_county_is_priced_far_outside_the_measured_range(rows, national):
    """A log-linear fit extrapolates without complaining; this is where it would show.

    This used to require every prediction to land strictly inside the observed range, and that
    was too strict once București entered the fit. Adding a city thirty times larger than the
    next one steepens the slope — 0,915 to 0,968 — which lowers predictions at the bottom, and
    Teleorman, whose largest town is the smallest in the country at 46 000, now predicts 3%
    under the cheapest county actually measured. That is the model doing its job, not failing.

    Including București was itself checked rather than assumed: it improves leave-one-out from
    1,65× to 1,61× and R² from 0,58 to 0,75. The capital earns its place in the fit.

    So the guard is now the one that was always meant — runaway extrapolation, not mild
    extrapolation. The observed range is widened by the model's own out-of-sample error, which
    is the amount by which the model already admits it can be wrong; anything beyond that is
    the fit being pushed somewhere it cannot go.
    """
    slack = national["assumptions"]["builtLeaveOneOutErrorFactor"]
    measured = [r for r in rows if r["basis"] == "measured"]
    observed = []
    for row in measured:
        found = sorted(DATA.glob(f"valoare-teren-{row['county'].lower()}-*.json"))
        document = json.loads(found[-1].read_text(encoding="utf-8"))
        extravilan = sum(x["extravilanValueEur"] for x in document["localities"])
        observed.append(
            (document["summary"]["landValueEur"]["central"] - extravilan)
            / document["summary"]["builtHa"]
        )
    floor, ceiling = min(observed) / slack, max(observed) * slack
    for row in rows:
        if row["basis"] == "predicted":
            assert floor <= row["builtEurPerHa"] <= ceiling, row["county"]


def test_the_total_is_the_sum_of_what_is_not_null(national, rows):
    counted = [r for r in rows if r["landValueEur"]]
    for band in BANDS:
        assert national["summary"]["landValueEur"][band] == pytest.approx(
            sum(r["landValueEur"][band] for r in counted), rel=1e-9
        )
    assert national["summary"]["measuredCounties"] == sum(
        1 for r in rows if r["basis"] == "measured"
    )
    assert national["summary"]["predictedCounties"] == sum(
        1 for r in rows if r["basis"] == "predicted"
    )


def test_the_bands_are_ordered_everywhere(rows):
    for row in rows:
        band = row["landValueEur"]
        if band:
            assert band["low"] < band["central"] < band["high"], row["county"]


def test_the_capital_status_is_stated_either_way(national, rows):
    """The reader must not be able to quote the headline without learning where the capital is.

    This used to assert three limitation *ids*, one of which was
    `bucurestiul-lipseste-din-total`. That was correct until București's grid was read, and
    then it was a test demanding the file keep saying something false — which is exactly what
    it did, under `blocking` severity, on a panel headed "tot pământul din România", until
    somebody read the page and asked why the capital was not summed.

    So the assertion is now conditional on the data rather than on the sentence that was true
    when it was written. Whichever state the file is in, it has to say so:

      capital absent   a blocking limitation, because a total without București reads as
                       Romania and is not
      capital present  a limitation naming it, because "toată țara" is an adjective and the
                       reader has no way to check an adjective
    """
    capital = next((r for r in rows if r["county"] == "B"), None)
    assert capital is not None, "București is not even listed among the counties"
    included = bool(capital["landValueEur"])

    mentions = [x for x in national["limitations"] if "ucureşti" in x["text"] or "ucurești" in x["text"]]
    assert mentions, "nothing in the file tells the reader where București stands"

    if not included:
        assert any(x["severity"] == "blocking" for x in mentions), (
            "București is outside the total and no limitation says so at blocking severity"
        )
    else:
        # It is in the total, so no limitation may claim otherwise — the failure this guards
        # is a frozen sentence outliving the fact it described.
        for limitation in national["limitations"]:
            assert "lipseste" not in limitation["id"], (
                f"{limitation['id']} still says something is missing that is in the total"
            )


def test_an_estimated_country_says_so_at_blocking_severity(national):
    """Estimation is the thing a reader most needs warned about, when there is any.

    Also conditional: with every county read there is nothing to warn about, and demanding the
    warning anyway is how a file ends up asserting that half the country is estimated on a page
    whose own summary says 100% of it was read.
    """
    blocking = {x["id"] for x in national["limitations"] if x["severity"] == "blocking"}
    if national["summary"]["predictedCounties"]:
        assert any("estimat" in x or "citita" in x for x in blocking), (
            "counties are predicted and no blocking limitation says the total is part model"
        )
    # Either way the total inherits whatever limits the grids it is made of.
    assert blocking, "a national total with no blocking limitation at all is overconfident"


def test_the_measured_half_is_still_the_larger_half(national):
    """Not a law of nature — a threshold that should be argued with if it is ever crossed.

    While more than half the value is read, the estimate is an extension of measurements. If
    predicted counties ever dominate it, the file has quietly become a model with some data
    attached, and that deserves a decision rather than a passing build.
    """
    assert national["summary"]["measuredShareOfValue"] > 0.5


def test_population_is_present_for_every_county_in_the_estimate(national):
    """The predictor has to exist for all 42, or the missing ones are silently dropped."""
    for county in national["counties"]:
        found = sorted(DATA.glob(f"populatie-{county.lower()}-*.json"))
        assert found, county
        summary = json.loads(found[-1].read_text(encoding="utf-8"))["summary"]
        assert summary["largestPeople"] > 0
        assert summary["largestPeople"] <= summary["people"]


def test_the_largest_town_is_actually_the_largest(national):
    """Cheap, and it caught nothing — but the rows are sorted by size and the summary reads
    the first one, so a change to that sort would silently make the predictor the *smallest*
    commune in the county and the fit would still converge."""
    for county in national["counties"]:
        path = sorted(DATA.glob(f"populatie-{county.lower()}-*.json"))[-1]
        document = json.loads(path.read_text(encoding="utf-8"))
        biggest = max(r["people"] for r in document["localities"])
        assert document["summary"]["largestPeople"] == biggest, county


def test_the_estimate_is_the_right_order_of_magnitude(national):
    """A country's land is worth a year or two of its output, not a tenth and not twenty.

    Romania's GDP is roughly 350 mld EUR. Land at 285 mld is 0,8 of it, which is low for
    Europe and exactly what a floor-priced grid without Bucharest should produce. The range
    here is wide on purpose: this is a check that a unit has not been lost, not a claim that
    the number is right.
    """
    central = national["summary"]["landValueEur"]["central"]
    assert 100e9 < central < 1500e9
    assert math.isfinite(central)

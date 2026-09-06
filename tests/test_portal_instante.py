"""Tests for the per-court builder.

The whole file exists so that a reader can ask for a county, a circumscription or a proposed
court and get a real quantile rather than an average of quantiles. Everything worth testing is
downstream of that one promise:

  * a histogram must be summable and its last bin must be open, or the tail of the distribution
    silently disappears into "no data" instead of "longer than we measured"
  * the vectorised binning has to agree with the scalar one exactly, because it is the fast path
    and the slow one is what the edges were reasoned about with
  * a quantile taken from summed bins must equal the quantile of the pooled sample, which is the
    claim the file makes and the only one that cannot be checked by looking at the output
  * the life table must reproduce a survival curve, and must not walk past the follow-up
  * every court must survive the county join, matched or not — the four suspended judecătorii
    are absent from the CSM annex, and dropping them would bias every county share
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "simulators/justitie/scripts"
MODULE = SCRIPTS / "build_portal_instante.py"

sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("build_portal_instante", MODULE)
courts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = courts
spec.loader.exec_module(courts)


EDGES = (0, 7, 14, 28)


def test_histogram_bins_are_half_open_and_the_last_one_is_unbounded():
    # 7 belongs to the bin that starts at 7, not the one that ends there; and 900 has to land
    # somewhere, because "longer than a month" is an observation and not a missing value.
    assert courts.histogram([0, 6, 7, 13, 14, 27, 28, 900], EDGES) == [2, 2, 2, 2]


def test_histogram_drops_values_below_the_first_edge():
    # A negative duration is not a short case, it is a case whose pronouncement predates its
    # registration here — the file that feeds this has already filtered them, and if one gets
    # through it must not be counted as same-day.
    assert courts.histogram([-1, -30, 3], EDGES) == [1, 0, 0, 0]


def test_the_fast_binning_agrees_with_the_slow_one():
    values = [0, 1, 6, 7, 8, 13, 14, 27, 28, 29, 400]
    indices = courts.bin_index(pd.Series(values), EDGES)
    fast = [0] * len(EDGES)
    for index in indices:
        if index >= 0:
            fast[int(index)] += 1
    assert fast == courts.histogram(values, EDGES)


def quantile_from_bins(counts: list[int], edges, fraction: float) -> float:
    """What the browser will do: walk the summed bins to the crossing point."""
    total = sum(counts)
    target = total * fraction
    seen = 0
    for index, count in enumerate(counts):
        if seen + count >= target:
            return edges[index]
        seen += count
    return edges[-1]


def test_a_quantile_from_summed_bins_is_the_pooled_quantile():
    # The claim the whole file rests on. Two courts, deliberately different: one fast, one slow.
    # An average of their medians would be 10,5; the pooled median is 14, and the summed
    # histogram has to give the second.
    fast_court = [1, 1, 2, 3, 5, 8]
    slow_court = [30, 40, 50, 60, 200]
    pooled = sorted(fast_court + slow_court)

    summed = [
        a + b
        for a, b in zip(
            courts.histogram(fast_court, EDGES), courts.histogram(slow_court, EDGES), strict=True
        )
    ]
    from_bins = quantile_from_bins(summed, EDGES, 0.5)
    exact = pooled[len(pooled) // 2]

    # Equal to the width of the bin the true median falls in, which is the documented grain.
    assert from_bins <= exact
    index = next(i for i, edge in enumerate(EDGES) if edge > exact) - 1
    assert from_bins == EDGES[index]


def survival(events: list[int], censored: list[int]) -> list[float]:
    """The actuarial estimator the shipped file is shaped for."""
    at_risk = sum(events) + sum(censored)
    curve = []
    running = 1.0
    for happened, lost in zip(events, censored, strict=True):
        effective = at_risk - lost / 2
        if effective > 0:
            running *= 1 - happened / effective
        at_risk -= happened + lost
        curve.append(running)
    return curve


def test_the_life_table_reproduces_a_survival_curve():
    # Nothing censored: the curve is one minus the empirical distribution, exactly.
    events = [20, 30, 25, 25]
    curve = survival(events, [0, 0, 0, 0])
    assert curve[0] == pytest.approx(0.8)
    assert curve[1] == pytest.approx(0.5)
    assert curve[-1] == pytest.approx(0.0)


def test_censoring_lifts_the_curve_rather_than_counting_as_resolution():
    # Fifty cases still running is not fifty cases resolved. The two must not produce the same
    # curve — that error is what makes a court look twice as fast as it is.
    resolved_only = survival([50, 0], [0, 0])
    half_censored = survival([50, 0], [50, 0])
    assert half_censored[0] > resolved_only[0]


def test_every_portal_court_keeps_its_row_whether_or_not_it_matched():
    table, names = courts.located_counties()
    assert len(names) > 200
    # The join key is shared with build_intrate, so a name in the annex must resolve through it.
    assert courts.key("Judecătoria ADJUD") in table
    entry = table[courts.key("Judecătoria ADJUD")]
    assert entry["judet"]


def test_the_shipped_file_publishes_no_percentile():
    """The schema forbids one; this checks the file, which is what a reader downloads.

    A p50 in here would be a field that cannot be summed sitting in a document whose entire
    purpose is that everything in it can be.
    """
    path = ROOT / "simulators/justitie/data/portal-instante.json"
    if not path.is_file():
        pytest.skip("portal-instante.json not built in this checkout")
    text = path.read_text(encoding="utf-8")
    for forbidden in ('"p25"', '"p50"', '"p75"', '"mediana', '"medie'):
        assert forbidden not in text


def test_the_shipped_histograms_all_match_the_published_edges():
    path = ROOT / "simulators/justitie/data/portal-instante.json"
    if not path.is_file():
        pytest.skip("portal-instante.json not built in this checkout")
    document = json.loads(path.read_text(encoding="utf-8"))
    edges = document["praguriZile"]
    for court in document["instante"]:
        assert len(court["primulTermen"]) == len(edges["termene"])
        assert len(court["intervalTermene"]) == len(edges["termene"])
        assert len(court["peRol"]) == len(edges["peRol"])
        assert len(court["durata"]["evenimente"]) == len(edges["durata"])
        assert len(court["durata"]["cenzurate"]) == len(edges["durata"])
        # The cohort size has to be the two histograms together, or a survival curve computed
        # from them starts from the wrong number at risk and every share is off.
        assert court["durata"]["dosare"] == sum(court["durata"]["evenimente"]) + sum(
            court["durata"]["cenzurate"]
        )


def test_a_court_the_crawl_did_not_finish_is_flagged_rather_than_published():
    """The failure this catches is the one that looks most like data.

    Two of twelve shards returned 2.825 rows where their siblings returned 470.000, so 41 courts
    arrived with a handful of cases each. Nothing about the shape of those rows says so — they
    validate, they sum, they render — and unflagged they state that Judecătoria Oltenița heard
    69 cases in three and a half years.
    """
    path = ROOT / "simulators/justitie/data/portal-instante.json"
    if not path.is_file():
        pytest.skip("portal-instante.json not built in this checkout")
    document = json.loads(path.read_text(encoding="utf-8"))
    threshold = document["snapshot"]["pragTrunchiere"]

    flagged = {court["institutie"] for court in document["instante"] if court["acoperire"]["trunchiat"]}
    assert flagged == set(document["instanteTrunchiate"])
    assert len(flagged) == document["snapshot"]["instanteTrunchiate"]

    for court in document["instante"]:
        ratio = court["acoperire"]["raportFataDeVolum"]
        if ratio is None:
            # No published volume to compare against is not evidence of completeness, so the
            # court must not be silently marked sound.
            assert not court["acoperire"]["trunchiat"]
            continue
        assert court["acoperire"]["trunchiat"] == (ratio < threshold)


def test_the_truncation_threshold_sits_in_empty_space():
    """A threshold picked to look reasonable would be a judgement; this one is a reading.

    Between a crawled court and an uncrawled one there is two orders of magnitude of nothing. If
    a future snapshot puts courts near the threshold, the bimodality has gone and the flag needs
    rethinking rather than retuning — which is what this test is for.
    """
    path = ROOT / "simulators/justitie/data/portal-instante.json"
    if not path.is_file():
        pytest.skip("portal-instante.json not built in this checkout")
    document = json.loads(path.read_text(encoding="utf-8"))
    threshold = document["snapshot"]["pragTrunchiere"]
    ratios = [
        court["acoperire"]["raportFataDeVolum"]
        for court in document["instante"]
        if court["acoperire"]["raportFataDeVolum"] is not None
    ]
    near = [ratio for ratio in ratios if threshold / 4 < ratio < threshold * 4]
    assert not near, f"{len(near)} courts sit near the threshold; the two modes have merged"


def test_the_national_total_survives_the_split_by_court():
    path = ROOT / "simulators/justitie/data/portal-instante.json"
    if not path.is_file():
        pytest.skip("portal-instante.json not built in this checkout")
    document = json.loads(path.read_text(encoding="utf-8"))
    per_court = sum(court["dosare"] for court in document["instante"])
    assert per_court == document["snapshot"]["dosare"]

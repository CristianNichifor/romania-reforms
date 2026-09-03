"""Tests for the traffic data and the 2+1 programme.

This is the only dataset in the repository that OpenStreetMap could not supply, and it arrives
through a side door: a noise directive obliges Romania to publish the flow on every road above
three million vehicles a year. That inclusion rule is the thing most likely to be forgotten
once the numbers are quoted, so most of these tests guard it rather than the arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "data" / "trafic.json"
INPUTS = ROOT / "data" / "trafic-inputs.json"


@pytest.fixture(scope="module")
def built() -> dict:
    if not BUILT.exists():
        pytest.skip("traffic not built")
    return json.loads(BUILT.read_text(encoding="utf-8"))


def test_the_dataset_is_the_busy_end_by_construction(built):
    """Three million vehicles a year is an AADT of 8 219, so nothing quieter can appear. If a
    section ever came in below that, the source changed and every 'among the busy roads'
    caveat in this file would need rereading."""
    assert built["network"]["minAadt"] >= 8_000
    assert built["network"]["medianAadt"] > built["network"]["minAadt"]
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "doar-drumurile-aglomerate" in ids


def test_motorways_are_not_counted_as_needing_a_third_lane(built):
    """A motorway already has the lanes. Its traffic still belongs in the picture — it is what
    makes the case for the roads feeding it — but not in the programme."""
    assert built["network"]["motorwayKm"] > 0
    programme = sum(band["km"] for band in built["byBand"].values() if band["costRon"] is not None)
    assert programme == pytest.approx(built["programme"]["km"], rel=1e-6)
    assert built["programme"]["km"] < built["network"]["km"]


def test_the_band_above_the_range_is_excluded_rather_than_priced(built):
    """Above roughly 20 000 vehicles a day, 2+1 is not too expensive — it is not enough. That
    band must carry no cost, or the programme is quietly promising the wrong road type."""
    high = [b for b in built["byBand"].values() if b["toAadt"] is None]
    assert high, "there must be an unbounded top band"
    for band in high:
        assert band["costRon"] is None
        assert band["km"] > 0, "if nothing is above the range, check the source"


def test_the_cost_is_the_length_times_the_price(built):
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))["items"]
    rate = inputs["twoPlusOneWidenEurPerKm"]["value"] * inputs["ronPerEur"]["value"]
    assert built["programme"]["costRon"] == pytest.approx(built["programme"]["km"] * rate, rel=1e-3)
    # The floor is kept beside the working figure so the widening share stays visible.
    assert built["programme"]["upgradeOnlyEurPerKm"] < built["programme"]["eurPerKm"]


def test_it_admits_the_price_is_foreign(built):
    """Romania has no 2+1 roads, so the anchors are Irish. That is legitimate here — the
    network does not exist yet — but it must be stated, not absorbed."""
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "pretul-benzii-a-treia-e-strain" in ids
    assert "mza-nu-spune-varful" in ids


def test_the_source_is_named_and_fetchable(built):
    """A number nobody can re-download is a number nobody can check."""
    assert built["source"]["url"].startswith("https://")
    assert "2002/49" in built["provenance"]["locator"] or "2002/49" in built["source"]["title"]
    assert built["provenance"]["confidence"] == "verbatim"


def test_the_traffic_is_not_yet_joined_to_the_model(built):
    """Declared blocking on purpose: until the sections are matched to the road graph, the
    bypass benefit is still per seat-pair rather than per vehicle, which is the difference
    between a cost list and a cost-benefit comparison."""
    by_id = {limitation["id"]: limitation for limitation in built["limitations"]}
    assert by_id["sectiunile-nu-sunt-legate-de-model"]["severity"] == "blocking"


def test_2plus1_is_far_cheaper_than_bypassing_everything(built):
    """The comparison that makes both numbers mean something. If this ever inverted, one of
    the two unit prices is wrong by an order of magnitude."""
    bypasses = ROOT / "data" / "ocoliri.json"
    if not bypasses.exists():
        pytest.skip("bypasses not built")
    other = json.loads(bypasses.read_text(encoding="utf-8"))
    assert built["programme"]["costRon"] < other["headline"]["costRon"]


def test_the_2plus1_rate_is_interpolated_between_romanian_contracts(built):
    """It used to be a foreign guess. It is now bracketed by two CNAIR contracts on existing
    alignment — modernisation without an extra lane, and widening to four — because the
    physical work is the same whatever is painted on top. A 2+1 adds one lane, so it must sit
    strictly between them; outside that range the interpolation has been broken rather than
    adjusted."""
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    marks = inputs["benchmarks"]
    items = inputs["items"]
    rate_ron = items["twoPlusOneWidenEurPerKm"]["value"] * items["ronPerEur"]["value"]
    assert marks["dn29dModernisation"]["value"] < rate_ron < marks["dn7FourLaneWidening"]["value"]
    assert inputs["items"]["twoPlusOneWidenEurPerKm"]["confidence"] == "derived"


def test_the_romanian_ladder_is_ordered(built):
    """Rehabilitation, then modernisation, then widening. If this ever inverted, two contracts
    have been transcribed onto the wrong rungs and the interpolation is meaningless."""
    marks = json.loads(INPUTS.read_text(encoding="utf-8"))["benchmarks"]
    assert (
        marks["dn24Rehabilitation"]["value"]
        < marks["dn29dModernisation"]["value"]
        < marks["dn7FourLaneWidening"]["value"]
    )


def test_the_irish_figures_survive_only_as_a_cross_check(built):
    """Kept because a derived figure falling outside them would be a warning, and deleted
    anchors cannot warn anyone."""
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    rate_eur = inputs["items"]["twoPlusOneWidenEurPerKm"]["value"]
    assert inputs["items"]["twoPlusOneUpgradeEurPerKm"]["value"] < rate_eur
    assert rate_eur < inputs["benchmarks"]["irelandNewBuildEurPerKm"]["value"]


def test_the_interpolation_rule_is_declared_as_assumed(built):
    """The two ends are measured; the rule between them is not, and pretending otherwise would
    be the exact dishonesty the rest of this repository avoids."""
    ids = {limitation["id"] for limitation in built["limitations"]}
    assert "pretul-benzii-a-treia-e-strain" in ids or "regula-de-jumatate-e-presupusa" in ids
    input_ids = {
        limitation["id"]
        for limitation in json.loads(INPUTS.read_text(encoding="utf-8"))["limitations"]
    }
    assert "regula-de-jumatate-e-presupusa" in input_ids

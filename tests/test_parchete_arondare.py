"""Tests for prosecution routed by distance alongside the courts.

This file exists because a blocking limitation was wrong. `parchete-comasare` asserted that
prosecution could not be routed by distance, because no document publishes which communes an
office covers — when a parchet *de pe lângă* a court works in that court's circumscription, and
HG 1217/2023 publishes it. Nothing had to be found; something had to be noticed.

So the first tests are about the inference that replaced the mistake: that the territory really
is taken from the court, that it is declared as an inference rather than a reading, and that the
retired caveat cannot quietly return as blocking.

The rest guard the arithmetic, and one guards the honesty of the result: routing by distance
makes workload slightly *less* even than merging by county, and the file has to keep saying so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARONDARE = ROOT / "simulators/justitie/data/parchete-arondare.json"
COMASARE = ROOT / "simulators/justitie/data/parchete-comasare.json"
NOUA = ROOT / "simulators/justitie/data/arondare-noua.json"


@pytest.fixture(scope="module")
def routed() -> dict:
    if not ARONDARE.exists():
        pytest.skip("prosecution routing not built")
    return json.loads(ARONDARE.read_text(encoding="utf-8"))


def test_the_territory_is_declared_as_an_inference(routed):
    """No decision names a prosecution circumscription directly. Taking the court's is sound and
    is still a deduction, so it has to be labelled as one."""
    ids = {x["id"] for x in routed["limitations"]}
    assert "circumscriptia-parchetului-e-a-instantei" in ids
    assert routed["provenance"]["confidence"] == "derived"


def test_the_retired_caveat_did_not_come_back_as_blocking(routed):
    """It claimed this work was impossible. It is not, and a blocking limitation that says
    otherwise would be telling a reader nothing can be said about a page that says it."""
    if not COMASARE.exists():
        pytest.skip("county merge not built")
    comasare = json.loads(COMASARE.read_text(encoding="utf-8"))
    caveat = next(
        (x for x in comasare["limitations"] if x["id"] == "comasare-pe-judet-nu-pe-distanta"), None
    )
    assert caveat is not None
    assert caveat["severity"] != "blocking"
    assert "parchete-arondare" in caveat["text"]


def test_it_lands_on_the_same_seats_as_the_courts(routed):
    """The whole point: prosecutor and judge in the same town. If the two maps ever stopped
    agreeing, routing prosecution by distance would have bought nothing."""
    if not NOUA.exists():
        pytest.skip("court routing not built")
    noua = json.loads(NOUA.read_text(encoding="utf-8"))
    court_seats = {u["courtSiruta"] for u in noua["units"] if u["courtSiruta"]}
    assert {o["siruta"] for o in routed["offices"]} == court_seats
    assert routed["summary"]["seats"] == 42


def test_volume_is_conserved_through_the_routing(routed):
    summary = routed["summary"]
    assert sum(o["volume"] for o in routed["offices"]) == pytest.approx(
        summary["totalVolume"], abs=len(routed["offices"])
    )
    for office in routed["offices"]:
        if office["prosecutors"]:
            assert office["perProsecutor"] == pytest.approx(
                office["volume"] / office["prosecutors"], rel=1e-2
            )


def test_how_much_rests_on_the_population_split_is_reported(routed):
    summary = routed["summary"]
    assert 0 < summary["invariantShare"] <= 1
    assert summary["invariantShare"] > 0.5
    assert "dosarele-se-impart-dupa-populatie" in {x["id"] for x in routed["limitations"]}


def test_the_shift_against_the_county_merge_is_quantified(routed):
    """Saying the two differ is not a finding; saying by how much is."""
    summary = routed["summary"]
    assert summary["countiesDiffering"] > 0
    assert summary["volumeChangingSeat"] > 0
    assert summary["shareChangingSeat"] == pytest.approx(
        summary["volumeChangingSeat"] / summary["totalVolume"], rel=1e-2
    )
    assert len(routed["differences"]) == summary["countiesDiffering"]
    # Sorted largest shift first, so the biggest one is the one reported.
    assert routed["summary"]["biggestShift"]["delta"] == routed["differences"][0]["delta"]


def test_the_cost_of_routing_by_distance_is_kept_visible(routed):
    """Distance routing buys logistics, not evenness. The county merge produces a tighter
    workload spread and the file carries both numbers so the trade cannot be hidden."""
    summary = routed["summary"]
    assert summary["countySpreadMaxOverMin"] > 0
    assert summary["spread"]["maxOverMin"] > summary["countySpreadMaxOverMin"], (
        "if distance routing ever became the more even option too, the docstring claiming a "
        "trade-off needs rewriting rather than this test relaxing"
    )


def test_fractional_prosecutors_are_admitted(routed):
    """Splitting an office's staff on the same weights as its cases is the only consistent
    apportionment and it produces tenths of a person, which is stated rather than rounded away."""
    assert "procurorii-merg-cu-dosarele" in {x["id"] for x in routed["limitations"]}
    assert any(o["prosecutors"] % 1 for o in routed["offices"])

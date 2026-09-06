"""Tests for the served-population join.

The join is a sum, and sums do not need tests. What needs tests is the set of ways this file
could be confidently wrong:

  * a court that fails to match its register entry drops its whole population, and the total
    would still look like a total
  * the two territorial tiers are computed from the same communes by different routes, so they
    must agree exactly — if they do not, one of the routes lost a court
  * "population" means five different things across the tiers, and summing the wrong subset
    double-counts four counties or invents 3,6 million people in military jurisdictions
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "simulators/justitie/scripts"
MODULE = SCRIPTS / "build_populatie_arondata.py"
DOCUMENT = ROOT / "simulators/justitie/data/populatie-arondata.json"

sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("build_populatie_arondata", MODULE)
served = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = served
spec.loader.exec_module(served)


@pytest.fixture(scope="module")
def document() -> dict:
    if not DOCUMENT.is_file():
        pytest.skip("populatie-arondata.json not built in this checkout")
    return json.loads(DOCUMENT.read_text(encoding="utf-8"))


def test_the_payload_is_read_the_same_way_the_browser_reads_it():
    """`attributes.bin` opens with one u32 population per UAT, in `attributes.json` order.

    If that layout ever changes, this reads the wrong bytes and produces populations that are
    plausible integers in the wrong places — the failure that would be hardest to see.
    """
    population, names = served.population_by_siruta()
    assert len(population) == len(names)
    total = sum(population.values())
    # Romania is between 18 and 21 million on any registry anyone would ship here. A misread
    # offset produces a number nowhere near it.
    assert 18_000_000 < total < 21_000_000


def test_the_two_territorial_tiers_agree(document):
    """Judecătorii and county tribunals are the same communes counted two ways.

    Every commune belongs to one judecătorie and every judecătorie to one county, so the two
    sums must be identical. A mismatch means one route lost a court, and a lost court is
    invisible in a total.
    """
    by_basis: dict[str, int] = {}
    for court in document["instante"]:
        if court["populatie"] is None:
            continue
        by_basis[court["bazaPopulatiei"]] = (
            by_basis.get(court["bazaPopulatiei"], 0) + court["populatie"]
        )
    assert by_basis["comune-arondate"] == by_basis["judet"]
    assert by_basis["comune-arondate"] == document["summary"]["populatieArondata"]


def test_the_arondated_population_is_the_country(document):
    summary = document["summary"]
    assert summary["cotaArondata"] > 0.99
    # The gap has to be exactly the named communes, not an unexplained remainder.
    assert len(document["comuneNearondate"]) == summary["comuneNearondate"]


def test_an_unmatched_court_is_a_failure_not_a_footnote(document):
    # A court in the decision that does not meet the register contributes nothing, and its
    # absence would look like a smaller country rather than a broken join. The schema caps this
    # array at zero items and the builder exits non-zero; this checks the shipped file.
    assert document["summary"]["judecatoriiNepotrivite"] == []


def test_a_military_tribunal_has_no_territory(document):
    """Its jurisdiction is over service members, not over the county it sits in.

    Giving Tribunalul Militar Iaşi the 760.774 people of Iaşi county would be a claim nobody
    made, and it would add millions of phantom residents to any national sum.
    """
    military = [c for c in document["instante"] if c["bazaPopulatiei"] == "jurisdictie-personala"]
    assert military, "no military tribunals classified"
    for court in military:
        assert court["populatie"] is None
        assert "Militar" in court["nume"]


def test_a_specialised_tribunal_shares_its_county_rather_than_adding_one(document):
    """Cluj has an ordinary tribunal and a specialised one, and one population.

    The specialised court's figure is real — it does serve those people, for its subject matter —
    so it is published; but it carries a basis that keeps it out of a national sum. Adding both
    would count four counties twice.
    """
    shared = [c for c in document["instante"] if c["bazaPopulatiei"] == "judet-partajat"]
    assert shared
    counties = {c["judet"] for c in shared}
    ordinary = {
        c["judet"]: c["populatie"]
        for c in document["instante"]
        if c["bazaPopulatiei"] == "judet" and c["judet"] in counties
    }
    for court in shared:
        assert court["populatie"] == ordinary[court["judet"]]


def test_appeal_courts_carry_the_question_rather_than_a_guess(document):
    # The seat's county would understate each by roughly three times. A visible null is better
    # than a figure that cannot be contradicted.
    appeal = [
        c for c in document["instante"] if c["bazaPopulatiei"] == "circumscriptie-nepublicata"
    ]
    assert len(appeal) == 15
    assert all(court["populatie"] is None for court in appeal)
    assert all(court["dosarePerMieDeLocuitori"] is None for court in appeal)


def test_cases_per_thousand_exists_wherever_a_denominator_does(document):
    for court in document["instante"]:
        has_rate = court["dosarePerMieDeLocuitori"] is not None
        assert has_rate == bool(court["populatie"] and court["volumCsm"])


def test_the_spread_in_cases_per_resident_is_real_and_large(document):
    """The finding the denominator was missing for.

    Court size mostly tracks how many people a court serves; what is left over is how litigious
    they are, and it is not small. This asserts the shape rather than the value — a build that
    flattened it would mean the population had been attached to the wrong courts.
    """
    rates = sorted(
        court["dosarePerMieDeLocuitori"]
        for court in document["instante"]
        if court["grad"] == "judecatorie" and court["dosarePerMieDeLocuitori"]
    )
    assert len(rates) > 150
    assert rates[-1] / rates[0] > 3

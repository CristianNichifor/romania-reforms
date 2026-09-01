"""The institutional design must keep quoting the model it claims to describe.

This repository has published four artefacts that made false statements about themselves —
a cost file claiming no price was sourced after several had been, a limitation describing a
benchmark failure that had been withdrawn. Prose goes stale silently; the numbers in it are
copied once and then drift as the pipeline moves.

INSTITUTIONS.md argues from specific outputs: the number of routes is why the authority cannot
be a commune, the farebox recovery is why the contract must be gross-cost. If those figures
stop matching `data/`, the argument stops resting on this model and starts resting on a
remembered one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "INSTITUTIONS.md"


@pytest.fixture(scope="module")
def text() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def built() -> dict:
    files = {name: ROOT / "data" / f"{name}.json" for name in ("cost", "network", "fares")}
    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        pytest.skip(f"not built: {missing}")
    return {name: json.loads(path.read_text(encoding="utf-8")) for name, path in files.items()}


def spaced(value: int) -> str:
    """1708 as INSTITUTIONS.md writes it: a thin-space thousands separator."""
    return f"{value:,}".replace(",", " ")


def grouped_in(value: int, text: str) -> bool:
    """True if the number appears with either thousands separator this repository uses.

    INSTITUTIONS.md is English prose and groups with a thin space; the README's headline block
    is a Romanian-facing summary and groups with a full stop. Both are deliberate, so the test
    accepts either rather than forcing one document into the other's convention.
    """
    return any(f"{value:,}".replace(",", sep) in text for sep in (" ", "."))


def test_the_network_figures_are_the_ones_in_the_data(text, built):
    """The route and centre counts carry the argument that the buyer is larger than a commune."""
    summary = built["network"]["summary"]
    assert spaced(summary["routes"]) in text
    assert str(summary["hubs"]) in text
    assert spaced(summary["uatsServed"]) in text
    assert spaced(summary["uatsTotal"]) in text


def test_the_fleet_figures_are_the_ones_in_the_data(text, built):
    """The fleet size is why a spare ratio applied network-wide is a real saving."""
    assert spaced(built["cost"]["fleet"]["total"]) in text
    assert spaced(built["cost"]["drivers"]) in text


def test_the_farebox_recovery_is_the_one_in_the_data(text, built):
    """Load-bearing twice over: it sets the size of the compensation, and the comparison
    against Movia is the reason the document can claim the model errs on the safe side. An
    earlier draft of this document said 58%, which was the browser's live scenario rather
    than the committed run, and it turned a passing check into a stated red flag."""
    recovery = built["fares"]["central"]["recovery"]
    assert f"{recovery * 100:.1f}".replace(".", ",") in text
    # Below Movia is the whole point. If the model ever climbs above it, the paragraph
    # explaining why rural recovery is lower than urban has to be rewritten, not kept.
    assert recovery < built["fares"]["benchmark"]["moviaRecovery"]


def test_it_names_the_legal_instruments_rather_than_gesturing_at_them(text):
    """A policy document that says "under EU rules" cannot be checked. These are the specific
    instruments the design depends on, and each is load-bearing: the regulation caps the
    contract length, the Romanian law supplies the authority that can own the network."""
    for instrument in ("1370/2007", "92/2007", "328/2018", "ANRSC", "ADI"):
        assert instrument in text, instrument


def test_it_still_says_what_it_cannot_support(text):
    """The document used to be checked for the phrase "not costed", because the authorities
    were the largest institutional omission. They are costed now, so what must survive is the
    successor caveat: the staff count is assumed, setting the bodies up is not priced, and
    ticketing is counted twice."""
    assert "not costed" not in text, "the authorities are costed; this claim is stale"
    assert "assumed" in text and "counted twice" in text
    assert "272/2007" in text, "the ANRSC methodology mismatch is a real legislative task"


def test_the_authority_figures_match_the_model(text, built):
    """Prose goes stale silently. The staff count and the Movia comparison are the whole
    argument of that section, so they have to keep coming from data/."""
    authority = built["cost"]["authority"]
    assert str(authority["staffEach"]) in text
    assert f"{authority['shareOfOperatorCost'] * 100:.1f}".replace(".", ",") in text
    assert f"{authority['moviaShare'] * 100:.1f}".replace(".", ",") in text


def test_no_headline_number_appears_without_a_thousands_separator(text):
    """Guards the check above. If a figure is written 1708 rather than 1 708, the tests that
    look for the spaced form pass vacuously somewhere else in the file and stop guarding."""
    bare = re.findall(r"(?<![\d\s.,/])\b\d{4,}\b(?!\d)", text)
    allowed = {"1370", "2007", "2018", "2008"}  # instrument and year references
    assert [n for n in bare if n not in allowed] == []


README = ROOT / "README.md"


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


def test_the_readme_headline_is_the_committed_run(readme, built):
    """The headline block quoted 4 705 drivers for weeks after the duty model raised the real
    figure to 5 552 — it had been copied from a browser session and then left. Every number in
    it now has to come back out of data/, so the same drift fails the build instead of being
    published.
    """
    cost, network, fares = built["cost"], built["network"]["summary"], built["fares"]
    for value in (network["hubs"], network["routes"], network["uatsTotal"]):
        assert grouped_in(value, readme), value
    assert grouped_in(cost["fleet"]["total"], readme)
    assert grouped_in(cost["drivers"], readme)
    assert grouped_in(cost["perWeekday"]["duties"], readme)
    assert str(cost["authority"]["count"]) in readme
    assert str(cost["authority"]["staffEach"]) in readme
    # Recovery and subsidy, with the Romanian decimal comma the document is written in.
    assert f"{fares['central']['recovery'] * 100:.0f}% recovery" in readme
    assert f"{round(fares['central']['subsidyPerPersonYearRon'])} lei a head" in readme


def test_the_readme_says_the_ledger_excludes_rail(readme):
    """Without this the headline reads as the whole transport bill, and rail's 282 md of extra
    track sits outside it with nothing saying so."""
    assert "rail is priced separately and NOT added" in readme


def test_the_readme_no_longer_claims_nothing_is_validated(readme):
    """Third place that carried the claim. It was true when written and stopped being true
    twice over — county timetables, then the drive-time gate."""
    assert "No such observation exists in" not in readme
    assert "552" in readme and "Vâlcea" in readme

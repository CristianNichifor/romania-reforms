"""Tests for the filings-per-court builder.

Two things here can be wrong without looking wrong.

The join is by name across two vocabularies that agree about nothing except the letters — CSM
writes "Judecătoria ADJUD" and the portal enum writes "JudecatoriaADJUD" — so the key has to
survive diacritics in both Unicode encodings, spacing and case, and it has to keep 237 of 241
courts meeting. A key that quietly stopped matching would not raise; it would produce a smaller,
tidier, wrong national total.

The other is the distinction between a court that filed nothing and a court whose name failed to
match. Both are absent from a naive count, and conflating them turns a quiet court into a data
quality incident — which is exactly what happened to Tribunalul Militar Timişoara before the
crawled set was separated from the filed set.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "simulators/justitie/scripts/build_intrate.py"
CSM = ROOT / "simulators/justitie/data/instante-2025.json"

spec = importlib.util.spec_from_file_location("build_intrate", MODULE)
intrate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = intrate
spec.loader.exec_module(intrate)


def test_the_two_vocabularies_meet_on_the_key() -> None:
    assert intrate.key("Judecătoria ADJUD") == intrate.key("JudecatoriaADJUD")
    assert intrate.key("Curtea de Apel ALBA IULIA") == intrate.key("CurteadeApelALBAIULIA")
    assert intrate.key("Tribunalul BRAŞOV") == intrate.key("TribunalulBRASOV")
    # Both Unicode encodings of ș and ț, which ECRIS and the report do not agree about.
    assert intrate.key("Tribunalul BRAȘOV") == intrate.key("TribunalulBRASOV")


def test_renamed_tribunals_are_aliased_rather_than_fuzzily_matched() -> None:
    # The report calls them specialised, the portal enum still calls them commercial.
    for county in ("ARGES", "CLUJ", "MURES"):
        assert intrate.key(f"Tribunalul Specializat {county}") == f"TRIBUNALULCOMERCIAL{county}"
    # An alias must not swallow the ordinary tribunal of the same county.
    assert intrate.key("Tribunalul CLUJ") == "TRIBUNALULCLUJ"


def test_distinct_courts_do_not_collide_on_the_key() -> None:
    document = json.loads(CSM.read_text(encoding="utf-8"))
    keys = [intrate.key(court["name"]) for court in document["courts"]]
    assert len(keys) == len(set(keys)), "two courts folded onto one key"


def test_the_real_join_still_covers_the_published_courts() -> None:
    """A regression guard on the match rate, not a restatement of it.

    237 of 241 was measured against the live enum. The four that do not join are named, so a
    drop below that is a change in one of the two vocabularies rather than noise, and the test
    says which court moved.
    """
    document = json.loads(CSM.read_text(encoding="utf-8"))
    csm_keys = {intrate.key(court["name"]): court["name"] for court in document["courts"]}
    # The enum as crawled, kept here rather than fetched so the test does not need the network.
    enum = [
        "JudecatoriaADJUD",
        "TribunalulALBA",
        "CurteadeApelALBAIULIA",
        "TribunalulComercialCLUJ",
        "TribunalulCLUJ",
        "JudecatoriaSECTORUL4BUCURESTI",
        "CurteadeApelBUCURESTI",
    ]
    for name in enum:
        assert intrate.key(name) in csm_keys, f"{name} no longer joins to the annex"


def csm_row(name, tier, volume, resolved=0):
    return {"name": name, "tier": tier, "volume": volume, "resolved": resolved}


def test_a_court_that_filed_nothing_joins_with_a_zero() -> None:
    """The distinction that cost Tribunalul Militar Timişoara a false coverage failure.

    A crawled court with no filings in the compared year must appear as a court with zero, not
    vanish and be reported as an unmatched name.
    """
    csm = {
        "A": csm_row("Judecătoria A", "judecatorie", 1000),
        "B": csm_row("Judecătoria B", "judecatorie", 500),
    }
    # B was crawled and filed nothing.
    portal = {"A": 100, "B": 0}

    courts, tiers, totals = intrate.compare(csm, portal)

    assert totals["pereche"] == 2
    assert {row["name"]: row["intrate"] for row in courts} == {
        "Judecătoria A": 100,
        "Judecătoria B": 0,
    }
    assert tiers[0]["intrate"] == 100
    assert tiers[0]["instante"] == 2


def test_shares_are_taken_over_the_matched_set_only() -> None:
    """An unmatched court must not shrink everybody else's share.

    Including it in the denominator would make every share slightly too small, and the error
    would fall hardest on the tier holding the most unmatched courts.
    """
    csm = {
        "A": csm_row("Judecătoria A", "judecatorie", 750),
        "B": csm_row("Judecătoria B", "judecatorie", 250),
        # In the annex, never crawled — the Înalta Curte case.
        "C": csm_row("Înalta Curte", "iccj", 9999),
    }
    portal = {"A": 300, "B": 100}

    courts, _, totals = intrate.compare(csm, portal)

    assert totals["pereche"] == 2
    assert totals["intrate"] == 400
    assert totals["volum"] == 1000
    by_name = {row["name"]: row for row in courts}
    assert by_name["Judecătoria A"]["cotaIntrate"] == 0.75
    assert by_name["Judecătoria A"]["cotaVolum"] == 0.75
    # Filings and published volume agree about this court's relative size.
    assert by_name["Judecătoria A"]["divergentaCota"] == 0.0


def test_divergence_is_signed_towards_the_court_that_files_more_than_its_volume_share() -> None:
    csm = {
        "A": csm_row("Judecătoria A", "judecatorie", 500),
        "B": csm_row("Judecătoria B", "judecatorie", 500),
    }
    # A files three quarters of the national total while carrying half the published volume.
    portal = {"A": 300, "B": 100}

    courts, _, _ = intrate.compare(csm, portal)
    by_name = {row["name"]: row for row in courts}

    assert by_name["Judecătoria A"]["divergentaCota"] == 0.25
    assert by_name["Judecătoria B"]["divergentaCota"] == -0.25


def test_a_court_with_no_published_volume_reports_null_rather_than_dividing() -> None:
    csm = {"A": csm_row("Judecătoria A", "judecatorie", 0)}
    courts, tiers, _ = intrate.compare(csm, {"A": 10})
    assert courts[0]["intratePerVolum"] is None
    assert tiers[0]["intratePerVolum"] is None


def test_courts_are_ordered_by_filings() -> None:
    csm = {
        "A": csm_row("Judecătoria A", "judecatorie", 100),
        "B": csm_row("Judecătoria B", "judecatorie", 100),
    }
    courts, _, _ = intrate.compare(csm, {"A": 5, "B": 50})
    assert [row["name"] for row in courts] == ["Judecătoria B", "Judecătoria A"]

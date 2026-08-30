"""Tests for the coverage ledger.

The ledger's whole purpose is to stop the page overstating itself, so the checks are aimed at
the ways it could do that: a chapter claiming documents that do not exist, a count that does
not match its own rows, or the two kinds of gap quietly merging into one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ACOPERIRE = ROOT / "simulators/justitie/data/acoperire.json"
DATA = ROOT / "simulators/justitie/data"


@pytest.fixture(scope="module")
def acoperire() -> dict:
    if not ACOPERIRE.exists():
        pytest.skip("coverage ledger not built")
    return json.loads(ACOPERIRE.read_text(encoding="utf-8"))


def test_every_claimed_document_exists(acoperire):
    """The claim that makes the headline checkable rather than typed."""
    for chapter in acoperire["chapters"]:
        for document in chapter["simulated"]:
            assert (DATA / f"{document}.json").exists(), (chapter["number"], document)


def test_the_counts_match_the_rows(acoperire):
    chapters = acoperire["chapters"]
    counts = acoperire["counts"]
    assert counts["total"] == len(chapters)
    for status in ("simulat", "citat", "negacoperit"):
        assert counts[status] == sum(1 for c in chapters if c["status"] == status), status
    assert counts["simulat"] + counts["citat"] + counts["negacoperit"] == counts["total"]
    assert counts["buildable"] == sum(1 for c in chapters if c["gap"] == "buildable")
    assert counts["notAQuantity"] == sum(1 for c in chapters if c["gap"] == "not-a-quantity")


def test_status_follows_from_the_evidence(acoperire):
    """Status is derived, not asserted: a chapter with documents is simulated, one without but
    quoted is quoted, and anything else is uncovered."""
    for c in acoperire["chapters"]:
        if c["simulated"]:
            assert c["status"] == "simulat", c["number"]
        elif c["quoted"]:
            assert c["status"] == "citat", c["number"]
        else:
            assert c["status"] == "negacoperit", c["number"]


def test_the_two_kinds_of_gap_stay_apart(acoperire):
    """A chapter nobody has built and a chapter that cannot be built are different admissions.

    If every gap were 'not-a-quantity' the ledger would be excusing itself; if every gap were
    'buildable' it would be inventing obligations. Both kinds must be present, and each
    uncovered chapter must say which it is and why.
    """
    gaps = [c for c in acoperire["chapters"] if c["status"] == "negacoperit"]
    kinds = {c["gap"] for c in gaps}
    assert kinds == {"buildable", "not-a-quantity"}, kinds
    for c in gaps:
        assert c["why"], c["number"]


def test_covered_chapters_carry_no_gap(acoperire):
    for c in acoperire["chapters"]:
        if c["status"] != "negacoperit":
            assert c["gap"] is None, c["number"]


def test_chapters_are_numbered_without_holes(acoperire):
    numbers = [c["number"] for c in acoperire["chapters"]]
    assert numbers == sorted(numbers)
    assert numbers == list(range(1, len(numbers) + 1))


def test_pages_come_from_the_body_not_the_contents(acoperire):
    """The contents run to page 4; a chapter located there would be the contents entry.

    Chapter 1 is the exception the rule was written around: its body heading really does sit on
    page 4, immediately after the contents end.
    """
    for c in acoperire["chapters"]:
        if c["number"] > 1:
            assert c["page"] > 4, (c["number"], c["page"])
    pages = [c["page"] for c in acoperire["chapters"]]
    assert pages == sorted(pages), "chapters must run forward through the document"


def test_coverage_is_not_claimed_to_be_validation(acoperire):
    """The simulator contradicts the paper in places. 'Simulated' must not read as 'confirmed'."""
    ids = {x["id"] for x in acoperire["limitations"]}
    assert "acoperire-nu-inseamna-validare" in ids
    assert "incadrarea-e-o-judecata" in ids


def test_the_classification_is_declared_a_judgement(acoperire):
    assert acoperire["provenance"]["confidence"] == "assumed"

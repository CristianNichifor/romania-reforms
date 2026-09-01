"""Tests for the paper carried in its own words.

This file exists because an audit of the page found 9% of the sidebar was about what the reform
proposes and 91% about whether its numbers hold — with the proposals reduced to eight headings
and their page numbers, and seven chapters appearing nowhere but a "not covered" list.

The tests that matter here are about provenance rather than arithmetic. A page that argues with
a document has to reproduce the document faithfully, and it has to be impossible for a quote it
argues against to drift away from what the document says. So: every claim must be findable,
verbatim, inside the chapter it is attributed to.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LUCRAREA = ROOT / "simulators/justitie/data/lucrarea.json"
ACOPERIRE = ROOT / "simulators/justitie/data/acoperire.json"


@pytest.fixture(scope="module")
def paper() -> dict:
    if not LUCRAREA.exists():
        pytest.skip("the paper is not extracted")
    return json.loads(LUCRAREA.read_text(encoding="utf-8"))


def test_all_nineteen_chapters_are_present_and_in_order(paper):
    numbers = [c["number"] for c in paper["chapters"]]
    assert numbers == list(range(1, 20))
    pages = [c["page"] for c in paper["chapters"]]
    assert pages == sorted(pages), "chapters must be in the order the paper prints them"


def test_no_chapter_came_out_empty(paper):
    """The extraction slices between headings; an off-by-one there produces a chapter of a few
    characters that still looks like a chapter."""
    for chapter in paper["chapters"]:
        assert chapter["characters"] == len(chapter["text"])
        assert chapter["characters"] > 100, chapter["number"]


def test_a_chapter_does_not_repeat_its_own_heading(paper):
    """The section that renders these already shows the number and the title."""
    for chapter in paper["chapters"]:
        assert not re.match(rf"^\s*{chapter['number']}\s*\.", chapter["text"]), chapter["number"]


def test_the_papers_lists_survived_extraction(paper):
    """The document is largely bullet lists. An earlier version stripped headings by splitting
    on whitespace and rejoining with spaces, which silently flattened every list into one
    paragraph — the text was all still there and had stopped being readable."""
    bulleted = [c for c in paper["chapters"] if "●" in c["text"]]
    assert len(bulleted) >= 10
    for chapter in bulleted:
        assert "\n● " in chapter["text"], chapter["number"]


def test_every_claim_is_verbatim_from_the_chapter_it_cites(paper):
    """The invariant the whole file rests on. A quote the page argues against must be findable,
    exactly, in the chapter it is attributed to — otherwise the argument stands against a
    sentence nobody wrote."""
    text_of = {c["number"]: c["text"] for c in paper["chapters"]}
    for claim in paper["claims"]:
        assert claim["chapter"] in text_of, claim["fold"]
        haystack = re.sub(r"\s+", " ", text_of[claim["chapter"]])
        needle = re.sub(r"\s+", " ", claim["quote"])
        assert needle in haystack, f"{claim['fold']}: {needle!r} is not in chapter {claim['chapter']}"


def test_claims_carry_a_page_and_point_at_a_real_section(paper):
    pages = {c["number"]: c["page"] for c in paper["chapters"]}
    for claim in paper["claims"]:
        assert claim["page"] == pages[claim["chapter"]]
        assert claim["fold"].endswith("-fold")
        assert claim["label"]


def test_the_text_is_quoted_and_the_pairing_is_judged(paper):
    """Two different kinds of statement, and they must not be given the same confidence: the
    words are the paper's, the decision that a finding tests this sentence is the author's."""
    assert paper["provenance"]["confidence"] == "verbatim"
    assert paper["claimsProvenance"]["confidence"] == "assumed"


def test_the_chapters_with_nothing_to_check_are_still_carried(paper):
    """The seven argumentative chapters are why the page looked one-sided. Reproducing them is
    not verifying them, and the file says so."""
    if not ACOPERIRE.exists():
        pytest.skip("ledger not built")
    ledger = json.loads(ACOPERIRE.read_text(encoding="utf-8"))
    uncovered = {c["number"] for c in ledger["chapters"] if c["status"] == "negacoperit"}
    carried = {c["number"] for c in paper["chapters"]}
    assert uncovered <= carried
    assert "capitolele-fara-cifre-raman-necontrolate" in {x["id"] for x in paper["limitations"]}


def test_the_repagination_is_declared(paper):
    assert "textul-e-repaginat" in {x["id"] for x in paper["limitations"]}
    assert "asocierea-afirmatie-sectiune-e-o-judecata" in {x["id"] for x in paper["limitations"]}

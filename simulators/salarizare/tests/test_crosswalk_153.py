"""Tests for the 153/2017 -> draft assimilation.

Neither law publishes the mapping, so every link here is a reconstruction. The danger is
not that the script crashes but that it becomes confidently wrong: a loose match produces
a link that reads like a fact about someone's job.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CROSSWALK = ROOT / "data/crosswalks/ro-153-2017--ro-draft-2026-07-16.json"


@pytest.fixture(scope="module")
def crosswalk() -> dict:
    if not CROSSWALK.exists():
        pytest.skip("crosswalk not built yet")
    return json.loads(CROSSWALK.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def regimes() -> tuple[dict, dict]:
    return (
        json.loads((ROOT / "data/regimes/ro-153-2017.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "data/regimes/ro-draft-2026-07-16.json").read_text(encoding="utf-8")),
    )


def test_never_claims_to_be_published(crosswalk):
    """Art. 32 requires reassignment and leaves the mapping to each ordonator.

    So no link may claim `verbatim`, and the document must say it is reconstructed. A
    crosswalk that quietly presents a guess as a right is worse than no crosswalk.
    """
    assert crosswalk["authority"] == "reconstructed"
    assert {l["confidence"] for l in crosswalk["links"]} <= {"derived", "assumed"}


def test_every_endpoint_exists(crosswalk, regimes):
    """A link into a code that no longer exists is a silent dead end in the UI."""
    old, new = regimes
    old_codes = {p["code"] for p in old["positions"]}
    new_codes = {p["code"] for p in new["positions"]}
    for link in crosswalk["links"]:
        for e in link["from"]:
            assert e["positionCode"] in old_codes, f"{link['id']} points at a missing old post"
        for e in link["to"]:
            assert e["positionCode"] in new_codes, f"{link['id']} points at a missing new post"


def test_no_position_is_linked_twice(crosswalk):
    """Two links onto one post would double-count it and contradict each other."""
    for side in ("from", "to"):
        codes = [e["positionCode"] for l in crosswalk["links"] for e in l[side]]
        assert len(codes) == len(set(codes)), f"a post appears in more than one link on {side}"


def test_links_stay_within_an_occupational_family(crosswalk, regimes):
    """A director in education and one in administration are different posts.

    Family is the guard that stops a shared word joining them, and it is the reason the
    match rate is 34% rather than something flattering.
    """
    old, new = regimes
    family = {p["code"]: p.get("family") for p in old["positions"] + new["positions"]}
    for link in crosswalk["links"]:
        families = {family[e["positionCode"]] for e in link["from"] + link["to"]}
        assert len(families) == 1, f"{link['id']} crosses families: {families}"


def test_weak_matches_are_the_exception_and_are_marked(crosswalk):
    """Stem matches drop the grade and the study level, so they are `assumed`, not `derived`.

    They must also stay rare: if they ever dominate, the crosswalk has stopped reading
    titles and started guessing.
    """
    links = crosswalk["links"]
    assumed = [l for l in links if l["confidence"] == "assumed"]
    assert len(assumed) < len(links) * 0.25
    for link in assumed:
        assert len(link["from"]) == 1 and len(link["to"]) == 1


def test_coverage_is_reported_rather_than_inflated(crosswalk, regimes):
    """Unmatched posts are left unmatched, never called `abolished`.

    Calling them abolished would roughly double the apparent coverage and would assert
    something the evidence does not support.
    """
    old, _ = regimes
    assert "abolished" not in {l["relation"] for l in crosswalk["links"]}
    linked = {e["positionCode"] for l in crosswalk["links"] for e in l["from"]}
    assert len(linked) < len(old["positions"])
    assert "reconstructia acopera" in crosswalk["provenance"]["note"].lower()

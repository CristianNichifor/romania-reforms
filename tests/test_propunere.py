"""Tests for the proposal document.

The baseline is published by the CSM and the proposal is not. Everything here guards that
distinction, because the failure mode is not a wrong number — it is an unpublished claim
quietly reading as an official plan.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROPOSAL = ROOT / "simulators/justitie/data/propunere-harta-judiciara.json"
PAPER = ROOT / "simulators/justitie/sources/reforma-sistem-judiciar-romania.pdf"
REGISTRY = ROOT / "simulators/administrativ/web/public/data/attributes.json"


@pytest.fixture(scope="module")
def proposal() -> dict:
    if not PROPOSAL.exists():
        pytest.skip("proposal not imported")
    return json.loads(PROPOSAL.read_text(encoding="utf-8"))


def test_the_paper_is_in_the_repository():
    """It has no public URL, so if it is not committed the reader cannot check it.

    Every other source here is downloaded from a stable address by its importer. This one
    is the author's own document, which is exactly why it has to travel with the code.
    """
    assert PAPER.exists(), "the reform paper is missing from sources/"


def test_it_is_marked_unpublished(proposal):
    assert proposal["published"] is False
    assert any(x["id"] == "propunere-nepublicata" for x in proposal["limitations"])


def test_every_target_figure_cites_a_page(proposal):
    for name, tier in proposal["tinta"].items():
        locator = tier["provenance"]["locator"]
        assert "p. 59" in locator, f"{name} does not say where it was read from: {locator}"
        assert tier["provenance"]["confidence"] == "verbatim", name


def test_the_arithmetic_gap_is_recorded_and_still_true(proposal):
    """The proposal's two numbers do not close, and the document says so.

    42 courts at 150.000-200.000 inhabitants each covers 6,3-8,4 million people. Romania has
    19 million. This recomputes it from the registry rather than trusting the prose, so the
    limitation cannot quietly stop being true.
    """
    blocking = [x for x in proposal["limitations"] if x["id"] == "tinta-nu-se-inchide-aritmetic"]
    assert blocking and blocking[0]["severity"] == "blocking"

    if not REGISTRY.exists():
        pytest.skip("registry not built")
    import struct

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    count = len(registry["siruta"])
    raw = (REGISTRY.parent / "attributes.bin").read_bytes()
    population = sum(struct.unpack_from(f"<{count}I", raw, 0))

    tier = proposal["tinta"]["nivel1"]
    per_court = population / tier["instante"]
    assert per_court > tier["populatieMaxima"], (
        f"{per_court:,.0f} per court is inside the stated band, so the limitation is stale"
    )
    needed_low = population / tier["populatieMaxima"]
    needed_high = population / tier["populatieMinima"]
    assert needed_low > tier["instante"], (needed_low, tier["instante"])
    # The range the text quotes, recomputed.
    assert 90 <= needed_low <= 100, needed_low
    assert 120 <= needed_high <= 135, needed_high

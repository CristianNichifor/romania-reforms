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


def test_the_viability_floor_holds(proposal):
    """Every county can sustain a court, which is what makes the two rules compatible.

    The population figures are a minimum — a court should serve at least 150.000-200.000 —
    not a band each court must fall inside. Read as a band they would need roughly 116
    courts instead of 42, which is the misreading the `formulare-de-clarificat` note exists
    to prevent. Recomputed from the registry so the claim cannot quietly stop being true.
    """
    tier = proposal["tinta"]["nivel1"]
    assert tier["regula"] == "acoperire"
    assert tier["pragEste"] == "minim"

    if not REGISTRY.exists():
        pytest.skip("registry not built")
    import collections
    import struct

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    raw = (REGISTRY.parent / "attributes.bin").read_bytes()
    by_county: dict[str, int] = collections.Counter()
    for index, code in enumerate(registry["county"]):
        by_county[code] += struct.unpack_from("<I", raw, index * 4)[0]

    assert len(by_county) == tier["instante"], (len(by_county), tier["instante"])
    below = {c: p for c, p in by_county.items() if p < tier["populatieMinima"]}
    assert below == {}, f"a county cannot sustain its own court: {below}"

    # Tulcea is the only county inside the band rather than above it. If that changes, the
    # note describing the floor as nearly slack has changed with it.
    inside = sorted(c for c, p in by_county.items() if p < tier["populatieMaxima"])
    assert inside == ["TL"], inside


def test_the_wording_is_flagged(proposal):
    assert any(x["id"] == "formulare-de-clarificat" for x in proposal["limitations"])

"""Tests for the resolved court-to-commune list.

The file exists so the browser never has to match a court name, and everything worth testing is
about the two ways that could still go wrong: a court that quietly fails to resolve and takes its
whole caseload out of the routing, and a set of indices that addresses the wrong communes because
the payload moved underneath it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCUMENT = ROOT / "simulators/justitie/data/arondare-instante.json"
PAYLOAD = ROOT / "simulators/administrativ/web/public/data/manifest.json"


@pytest.fixture(scope="module")
def document() -> dict:
    if not DOCUMENT.is_file():
        pytest.skip("arondare-instante.json not built in this checkout")
    return json.loads(DOCUMENT.read_text(encoding="utf-8"))


def test_no_court_failed_to_resolve(document):
    # An unresolved court contributes nothing to any proposed seat, and the result would still be
    # 42 plausible courts with plausible caseloads.
    assert document["summary"]["nepotrivite"] == []


def test_the_indices_match_the_payload_they_address(document):
    manifest = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert document["summary"]["uatCount"] == manifest["uatCount"]
    ceiling = manifest["uatCount"]
    for court in document["instante"]:
        assert court["uat"], f"{court['institutie']} serves nothing"
        assert max(court["uat"]) < ceiling
        assert min(court["uat"]) >= 0


def test_every_commune_belongs_to_exactly_one_judecatorie(document):
    """Overlap would double-count a commune's caseload onto two seats.

    The tribunals deliberately repeat their county's communes, so only the first-instance tier is
    checked — that is the tier the arondare actually partitions.
    """
    seen: set[int] = set()
    for court in document["instante"]:
        if court["grad"] != "judecatorie":
            continue
        overlap = seen & set(court["uat"])
        assert not overlap, f"{court['institutie']} shares communes with an earlier court"
        seen.update(court["uat"])
    manifest = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    # Two communes were founded after the decision and belong to none; everything else must.
    assert len(seen) >= manifest["uatCount"] - 2


def test_a_tribunal_covers_its_county_and_nothing_else(document):
    by_county: dict[str, set[int]] = {}
    for court in document["instante"]:
        if court["grad"] == "judecatorie" and court["judet"]:
            by_county.setdefault(court["judet"], set()).update(court["uat"])
    tribunals = [c for c in document["instante"] if c["grad"] == "tribunal"]
    assert len(tribunals) == 42
    for court in tribunals:
        assert set(court["uat"]) == by_county[court["judet"]]


def test_military_tribunals_are_not_routed(document):
    # Their jurisdiction is over service members. Spreading their caseload over a county would
    # move work that never came from it.
    for court in document["instante"]:
        assert "MILITAR" not in court["institutie"].upper()


def test_appeal_courts_are_absent_rather_than_empty(document):
    # An empty commune list would read as "serves nobody" instead of "not known".
    for court in document["instante"]:
        assert not court["institutie"].startswith("CurteadeApel")

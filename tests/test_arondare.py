"""Tests for the arondare — which localities each judecătorie serves.

The arondare partitions the country, which makes it unusually testable: every commune belongs
to exactly one court, so a parse hole is arithmetic rather than opinion. That matters because
a partial arondare still draws a map, and the map would quietly understate what closing a
court costs the people who use it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARONDARE = ROOT / "simulators/justitie/data/arondare-2023.json"
COURTS = ROOT / "simulators/justitie/data/instante-localizate-2025.json"
REGISTRY = ROOT / "simulators/administrativ/web/public/data/attributes.json"

# Created after the decision was adopted in November 2023, so it does not mention them.
CREATED_LATER = {"CAPU CÂMPULUI", "GOLOGANU"}


@pytest.fixture(scope="module")
def arondare() -> dict:
    if not ARONDARE.exists():
        pytest.skip("arondare not imported")
    return json.loads(ARONDARE.read_text(encoding="utf-8"))


def test_the_decision_defines_176_courts(arondare):
    assert len(arondare["courts"]) == 176


def test_it_covers_the_country(arondare):
    """Every commune belongs to a court, bar the two the decision predates.

    Listed by name rather than counted, so a *new* gap fails instead of being absorbed into
    a tolerance.
    """
    if not REGISTRY.exists():
        pytest.skip("registry not built")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    name_of = dict(zip(registry["siruta"], registry["name"], strict=True))

    assigned = {s for court in arondare["courts"] for s in court["localities"]}
    missing = sorted(name_of[s] for s in registry["siruta"] if s not in assigned)
    assert set(missing) == CREATED_LATER, missing


def test_no_commune_belongs_to_two_courts(arondare):
    """The failure this catches is real, not hypothetical.

    Judecatoria Insuratei is suspended and the decision lists its eleven communes twice —
    once under the courts holding them today and once under Insuratei with a forward
    reference. Read naively, all eleven land in two courts at once.
    """
    seen: dict[str, str] = {}
    doubled = []
    for court in arondare["courts"]:
        for siruta in court["localities"]:
            if siruta in seen:
                doubled.append(f"{siruta}: {seen[siruta]} and {court['name']}")
            seen[siruta] = court["name"]
    assert doubled == [], doubled


def test_only_the_suspended_court_serves_nobody(arondare):
    empty = [c["name"] for c in arondare["courts"] if not c["localities"]]
    assert empty == ["Judecătoria Însurăţei"], empty
    suspended = [c["name"] for c in arondare["courts"] if c["suspended"]]
    assert suspended == ["Judecătoria Însurăţei"], suspended


def test_it_joins_to_the_caseload_by_seat(arondare):
    """The join is on SIRUTA, not on names, and this is why.

    Eleven of the 176 are spelled differently in the two documents — the decision writes
    "Judecatoria Gurahont" and "Judecatoria Odorheiu Secuiesc", the CSM report "GURA HONT"
    and "ODORHEIUL SECUIESC". Matching by name loses eleven courts and their caseloads; a
    code is the same in both.

    The single court that does not join is Insuratei, which is suspended and therefore absent
    from the report — which is also why the decision defines 176 courts and the report counts
    175. The two documents agree; they just describe different things.
    """
    if not COURTS.exists():
        pytest.skip("courts not located")
    located = json.loads(COURTS.read_text(encoding="utf-8"))["courts"]
    seats = {c["siruta"] for c in located if c["tier"] == "judecatorie" and c["siruta"]}

    unjoined = [c["name"] for c in arondare["courts"] if c["seatSiruta"] not in seats]
    assert unjoined == ["Judecătoria Însurăţei"], unjoined


def test_every_sitting_court_has_a_seat(arondare):
    seatless = [c["name"] for c in arondare["courts"] if not c["seatSiruta"]]
    assert seatless == [], seatless


def test_the_gaps_are_declared(arondare):
    ids = {x["id"] for x in arondare["limitations"]}
    assert "comune-mai-noi-decat-hotararea" in ids
    assert "judecatoria-insuratei-suspendata" in ids

"""Tests for the court locator.

A join that silently drops rows still produces a map — a smaller one, arguing from a subset
while looking complete. The importer guards its reading of the PDF against the report's own
row numbering; these guard the join against the registry it joins to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Every edition that has been located, so a new year is covered the moment it is imported
# rather than when someone remembers to widen the test.
LOCATED_FILES = sorted((ROOT / "simulators/justitie/data").glob("instante-localizate-*.json"))
LOCATED = LOCATED_FILES[-1] if LOCATED_FILES else ROOT / "simulators/justitie/data/none.json"
SOURCE = (
    LOCATED.with_name(LOCATED.name.replace("-localizate", "")) if LOCATED_FILES else LOCATED
)
REGISTRY = ROOT / "simulators/administrativ/web/public/data/attributes.json"

# Anything above this is a commune.
ADMIN_RANK_ORAS = 3


@pytest.fixture(scope="module")
def located() -> list[dict]:
    if not LOCATED.exists():
        pytest.skip("courts not located yet; run scripts/locate_instante.py")
    return json.loads(LOCATED.read_text(encoding="utf-8"))["courts"]


@pytest.fixture(scope="module")
def registry() -> dict:
    if not REGISTRY.exists():
        pytest.skip("the administrative payload is not built")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_every_court_is_placed(located):
    missing = [c["name"] for c in located if not c.get("county")]
    assert missing == [], missing


def test_nothing_was_lost_or_invented(located):
    """The join must be exactly the same courts, carrying exactly the same work.

    The failure this catches is the quiet one: a name that does not match is dropped, and
    241 courts silently become 230 without the total looking wrong to anyone who has not
    added it up.
    """
    source = json.loads(SOURCE.read_text(encoding="utf-8"))["courts"]
    assert len(located) == len(source)
    assert sorted(c["id"] for c in located) == sorted(c["id"] for c in source)
    assert sum(c["volume"] for c in located) == sum(c["volume"] for c in source)


def test_an_ambiguous_name_resolves_to_the_town(located, registry):
    """The rule that resolves nineteen ambiguous names, asserted rather than assumed.

    There are four places called Calarasi and five called Costesti, and the court is in the
    town every time. This pins the disambiguation only — it is not a claim that every court
    is in a town, which is false and tested below.
    """
    rank_of = dict(zip(registry["siruta"], registry["adminRank"], strict=True))
    name_of = dict(zip(registry["siruta"], registry["name"], strict=True))

    ambiguous: dict[str, list[str]] = {}
    for siruta, name in zip(registry["siruta"], registry["name"], strict=True):
        bare = name.split(" ", 1)[-1] if name.startswith(("MUNICIPIUL", "ORAȘ", "COMUNA")) else name
        ambiguous.setdefault(bare.upper(), []).append(siruta)

    wrong = []
    for court in located:
        if court["siruta"] is None:
            continue
        bare = name_of[court["siruta"]]
        bare = bare.split(" ", 1)[-1] if bare.startswith(("MUNICIPIUL", "ORAȘ", "COMUNA")) else bare
        if len(ambiguous.get(bare.upper(), [])) > 1 and rank_of[court["siruta"]] > ADMIN_RANK_ORAS:
            wrong.append(f"{court['name']} -> {name_of[court['siruta']]}")
    assert wrong == [], wrong


def test_the_courts_that_really_are_in_communes(located, registry):
    """Five judecatorii sit in communes, and that is the map's whole subject.

    An earlier version of the test above asserted no court sits in a commune. The data
    refuted it: Cornetu, Gurahont, Liesti, Podu Turcului and Raducaneni are all real courts
    in real communes, and all five have unambiguous names, so the town rule never applies to
    them. They are also the courts a consolidation reform is aimed at, so a join that
    "corrected" them into the nearest town would be erasing the argument.
    """
    rank_of = dict(zip(registry["siruta"], registry["adminRank"], strict=True))
    in_communes = {
        c["name"] for c in located if c["siruta"] and rank_of[c["siruta"]] > ADMIN_RANK_ORAS
    }
    assert len(in_communes) == 5, sorted(in_communes)
    # Both spellings: the 2023 annex prints "Judecatoria", the 2025 one "Judecătoria". The
    # same five courts either way, and the diacritic is the only thing that moved.
    assert all(n.startswith(("Judecatoria", "Judecătoria")) for n in in_communes), sorted(
        in_communes
    )


def test_only_bucharest_courts_are_placed_without_a_uat(located):
    # A null SIRUTA means "the city as a whole", which is only meaningful for Bucharest —
    # six sectors and no single seat. Anywhere else it would mean the join gave up.
    stray = [c["name"] for c in located if c["siruta"] is None and c["county"] != "B"]
    assert stray == [], stray


def test_the_garbled_name_still_finds_its_county(located):
    """Page 142 of the report prints `Tribunalul VŢLCEA`, with a T-cedilla for an A-circumflex.

    Pages 42, 53 and 125 of the same document print it correctly, so the import is faithful
    and the dataset's name is genuinely what the annex says. The alias is what lets it join
    anyway, and without it the court lands nowhere.
    """
    court = next(c for c in located if "V" in c["name"] and "LCEA" in c["name"])
    assert court["county"] == "VL", court


def test_every_county_has_a_court(located):
    counties = {c["county"] for c in located}
    assert len(counties) == 42, sorted(counties)


def test_the_location_is_never_claimed_as_verbatim():
    """The report contains no locations, so nothing here may say it read one.

    This is the rule the whole repository runs on, and it is the one a join is most likely
    to break: the caseloads are printed, the place is inferred, and the document must not
    blur the two.
    """
    document = json.loads(LOCATED.read_text(encoding="utf-8"))
    assert document["provenance"]["confidence"] == "derived"


def test_the_access_limitation_is_still_blocking():
    """Knowing where a court is, is not knowing what it serves.

    The arondare is set by law rather than by this report, so the cost of closing a
    courthouse — how much further someone then travels — remains unanswerable. A map that
    quietly dropped this limitation because it now has coordinates would be claiming to
    answer it.
    """
    document = json.loads(LOCATED.read_text(encoding="utf-8"))
    blocking = [x for x in document["limitations"] if x["id"] == "fara-geografie"]
    assert blocking and blocking[0]["severity"] == "blocking"
    assert "access" in blocking[0]["affects"]

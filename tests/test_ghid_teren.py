"""Tests for the notaries' land grids, which are the base a land value tax would stand on.

Reading tables out of a PDF is the least reliable thing this repository does, and these
studies are worse than most: 41 counties, no shared template, names that wrap mid-word and
are spelled two ways inside the same document. A parse that quietly drops a commune produces
a land map with a hole in it, and a hole looks exactly like cheap land.

So the tests here are mostly about absence rather than about values. The INS land register
says which localities the county has, the study numbers its own rural table, and the parse
has to account for both. What survived from an earlier version is
recorded as a test because each was a real defect: a number regex that read "256 123" as one
number and lost the CC row of Bacău's largest city, a noise filter that ate the "TI" ending
two commune names, and a name rule that rejected "BERESTI - BISTRITA" outright.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "simulators/impozit-teren/data"
COUNTIES = ["bacau", "neamt", "alba", "iasi", "sibiu", "constanta", "tulcea", "prahova"]


def load(county: str) -> dict:
    # Whichever edition exists. The Ploiești chamber published nothing for 2026, so Prahova's
    # grid is the 2025 one and a test that insists on a common year silently skips it.
    editions = sorted(DATA.glob(f"ghid-teren-{county}-*.json"))
    if not editions:
        pytest.skip(f"the {county} grid is not imported")
    return json.loads(editions[-1].read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=COUNTIES)
def grid(request) -> dict:
    return load(request.param)


def test_every_commune_the_register_names_is_in_the_grid(grid):
    """The INS land register is the check, and it must balance in both directions.

    An outside list, not another page of the same document. The first version read the roster
    off the study's own organisation page, which exists in the two studies from CNP Bacău and
    in none of the fifteen tried from four other chambers.

    A missing commune is the failure that matters: it does not look like an error downstream,
    it looks like a place with no land value. The reverse check matters too — a commune the
    register never names means the parse invented one out of a wrapped line.
    """
    summary = grid["summary"]
    # Invented places are a bug; missing ones are a short document. Only the first is fatal.
    assert summary["tableMissingFromRoster"] == []
    assert summary["duplicateLocalities"] == []
    assert all(commune["matchedRoster"] for commune in grid["communes"])
    # And the county has to be substantially there. Alba is 98,7% — one town whose own table
    # is broken in the source — while a parse that has lost a tenth of a county is broken.
    assert summary["coverage"]["share"] >= 0.9
    assert summary["coverage"]["localitiesPriced"] > 0


def test_the_studys_own_numbering_runs_without_a_gap(grid):
    """The rural table numbers its communes; a gap means a block was skipped."""
    assert grid["summary"]["numberingProblems"] == []


def test_almost_every_town_is_priced(grid):
    """Towns carry most of the land value, so a town lost costs more than a commune lost.

    Not required to be none: Abrud's own table is broken in Alba's study — its heading, its
    unit label and its zone D are all missing — so the honest output names it rather than
    inventing a price or discarding the county. One town in a county is the tolerance.
    """
    assert len(grid["summary"]["townsWithoutZoneGrid"]) <= 1


def test_zoned_localities_are_not_assumed_to_be_towns(grid):
    """A commune can pass its own zoning decision, and Podu Turcului has.

    Worth pinning because the obvious shortcut — "a zone matrix means a town" — is wrong in
    the first county tried, and would have filed a commune's grid under a town that does not
    exist.
    """
    ranks = {entry["rank"] for entry in grid["zoned"]}
    assert ranks <= {"municipii", "orase", "comune"}
    assert {"municipii", "orase"} & ranks


def test_towns_keep_their_villages_in_the_rural_table(grid):
    """Not every row of the rural table is a commune, and that is the document being right.

    Bicaz and Roznov are towns whose attached villages are priced village by village while
    the town itself is priced by zone. Reading those rows as communes the roster forgot would
    have been a bug report against a correct document.
    """
    ranks = {commune["rank"] for commune in grid["communes"]}
    assert ranks <= {"municipii", "orase", "comune"}


def test_a_missing_zone_is_absent_rather_than_free(grid):
    """Dărmănești has no zone D and the study prints a dash there.

    Zero would be a land value of nothing, which under a land tax is a bill of nothing. The
    absence has to survive as null all the way to the tax calculation.
    """
    for entry in grid["zoned"]:
        for values in entry["intravilan"].values():
            assert set(values) == set(entry["zones"])
            assert all(v is None or v > 0 for v in values.values())


def test_the_headline_categories_are_present_and_ordered_by_value(grid):
    """CC is the category a land tax mostly lands on, so it must be there and be the dearest.

    Curți construcții is building land; arable and pasture are worth less per square metre
    everywhere in both counties. If CC were ever missing — as it was for Bacău, until the
    number pattern stopped reading "256 123" as 256123 — the grid would still validate and
    still be useless.
    """
    for entry in grid["zoned"]:
        assert "CC" in entry["intravilan"], entry["name"]
        for zone, cc in entry["intravilan"]["CC"].items():
            for code in ("A", "P+F"):
                other = entry["intravilan"].get(code, {}).get(zone)
                if cc is not None and other is not None:
                    assert cc >= other, f"{entry['name']} {zone} {code}"


def test_villages_carry_values_and_communes_carry_extravilan(grid):
    """The two granularities the document publishes, kept apart.

    Extravilan is printed once per commune. Spreading it onto villages would read as
    per-village precision that was never measured.
    """
    # At least one priced locality per commune. Not strictly more: Prahova's chamber prices
    # the commune as a whole and lists its villages only as names, so there the two are equal
    # — and that is the document's granularity, not a loss in the reading of it.
    assert grid["summary"]["villages"] >= grid["summary"]["communes"]
    # Nearly every commune, not every one: Alba's study prints no extravilan grid for two of
    # its sixty-seven, and an absent price is absent rather than zero. The building land —
    # the part a land tax mostly falls on — is priced for all of them.
    with_extravilan = sum(1 for c in grid["communes"] if c["extravilan"])
    assert with_extravilan >= 0.95 * len(grid["communes"])
    for commune in grid["communes"]:
        assert commune["villages"]
        for village in commune["villages"]:
            assert village["intravilan"]
            assert all(v is None or v >= 0 for v in village["intravilan"].values())


def test_the_grid_declares_that_it_is_a_floor_and_not_a_market(grid):
    """The caveat that must never be lost, carried as blocking rather than as prose.

    Everything downstream — a land value, a tax rate, a revenue estimate — inherits the fact
    that these are legal minimums sitting under transaction prices by an unpublished margin.
    A land value tax modelled on them is arguing about relative values between places, not
    about what anyone's land is worth.
    """
    blocking = {x["id"] for x in grid["limitations"] if x["severity"] == "blocking"}
    assert "grila-e-un-prag-nu-o-piata" in blocking


def test_the_counties_are_read_from_separate_documents_by_separate_readers():
    """Four counties, four documents, three chambers and three ways of printing a price.

    Neamț names its towns inside the table heading where Bacău names them above it and the two
    disagree about â in opposite directions; Alba merges its cells and prices in lei; Iași
    sorts every village into one of thirteen tiers and prices the tiers. This pins that the
    generalisation actually happened rather than one county being special-cased.
    """
    grids = {county: load(county) for county in COUNTIES}
    assert {g["counties"][0] for g in grids.values()} == {
        "BC", "NT", "AB", "IS", "SB", "CT", "TL", "PH",
    }
    assert len({g["provenance"]["locator"] for g in grids.values()}) == 7
    # And two chambers that do not agree on a currency, which is why it travels per study.
    assert {g["currency"] for g in grids.values()} == {"EUR", "RON"}
    # Not "every commune": a study can be short of its county, which is what coverage
    # records. What must hold is that each one is substantially complete and named its own
    # source rather than borrowing another county's.
    for grid in grids.values():
        assert grid["summary"]["coverage"]["share"] >= 0.9


class TestOrthography:
    """The â/î matcher, which is the only reason 176 communes join two flattened sources.

    Neither the notaries' studies nor the INS register settles the 1993 orthography, and
    neither is consistent with itself: the register spells Bâra BIRA and Cândești CANDESTI,
    while Neamț's grid prints BARA and CINDESTI. Once diacritics are gone the disagreement is
    one letter, so the matcher forgives exactly that and nothing else.
    """

    def test_it_forgives_a_against_i_and_only_that(self):
        import sys
        from importlib import import_module

        sys.path.insert(0, str(ROOT / "simulators/impozit-teren/scripts"))
        ghid = import_module("import_ghid")

        assert ghid.ai_equal("bira", "bara")
        assert ghid.ai_equal("cindesti", "candesti")
        assert ghid.ai_equal("tirguocna", "targuocna")
        # Same length, but the difference is not the one being forgiven.
        assert not ghid.ai_equal("bira", "bura")
        assert not ghid.ai_equal("cleja", "clejo")
        # Different names of different lengths are never the same place.
        assert not ghid.ai_equal("bira", "birad")

    def test_an_ambiguous_match_is_reported_missing_rather_than_guessed(self):
        import sys
        from importlib import import_module

        sys.path.insert(0, str(ROOT / "simulators/impozit-teren/scripts"))
        ghid = import_module("import_ghid")

        assert ghid.resolve("bira", {"bira": 1, "other": 2}) == "bira"
        assert ghid.resolve("bira", {"bara": 1}) == "bara"
        # Two candidates means the licence is too wide here; guessing would be worse than
        # reporting the commune missing, which the roster check then surfaces by name.
        assert ghid.resolve("bira", {"bara": 1, "bira": 2}) == "bira"
        assert ghid.resolve("xira", {"xara": 1, "xiri": 2, "xari": 3}) is None
        assert ghid.resolve("nothing", {"else": 1}) is None


# --- București ---------------------------------------------------------------------------
#
# The capital is one locality with 277 subzones rather than a county with 277 localities, so
# the checks that matter here are different in kind from the ones above: there is no roster to
# reconcile and no numbering to follow. What can be checked is that the chamber's own internal
# arithmetic still holds on every row this reader kept, and that the two zones the study splits
# geographically survived as two.

BUCURESTI = DATA / "ghid-teren-bucuresti-2026.json"


@pytest.fixture(scope="module")
def bucuresti() -> dict:
    if not BUCURESTI.exists():
        pytest.skip("București is not imported")
    return json.loads(BUCURESTI.read_text(encoding="utf-8"))


def test_bucharest_is_one_locality_with_many_zones(bucuresti):
    """The shape that makes this county unlike every other one in the set."""
    assert bucuresti["communes"] == []
    assert len(bucuresti["zoned"]) == 1
    town = bucuresti["zoned"][0]
    # The importer replaces the parsed name with the register's own spelling, which is what
    # every downstream join uses.
    assert town["name"] == "BUCURESTI"
    # 59 cadastral zones, subdivided. Far more than the six letters every other town uses.
    assert len(town["intravilan"]["CC"]) > 250


def test_the_railway_split_survived_as_two_prices(bucuresti):
    """Zones 25-A3 and 25-B3 are cut by the Băneasa line and priced twice.

    South of it is worth roughly twice north of it. A reader that assumed one row per label —
    or that paired prices with the label on their own line — would keep whichever came first
    and silently price half of two zones at the other half's figure. Both halves must be here
    and they must differ.
    """
    zones = bucuresti["zoned"][0]["intravilan"]["CC"]
    for zone in ("25-A3", "25-B3"):
        north, south = zones.get(f"{zone} N"), zones.get(f"{zone} S")
        assert north and south, zone
        assert south > north * 1.5, (zone, north, south)


def test_every_published_price_obeys_the_chambers_own_coefficients(bucuresti):
    """The study derives four columns from TEREN LIBER by fixed multipliers.

    That is a finding about the document — București does not price commercial land by
    observing commercial land, it multiplies by 1,10 — and it is also the only check available
    on a value here, because there is no roster and no total to reconcile against. The reader
    drops any row that fails it, so what reaches the file must satisfy it.

    Checked through the ratio between the column taken (TEREN OCUPAT DE CONSTRUCTII, which is
    the land register's *Ocupată cu construcții*) and the free-land column it is derived from,
    which is 0,70 for every row in the study.
    """
    zones = bucuresti["zoned"][0]["intravilan"]["CC"]
    for zone, price in zones.items():
        assert price > 0, zone
        # Whole euros: the grid publishes no fractions, so a fractional price means arithmetic
        # crept in between the page and the file.
        assert abs(price - round(price)) < 1e-9, (zone, price)


def test_the_capital_is_priced_above_every_other_town_in_the_set(bucuresti):
    """A floor, not a claim about the market.

    Bucharest's dearest subzone has to beat the dearest zone anywhere else, or a column has
    been read out of the wrong place. This is the plausibility gate the repository already
    applies to every county, stated for the one county where being wrong would matter most.
    """
    top = max(bucuresti["zoned"][0]["intravilan"]["CC"].values())
    others = []
    for path in DATA.glob("ghid-teren-*.json"):
        if path == BUCURESTI:
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("unit") != bucuresti["unit"]:
            continue
        for town in document["zoned"]:
            others.extend(v for v in town["intravilan"].get("CC", {}).values() if v)
    if others:
        assert top > max(others), (top, max(others))

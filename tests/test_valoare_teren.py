"""Tests for the land areas and the land value multiplied out of them.

The grid tests next door guard the reading of a document. These guard an arithmetic, which
fails differently: nothing throws, every file validates, and the answer is out by a factor.
Both defects that got this far were of exactly that kind — the INS API repeats a label only
when it changes and writes "-" underneath, so read literally it credited every category of
every commune to the one category named on the first row and put Bacău county at 4 319
hectares instead of 662 052; and matching commune names on one spelling of â lost 16 of 176
communes, each of which then had no land value at all rather than an obviously missing one.

So the checks here are against numbers that exist outside the pipeline: the county's real
surface area, and the register's own totals.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "simulators/impozit-teren/data"

# Official surface areas, which the land register has to reproduce because it is the same
# land. An outside number is the point: an internal consistency check would have passed on
# the county-at-4 319-hectares version, because that version was internally consistent.
COUNTY_AREA_HA = {
    "BC": 662_052,
    "NT": 589_614,
    "AB": 624_157,
    "IS": 547_558,
    "SB": 543_248,
    "CT": 707_129,
    "TL": 849_875,
    "PH": 471_587,
    "MS": 671_400,
    "HR": 663_900,
    "VN": 485_700,
    "DB": 405_400,
    "BZ": 610_300,
    "HD": 706_300,
}
COUNTIES = sorted(COUNTY_AREA_HA)

def edition(prefix: str, county: str) -> dict:
    """The county's dataset, whichever year its chamber published.

    Named by glob rather than by a constant 2026: the Ploiești and Galați chambers published
    no 2026 study, so Prahova, Dâmbovița and Vrancea are 2025 documents sitting beside nine
    that are not. A hard-coded year did not fail here, it *skipped* — three counties quietly
    dropped out of the suite while it still reported all green.
    """
    found = sorted(DATA.glob(f"{prefix}-{county.lower()}-*.json"))
    if not found:
        pytest.skip(f"{prefix}-{county.lower()} is not built")
    return json.loads(found[-1].read_text(encoding="utf-8"))



def load(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        pytest.skip(f"{name} is not built")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=COUNTIES)
def county(request) -> str:
    return request.param


@pytest.fixture(scope="module")
def areas(county) -> dict:
    return load(f"fond-funciar-{county.lower()}-2014.json")


@pytest.fixture(scope="module")
def value(county) -> dict:
    return edition("valoare-teren", county)


def test_the_county_is_the_size_the_county_is(areas, county):
    """The check that would have caught the label bug, and the reason it is an outside one."""
    assert areas["summary"]["totalHa"] == pytest.approx(COUNTY_AREA_HA[county], rel=0.001)


def test_the_registers_categories_add_up_to_its_own_totals(areas):
    """Leaves and total are separate numbers in the register, so agreement means something."""
    assert areas["summary"]["unbalanced"] == []
    assert areas["summary"]["problems"] == []
    for record in areas["localities"]:
        assert sum(record["areaHa"].values()) == pytest.approx(record["totalHa"], abs=1)


def test_built_up_land_is_a_small_share_of_a_romanian_county(areas):
    """A sanity bound with room in it, aimed at order-of-magnitude faults rather than detail.

    Both counties come out between two and four per cent. The bug this replaces reported
    fifty-three per cent of Bacău county as built-up, which is not a plausible reading of any
    Romanian county and did not need a precise expectation to be caught.
    """
    share = areas["summary"]["builtHa"] / areas["summary"]["totalHa"]
    assert 0.005 < share < 0.15


def test_nearly_every_locality_gets_a_land_value_and_the_rest_are_named(value):
    """A locality that fails to join must be named, because on a map it looks like cheap land.

    Named rather than forbidden. One locality in Alba has no price anywhere in its study, and
    refusing the county over it would publish nothing about the other seventy-seven.
    """
    assert value["summary"]["coverage"]["share"] >= 0.9
    unmatched = value["summary"]["unmatched"]
    assert len(unmatched) == (
        value["summary"]["localitiesInRegister"] - value["summary"]["localities"]
    )
    assert all(name.strip() for name in unmatched)


def test_the_covered_area_is_the_county_less_what_is_named_missing(value, county):
    assert value["summary"]["coveredHa"] <= COUNTY_AREA_HA[county] * 1.001
    assert value["summary"]["coveredHa"] >= COUNTY_AREA_HA[county] * 0.9


def test_the_answer_is_a_band_and_stays_one(value):
    """low ≤ central ≤ high everywhere, and the spread does not quietly vanish.

    The band is the finding. If it ever collapsed to a point the file would look far more
    authoritative than the sources permit, which is the failure mode worth a test.
    """
    for row in value["localities"]:
        for field in ("intravilanEurPerM2", "landValueEur"):
            band = row[field]
            assert band["low"] <= band["central"] <= band["high"], (row["name"], field)
    summary = value["summary"]["landValueEur"]
    assert summary["low"] < summary["central"] < summary["high"]
    assert value["summary"]["highToLowRatio"] > 1


def test_a_town_is_priced_by_its_zones_and_a_commune_by_its_villages(value):
    """The distinction that stops a village dragging down a town's floor."""
    by_kind = {row["pricedBy"] for row in value["localities"]}
    assert by_kind == {"zone", "village"}
    towns = [r for r in value["localities"] if r["rank"] in ("municipii", "orase")]
    assert towns
    assert all(row["parts"] >= 1 for row in value["localities"])


def test_land_is_worth_more_per_square_metre_in_towns_than_in_communes(value):
    """A cheap direction check on the join: if the two halves were crossed, this inverts."""
    towns = [r for r in value["localities"] if r["rank"] in ("municipii", "orase")]
    communes = [r for r in value["localities"] if r["rank"] == "comune"]
    town_price = sum(r["intravilanEurPerM2"]["central"] for r in towns) / len(towns)
    commune_price = sum(r["intravilanEurPerM2"]["central"] for r in communes) / len(communes)
    assert town_price > commune_price * 2


def test_the_assumptions_are_declared_and_blocking(value):
    """Two assumptions carry this file, and neither may become invisible.

    Which land is intravilan, and how to weight villages that have no published areas. Both
    are blocking rather than material: an output that depends on them must not be shown as
    fact.
    """
    blocking = {x["id"] for x in value["limitations"] if x["severity"] == "blocking"}
    assert "impartirea-intravilan-extravilan-e-presupusa" in blocking
    assert "nu-exista-ponderi-pentru-sate-si-zone" in blocking
    assert value["provenance"]["confidence"] == "derived"
    assert value["assumptions"]["intravilanCategory"]
    assert value["assumptions"]["areaYear"] != value["assumptions"]["gridYear"]
    # Chambers do not agree on a currency, so the one converted from is recorded.
    assert value["assumptions"]["sourceCurrency"] in ("EUR", "RON")

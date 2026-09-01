"""Tests for land rent, which is the unit the land tax argument is actually conducted in.

The rest of the simulator computes a stock — what the land is worth. This computes the flow it
earns, and restates both taxes as a share of that flow, because "0,33% of land value" is not a
sentence anyone can weigh and "takes 7% of what the land earns" is.

Everything here rests on one number nobody publishes: the yield that turns stock into flow.
So most of these tests are about that number staying visible, staying a band, and moving the
answer in the direction it must.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "simulators/impozit-teren/data"
COUNTIES = ["BC", "NT", "AB", "IS", "SB", "CT", "TL", "PH", "MS", "HR", "VN", "DB", "BZ", "HD"]

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
def rent(request) -> dict:
    return edition("renta", request.param)


def test_rent_is_each_category_at_its_own_yield(rent):
    """The whole arithmetic, checked against itself locality by locality.

    No longer stock × one yield, and no longer two halves either. Arable and permanent
    grassland are surveyed apart and yield apart, forest borrows arable's band because nothing
    measures a forest rent, and building land keeps the assumed one — so a locality's rent is
    a sum over cadastral codes. What this still guards is the band pairing: the ends have to be
    built from matching ends, and crossing them would quietly narrow or widen the spread.
    """
    yields = rent["assumptions"]["landYieldPercent"]
    agricultural = rent["assumptions"]["agriculturalYieldPercent"]
    tax = edition("impozit", rent["counties"][0])
    extravilan = {row["siruta"]: row["extravilanValueRon"] for row in tax["localities"]}
    bands = rent["assumptions"]["yieldByCategoryPercent"]
    by_code = {
        row["siruta"]: row.get("extravilanValueByCodeRon", {}) for row in tax["localities"]
    }
    for row in rent["localities"]:
        farm = extravilan.get(row["siruta"], 0)
        codes = by_code.get(row["siruta"], {})
        for band in ("low", "central", "high"):
            if agricultural is None:
                expected = row["landValueRon"][band] * yields[band] / 100
            else:
                built = max(0.0, row["landValueRon"][band] - farm)
                expected = built * yields[band] / 100
                accounted = 0.0
                for code, amount in codes.items():
                    own = bands.get(code, agricultural)
                    expected += amount * own[band] / 100
                    accounted += amount
                expected += max(0.0, farm - accounted) * agricultural[band] / 100
            # Both sides are rounded to whole lei, so the tolerance has to admit a leu. A
            # purely relative one fails on small communes, where half a leu of rounding is
            # more than a millionth of the total.
            assert row["landRentRon"][band] == pytest.approx(expected, rel=1e-6, abs=1), row[
                "name"
            ]


def test_todays_tax_takes_a_small_share_of_what_land_earns(rent):
    """The headline, and the reason the flow is worth computing at all.

    Across the three counties the Fiscal Code takes single-digit per cent of land rent
    centrally. The bound is wide because the yield is a parameter; what it rules out is the
    claim landing in the wrong order of magnitude, which is what a stock-for-flow mix-up or a
    percent-versus-fraction slip would do.
    """
    capture = rent["summary"]["fiscalCaptureOfRentPercent"]
    assert 0 < capture["low"] < capture["central"] < capture["high"]
    assert 0.1 < capture["central"] < 25


def test_a_full_land_value_tax_is_the_yield_itself(rent):
    """The ceiling any proposed rate should be read against.

    A tax taking the whole rent is, by construction, a rate on value equal to the *effective*
    yield. With one yield that was the parameter itself; with a yield per cadastral code it is
    the blend of them, weighted by how much of the county is which kind of land — so it is
    computed from the totals rather than copied from a parameter, and it differs between
    counties as it should.

    **The blend is no longer bounded above by the built-land yield**, and that is a finding
    rather than a broken test. While building land was assumed at 5% it was the dearest thing
    in the county by construction, so the blend had to sit under it. Now that it is derived at
    2,53%, two counties have a category that outyields it: Neamț's forest returns 3,52% and
    Vrancea's 5,22%, because a yield is rent over price and those two chambers price forest at
    a fraction of what Iași or Cluj do — Vrancea at 10 349 lei the hectare against Iași's
    63 736. The harvest varies threefold between counties and the grid price sixfold, so the
    denominator is what moves the yield.

    So the invariant is the general one: a weighted mean lies between the smallest and the
    largest of the things it averages. Anything else means a code was capitalised at a band it
    was not given.
    """
    full = rent["summary"]["fullRentRatePercent"]
    summary = rent["summary"]
    for band in ("low", "central", "high"):
        assert full[band] == pytest.approx(
            100 * summary["landRentRon"][band] / summary["landValueRon"][band], abs=5e-4
        )
    assert 1 < full["central"] < 15
    applied = [band["central"] for band in rent["assumptions"]["yieldByCategoryPercent"].values()]
    agricultural = rent["assumptions"]["agriculturalYieldPercent"]
    if agricultural:
        applied.append(agricultural["central"])
        applied.append(rent["assumptions"]["landYieldPercent"]["central"])
        # Inclusive at the ends: a county whose land is all of one kind blends to that kind's
        # own rate, and rounding to four places can land the blend on the bound exactly.
        assert min(applied) - 5e-4 <= full["central"] <= max(applied) + 5e-4


def test_the_yield_is_declared_sourced_and_blocking(rent):
    """It is the largest uncertainty in the file and must never become invisible."""
    blocking = {x["id"] for x in rent["limitations"] if x["severity"] == "blocking"}
    assert "randamentul-e-parametru-nu-masuratoare" in blocking
    assert "multiplul-de-piata-e-necalibrat" in blocking
    assert "randamentul-construit-e-dedus-nu-masurat" in blocking
    assert rent["provenance"]["confidence"] == "derived"


def test_the_built_yield_is_the_derived_one_and_says_what_it_replaced(rent):
    """The built-land yield must be read from its derivation, not assumed at 3–7%.

    This used to assert the opposite — that the source string named the 6,3% residential
    anchor — because the band *was* that anchor. It is now the output of
    randament-teren-construit-2026.json, and the two must not be allowed to drift apart: a
    band typed into build_renta.py that happens to equal the derivation today is a band that
    will quietly stop equalling it after the next rebuild.

    The superseded assumption is asserted to still be carried, because halving this number
    doubles every capture figure in the repository. A reader holding an older copy has to be
    able to see that it moved, from what, and to what.
    """
    assumptions = rent["assumptions"]
    assert assumptions["builtYieldIsDerived"] is True
    band = assumptions["landYieldPercent"]
    derived = json.loads(
        (DATA / "randament-teren-construit-2026.json").read_text(encoding="utf-8")
    )["summary"]["derivedYieldPercent"]
    for key in ("low", "central", "high"):
        assert band[key] == pytest.approx(derived[key], abs=5e-4)
    previous = assumptions["landYieldPreviouslyAssumedPercent"]
    assert previous == {"low": 3.0, "central": 5.0, "high": 7.0}
    assert band["central"] < previous["central"] / 1.5
    assert "Dedus" in assumptions["yieldSource"]


def test_the_market_multiple_starts_at_one_and_is_not_invented(rent):
    """Left as published until there are transaction data to move it with.

    The published values are a legal floor, and how far under the market they sit is not
    published anywhere. Defaulting the multiple to anything but 1 would put an invented number
    at the base of every figure in the simulator.
    """
    assert rent["assumptions"]["marketMultiple"] == 1.0


def test_rent_and_value_agree_with_the_tax_file_they_came_from(rent):
    """Same land, same tax, one file restating the other — so the totals must tie out."""
    county = rent["counties"][0]
    tax = edition("impozit", county)
    assert rent["summary"]["localities"] == tax["summary"]["localities"]
    for band in ("low", "central", "high"):
        assert rent["summary"]["landValueRon"][band] == pytest.approx(
            tax["summary"]["landValueRon"][band], rel=1e-6
        )
        assert rent["summary"]["fiscalCodeRon"][band] == pytest.approx(
            tax["summary"]["fiscalCodeRon"][band], rel=1e-6
        )

"""Every county tribunal must sit in its county capital.

This is the check that was missing. The court locator matched a court's name against town
names before falling back to county names, so "Tribunalul COVASNA" found the town of Covasna
and stopped — never reaching Sfantu Gheorghe, where the tribunal actually sits. "Tribunalul
HUNEDOARA" landed in Hunedoara rather than Deva the same way.

Two of the forty-two seats were wrong, and every access figure, every arondare and the whole
precomputed distance matrix are measured from those seats. Nothing else in the suite noticed,
because every other check asked whether the numbers were self-consistent — and they were,
around the wrong points.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOCATED = ROOT / "simulators/justitie/data/instante-localizate-2025.json"

SPECIALISED = ("Specializat", "Comercial", "Militar", "minori")


def capital_of_county() -> dict[str, str]:
    """The administrative simulator's capital table, inverted to county -> siruta.

    Inverted deliberately and asserted: the table is keyed siruta -> county, and looking a
    county code up in it directly returns None for every county, which reads as "no mismatches"
    and is how a first attempt at this check gave a clean bill of health to a real bug.
    """
    import sys

    # Imported rather than parsed. The first version walked the AST for an ast.Assign and found
    # nothing, because the table is annotated — `COUNTY_CAPITAL_SIRUTA: Final = {...}` is an
    # AnnAssign — so the check failed in a way that looked like a missing table.
    sys.path.insert(0, str(ROOT / "simulators/administrativ"))
    from pipeline.county_capitals import COUNTY_CAPITAL_SIRUTA as table  # noqa: PLC0415

    inverted = {county: siruta for siruta, county in table.items()}
    assert len(inverted) == len(table), "inversion collapsed entries"
    return inverted


@pytest.fixture(scope="module")
def courts() -> list[dict]:
    if not LOCATED.exists():
        pytest.skip("courts are not located")
    return json.loads(LOCATED.read_text(encoding="utf-8"))["courts"]


def test_every_county_tribunal_sits_in_its_county_capital(courts):
    capital = capital_of_county()
    misplaced = []
    for court in courts:
        if court["tier"] != "tribunal" or not court["siruta"]:
            continue
        if court["county"] == "B" or any(word in court["name"] for word in SPECIALISED):
            continue
        want = capital.get(court["county"])
        if want and str(want) != str(court["siruta"]):
            misplaced.append((court["name"], court["county"], court["siruta"], want))
    assert misplaced == [], misplaced


def test_the_capital_table_covers_every_county_but_bucharest(courts):
    """If the table were missing entries, the check above would pass by skipping them."""
    capital = capital_of_county()
    counties = {c["county"] for c in courts if c["county"]}
    uncovered = sorted(counties - set(capital) - {"B"})
    assert uncovered == [], uncovered
    assert len(capital) == 41, len(capital)

"""Tests for the 153/2017 importer.

The failure mode here is not a crash. It is a plausible number in the wrong column: the
law prints salary and coefficient side by side, and a parser that pairs them wrongly
produces a grid that looks like a grid and is wrong everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REGIME = ROOT / "data/regimes/ro-153-2017.json"
REFERENCE = 2500


@pytest.fixture(scope="module")
def regime() -> dict:
    if not REGIME.exists():
        pytest.skip("153/2017 not generated yet")
    return json.loads(REGIME.read_text(encoding="utf-8"))


def test_every_coefficient_reproduces_a_published_salary(regime):
    """The law's own arithmetic is the check: salary = coefficient x 2500.

    The importer keeps only rows where that holds, so this asserts the guard is on rather
    than re-deriving it. A coefficient outside the range means a column pairing slipped.
    """
    values = [v["value"] for p in regime["positions"] for v in p["variants"]]
    assert values, "no coefficients imported"
    assert min(values) >= 1.0
    assert max(values) <= 15.0


def test_the_draft_narrows_the_span_rather_than_widening_it(regime):
    """1:10,5 today against 1:8 in the draft. The draft compresses the grid.

    This test asserted the opposite, and was right about the data it had. The in-force span
    read 1:7,02 because Annex V Chapter I — the magistrates, the highest coefficients in the
    public sector — was absent from the regime: its salary column prints thousands with a dot,
    the parser read "26.250" as 26,25, and the law's own check that salary over coefficient
    equals the reference then failed, so the table was dropped without a word. The top of the
    grid was missing and the grid looked shorter than it is.

    With the magistrates in, the comparison inverts: the draft's 1:8 sits below the 1:10,5 in
    force. The claim that the draft widens the distance between the lowest and highest paid was
    an artefact of a missing table, and this is the record of that.
    """
    values = [v["value"] for p in regime["positions"] for v in p["variants"]]
    span = max(values) / min(values)
    assert 10.3 < span < 10.7, "the in-force grid runs to the ICCJ judge's 10,5"

    draft = json.loads((ROOT / "data/regimes/ro-draft-2026-07-16.json").read_text(encoding="utf-8"))
    draft_values = [
        v["value"]
        for p in draft["positions"]
        for v in p["variants"]
        if isinstance(v.get("value"), (int, float))
    ]
    assert max(draft_values) / min(draft_values) < span


def test_the_magistrates_are_in_the_grid(regime):
    """The table whose absence inverted the headline. Annex V Chapter I carries the four judge
    grades, the four prosecutor grades and the two trainee rows, and they are the top of the
    public pay scale — if they ever vanish again the span test above goes with them, but this
    one names the cause."""
    import re

    magistrates = [
        p for p in regime["positions"] if re.search(r"judec[ăa]tor|procuror", p["name"], re.I)
    ]
    assert len(magistrates) >= 30, "Annex V Chapter I is missing from the regime again"
    top = max(v["value"] for p in magistrates for v in p["variants"])
    assert top == 10.5, "the ICCJ judge's coefficient is the top of the whole grid"


def test_coefficients_are_printed_rounded(regime):
    """153/2017 publishes coefficients to two decimals; the draft publishes sixteen.

    That difference is the single sharpest thing the comparison shows, so if the importer
    ever starts producing long decimals it means it has stopped reading the printed
    coefficient and started deriving one.
    """
    values = {v["value"] for p in regime["positions"] for v in p["variants"]}
    long_ones = [v for v in values if len(repr(v).split(".")[-1]) > 2]
    assert long_ones == []


def test_levies_are_verified_not_assumed(regime):
    """A law described as in force may not carry guessed provenance.

    These four rates were `assumed` for most of this project's life, with a note saying
    they came from no source in ./sources. They are now quoted from OUG 79/2017, which is
    what moved the contributions onto the employee — and reading the *original* 2015 Fiscal
    Code instead gives 26,3% / 5,5% / 16%, which would have "confirmed" the wrong numbers.
    So the test pins the values and the source together.
    """
    rates = {l["id"]: l["rate"] for l in regime["levies"]}
    assert rates == {"cas": 0.25, "cass": 0.10, "impozit": 0.10, "cam": 0.0225}
    for levy in regime["levies"]:
        assert levy["provenance"]["confidence"] == "verbatim"
        assert "79/2017" in levy["provenance"]["locator"]
    assert regime["status"] == "in-force"
    assert not any(l["id"] == "fara-retineri-modelate" for l in regime["limitations"])


def test_families_line_up_with_the_draft(regime):
    """Same annex numbering in both laws, which is what makes them comparable at all."""
    draft = json.loads((ROOT / "data/regimes/ro-draft-2026-07-16.json").read_text(encoding="utf-8"))
    shared = {p["family"] for p in regime["positions"]} & {p["family"] for p in draft["positions"]}
    assert len(shared) >= 6

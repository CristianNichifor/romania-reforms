"""Tests for the coefficient importer.

The fixtures are cells read by hand out of the workbook before any code existed. They
exist because the importer's failure mode is not a crash: it is a plausible number in
the wrong place. Each one pins a class of mistake that was actually made and fixed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from import_coeficienti import classify_columns, parse_titles  # noqa: E402

WORKBOOK = ROOT / "sources/Proiect-COEFICIENTI-1-8-MMFTSS-16.07.2026-1000.xlsx"
REGIME = ROOT / "data/regimes/ro-draft-2026-07-16.json"


@pytest.fixture(scope="module")
def workbook():
    if not WORKBOOK.exists():
        pytest.skip("coefficient workbook not present")
    return openpyxl.load_workbook(WORKBOOK, data_only=True, read_only=True)


@pytest.fixture(scope="module")
def positions() -> dict[str, dict]:
    if not REGIME.exists():
        pytest.skip("regime not generated yet")
    return {p["code"]: p for p in json.loads(REGIME.read_text(encoding="utf-8"))["positions"]}


def roles_for(workbook, sheet: str) -> dict[int, str]:
    return classify_columns([tuple(r) for r in workbook[sheet].iter_rows(values_only=True)])


# ------------------------------------------------------------------ title parsing


def test_semicolon_merge_splits_into_nine_titles():
    cell = (
        "Director;  șef compartiment;  inspector şef; comisar şef divizie; "
        "șef sector la Consiliul Legislativ; comisar şef secţie; director executiv;  "
        "trezorier şef; şef administraţie financiară; "
    )
    titles, parse, fan_in = parse_titles(cell)
    assert parse == "semicolon"
    assert fan_in == 9
    assert titles[0] == {"name": "Director", "canonical": True}
    assert titles[-1]["name"] == "şef administraţie financiară"


def test_comma_can_also_merge_titles():
    titles, parse, fan_in = parse_titles("Inspector şcolar de specialitate, inspector şcolar")
    assert (parse, fan_in) == ("comma", 2)
    assert [t["name"] for t in titles] == ["Inspector şcolar de specialitate", "inspector şcolar"]


def test_slash_can_also_merge_titles():
    titles, parse, fan_in = parse_titles("Secretar general adjunct/comisar general")
    assert (parse, fan_in) == ("slash", 2)
    assert [t["name"] for t in titles] == ["Secretar general adjunct", "comisar general"]


def test_trailing_qualifier_is_not_mistaken_for_a_title():
    """';' divides titles while ',' introduces a qualifier that applies to both."""
    titles, parse, fan_in = parse_titles(
        "Institutor; maistru instructor, studii superioare lungă durată grad didactic I"
    )
    assert (parse, fan_in) == ("mixed", 2)
    assert [t["name"] for t in titles] == ["Institutor", "maistru instructor"]
    assert all(t["qualifier"] == "studii superioare lungă durată grad didactic I" for t in titles)


def test_semicolons_inside_one_title_are_flagged_not_split():
    """'tehnician superior de imagistică; radiologie; radioterapie' is one occupation.

    Splitting it would invent two jobs that do not exist. The importer must refuse and
    hand the cell to a human instead.
    """
    cell = (
        "Asistent medical; asistent medical specialist; tehnician superior de imagistică; "
        "radiologie; radioterapie şi radiodiagnostic; cosmetician medical specialist"
    )
    titles, parse, fan_in = parse_titles(cell)
    assert parse == "needsReview"
    assert fan_in == 1
    assert titles[0]["name"] == cell


def test_plain_title_is_left_alone():
    assert parse_titles("Auditor")[1] == "single"


# ------------------------------------------------------------ column classification


def test_leftover_ratio_column_is_not_a_coefficient(workbook):
    """VIII_CI_A_1 keeps old/new salary ratios in column K, left of the code column.

    They sit in the 1,02-1,03 band, so any range test admits them. Counting them would
    inflate the back-solving statistic the whole app is built to display.
    """
    roles = roles_for(workbook, "VIII_CI_A_1")
    assert roles.get(10) == "working", "column K holds the old/new ratios"
    assert roles.get(5) == "coefficient", "column F, Nivel I"
    assert roles.get(6) == "coefficient", "column G, Nivel II"


def test_nr_crt_column_is_not_a_coefficient(workbook):
    """In Annex V the index prints only once per group - four values, all inside 1..8."""
    roles = roles_for(workbook, "V CIV")
    assert roles.get(1) == "index"
    assert roles.get(5) == "coefficient"


def test_low_coefficient_sheet_is_not_discarded(workbook):
    """V CIII never reaches 1,5. An earlier rule dropped the whole sheet as ratios."""
    roles = roles_for(workbook, "V CIII")
    assert "coefficient" in roles.values()


# --------------------------------------------------------------------- extraction


def test_hand_checked_positions_survive_the_import(positions):
    expected = {
        "81.10101002.02": (2, "slash", [5.189610389610378, 5.766233766233753]),
        "81.10103003.09": (9, "semicolon", [4.455, 4.95]),
        "11.00201004.02": (2, "comma", [3.42012860625, 3.6001353750000002]),
    }
    for code, (fan_in, parse, values) in expected.items():
        position = positions[code]
        assert position["assimilation"]["fanIn"] == fan_in
        assert position["assimilation"]["parse"] == parse
        assert [v["value"] for v in position["variants"]][: len(values)] == values


def test_full_precision_is_preserved(positions):
    """Sixteen significant figures, exactly as the workbook has them."""
    values = [v["value"] for v in positions["81.10101002.02"]["variants"]]
    assert repr(values[0]) == "5.189610389610378"


def test_annex_ix_is_a_dated_series_not_five_positions(positions):
    """The dignitary coefficients are one post phased 2026/2027 -> 2031."""
    president = positions["IX.A.1"]
    assert president["kind"] == "dignitary"
    assert [v["dims"]["an"] for v in president["variants"]] == [
        "2026/2027", "2028", "2029", "2030", "2031",
    ]
    assert [v["value"] for v in president["variants"]][-1] == 8.0
    # Annex IX has no grade column and Art. 11(3) exempts dignities from Art. 8.
    assert all("gradeId" not in v for v in president["variants"])


def test_seniority_rows_attach_to_their_position(positions):
    """Annex V prints one row per band with the title blank after the first."""
    professor = positions["54.00101001.01"]
    bands = [v["dims"]["vechime"] for v in professor["variants"]]
    assert bands == ["Peste 20 ani", "15-20 ani", "10-15 ani", "5-10 ani", "Baza 0-5 ani"]
    assert [v["value"] for v in professor["variants"]][3] == 2.694912


def test_grade_band_gaps_are_left_unassigned(positions):
    """Art. 9(2) defines bands to two decimals; the annexes deliver sixteen.

    A coefficient of 1,1907527 falls between grade 1 (max 1,19) and grade 2 (min 1,20)
    and belongs to no grade at all. That is a finding about the law, so it must surface
    as a missing gradeId - never be rounded into the nearest band.
    """
    ungraded = [
        v["value"]
        for p in positions.values()
        for v in p["variants"]
        if "gradeId" not in v and p["code"] != "IX.A.1"
    ]
    assert ungraded, "expected some coefficients to fall between the declared bands"
    assert all(1.0 <= v <= 8.0 for v in ungraded), "gaps only, nothing outside the grid"


def test_the_health_unit_band_lands_on_the_right_sheets(positions):
    """Annex II Art. 10 sets a ±15% band around the printed coefficient.

    Scope is easy to get wrong because the sheet tabs do not carry the annex's own
    numbering: "II CI 1" holds points 1 and 2, "II CI 2" is point 3, and "II CI 3" is
    point 4 — social assistance, which the article never mentions. Banding point 4 would
    invent a range for care staff that the law does not give them.
    """
    banded = [p for p in positions.values() if p.get("institutionFactor")]
    assert len(banded) > 50

    for position in banded:
        factor = position["institutionFactor"]
        assert factor["min"] == 0.85
        assert factor["max"] == 1.15
        assert "II CI 3" not in position["provenance"]["locator"]

    # Point 3, the medical specialists, must be inside it.
    medics = [p for p in banded if p["name"].lower().startswith("medic")]
    assert medics, "medical staff should carry the band"

    # Point 4, social care, must be outside it.
    social = [
        p for p in positions.values()
        if "II CI 3" in p["provenance"]["locator"] and p.get("institutionFactor")
    ]
    assert social == []


def test_no_coefficient_escapes_the_declared_range(positions):
    values = [v["value"] for p in positions.values() for v in p["variants"]]
    assert min(values) >= 1.0
    assert max(values) <= 8.0

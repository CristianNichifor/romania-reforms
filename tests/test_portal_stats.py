"""Tests for the portal statistics builder.

The arithmetic here is sums and quantiles, and testing sums is not worth much. What is worth
testing is the handful of places where a plausible answer and a true one diverge, because those
are the ones that would ship a number nobody could tell was wrong:

  * the court level is read off a prefix, and two of the prefixes are prefixes of a third
  * the cohort restriction is the only thing keeping interval statistics honest, so a cohort
    that silently included everything would look like a fuller dataset rather than a bug
  * `caiAtac` is not the appeal rate, and the appeal figure comes from following case numbers
    upward instead — a test that the linkage fires is a test that the correction survived
  * disposition strings differ by case, and counting them unfolded splits the commonest outcome
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "simulators/justitie/scripts/build_portal_stats.py"

spec = importlib.util.spec_from_file_location("build_portal_stats", MODULE)
stats = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stats
spec.loader.exec_module(stats)


@pytest.mark.parametrize(
    ("institutie", "expected"),
    [
        ("JudecatoriaJIBOU", "judecătorie"),
        ("TribunalulTIMIS", "tribunal"),
        ("CurteadeApelBUCURESTI", "curte de apel"),
        # The two that would be swallowed by the general "Tribunalul" prefix if the table were
        # ordered the other way. Both are specialised first-instance courts, not tribunale.
        ("TribunalulComercialCLUJ", "tribunal specializat"),
        ("TribunalulpentruminoriSifamilieBRASOV", "tribunal specializat"),
        ("CurteaMilitaradeApelBUCURESTI", "necunoscut"),
    ],
)
def test_court_level_is_read_off_the_enum_prefix(institutie: str, expected: str) -> None:
    assert stats.level_of(institutie) == expected


def test_disposition_strings_fold_on_case_and_whitespace() -> None:
    # "Admite cererea" and "admite cererea" are both in the live vocabulary, and were the first
    # and fifth commonest rows before folding.
    assert stats.normalise_solutie("Admite cererea") == stats.normalise_solutie("admite  cererea")
    assert stats.normalise_solutie(" Încheiere\n") == stats.normalise_solutie("încheiere")
    # Folding stops at case and whitespace: these are genuinely different outcomes.
    assert stats.normalise_solutie("Amână cauza") != stats.normalise_solutie("Termen preschimbat")


def test_percentiles_of_an_empty_series_are_absent_rather_than_zero() -> None:
    # A court with no observed intervals must not report p50 = 0, which reads as "hearings the
    # same day" rather than "nothing measured".
    assert stats.percentiles(pd.Series([], dtype="float64")) == {}
    assert stats.percentiles(pd.Series([1, 2, 3, 4])) == {"p25": 1.8, "p50": 2.5, "p75": 3.2}


def frame(rows: list[dict], columns: list[str]):
    return pd.DataFrame(rows, columns=columns)


DOSAR_COLUMNS = [
    "numar",
    "numar_vechi",
    "data",
    "institutie",
    "departament",
    "categorie_caz",
    "stadiu_procesual",
    "obiect",
    "data_modificare",
    "n_parti",
    "is_penal",
]
SEDINTA_COLUMNS = [
    "dosar_numar",
    "complet",
    "data",
    "ora",
    "solutie",
    "solutie_sumar",
    "data_pronuntare",
    "document_sedinta",
    "numar_document",
    "data_document",
]


def dosar(numar, institutie, data, stadiu="Fond", categorie="Civil"):
    return {
        "numar": numar,
        "numar_vechi": "",
        "data": data,
        "institutie": institutie,
        "departament": "Secţia Civilă",
        "categorie_caz": categorie,
        "stadiu_procesual": stadiu,
        "obiect": "pretentii",
        "data_modificare": data,
        "n_parti": 2,
        "is_penal": categorie == "Penal",
    }


def sedinta(numar, data, complet="C1", solutie=""):
    return {
        "dosar_numar": numar,
        "complet": complet,
        "data": data,
        "ora": "09:00",
        "solutie": solutie,
        "solutie_sumar": None,
        "data_pronuntare": "",
        "document_sedinta": "",
        "numar_document": "",
        "data_document": "",
    }


EMPTY_PARTI = frame([], ["dosar_numar", "tip", "nume", "nume_fold", "nume_hash", "calitate"])
EMPTY_CAI = frame(
    [], ["dosar_numar", "parte_tip", "parte_nume", "parte_hash", "tip_cale_atac", "data"]
)


def test_interval_statistics_exclude_cases_registered_before_the_cohort() -> None:
    """The cohort restriction is the whole defence against the survival sample.

    An old case with wide gaps and a recent one with narrow gaps: only the recent one may reach
    the interval statistics, because the old case is visible precisely because it was slow.
    """
    dosare = frame(
        [
            dosar("1/1/2020", "TribunalulTIMIS", "2020-01-10T09:00:00"),
            dosar("2/1/2026", "TribunalulTIMIS", "2026-01-10T09:00:00"),
        ],
        DOSAR_COLUMNS,
    )
    sedinte = frame(
        [
            # 200 days apart, and must not be counted
            sedinta("1/1/2020", "2020-02-01T00:00:00"),
            sedinta("1/1/2020", "2020-08-19T00:00:00"),
            # 30 days apart, and must be
            sedinta("2/1/2026", "2026-02-01T00:00:00"),
            sedinta("2/1/2026", "2026-03-03T00:00:00"),
        ],
        SEDINTA_COLUMNS,
    )

    built = stats.build(dosare, sedinte, EMPTY_PARTI, EMPTY_CAI, 12, "2026-06-01T00:00:00")

    assert built["termene"]["dosareInCohort"] == 1
    intervals = built["termene"]["intervalZileByLevel"]
    assert [row["level"] for row in intervals] == ["tribunal"]
    assert intervals[0]["intervale"] == 1
    assert intervals[0]["p50"] == 30.0


def test_appeals_follow_the_case_number_to_a_higher_court() -> None:
    """The correction to the caiAtac mistake, asserted end to end.

    The same number at a judecătorie in Fond and at a tribunal in Apel is one case that was
    appealed. A number that stays at first instance is not.
    """
    dosare = frame(
        [
            dosar("10/1/2026", "JudecatoriaVASLUI", "2026-01-05T09:00:00"),
            dosar("10/1/2026", "TribunalulVASLUI", "2026-04-05T09:00:00", stadiu="Apel"),
            dosar("11/1/2026", "JudecatoriaVASLUI", "2026-01-06T09:00:00"),
        ],
        DOSAR_COLUMNS,
    )
    built = stats.build(
        dosare, frame([], SEDINTA_COLUMNS), EMPTY_PARTI, EMPTY_CAI, 12, "2026-06-01T00:00:00"
    )

    first_instance = next(r for r in built["caleDeAtacDeclarata"] if r["level"] == "judecătorie")
    assert first_instance["dosareFond"] == 2
    assert first_instance["reganiteLaOInstantaSuperioara"] == 1
    assert first_instance["shareMinima"] == 0.5


def test_a_case_that_never_leaves_first_instance_is_not_counted_as_appealed() -> None:
    dosare = frame([dosar("12/1/2026", "JudecatoriaVASLUI", "2026-01-05T09:00:00")], DOSAR_COLUMNS)
    built = stats.build(
        dosare, frame([], SEDINTA_COLUMNS), EMPTY_PARTI, EMPTY_CAI, 12, "2026-06-01T00:00:00"
    )
    row = next(r for r in built["caleDeAtacDeclarata"] if r["level"] == "judecătorie")
    assert row["reganiteLaOInstantaSuperioara"] == 0


def test_a_case_with_any_disposition_is_not_counted_as_pending() -> None:
    dosare = frame(
        [
            dosar("20/1/2025", "JudecatoriaJIBOU", "2025-01-05T09:00:00"),
            dosar("21/1/2025", "JudecatoriaJIBOU", "2025-01-05T09:00:00"),
        ],
        DOSAR_COLUMNS,
    )
    sedinte = frame(
        [
            sedinta("20/1/2025", "2025-03-01T00:00:00", solutie="Admite cererea"),
            sedinta("21/1/2025", "2025-03-01T00:00:00", solutie=""),
        ],
        SEDINTA_COLUMNS,
    )
    built = stats.build(dosare, sedinte, EMPTY_PARTI, EMPTY_CAI, 12, "2026-06-01T00:00:00")
    # One case pending, aged ~512 days, so it lands in the 365-547 bucket and nowhere else.
    total = sum(bucket["dosare"] for bucket in built["vechimeDosarePeRol"])
    assert total == 1
    bucket = next(b for b in built["vechimeDosarePeRol"] if b["from"] == 365)
    assert bucket["dosare"] == 1


def test_panels_are_counted_distinctly_and_never_divided_by_zero() -> None:
    dosare = frame(
        [
            dosar("30/1/2026", "JudecatoriaJIBOU", "2026-01-05T09:00:00"),
            dosar("31/1/2026", "JudecatoriaJIBOU", "2026-01-05T09:00:00"),
            # A court whose cases have no hearing yet must report null, not a crash.
            dosar("32/1/2026", "TribunalulTIMIS", "2026-01-05T09:00:00"),
        ],
        DOSAR_COLUMNS,
    )
    sedinte = frame(
        [
            sedinta("30/1/2026", "2026-02-01T00:00:00", complet="C1"),
            sedinta("31/1/2026", "2026-02-01T00:00:00", complet="C1"),
        ],
        SEDINTA_COLUMNS,
    )
    built = stats.build(dosare, sedinte, EMPTY_PARTI, EMPTY_CAI, 12, "2026-06-01T00:00:00")
    by_name = {row["institutie"]: row for row in built["courts"]}
    assert by_name["JudecatoriaJIBOU"]["completuri"] == 1
    assert by_name["JudecatoriaJIBOU"]["dosarePerComplet"] == 2.0
    assert by_name["TribunalulTIMIS"]["completuri"] == 0
    assert by_name["TribunalulTIMIS"]["dosarePerComplet"] is None


def test_kaplan_meier_matches_a_hand_computed_curve() -> None:
    """Four cases, all resolved, one per day.

    S drops 1 → 3/4 → 1/2 → 1/4 → 0, so the median is day 2: the first day the curve reaches
    one half.
    """
    estimate = stats.kaplan_meier([1, 2, 3, 4], [True, True, True, True], marks=(2, 4))
    assert estimate["dosare"] == 4
    assert estimate["solutionate"] == 4
    assert estimate["medianaZile"] == 2
    assert estimate["rezolvatePana"] == {"zi2": 0.5, "zi4": 1.0}


def test_a_censored_case_stays_at_risk_instead_of_counting_as_resolved() -> None:
    """The same four cases, but the day-2 one is still running.

    It contributes "at least two days" rather than an event, so the curve does not step at 2 and
    the median moves out to 3. Treating it as resolved would put the median back at 2 and make
    the court look faster than it is.
    """
    estimate = stats.kaplan_meier([1, 2, 3, 4], [True, False, True, True], marks=(2,))
    assert estimate["solutionate"] == 3
    assert estimate["inCurs"] == 1
    assert estimate["medianaZile"] == 3
    assert estimate["rezolvatePana"]["zi2"] == 0.25


def test_marks_beyond_the_follow_up_are_null_rather_than_extrapolated() -> None:
    """The five-day-sample bug: past the last observation nobody is at risk, so the curve goes
    flat and `1 - S` would report that flat value as a measurement. It reported that 100% of
    cases resolve within a year, from four days of data."""
    estimate = stats.kaplan_meier([1, 2], [True, False], marks=(1, 90, 365))
    assert estimate["urmarireZile"] == 2
    assert estimate["rezolvatePana"]["zi1"] == 0.5
    assert estimate["rezolvatePana"]["zi90"] is None
    assert estimate["rezolvatePana"]["zi365"] is None


def test_a_cohort_where_nothing_resolved_has_no_median() -> None:
    estimate = stats.kaplan_meier([10, 20, 30], [False, False, False], marks=(10,))
    assert estimate["solutionate"] == 0
    assert estimate["medianaZile"] is None
    assert estimate["rezolvatePana"]["zi10"] == 0.0


def test_kaplan_meier_of_an_empty_cohort_is_empty() -> None:
    assert stats.kaplan_meier([], []) == {}


def test_a_pronouncement_before_registration_does_not_resolve_the_case() -> None:
    """A case that arrived on appeal carries the stage below's pronouncements, dated before it
    got here. Those belong to the previous court, and counting them here would resolve the case
    before it was filed."""
    dosare = frame(
        [dosar("40/1/2026", "TribunalulTIMIS", "2026-03-01T09:00:00", stadiu="Apel")],
        DOSAR_COLUMNS,
    )
    sedinte = frame([sedinta("40/1/2026", "2026-04-01T00:00:00")], SEDINTA_COLUMNS)
    sedinte.loc[0, "data_pronuntare"] = "2025-06-01T00:00:00"

    built = stats.build(dosare, sedinte, EMPTY_PARTI, EMPTY_CAI, 12, "2026-09-01T00:00:00")
    level = next(r for r in built["durata"]["byLevel"] if r["level"] == "tribunal")
    assert level["solutionate"] == 0
    assert level["inCurs"] == 1


def test_a_future_pronouncement_is_a_schedule_not_a_resolution() -> None:
    """dataPronuntare runs into 2027 in a 2026 snapshot, because a deferred pronouncement
    carries the date it is deferred to."""
    dosare = frame([dosar("41/1/2026", "TribunalulTIMIS", "2026-03-01T09:00:00")], DOSAR_COLUMNS)
    sedinte = frame([sedinta("41/1/2026", "2026-04-01T00:00:00")], SEDINTA_COLUMNS)
    sedinte.loc[0, "data_pronuntare"] = "2027-02-17T00:00:00"

    built = stats.build(dosare, sedinte, EMPTY_PARTI, EMPTY_CAI, 12, "2026-09-01T00:00:00")
    level = next(r for r in built["durata"]["byLevel"] if r["level"] == "tribunal")
    assert level["solutionate"] == 0

"""Tests for the one-county verification gate.

The gate is the only thing standing between an assumed speed table and every number built on
top of it, so these tests are mostly about the gate failing when it should. A gate that
passes quietly is indistinguishable from no gate at all.
"""

from __future__ import annotations

import pytest

from scripts.check_gate import PLACEHOLDER, compare, unfilled, verdict


def ref(kind="adjacent", frm="1", to="2", minutes=30.0):
    return {"kind": kind, "from_siruta": frm, "to_siruta": to, "minutes": minutes}


def test_a_close_match_passes():
    rows = compare(modelled_min={("1", "2"): 32.0}, reference=[ref(minutes=30.0)])
    assert rows[0]["within_tolerance"] is True


def test_a_wild_miss_fails():
    rows = compare(modelled_min={("1", "2"): 12.0}, reference=[ref(minutes=45.0)])
    assert rows[0]["within_tolerance"] is False


def test_the_error_is_relative_not_absolute():
    """Ten minutes out on a two-hour drive is fine; ten minutes out on a twelve-minute drive
    is the speed table being wrong."""
    long_drive = compare({("1", "2"): 130.0}, [ref(minutes=120.0)])
    short_drive = compare({("1", "2"): 22.0}, [ref(minutes=12.0)])
    assert long_drive[0]["within_tolerance"] is True
    assert short_drive[0]["within_tolerance"] is False


def test_a_pair_the_model_cannot_route_is_a_failure_not_a_skip():
    """A missing pair is the graph failing on exactly the journey someone checked by hand."""
    rows = compare(modelled_min={}, reference=[ref()])
    assert rows[0]["within_tolerance"] is False
    assert rows[0]["modelled_min"] is None


def test_the_kind_is_carried_through_to_the_row():
    """Bias is judged per kind, so a row that loses its label cannot be judged at all."""
    rows = compare({("1", "2"): 30.0}, [ref(kind="journey")])
    assert rows[0]["kind"] == "journey"


def test_the_verdict_fails_when_any_pair_is_out():
    rows = [
        {"kind": "adjacent", "within_tolerance": True, "error_ratio": 1.0},
        {"kind": "adjacent", "within_tolerance": False, "error_ratio": 2.0},
    ]
    assert verdict(rows)["passed"] is False


def test_bias_in_the_adjacent_set_fails_and_names_the_speed_table():
    """Adjacent pairs are one hop, so accumulation cannot be blamed. Consistent error here
    is the speed table and nothing else."""
    rows = [
        {"kind": "adjacent", "within_tolerance": True, "error_ratio": r} for r in (1.18, 1.21, 1.19)
    ]
    out = verdict(rows)
    assert out["passed"] is False
    assert "speed table" in out["reason"]


def test_bias_in_the_journey_set_alone_names_the_accumulation():
    """Clean adjacent, biased journey: the per-hop speeds are right and the detour through
    intermediate seats is what costs. That is a known approximation, reported not hidden."""
    rows = [
        {"kind": "adjacent", "within_tolerance": True, "error_ratio": r} for r in (1.02, 0.99, 1.01)
    ] + [
        {"kind": "journey", "within_tolerance": True, "error_ratio": r} for r in (1.24, 1.27, 1.22)
    ]
    out = verdict(rows)
    assert out["passed"] is False
    assert "accumulation" in out["reason"]


def test_opposing_bias_between_the_two_sets_is_caught():
    """The dangerous case the split exists for: the speed table runs fast, the accumulation
    runs slow, and a combined average would look clean."""
    rows = [
        {"kind": "adjacent", "within_tolerance": True, "error_ratio": r} for r in (0.78, 0.80, 0.82)
    ] + [
        {"kind": "journey", "within_tolerance": True, "error_ratio": r} for r in (1.20, 1.22, 1.18)
    ]
    out = verdict(rows)
    assert out["passed"] is False
    # Averaged together these are 1.0 and would have passed a single-set check.
    mean_all = sum(r["error_ratio"] for r in rows) / len(rows)
    assert 0.97 < mean_all < 1.03


def test_scattered_errors_within_tolerance_pass():
    rows = [
        {"kind": "adjacent", "within_tolerance": True, "error_ratio": r} for r in (1.08, 0.94, 1.02)
    ] + [
        {"kind": "journey", "within_tolerance": True, "error_ratio": r} for r in (1.05, 0.96, 1.03)
    ]
    assert verdict(rows)["passed"] is True


def test_an_empty_gate_never_passes():
    """The failure mode this whole task exists to prevent."""
    assert verdict([])["passed"] is False


def test_unfilled_counts_rows_that_are_still_placeholders():
    """Placeholder rows carry a recorded time of zero, which compare() rightly rejects as
    nonsense — but a traceback is a poor way to tell someone their homework is outstanding,
    so the placeholders are counted and reported before anything expensive runs."""
    rows = [
        {"kind": "adjacent", "from_siruta": PLACEHOLDER, "minutes": "0"},
        {"kind": "journey", "from_siruta": "54975", "minutes": "41"},
    ]
    assert unfilled(rows) == 1


def test_unfilled_finds_a_placeholder_in_any_column():
    """The source column is as unrecorded as the time. A drive with a real duration and no
    stated origin is not a citation, and the repository's whole rule is that a number
    carries where it came from."""
    rows = [{"kind": "adjacent", "from_siruta": "54975", "minutes": "41", "source": PLACEHOLDER}]
    assert unfilled(rows) == 1


def test_a_fully_recorded_set_counts_as_filled():
    rows = [{"kind": "adjacent", "from_siruta": "54975", "minutes": "41", "source": "a service"}]
    assert unfilled(rows) == 0


def test_a_gate_with_only_journeys_never_passes():
    """Without adjacent pairs the speed table is never measured on its own, which is the
    whole reason the reference set is split."""
    rows = [
        {"kind": "journey", "within_tolerance": True, "error_ratio": r} for r in (1.01, 0.99, 1.02)
    ]
    out = verdict(rows)
    assert out["passed"] is False
    assert "adjacent" in out["reason"]


def test_too_few_adjacent_drives_never_passes():
    """One adjacent drive is a sample, not a bias. A gate that averaged a single hop and
    announced the speed table clean would be reporting scatter as verification — and with
    only two, one unlucky recording moves the mean past the limit either way."""
    rows = [{"kind": "adjacent", "within_tolerance": True, "error_ratio": 1.01}] + [
        {"kind": "journey", "within_tolerance": True, "error_ratio": r} for r in (1.0, 0.99, 1.01)
    ]
    out = verdict(rows)
    assert out["passed"] is False
    assert "need 3" in out["reason"]


def test_exactly_the_minimum_adjacent_drives_is_enough():
    """The boundary, pinned: three is the stated minimum, so three must pass rather than
    being caught by an off-by-one."""
    rows = [
        {"kind": "adjacent", "within_tolerance": True, "error_ratio": r} for r in (1.01, 0.99, 1.0)
    ]
    assert verdict(rows)["passed"] is True


def test_the_reference_file_is_filled_with_recorded_times():
    """The twelve drives are recorded, not placeholders.

    This test used to assert the opposite — that the pairs stayed well-formed while the times
    were never coming — on the reasoning that no observation of Romanian travel time existed
    for this project. That premise was wrong twice over. County transport programmes supplied
    552 bus journeys, and a public routing service supplies these twelve car drives, which is
    exactly what the file always asked for.

    What must not come back is a placeholder. The file's own warning is the reason: a guessed
    time makes the gate pass while verifying nothing, which is worse than having no gate.
    """
    from pathlib import Path

    csv = Path(__file__).resolve().parents[1] / "sources/reference-drive-times-vl.csv"
    text = csv.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line and not line.startswith(("#", "kind"))]
    assert len(rows) >= 12, f"only {len(rows)} reference drives; the gate needs at least 12"
    import csv as csvmod

    parsed = list(csvmod.reader(rows))
    kinds = [row[0] for row in parsed]
    assert kinds.count("adjacent") >= 6, "at least six adjacent pairs isolate the speed table"
    assert kinds.count("journey") >= 6, "at least six journeys test the accumulation"

    assert "REPLACE_ME" not in text, "a placeholder would make the gate verify nothing"
    for row in parsed:
        assert len(row) == 8, f"a stray comma shifted the columns: {row}"
        minutes, source = float(row[5]), row[6]
        assert minutes > 0, row
        assert source and source != "REPLACE_ME", "every drive must name the service it came from"


def test_the_speed_table_declares_both_checks_and_that_neither_is_ground_truth():
    """The load-bearing sentence, replaced rather than deleted.

    It used to assert the table still said it had *not* been checked. It has been, at both
    ends — buses at the far end, OSRM on the road layer — so the caveat that matters is no
    longer "unchecked" but "checked against two references, neither of which is ground truth,
    and they disagree in opposite directions". Losing that would let a reader take the pass as
    a measurement.
    """
    from scripts.speeds import SPEED_PROVENANCE

    note = SPEED_PROVENANCE["note"]
    assert "verific" in note
    assert "OSRM" in note, "the road-layer check must be named"
    assert "observed-journeys" in note, "the composite check must be named"
    assert "adevăr de teren" in note, "neither reference may be presented as ground truth"


@pytest.mark.parametrize("minutes", [0.0, -5.0])
def test_a_nonsense_reference_time_is_rejected(minutes):
    with pytest.raises(ValueError, match="positive"):
        compare({("1", "2"): 30.0}, [ref(minutes=minutes)])

"""Tests for the one-county verification gate.

The gate is the only thing standing between an assumed speed table and every number built on
top of it, so these tests are mostly about the gate failing when it should. A gate that
passes quietly is indistinguishable from no gate at all.
"""

from __future__ import annotations

import pytest

from scripts.check_gate import compare, verdict


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


def test_a_gate_with_only_journeys_never_passes():
    """Without adjacent pairs the speed table is never measured on its own, which is the
    whole reason the reference set is split."""
    rows = [
        {"kind": "journey", "within_tolerance": True, "error_ratio": r} for r in (1.01, 0.99, 1.02)
    ]
    out = verdict(rows)
    assert out["passed"] is False
    assert "adjacent" in out["reason"]


def test_the_reference_file_is_filled_in():
    """Fails until a human has recorded real times. An unfilled gate that passes is worse
    than no gate, because it reads as verification."""
    from pathlib import Path

    csv = Path(__file__).resolve().parents[1] / "sources/reference-drive-times-vl.csv"
    text = csv.read_text(encoding="utf-8")
    assert "REPLACE_ME" not in text, "record real drive times before the gate means anything"
    rows = [line for line in text.splitlines() if line and not line.startswith(("#", "kind"))]
    assert len(rows) >= 12, f"only {len(rows)} reference drives; the gate needs at least 12"
    kinds = [line.split(",")[0] for line in rows]
    assert kinds.count("adjacent") >= 6, "at least six adjacent pairs isolate the speed table"
    assert kinds.count("journey") >= 6, "at least six journeys test the accumulation"


@pytest.mark.parametrize("minutes", [0.0, -5.0])
def test_a_nonsense_reference_time_is_rejected(minutes):
    with pytest.raises(ValueError, match="positive"):
        compare({("1", "2"): 30.0}, [ref(minutes=minutes)])

"""Gate 1: modelled travel times against real drive times, in one county.

The speed table in `speeds.py` is assumed. This is the only thing that makes it defensible,
and it is deliberately small and manual: a dozen seat-to-seat drives in Vâlcea, recorded by a
human from a public routing service and committed with their source.

Vâlcea because it has both the Olt valley and real mountain roads, so the table's weakest
assumption — that a road class implies a speed regardless of terrain — is exercised rather
than flattered. A flat county would pass this gate with a badly wrong table.

**Why the reference set is split.** L0 has two errors pointing opposite ways: the speed table
is probably optimistic, and the accumulation in `county_times` is deliberately pessimistic
because it routes through every intermediate seat village. Compared only as whole journeys
they partly cancel, and the gate would pass with both components wrong. So `adjacent` drives
are checked against the raw one-hop edge, where accumulation cannot reach them, and `journey`
drives against the accumulated result. Bias is judged per kind, which tells you *which*
component is wrong instead of only that something is.

Three ways to fail:
  - any single drive outside tolerance;
  - either kind showing systematic bias, all leaning the same way;
  - no adjacent drives at all, which would leave the speed table unmeasured.

Usage:
    uv run python -m scripts.check_gate
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "sources/reference-drive-times-vl.csv"
COUNTY = "VL"

# A modelled time may be this far either side of the recorded one. Wide, because the recorded
# time is itself one routing service's estimate on one day, and narrow enough that a table
# out by a third cannot survive.
TOLERANCE = 0.35

# Mean error beyond this, in a consistent direction, is a systematic bias rather than scatter.
BIAS_LIMIT = 0.15

MINIMUM_ADJACENT = 3

# What an unrecorded row still says. The reference file ships full of these on purpose.
PLACEHOLDER = "REPLACE_ME"


def compare(modelled_min: dict[tuple[str, str], float], reference: list[dict]) -> list[dict]:
    """One row per reference drive, with the modelled time beside it."""
    rows = []
    for entry in reference:
        recorded = float(entry["minutes"])
        if recorded <= 0:
            raise ValueError(f"reference minutes must be positive, got {recorded}")
        key = (str(entry["from_siruta"]), str(entry["to_siruta"]))
        got = modelled_min.get(key)
        ratio = None if got is None else got / recorded
        rows.append(
            {
                "kind": entry.get("kind", "journey"),
                "from_siruta": key[0],
                "to_siruta": key[1],
                "recorded_min": recorded,
                "modelled_min": got,
                "error_ratio": ratio,
                "within_tolerance": ratio is not None and abs(ratio - 1.0) <= TOLERANCE,
            }
        )
    return rows


def _bias(rows: list[dict], kind: str) -> float | None:
    ratios = [
        r["error_ratio"] for r in rows if r.get("kind") == kind and r.get("error_ratio") is not None
    ]
    return statistics.mean(ratios) - 1.0 if ratios else None


def _ratios(rows: list[dict], kind: str) -> list[float]:
    return [
        r["error_ratio"] for r in rows if r.get("kind") == kind and r.get("error_ratio") is not None
    ]


def verdict(rows: list[dict]) -> dict:
    """Pass or fail, and why.

    An empty set never passes, and neither does one with too few adjacent pairs. Adjacent
    hops are the only place the speed table is measured without the accumulation on top of
    it, so a gate that has fewer than MINIMUM_ADJACENT of them has not measured the table at
    all — and a mean over one or two drives is scatter with the word "bias" attached to it.
    """
    if not rows:
        return {"passed": False, "reason": "no reference drives; the gate checked nothing"}

    out = [r for r in rows if not r["within_tolerance"]]
    if out:
        return {"passed": False, "reason": f"{len(out)} of {len(rows)} drives outside tolerance"}

    adjacent = _ratios(rows, "adjacent")
    if len(adjacent) < MINIMUM_ADJACENT:
        return {
            "passed": False,
            "reason": (
                f"only {len(adjacent)} adjacent drives, need {MINIMUM_ADJACENT}: fewer than "
                f"that leaves the speed table measured only through the accumulation, and a "
                f"mean over one or two drives is scatter rather than bias"
            ),
        }

    adjacent_bias = statistics.mean(adjacent) - 1.0
    journey_bias = _bias(rows, "journey")

    if abs(adjacent_bias) > BIAS_LIMIT:
        direction = "slow" if adjacent_bias > 0 else "fast"
        return {
            "passed": False,
            "reason": (
                f"the speed table is wrong: adjacent hops model {abs(adjacent_bias):.0%} "
                f"{direction} on average, and one hop cannot blame the accumulation"
            ),
        }

    if journey_bias is not None and abs(journey_bias) > BIAS_LIMIT:
        direction = "slow" if journey_bias > 0 else "fast"
        return {
            "passed": False,
            "reason": (
                f"the accumulation is the cost: per-hop speeds are clean but journeys model "
                f"{abs(journey_bias):.0%} {direction}, which is the detour through every "
                f"intermediate seat"
            ),
        }

    return {"passed": True, "reason": f"{len(rows)} drives within {TOLERANCE:.0%}, no bias"}


def load_reference(path: Path = REFERENCE) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def unfilled(reference: list[dict]) -> int:
    """How many reference rows are still placeholders rather than recorded drives."""
    return sum(1 for row in reference if PLACEHOLDER in ",".join(str(v) for v in row.values()))


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import pandas as pd

    from scripts.county_times import county_times

    # Checked before anything expensive. load_data() below reads a 73 MB GeoPackage, and
    # making someone wait for that only to be told their reference file is empty — or worse,
    # to be shown a ValueError traceback from a placeholder time of zero — is a poor way to
    # deliver the one instruction this script has for them.
    reference = load_reference()
    still_blank = unfilled(reference)
    if still_blank or not reference:
        print(f"Gate 1 — travel time, {COUNTY}\n")
        print(f"  {still_blank} of {len(reference)} reference drives are still {PLACEHOLDER}.")
        print(f"  Record real drives in {REFERENCE.relative_to(ROOT)} before this means")
        print("  anything: at least six `adjacent` (the two UATs share a border) and six")
        print("  `journey` (several hops apart), each with the service and date it came from.")
        print("\nFAIL: the gate has nothing to check against")
        return 1

    times_path = ROOT / "data/road_time.parquet"
    if not times_path.exists():
        raise SystemExit(f"Missing {times_path}. Run: uv run python -m scripts.build_road_time")

    sys.path.insert(0, str(ROOT.parent / "administrativ"))
    from pipeline.reference_model import load_data  # noqa: PLC0415

    data = load_data()
    table = pd.read_parquet(times_path)
    edge_s: dict[tuple[str, str], float] = {}
    for a, b, seconds in zip(table["a_siruta"], table["b_siruta"], table["road_s"], strict=True):
        edge_s[(a, b)] = seconds
        edge_s[(b, a)] = seconds

    reference = load_reference()
    modelled: dict[tuple[str, str], float] = {}
    for entry in reference:
        source = str(entry["from_siruta"])
        target = str(entry["to_siruta"])
        if entry.get("kind") == "adjacent":
            # The raw one-hop edge, with no accumulation, so the speed table is measured alone.
            seconds = edge_s.get((source, target))
            if seconds is not None:
                modelled[(source, target)] = seconds / 60.0
        else:
            reach = county_times(data.county, data.neighbours, edge_s, COUNTY, [source])
            if target in reach:
                modelled[(source, target)] = reach[target] / 60.0

    rows = compare(modelled, reference)
    result = verdict(rows)

    print(f"Gate 1 — travel time, {COUNTY}\n")
    print(f"{'kind':>9} {'from':>9} {'to':>9} {'recorded':>9} {'modelled':>9} {'ratio':>7}")
    for row in rows:
        got = "—" if row["modelled_min"] is None else f"{row['modelled_min']:.0f}"
        ratio = "—" if row["error_ratio"] is None else f"{row['error_ratio']:.2f}"
        mark = " " if row["within_tolerance"] else "✗"
        print(
            f"{row['kind']:>9} {row['from_siruta']:>9} {row['to_siruta']:>9} "
            f"{row['recorded_min']:>8.0f}m {got:>8}m {ratio:>7} {mark}"
        )

    for kind in ("adjacent", "journey"):
        bias = _bias(rows, kind)
        if bias is not None:
            print(f"\n  {kind:>8} bias: {bias:+.1%}")

    print(f"\n{'PASS' if result['passed'] else 'FAIL'}: {result['reason']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

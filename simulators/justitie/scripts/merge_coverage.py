"""Merge the shards' coverage reports into one, and refuse the merges that must not happen.

Twelve crawlers each write a coverage report; a reader wants one file that says whether the day
is usable. Merging them is three lines. The reason this is a script with tests rather than three
lines of YAML is the check in the middle, which exists because of a failure that shipped.

On 2026-09-05 the scheduled crawl finished at 18:02 and published twelve shards of its two-month
window. A backfill started five minutes later with `--since 2023-01-01`; ten shards succeeded and
two were cancelled. The publish job runs on `always()`, deliberately, so that a day is not lost to
one court's outage — and it uploads with `--clobber`, which replaces the assets *this* run
produced. The two shards that produced nothing left the earlier run's assets in place.

The release then held ten shards covering 2023-01-03 to 2026-09-05 and two covering 2026-09-01 to
2026-09-05. It validated. It summed. It rendered. Forty-one courts appeared to have heard a few
dozen cases in three and a half years, and the only way to notice was to compare each court
against an outside figure — CSM's published annual volume — and find a two-order-of-magnitude
gap in what should be a smooth distribution.

So: a set of shards that read different windows is not a snapshot, and no downstream consumer can
discover that from the data. It fails here instead.

Usage:
    python3 scripts/merge_coverage.py out/ --shards 10 > out/coverage.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

EXPECTED_SHARDS = 12


class MixedWindows(Exception):
    """Raised when the shards did not all read the same registration window."""


def merge(parts: list[dict], collected: int, expected: int = EXPECTED_SHARDS) -> dict:
    """One report from many.

    `parts` must be non-empty and must agree about the window. Everything else is summed or
    unioned; `complete` is true only when every expected shard arrived and each said so itself.
    """
    if not parts:
        raise ValueError("no coverage reports to merge")

    windows = {part["window"]["since"][:10] for part in parts}
    if len(windows) > 1:
        raise MixedWindows(
            f"shards read different windows: {sorted(windows)}. "
            "A snapshot stitched from two crawls describes no period at all."
        )

    courts: dict[str, dict] = {}
    for part in parts:
        courts.update(part["courts"])

    return {
        "crawledAt": max(part["crawledAt"] for part in parts),
        # Recorded rather than inferred. Holding only the merged file, a consumer cannot otherwise
        # tell a two-month daily from a four-year backfill, and the two produce per-court counts
        # that differ by two orders of magnitude.
        "window": parts[0]["window"],
        "shardsCollected": collected,
        "shardsExpected": expected,
        "complete": collected == expected and all(part.get("complete") for part in parts),
        "courtsCrawled": len(courts),
        "dosare": sum(part["totals"]["dosare"] for part in parts),
        "calls": sum(part["totals"]["calls"] for part in parts),
        "incompleteCourts": [
            name
            for name, entry in courts.items()
            if entry.get("failedWindows") or entry.get("irreducibleTruncations")
        ],
        "note": parts[0]["note"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="directory holding coverage-*.json")
    parser.add_argument("--shards", type=int, required=True, help="how many shards reported")
    parser.add_argument("--expected", type=int, default=EXPECTED_SHARDS)
    args = parser.parse_args(argv)

    # `coverage-*.json` and not `coverage*.json`: the merged file is written into the same
    # directory and must not be read back in as though it were a shard.
    paths = sorted(glob.glob(str(Path(args.directory) / "coverage-*.json")))
    if not paths:
        print(f"no coverage-*.json under {args.directory}", file=sys.stderr)
        return 1

    parts = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    try:
        report = merge(parts, args.shards, args.expected)
    except MixedWindows as exc:
        print(str(exc), file=sys.stderr)
        print("refusing to publish", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

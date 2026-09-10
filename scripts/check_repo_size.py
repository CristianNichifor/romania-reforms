"""Fail before the repository becomes a problem, rather than after.

GitHub Pages publishes at most 1 GB, and a repository carrying generated payloads grows
every time one is regenerated — the blob is stored again, and git never forgets it. The point
of this check is that nobody notices the day it stops being true, because no single commit is
ever the problem.

Deliberately measured on the *tracked tree*, not on `.git`. CI clones shallow, so the pack
size there says nothing, while the tree is exactly what a regeneration inflates.

When this trips, the fix is not to raise the ceiling. It is to stop committing whatever grew:
a derived payload is reproducible from the pipeline, so it belongs in a release asset fetched
at build time by `scripts/fetch_release_data.py`. That is what happened to the administrative
road layers this docstring used to nominate, and to the local-finance mart and the July salary
regime.

**Except where a derived payload is the test.** `simulators/impozit-teren/data` and
`simulators/justitie/data` are rebuilt by CI and compared against their committed bytes with
`git diff --exit-code` — eight steps in `ci.yml` do this. The committed copy is not a cached
convenience, it is the expected output, and it catches a class of bug nothing else does:
`impozit-teren/scripts/rebuild.sh` records that building a yield before its inputs "never
fails" and instead moves the fourth significant figure, which only the byte diff notices.

Move those to a release asset and `git diff --exit-code` has nothing to compare. It does not
fail — it passes, on an empty diff, for as long as anyone cares to look. `ci.yml` already
guards the small version of this, noting that an unreachable import "writes nothing, so there
is nothing to diff and the check is vacuous rather than either failing or being quietly
dropped." Removing the baselines would make all eight permanently vacuous.

So the two are counted separately, with separate ceilings. The number worth watching is the
second one: it is the part that could move to a release and has not. A baseline growing means
another county or another year, which is the repository working.

Measured 2026-09-10: 22.8 MB of baselines in 309 files, 35.6 MB of everything else in 811,
and 32.5 MiB of packed history — small, because JSON and GeoJSON delta-compress well. History
is not the problem here; the tree is.

Usage:
    uv run python scripts/check_repo_size.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Rebuilt by CI and compared against the committed bytes with `git diff --exit-code`. See the
# docstring: these are expected outputs, not cached convenience, and moving them to a release
# asset would make eight CI steps pass on an empty diff instead of failing.
BASELINE_PREFIXES = (
    "simulators/impozit-teren/data/",
    "simulators/justitie/data/",
)

# The number worth watching: the part that could move to a release and has not. Roughly
# 10 MB above today's 35.6 MB, which is a new simulator's worth of room and not much more.
LIMIT_MB = 45.0

# Baselines grow when a county or a year is added, which is the repository working rather
# than a payload leaking in. Loose enough not to nag, present so the growth is still bounded.
BASELINE_LIMIT_MB = 40.0

# Reported individually above this, because one large file is a different conversation from
# a thousand small ones.
NOTABLE_MB = 1.0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    sizes: list[tuple[int, str]] = []
    for name in listing.split("\0"):
        if not name:
            continue
        path = root / name
        # A tracked path can be absent in a worktree that has not checked everything out.
        if path.is_file():
            sizes.append((path.stat().st_size, name))

    baseline = [(s, n) for s, n in sizes if n.startswith(BASELINE_PREFIXES)]
    other = [(s, n) for s, n in sizes if not n.startswith(BASELINE_PREFIXES)]

    baseline_mb = sum(s for s, _ in baseline) / 1_048_576
    other_mb = sum(s for s, _ in other) / 1_048_576

    other.sort(reverse=True)

    print(f"tracked: {baseline_mb + other_mb:.1f} MB in {len(sizes):,} files")
    print(f"  movable:  {other_mb:6.1f} MB in {len(other):,} files (limit {LIMIT_MB:.0f} MB)")
    for size, name in other[:5]:
        if size / 1_048_576 < NOTABLE_MB:
            break
        print(f"    {size / 1_048_576:6.1f} MB  {name}")
    print(
        f"  baselines: {baseline_mb:6.1f} MB in {len(baseline):,} files "
        f"(limit {BASELINE_LIMIT_MB:.0f} MB, rebuilt and byte-diffed by ci.yml)"
    )

    failed = False
    if other_mb > LIMIT_MB:
        print(
            f"\nFAIL: {other_mb:.1f} MB outside the CI baselines, over the "
            f"{LIMIT_MB:.0f} MB ceiling.\n"
            "Move the generated payloads to a release asset fetched at build time by "
            "scripts/fetch_release_data.py, rather than raising this number — see the "
            "docstring in this file.",
            file=sys.stderr,
        )
        failed = True

    if baseline_mb > BASELINE_LIMIT_MB:
        print(
            f"\nFAIL: the CI baselines are {baseline_mb:.1f} MB, over the "
            f"{BASELINE_LIMIT_MB:.0f} MB ceiling.\n"
            "Do NOT move these to a release asset: ci.yml rebuilds them and compares the "
            "bytes, so without them in the tree those steps pass on an empty diff. Narrow "
            "what is diffed, or drop an edition that is no longer published.",
            file=sys.stderr,
        )
        failed = True

    if failed:
        return 1

    print(f"ok: {LIMIT_MB - other_mb:.1f} MB of movable headroom")
    return 0


if __name__ == "__main__":
    sys.exit(main())

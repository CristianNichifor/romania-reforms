"""Fail before the repository becomes a problem, rather than after.

GitHub Pages publishes at most 1 GB, and a repository carrying generated payloads grows
every time one is regenerated — the blob is stored again, and git never forgets it. Today
that is not close: 27 MB tracked and 11 MiB of packed history. The point of this check is
that nobody notices the day it stops being true, because no single commit is ever the
problem.

Deliberately measured on the *tracked tree*, not on `.git`. CI clones shallow, so the pack
size there says nothing, while the tree is exactly what a regeneration inflates.

When this trips, the fix is not to raise the ceiling. It is to stop committing whatever grew:
the derived payloads are all reproducible from the pipeline, so they belong in a release asset
fetched at build time. `simulators/administrativ/web/public/data` is the candidate — 12 MB, of
which the two road layers are 6 MB, drawn on the map and read by nothing else.

Usage:
    uv run python scripts/check_repo_size.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Roughly twice what is tracked today. Chosen to catch a payload doubling or a large binary
# arriving by accident, while leaving room for a third simulator to land without ceremony.
LIMIT_MB = 60.0

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

    total = sum(size for size, _ in sizes)
    total_mb = total / 1_048_576
    sizes.sort(reverse=True)

    print(f"tracked: {total_mb:.1f} MB in {len(sizes):,} files (limit {LIMIT_MB:.0f} MB)")
    for size, name in sizes[:5]:
        if size / 1_048_576 < NOTABLE_MB:
            break
        print(f"  {size / 1_048_576:6.1f} MB  {name}")

    if total_mb > LIMIT_MB:
        print(
            f"\nFAIL: {total_mb:.1f} MB tracked, over the {LIMIT_MB:.0f} MB ceiling.\n"
            "Move the generated payloads to a release asset fetched at build time rather "
            "than raising this number — see the docstring in this file.",
            file=sys.stderr,
        )
        return 1

    print(f"ok: {LIMIT_MB - total_mb:.1f} MB of headroom")
    return 0


if __name__ == "__main__":
    sys.exit(main())

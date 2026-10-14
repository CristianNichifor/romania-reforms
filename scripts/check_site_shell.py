"""Check that every page of the assembled site carries the shared shell.

    python3 scripts/check_site_shell.py dist

Every HTML page must have the site's Content Security Policy and the navigation that links
the home page and all seven simulators (site/shell.mjs). Exits 1 and names each page that
does not, so a simulator that stopped applying the shell fails the deploy instead of shipping.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAV = re.compile(r'<nav class="rr-nav" aria-label="[^"]+">(.*?)</nav>', re.S)
CSP = re.compile(r'<meta http-equiv="Content-Security-Policy" content="[^"]+"')
LINKS = 8  # the home page and seven simulators


def problems(html: str) -> list[str]:
    found = []
    if not CSP.search(html):
        found.append("no Content Security Policy")
    nav = NAV.search(html)
    if nav is None:
        found.append("no simulator navigation")
    elif nav.group(1).count("<a ") != LINKS:
        found.append(f"navigation has {nav.group(1).count('<a ')} links, not {LINKS}")
    return found


def main(root: Path) -> int:
    failed = 0
    for page in sorted(root.rglob("*.html")):
        for problem in problems(page.read_text(encoding="utf-8")):
            print(f"{page.relative_to(root)}: {problem}")
            failed = 1
    return failed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1])))

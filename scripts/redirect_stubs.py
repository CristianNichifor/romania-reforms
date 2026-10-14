"""Write redirect stubs for renamed simulator paths into the staged Pages site.

    python3 scripts/redirect_stubs.py cf-site

The Pages middleware (functions/_middleware.js) already answers the old paths with 301. These
are the static fallbacks for a host that serves the files without the middleware: an
index.html per old path that sends the reader on, keeping the rest of the path, the query and
the hash, and a _redirects rule per old path for Cloudflare Pages. The renamed paths are read
from functions/renamed-paths.js, so the two cannot disagree.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENAMED_MODULE = ROOT / "functions" / "renamed-paths.js"
BASE = "/romania-reforms/"
HOST = "https://projects.cristian-nichifor.com"

STUB = """<!doctype html>
<html lang="ro">
  <head>
    <meta charset="utf-8" />
    <title>Pagina s-a mutat</title>
    <meta name="robots" content="noindex" />
    <link rel="canonical" href="{canonical}" />
    <meta http-equiv="refresh" content="0; url={target}" />
    <script>{script}</script>
  </head>
  <body>
    <p>Simulatorul s-a mutat la <a href="{target}">{target}</a>.</p>
  </body>
</html>
"""


def read_renamed_paths() -> dict[str, str]:
    source = RENAMED_MODULE.read_text(encoding="utf-8")
    match = re.search(r"RENAMED_PATHS\s*=\s*Object\.freeze\((\{.*?\})\)", source, re.S)
    if match is None:
        raise ValueError(f"RENAMED_PATHS not found in {RENAMED_MODULE}")
    return json.loads(match.group(1))


def stub(old: str, new: str) -> str:
    target = f"{BASE}{new}/"
    old_prefix = json.dumps(f"{BASE}{old}")
    new_prefix = json.dumps(f"{BASE}{new}")
    script = (
        f"location.replace({new_prefix} + location.pathname.slice({old_prefix}.length)"
        " + location.search + location.hash);"
    )
    return STUB.format(
        canonical=html.escape(HOST + target),
        target=html.escape(target),
        script=script,
    )


def write_stubs(site: Path) -> None:
    renamed = read_renamed_paths()
    for old, new in renamed.items():
        page = site / BASE.strip("/") / old / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(stub(old, new), encoding="utf-8")

    redirects = site / "_redirects"
    rules = redirects.read_text(encoding="utf-8").splitlines() if redirects.exists() else []
    for old, new in renamed.items():
        for rule in (f"{BASE}{old} {BASE}{new}/ 301", f"{BASE}{old}/* {BASE}{new}/:splat 301"):
            if rule not in rules:
                rules.append(rule)
    redirects.write_text("\n".join(rules) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    write_stubs(Path(sys.argv[1]))

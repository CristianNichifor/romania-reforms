"""The family UX guideline stays true to the repository it describes.

It names every simulator the shared shell lists, and every test it cites as conformance
evidence exists, so the checklist cannot point at a test that was renamed or deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs/ux-guidelines.md"


def _simulator_paths() -> list[str]:
    shell = (ROOT / "site/shell.mjs").read_text(encoding="utf-8")
    block = shell.split("SIMULATORS = Object.freeze([", 1)[1].split("]);", 1)[0]
    return re.findall(r"\['([a-z-]+)'", block)


def test_the_guideline_names_every_simulator():
    text = GUIDE.read_text(encoding="utf-8")
    missing = [path for path in _simulator_paths() if f"`/{path}/`" not in text]
    assert not missing, f"docs/ux-guidelines.md does not cover: {missing}"


def test_every_cited_test_exists():
    text = GUIDE.read_text(encoding="utf-8")
    conformance = text.split("## 8. Conformance", 1)[1].split("\n## ", 1)[0]
    cited = re.findall(
        r"`((?:tests|simulators)/[^`:]+?\.(?:py|ts|tsx|mjs|cjs))(?:::[^`]*)?`", conformance
    )
    assert cited, "the conformance checklist cites no tests"
    missing = [path for path in cited if not (ROOT / path).is_file()]
    assert not missing, f"conformance cites missing tests: {missing}"

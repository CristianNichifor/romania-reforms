"""Document pages are light by default and dark only when the reader's system asks.

docs/ux-guidelines.md section 6: one family style, light first; only map canvases may be
dark by default. These pages used to set the dark palette on :root and switch to light
under `prefers-color-scheme: light`, so a reader with no stated preference got dark.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    "site/index.html",
    "site/en/index.html",
    "site/privacy.html",
    "site/brief.html",
    "simulators/deconcentrare/app/src/style.css",
]


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.mark.parametrize("page", PAGES)
def test_the_default_palette_is_light(page):
    css = (ROOT / page).read_text(encoding="utf-8")
    first_root = re.search(r":root\s*\{([^}]*)\}", css)
    assert first_root, f"{page} has no :root block"
    bg = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})", first_root.group(1))
    assert bg and _luminance(bg.group(1)) > 0.5, f"{page}: default --bg is dark"


@pytest.mark.parametrize("page", PAGES)
def test_dark_follows_the_system_setting(page):
    css = (ROOT / page).read_text(encoding="utf-8")
    assert "prefers-color-scheme: light" not in css
    assert "prefers-color-scheme: dark" in css

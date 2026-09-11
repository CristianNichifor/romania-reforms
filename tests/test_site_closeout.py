"""Source-level smoke checks for the public project inventory.

The data builders already prove the numbers. These checks stop the hand-written entry points
from drifting back to old headline figures after a data-complement PR.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
INDEX = ROOT / "site" / "index.html"
BRIEF = ROOT / "site" / "brief.html"
DECONCENTRARE = ROOT / "simulators" / "deconcentrare" / "data" / "deconcentrare.json"
COMPANII_STAT = ROOT / "simulators" / "companii-stat" / "data" / "companii-stat.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["summary"]


def test_readme_lists_the_finished_apps_and_live_paths():
    readme = _read(README)

    for app in ("deconcentrare", "companii-stat"):
        assert f"| **{app}** |" in readme
        assert f"/romania-reforms/{app}/" in readme


def test_public_pages_use_the_current_deconcentrare_headline():
    summary = _summary(DECONCENTRARE)
    index = _read(INDEX)
    brief = _read(BRIEF)
    deconcentrare_app = _read(ROOT / "simulators" / "deconcentrare" / "app" / "index.html")
    justitie_app = _read(ROOT / "simulators" / "justitie" / "app" / "src" / "main.ts")

    total = summary["deconcentratedOfficesTotal"]
    today = summary["officesTodayInRegionalFamilies"]
    proposed = summary["officesProposedOnEightRegions"]

    assert f"cele {total} birouri" in brief.lower()
    assert f"Cele {total} birouri" in index
    assert f"{today} de birouri regionalizabile" in index
    assert f"{today} de birouri la {proposed}" in deconcentrare_app
    assert f"{today} de birouri la {proposed}" in justitie_app
    assert f'<td class="num">{today}</td>' in brief
    assert f'<td class="num">{proposed}</td>' in brief
    assert "549 de birouri la 117" not in index + brief + deconcentrare_app + justitie_app


def test_public_pages_use_the_current_companii_stat_headline():
    summary = _summary(COMPANII_STAT)
    brief = _read(BRIEF)
    readme = _read(ROOT / "simulators" / "companii-stat" / "README.md")
    methodology = _read(ROOT / "simulators" / "companii-stat" / "docs" / "METHODOLOGY.md")

    micro = summary["microUnder20"]

    assert f"{micro} dintre" in brief
    assert f'<td class="num">{micro}</td>' in brief
    assert f"**{micro} companies have under 20 employees**" in readme
    assert f"{micro} micro companies" in methodology
    assert "255 companies have under 20 employees" not in readme
    assert "255 micro companies" not in methodology

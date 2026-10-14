"""Shared navigation and Content Security Policy on every page (RR-3, RR-9).

The shell lives in site/shell.mjs. The apps apply it in their Vite builds; the static pages in
site/ carry its output verbatim. These tests render it with node and compare, apply each app's
build transform to its HTML entries, and check the checker the deploy can run over dist/.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node") or "node"
sys.path.insert(0, str(ROOT / "scripts"))
from check_site_shell import problems  # noqa: E402

APPS = {
    "administrative-reform": ROOT / "simulators/administrativ/web",
    "public-pay": ROOT / "simulators/salarizare/app",
    "transport": ROOT / "simulators/transport/app",
    "justitie": ROOT / "simulators/justitie/app",
    "impozit-teren": ROOT / "simulators/impozit-teren/app",
    "deconcentrare": ROOT / "simulators/deconcentrare/app",
    "companii-stat": ROOT / "simulators/companii-stat/app",
}
STATIC_PAGES = {
    "index.html": ("''", "'ro'"),
    "brief.html": ("''", "'ro'"),
    "privacy.html": ("''", "'ro'"),
    "en/index.html": ("'../'", "'en'"),
}


def shell(expression: str) -> str:
    script = (
        f"import('{(ROOT / 'site/shell.mjs').as_uri()}')"
        f".then((s) => process.stdout.write(JSON.stringify({expression})))"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def built(app: str, page: Path) -> str:
    return shell(f"s.applyShell({json.dumps(page.read_text(encoding='utf-8'))}, {{current: '{app}'}})")


def test_the_simulator_list_matches_the_landing_page():
    simulators = [path for path, _, _ in shell("s.SIMULATORS")]
    landing = (ROOT / "site/index.html").read_text(encoding="utf-8")
    linked = re.findall(r'<li>\s*<a href="([a-z-]+)/">', landing)
    assert simulators == linked == list(APPS)


@pytest.mark.parametrize("page", list(STATIC_PAGES))
def test_static_pages_carry_the_shell(page):
    html = (ROOT / "site" / page).read_text(encoding="utf-8")
    prefix, lang = STATIC_PAGES[page]
    assert shell(f"s.navHtml('', {prefix}, {lang})") in html
    assert shell("s.CSP_META") in html
    assert problems(html) == []


@pytest.mark.parametrize("app", list(APPS))
def test_every_app_registers_the_shell_for_its_own_path(app):
    config = next(APPS[app].glob("vite.config.*")).read_text(encoding="utf-8")
    assert "site/shell.mjs" in config
    assert f"siteShell('{app}')" in config


@pytest.mark.parametrize("app", list(APPS))
def test_every_built_page_of_every_app_has_nav_and_csp(app):
    pages = [p for p in APPS[app].glob("*.html")]
    assert pages
    for page in pages:
        html = built(app, page)
        assert problems(html) == [], page
        assert f'<a href="../{app}/" aria-current="page">' in html


def test_the_checker_reports_a_page_without_the_shell(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "index.html").write_text("<html><head></head><body></body></html>")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_site_shell.py"), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "x/index.html: no Content Security Policy" in result.stdout
    assert "x/index.html: no simulator navigation" in result.stdout

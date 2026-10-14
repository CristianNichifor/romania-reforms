"""Renamed simulator paths keep working after the English paths (RR-1)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Node runs the Pages middleware and the stub's script. It is preinstalled on CI runners; a
# missing node fails these tests rather than skipping them, like every other missing input.
NODE = shutil.which("node") or "node"

sys.path.insert(0, str(ROOT / "scripts"))
from redirect_stubs import BASE, read_renamed_paths, write_stubs  # noqa: E402


def test_renamed_paths_come_from_the_middleware_module():
    assert read_renamed_paths() == {
        "administrativ": "administrative-reform",
        "salarizare": "public-pay",
    }


def test_every_renamed_path_gets_a_stub_and_a_redirect_rule(tmp_path):
    site = tmp_path / "cf-site"
    (site / "romania-reforms").mkdir(parents=True)
    (site / "_redirects").write_text("/ /romania-reforms/ 302\n")

    write_stubs(site)

    rules = (site / "_redirects").read_text().splitlines()
    assert rules[0] == "/ /romania-reforms/ 302"
    for old, new in read_renamed_paths().items():
        stub = (site / "romania-reforms" / old / "index.html").read_text()
        target = f"{BASE}{new}/"
        canonical = f"https://projects.cristian-nichifor.com{target}"
        assert f'<link rel="canonical" href="{canonical}"' in stub
        assert '<meta name="robots" content="noindex"' in stub
        assert f'<meta http-equiv="refresh" content="0; url={target}"' in stub
        assert "location.replace" in stub
        assert f"{BASE}{old}/* {BASE}{new}/:splat 301" in rules
        assert f"{BASE}{old} {BASE}{new}/ 301" in rules


def test_stubs_are_idempotent(tmp_path):
    write_stubs(tmp_path)
    write_stubs(tmp_path)
    rules = (tmp_path / "_redirects").read_text().splitlines()
    assert len(rules) == len(set(rules))


def test_stub_script_keeps_the_rest_of_the_path_query_and_hash(tmp_path):
    write_stubs(tmp_path)
    stub = (tmp_path / "romania-reforms" / "administrativ" / "index.html").read_text()
    script = stub.split("<script>")[1].split("</script>")[0]
    probe = f"""
const location = {{ pathname: "/romania-reforms/administrativ/a/b", search: "?x=1", hash: "#s=2",
  replace(url) {{ console.log(url); }} }};
{script}
"""
    out = subprocess.run([NODE, "-e", probe], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "/romania-reforms/administrative-reform/a/b?x=1#s=2"


def test_middleware_redirects_old_paths():
    result = subprocess.run(
        [
            NODE,
            "--test",
            "tests/renamed_paths_middleware.test.mjs",
            "tests/preview_gate_middleware.test.mjs",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_writes_into_the_given_directory(tmp_path):
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "redirect_stubs.py"), str(tmp_path)],
        check=True,
    )
    stubs = sorted(p.name for p in (tmp_path / "romania-reforms").iterdir())
    assert stubs == ["administrativ", "salarizare"]

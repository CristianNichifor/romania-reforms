"""Replay the reporting steps without contacting the portal or publishing releases."""

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/portal-snapshot.yml"


def run_step(name, tmp_path, *, pipefail=False, **env):
    source = WORKFLOW.read_text().split(f"      - name: {name}\n", 1)[1]
    body = source.split("        run: |\n", 1)[1]
    body = re.split(r"\n(?=      \S)", body)[0]
    body = textwrap.dedent(body)
    body = body.replace("${{ matrix.shard }}", "0")
    body = body.replace("${{ inputs.since }}", "")
    body = body.replace("${{ github.run_id }}", "36698358372")
    return subprocess.run(
        ["bash", "-e", *(["-o", "pipefail"] if pipefail else []), "-c", body],
        cwd=tmp_path,
        env={
            **os.environ,
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
            "GITHUB_OUTPUT": str(tmp_path / "output"),
            **env,
        },
        capture_output=True,
        text=True,
    )


def test_report_explains_bootstrap_failure_without_coverage(tmp_path):
    result = run_step("Report coverage", tmp_path, IMPORT_EXIT="1")
    assert result.returncode == 1
    assert "No coverage" in (tmp_path / "summary").read_text()
    assert "No such file" not in result.stderr


def test_report_keeps_partial_coverage_for_upload(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out/coverage-part00of12.json").write_text('{"complete": false}')
    result = run_step("Report coverage", tmp_path, IMPORT_EXIT="1")
    assert result.returncode == 0
    assert "Incomplete" in (tmp_path / "summary").read_text()
    assert '"complete": false' in (tmp_path / "summary").read_text()


@pytest.mark.parametrize("pipefail", [False, True])
def test_empty_day_fails_with_diagnostic_before_publish(tmp_path, pipefail):
    result = run_step("Summarise the day", tmp_path, pipefail=pipefail)
    assert result.returncode == 1
    assert "No shard produced output" in result.stderr
    assert "No shard produced output" in (tmp_path / "summary").read_text()


@pytest.mark.parametrize("exit_code", [None, "1", "2"])
def test_crawler_failure_survives_partial_upload(tmp_path, exit_code):
    env = {} if exit_code is None else {"IMPORT_EXIT": exit_code}
    result = run_step("Preserve crawler failure after uploading partial output", tmp_path, **env)
    assert result.returncode == 1

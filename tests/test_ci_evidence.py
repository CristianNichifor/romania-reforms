"""Missing verification subjects must not turn a required check green."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "content",
    [
        None,
        "<broken",
        "<testsuites/>",
        '<testsuite><testcase><skipped message="pipeline not built"/></testcase></testsuite>',
        "<testsuite><testcase><failure/></testcase></testsuite>",
        "<testsuite><testcase><error/></testcase></testsuite>",
    ],
)
def test_missing_empty_or_unsuccessful_evidence_fails(tmp_path, content):
    report = tmp_path / "report.xml"
    if content is not None:
        report.write_text(content)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_test_report.py"), str(report)],
        capture_output=True,
    )
    assert result.returncode == 1


def test_executed_passing_tests_succeed(tmp_path):
    report = tmp_path / "report.xml"
    report.write_text('<testsuite><testcase name="real test"/></testsuite>')
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_test_report.py"), str(report)],
        capture_output=True,
    )
    assert result.returncode == 0


def test_verify_depends_on_every_ci_job():
    import re

    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    # Only top-level entries after jobs:, excluding workflow permissions.
    jobs = set(re.findall(r"^  ([a-z][a-z-]*):$", workflow.split("jobs:", 1)[1], re.MULTILINE))
    needs = re.search(r"^    needs: \[(.*)\]$", workflow, re.MULTILINE).group(1)
    assert {job.strip() for job in needs.split(",")} == jobs - {"verify"}
    for name in ("justice-browser", "native-consumers"):
        assert f"uses: ./.github/workflows/{name}.yml" in workflow
        reusable = (ROOT / f".github/workflows/{name}.yml").read_text()
        assert "  workflow_call:" in reusable
        assert "on: [push, pull_request]" not in reusable


@pytest.mark.parametrize(
    "status, expected", [("success", 0), ("failure", 1), ("cancelled", 1), ("skipped", 1)]
)
def test_aggregate_rejects_every_unsuccessful_dependency(status, expected):
    import json
    import os
    import textwrap

    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    code = workflow.split("python - <<'PYCODE'\n", 1)[1].split("          PYCODE", 1)[0]
    results = {"shared": {"result": "success"}, "native-consumers": {"result": status}}
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        env={**os.environ, "RESULTS": json.dumps(results)},
        capture_output=True,
    )
    assert result.returncode == expected

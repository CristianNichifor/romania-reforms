"""Tests for the gate that validates every simulator's data against its schema.

The gate had no tests, which is how it carried the bug these cover. A document with no `$schema`
resolved the empty reference to its own data directory; a directory exists, so the `exists()`
check passed, and the validator died reading it. What a contributor saw was a traceback out of
`pathlib` naming a path, rather than the sentence the error branch was written to produce — and
the failure is one every new dataset can cause, because forgetting the `$schema` line is the
easiest thing to forget about a new document.

These run the gate as a subprocess against a temporary tree rather than importing `main()`,
because what is being checked is the contract CI depends on: the exit code, and whether the
message names the file a person then has to go and fix.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "validate_data.py"

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id"],
    "properties": {"$schema": {"type": "string"}, "id": {"type": "string"}},
}


@pytest.fixture
def simulator(tmp_path: Path) -> Path:
    """A minimal simulator tree — `simulators/<name>/data` and `schema` — for the gate to walk."""
    sim = tmp_path / "simulators" / "proba"
    (sim / "data").mkdir(parents=True)
    (sim / "schema").mkdir()
    (sim / "schema" / "proba.schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_data.py").write_text(
        GATE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # The shared vocabulary is resolved by bare filename from any simulator, so it has to be
    # where the gate expects it even when nothing under test references it.
    shared = tmp_path / "packages" / "provenance" / "schema"
    shared.mkdir(parents=True)
    for path in (ROOT / "packages" / "provenance" / "schema").glob("*.json"):
        (shared / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return sim


def _run(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tmp_path / "scripts" / "validate_data.py")],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_document_that_matches_its_schema_passes(simulator: Path, tmp_path: Path):
    (simulator / "data" / "bun.json").write_text(
        json.dumps({"$schema": "../schema/proba.schema.json", "id": "bun"}), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_document_with_no_schema_is_named_rather_than_crashing_the_gate(
    simulator: Path, tmp_path: Path
):
    """The regression. An empty `$schema` resolves to the data directory, which exists — so an
    `exists()` check let it through to `read_text`, and the gate died on a directory instead of
    telling the contributor which file was missing its schema line."""
    (simulator / "data" / "fara-schema.json").write_text(
        json.dumps({"id": "fara-schema"}), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "fara-schema.json" in result.stdout
    assert "Traceback" not in result.stderr
    assert "IsADirectoryError" not in result.stderr


def test_a_schema_reference_that_points_nowhere_is_named_too(simulator: Path, tmp_path: Path):
    (simulator / "data" / "gresit.json").write_text(
        json.dumps({"$schema": "../schema/nu-exista.schema.json", "id": "gresit"}), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "gresit.json" in result.stdout and "nu-exista" in result.stdout


def test_a_document_that_breaks_its_schema_fails_with_the_field_named(
    simulator: Path, tmp_path: Path
):
    """A gate that only caught missing schemas would pass anything that had one."""
    (simulator / "data" / "invalid.json").write_text(
        json.dumps({"$schema": "../schema/proba.schema.json"}), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "invalid.json" in result.stdout and "id" in result.stdout

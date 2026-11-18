"""Guards on the data-root override.

``pipeline.paths`` resolves its constants at import, so each case runs in a fresh
interpreter. The override must move only the fetched and processed data: the web
artefacts and the docs are tracked, and stay under the simulator root.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SIMULATOR_ROOT = Path(__file__).resolve().parent.parent

_NAMES = ("DATA_DIR", "RAW_DIR", "PROCESSED_DIR", "REPORTS_DIR", "WEB_DATA_DIR", "DOCS_DIR")
_PROBE = (
    "import json; from pipeline import paths; "
    f"print(json.dumps({{n: str(getattr(paths, n)) for n in {_NAMES!r}}}))"
)


def _resolve(override: str | None) -> dict[str, Path]:
    env = {k: v for k, v in os.environ.items() if k != "ADMIN_REFORM_DATA_DIR"}
    if override is not None:
        env["ADMIN_REFORM_DATA_DIR"] = override
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=SIMULATOR_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {name: Path(value) for name, value in json.loads(out).items()}


def test_default_data_tree_is_under_the_simulator_root() -> None:
    paths = _resolve(None)
    assert paths["DATA_DIR"] == SIMULATOR_ROOT / "data"
    assert paths["RAW_DIR"] == SIMULATOR_ROOT / "data" / "raw"
    assert paths["REPORTS_DIR"] == SIMULATOR_ROOT / "data" / "processed" / "reports"


def test_empty_override_means_unset() -> None:
    assert _resolve("") == _resolve(None)


def test_override_relocates_only_the_data_tree(tmp_path: Path) -> None:
    default = _resolve(None)
    moved = _resolve(str(tmp_path))
    root = tmp_path.resolve()
    assert moved["DATA_DIR"] == root
    assert moved["RAW_DIR"] == root / "raw"
    assert moved["PROCESSED_DIR"] == root / "processed"
    assert moved["REPORTS_DIR"] == root / "processed" / "reports"
    assert moved["WEB_DATA_DIR"] == default["WEB_DATA_DIR"]
    assert moved["DOCS_DIR"] == default["DOCS_DIR"]

"""Pinned contributor rebuilds must neither contact ECB nor invent a missing baseline."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "simulators/impozit-teren/scripts"
DATA = SCRIPTS.parent / "data"


@pytest.fixture
def tax_builder(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "pinned_tax_builder", SCRIPTS / "build_impozit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "data").mkdir()
    for name in (
        "cod-fiscal-teren-2026.json",
        "fond-funciar-bc-2014.json",
        "valoare-teren-bc-2026.json",
        "impozit-bc-2026.json",
    ):
        shutil.copyfile(DATA / name, tmp_path / "data" / name)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["build_impozit.py", "--county", "BC", "--reuse-exchange-rate"]
    )

    def no_network():
        pytest.fail("a pinned rebuild called the live exchange-rate endpoint")

    monkeypatch.setattr(module, "exchange_rate", no_network)
    return module, tmp_path / "data/impozit-bc-2026.json"


def test_tax_cli_preserves_the_baseline_exchange_rate(tax_builder):
    module, output = tax_builder
    before = json.loads(output.read_text())["assumptions"]
    assert module.main() == 0
    after = json.loads(output.read_text())["assumptions"]
    assert (after["ronPerEur"], after["exchangeRateDate"]) == (
        before["ronPerEur"],
        before["exchangeRateDate"],
    )


def test_tax_cli_refuses_missing_pinned_baseline(tax_builder):
    module, output = tax_builder
    output.unlink()
    with pytest.raises(SystemExit, match="missing pinned exchange-rate baseline"):
        module.main()

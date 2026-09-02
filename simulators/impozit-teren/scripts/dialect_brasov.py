"""Brașov, out of the volume it shares with its neighbour. See cnp_brasov.py for the reading.

Two lines on top of a shared module: the counties are laid out alike in their towns and
differently in their countryside, and both branches live in one place rather than being
copied into two readers that would then drift.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnp_brasov import parse_county  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _names() -> dict[str, str]:
    """SIRUTA to the register's own spelling, which every join downstream uses."""
    path = ROOT / "data" / "fond-funciar-bv-2014.json"
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    # Strip a rank word and nothing else. Dropping the first word unconditionally turned
    # "VAMA BUZAULUI" into "BUZAULUI" and "POIANA MARULUI" into "MARULUI" — four communes
    # published under half their own names, which the roster gate caught and coverage did not.
    return {
        row["siruta"]: re.sub(
            r"^(?:MUNICIPIUL|ORA[ȘS]UL|ORAS|COMUNA)\s+", "", row["name"], flags=re.I
        )
        for row in document["localities"]
    }


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    known = _names()
    return parse_county(name, is_local, "BV", "BRAȘOV", known.get)

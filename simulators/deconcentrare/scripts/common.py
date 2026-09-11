"""Shared helpers for the deconcentrare pipeline scripts.

`fold` is the normalisation every matcher uses; `strip_county` peels the trailing county
name off an institution name; the three loaders read the shared SIRUTA registry and the
canonical justitie county→region map.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
REGISTRY = REPO / "packages" / "uat_registry" / "data" / "uat-registry-2026.json"
REGION_MAP = REPO / "simulators" / "justitie" / "data" / "curti-apel-regiuni.json"


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def load_county_codes() -> dict[str, str]:
    """Folded county name -> county code, from the shared SIRUTA registry."""
    units = json.loads(REGISTRY.read_text(encoding="utf-8"))["units"]
    pairs = {}
    for unit in units:
        if unit.get("level") == "county" and unit.get("countyCode"):
            pairs[fold(unit["countyName"])] = unit["countyCode"]
    return pairs


def load_county_population() -> dict[str, int]:
    """County code -> population, from the shared SIRUTA registry."""
    units = json.loads(REGISTRY.read_text(encoding="utf-8"))["units"]
    pairs = {}
    for unit in units:
        if unit.get("level") == "county" and unit.get("countyCode") and unit.get("population"):
            pairs[unit["countyCode"]] = unit["population"]
    return pairs


def load_region_of_county() -> dict[str, str]:
    """County code -> development region, reused from the justitie variant."""
    regions = json.loads(REGION_MAP.read_text(encoding="utf-8"))["regions"]
    return {code: region["region"] for region in regions for code in region["counties"]}


def strip_county(name: str, counties: list[str]) -> str:
    folded = fold(name)
    for county in counties:
        if folded.endswith(" " + county):
            return folded[: -(len(county) + 1)].strip()
    folded = re.sub(r"\s*[- ]*UT\s*\d+$", "", folded)
    folded = re.sub(r"\s*UNITATEA TERITORIALA\s*\d+$", "", folded)
    return re.sub(r"\s*\d+$", "", folded).strip()

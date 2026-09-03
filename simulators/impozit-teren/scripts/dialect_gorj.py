"""Gorj, one of the four counties CNP Craiova prices in a single document.

The reading is shared — see `cnp_craiova` for the layout and for why the section boundary is
the county's own `ANEXA Z` rather than the running header.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnp_craiova import parse_county  # noqa: E402

COUNTY = "GJ"
SECTION = "Gorj"


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    return parse_county(name, is_local, COUNTY, SECTION)

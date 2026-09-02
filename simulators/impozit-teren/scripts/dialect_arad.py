"""Arad, which this repository said contained no land at all.

It contains two annexes of it, in the layout its own chamber uses for Timiș — five
`Localitate · Valoare` columns interleaved on every line, with no ruling lines to separate
them:

    anexa 12 ARAD
    Localitate Valoare  Localitate Valoare  Localitate Valoare  Localitate Valoare
    Chișineu Criș 22    Sebiș 11            Căpruța 2,5         Mânerău 2,5
    Nădab 10            Donceni 2           Dumbravița 2        Răpsig 2,5

Read as a line, `Nădab 10 Donceni 2` is one row of something. It is two halves of two different
communes. The word-geometry reader written for Timiș already handles this — it takes the column
edges from the `Localitate` headers and reads each column independently — and it takes five
columns as readily as four, because the edges are counted rather than assumed. So this file
borrows `rows_of`, `bands_of` and `read_page` from it and supplies only what differs.

**What differs is how the two annexes are told apart.** Timiș labels them by unit — `euro/mp`
for intravilan, `euro/ha` for extravilan — and Arad labels neither. They are annex 12 and annex
13, and nothing else on the page says which is which. The magnitudes are unmistakable once
read, 22 against 9 500, but picking by magnitude would be deciding the answer before reading
it; the annex number is what the document actually asserts.

**The earlier verdict here was "annexes contain no land at all".** It came from looking for
land in tables, and this document has none: pdfplumber finds no table on any of these pages,
because there is nothing to find. That was the fourth time counting tables gave the wrong
answer about a county.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dialect_timisoara import (  # noqa: E402
    M2_PER_HA,
    ZONE_LETTERS,
    bands_of,
    read_page,
    rows_of,
)
from extract_cache import CACHE, load  # noqa: E402

# Both annex files are needed and one of them is a near-duplicate: `Anexe_Arad_2026_02.pdf` is
# the same 46 pages re-exported. Reading both is harmless — every value is set once, by
# `setdefault` — and asking which is authoritative is a question the chamber has not answered.
NEEDS = re.compile(r"^Anexe_Arad_\d{4}", re.I)
CITY_ANNEX = re.compile(r"anexa\s*7\b", re.I)
INTRAVILAN_ANNEX = re.compile(r"anexa\s*12\b", re.I)
EXTRAVILAN_ANNEX = re.compile(r"anexa\s*13\b", re.I)
CITY = "ARAD"
YEAR = re.compile(r"_(\d{4})")
# "Zona A 200", "Toate zonele 1,5" — annex 7's rows, which are a table with no ruling lines.
CITY_ZONE = re.compile(r"^Zona\s+([A-F])\s+([\d,]+)$", re.I)
CITY_EXTRA = re.compile(r"^Toate\s+zonele\s+([\d,]+)$", re.I)


def siblings(name: str) -> list[str]:
    """Every cached export of *this study's year*.

    Not every cached `Anexe_Arad_*`. The 2025 annexes are still in the cache from an earlier
    fetch, and they sort first, so a glob without the year hands 2025 to a `setdefault` that
    then refuses 2026's value for the same locality. The county reads clean either way and
    prices itself from last year's study.
    """
    found = YEAR.search(name)
    year = found.group(1) if found else r"[0-9][0-9][0-9][0-9]"
    same_year = sorted(
        path.name[: -len(".json.gz")] for path in CACHE.glob(f"Anexe_Arad_{year}*.json.gz")
    )
    return same_year or [name]


def city_prices(page: dict) -> tuple[dict[str, float], float | None]:
    """Annex 7: the municipality's own land, which annexes 12 and 13 do not carry.

    Arad city is 168 350 people and the largest settlement in the county, and reading only the
    locality annexes leaves it out entirely — at no cost to the coverage figure, which counts
    localities and does not know that this one is worth more than the other two hundred.
    """
    lines: dict[int, list[tuple[float, str]]] = {}
    for text, x0, _x1, top in page.get("words") or []:
        lines.setdefault(round(top / 3), []).append((x0, text))

    zones: dict[str, float] = {}
    extravilan: float | None = None
    for key in sorted(lines):
        line = " ".join(word for _, word in sorted(lines[key]))
        zone = CITY_ZONE.match(line)
        if zone:
            zones[zone.group(1).upper()] = float(zone.group(2).replace(",", "."))
            continue
        # Per square metre in this annex, unlike annex 13 for every other locality.
        found = CITY_EXTRA.match(line)
        if found:
            extravilan = float(found.group(1).replace(",", "."))
    return zones, extravilan


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    intravilan: dict[str, dict[str, float]] = {}
    flat: dict[str, list[float]] = {}
    arable: dict[str, float] = {}
    pages_of: dict[str, int] = {}

    for document in siblings(name):
        try:
            pages = load(document)["pages"]
        except SystemExit:
            continue
        for index, page in enumerate(pages, start=1):
            words = page.get("words") or []
            if not words:
                continue
            header = page["text"][:200]
            if CITY_ANNEX.search(header[:40]):
                zones, flat_extra = city_prices(page)
                if zones:
                    intravilan.setdefault(CITY, {}).update(zones)
                    pages_of.setdefault(CITY, index)
                if flat_extra is not None:
                    arable.setdefault(CITY, flat_extra)
                continue
            if bands_of(rows_of(words)) is None:
                continue
            is_intra = bool(INTRAVILAN_ANNEX.search(header))
            is_extra = bool(EXTRAVILAN_ANNEX.search(header))
            if not (is_intra or is_extra):
                continue
            for place, zone, value in read_page(words):
                if not is_local(place):
                    continue
                key = place.upper()
                pages_of.setdefault(key, index)
                if is_intra:
                    if zone:
                        intravilan.setdefault(key, {})[zone] = value
                    else:
                        flat.setdefault(key, []).append(value)
                else:
                    # Euro per hectare in this annex; per square metre everywhere downstream.
                    arable.setdefault(key, value / M2_PER_HA)

    towns: list[dict] = []
    communes: list[dict] = []
    for key in sorted(set(intravilan) | set(flat)):
        extra = {"A": arable[key]} if key in arable else {}
        zones = dict(intravilan.get(key, {}))
        if not zones:
            # A locality with one price and no zone letter is a village, not a town: the
            # column gives it a single figure and the document draws no zones around it.
            prices = sorted(set(flat.get(key, [])), reverse=True)[: len(ZONE_LETTERS)]
            if not prices:
                continue
            communes.append(
                {
                    "name": key.title(),
                    "villages": [
                        {"name": key.title(), "intravilan": {"CC": prices[0]}}
                    ],
                    "extravilan": extra,
                    "page": pages_of.get(key, 1),
                }
            )
            continue
        towns.append(
            {
                "name": key.title(),
                "rank": None,
                "zones": sorted(zones),
                "intravilan": {"CC": zones},
                "extravilan": extra,
                "page": pages_of.get(key, 1),
            }
        )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    notes = [] if towns or communes else ["no land annex parsed"]
    return towns, communes, notes

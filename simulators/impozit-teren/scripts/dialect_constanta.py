"""The CNP Constanța dialect: a chapter per locality, read as text rather than as tables.

Two counties in one 524-page document, organised as a numbered chapter per locality —
`4.16 MIHAIL KOGALNICEANU` — each carrying its own flats, houses and then its land. So the
locality is a heading, not a column, and the reader's first job is to cut the document into
chapters.

Its second job is to ignore the tables. pdfplumber finds them, but their cell boundaries
collapse: a whole row comes back in one cell as `Zona A - Centru 40 40`. The text layer,
unusually for these studies, is clean and ordered, so this reads that instead — the one
chamber so far where the flattened text is the better source.

Land appears in two shapes, and a locality has one or the other:

    zoned    Amplasarea  Curti constructii  Arabil
             Zona A - Centru   40  40
             Zona B - Mediana  30  30

    flat     Curti Constructii 3  euro/mp
             Arabil 2  euro/mp

**Extravilan is quoted in euro per hectare**, alone among the chambers read so far, and is
converted here. Its rows also run together — `la DN, DJ 6000 3500 7500 Alte locatii 4500`
puts two amplasaments on one line — so the first run of figures after the caption is taken as
arable, pasture and vineyard, and land away from a main road is not distinguished from land
beside one. That distinction is real and is lost; it is worth less than the intravilan figure,
which is where a land tax mostly falls and which is read exactly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# "4.16 MIHAIL KOGALNICEANU" — the chapter heading that names a locality.
CHAPTER = re.compile(r"^\s*\d+\.\d+\.?\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.']{2,})\s*$")
# Headings only, and the whole line. The words also open the prose that lists which streets
# fall in which zone — "Terenuri intravilane zona Popas Cișmea;" — and matching those turned
# a street list into a price table and put Ovidiu's land at 3 500 €/m², twenty times
# Constanța's own.
INTRA_HEAD = re.compile(r"^\s*TERENURI\s+INTRAVILANE\s*$", re.I)
EXTRA_HEAD = re.compile(r"^\s*TERENURI\s+EXTRAVILANE\s*$", re.I)
# "Zona A - Centru 40 40" and "Aeroport 20 15" — a place inside the town, then its figures.
# The label is short — "Zona A - Centru", "Aeroport". A long one is a sentence, not a place.
ZONED_ROW = re.compile(
    r"^\s*(Zona\s+[A-F]\b[^\d]{0,40}|[A-Za-zĂÂÎȘŞȚŢăâîșşțţ][\w \-,\.]{2,40}?)\s+"
    r"([\d.,]+)\s+([\d.,]+)\s*$"
)
# "Curti Constructii 3  euro/mp"
FLAT_ROW = re.compile(r"^\s*(Curti\s+Construc\w*|Arabil)\s+([\d.,]+)\s*euro", re.I)
NOISE = re.compile(r"euro|amplasarea|nota|pagina|studiu|valorile", re.I)
M2_PER_HA = 10_000


def number(text: str) -> float | None:
    cleaned = text.strip().replace(" ", "")
    if not re.fullmatch(r"\d{1,7}([.,]\d+)?", cleaned):
        return None
    value = float(cleaned.replace(",", "."))
    return value if value > 0 else None


def chapters(pages: list[dict]) -> list[tuple[str, list[str]]]:
    """The document cut into its numbered locality chapters."""
    found: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for page in pages:
        for line in page["text"].splitlines():
            heading = CHAPTER.match(line)
            if heading:
                current = (re.sub(r"\s+", " ", heading.group(1)).strip(" .-"), [])
                found.append(current)
            elif current is not None:
                current[1].append(line)
    return found


def read_intravilan(lines: list[str]) -> tuple[list[float], dict[str, float]]:
    """Every published building-land price for one locality, and its zones if it has them.

    Returned apart because the distinction is in the document: a town is priced zone by zone
    and a commune by a single figure, and flattening the first into the second would throw
    away which is which.
    """
    prices: list[float] = []
    zones: dict[str, float] = {}
    active = False
    for line in lines:
        if INTRA_HEAD.search(line):
            active = True
            continue
        if EXTRA_HEAD.search(line) or CHAPTER.match(line):
            active = False
        if not active:
            continue
        flat = FLAT_ROW.match(line)
        if flat and flat.group(1).lower().startswith("curti"):
            value = number(flat.group(2))
            if value:
                prices.append(value)
            continue
        row = ZONED_ROW.match(line)
        if row and not NOISE.search(row.group(1)):
            # Two figures per row: building land, then arable. The first is the one wanted.
            value = number(row.group(2))
            if value:
                prices.append(value)
                letter = re.match(r"\s*Zona\s+([A-F])\b", row.group(1), re.I)
                if letter:
                    zones.setdefault(letter.group(1).upper(), value)
    return prices, zones


def read_extravilan(lines: list[str]) -> dict[str, float]:
    """Arable, pasture and vineyard for one locality, converted from euro per hectare."""
    active = False
    for line in lines:
        if EXTRA_HEAD.search(line):
            active = True
            continue
        if CHAPTER.match(line) or INTRA_HEAD.search(line):
            active = False
        if not active or NOISE.search(line):
            continue
        figures = [number(x) for x in re.findall(r"[\d.,]+", line)]
        figures = [x for x in figures if x and x >= 100]
        if len(figures) >= 3:
            return {
                code: figures[index] / M2_PER_HA
                for index, code in enumerate(("A", "P+F", "V+L"))
            }
    return {}


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    communes: dict[str, dict] = {}
    towns: list[dict] = []
    for locality, lines in chapters(pages):
        if not is_local(locality):
            continue
        prices, zones = read_intravilan(lines)
        if not prices:
            continue
        if len(zones) >= 3:
            # Priced zone by zone, which is how this chamber prices a town.
            towns.append(
                {
                    "name": locality,
                    "rank": None,
                    "zones": sorted(zones),
                    "intravilan": {"CC": zones},
                    "extravilan": read_extravilan(lines),
                    "page": 1,
                }
            )
            continue
        entry = communes.setdefault(
            locality.upper(),
            {"name": locality, "villages": [], "extravilan": {}, "page": 1},
        )
        # Each published price becomes its own reading, so a town's zones widen its band
        # instead of one of them standing for the whole place.
        for position, price in enumerate(sorted(set(prices), reverse=True), start=1):
            entry["villages"].append(
                {"name": f"{locality} ({position})", "intravilan": {"CC": price}}
            )
        if not entry["extravilan"]:
            entry["extravilan"] = read_extravilan(lines)
    for position, entry in enumerate(communes.values(), start=1):
        entry["index"] = position
    return towns, list(communes.values()), []

"""The CNP Galați dialect for Vrancea: twelve annexes, five layouts, one county.

Vrancea is not organised by locality or by category but by **where in the county you are**.
Annexes 1–5 price the five towns, one table each, zone by zone. Annexes 6–11 price the
communes in geographic bands — the ring around Focșani, the tourist valley, the northern
hills, the plain, the mountains — and each band was drawn up with its own column headings:

    hills / plain   Nr · Comuna · reședință existent · reședință atras ·
                    celelalte existent · celelalte atras
    mountains       the same, but the reședință columns split again by parcel size
    tourist valley  ten columns, villas and village centres and one commune per two rows

Annex 12 then prices the extravilan for every locality in the county at once, in **euro per
hectare**, with arable and pasture each carrying a quality zone in roman numerals beside the
price.

So the reader takes the county in two passes. The extravilan annex is regular and is read by
column position, asserted against its own caption. The intravilan annexes are not regular at
all, and are read by the only thing all six share: a row that names a locality the register
knows, followed by figures. Every figure on that row is kept as a separate reading — the
"terenuri atrase în intravilan" columns are genuinely cheaper land in the same commune, not a
different measurement of the same land — so the band this reports is the annex's own spread.

A town's name is nowhere in its own table. It is in the sentence above it —
`Valoarea de circulatie a terenurilor din intravilanul orasului Odobesti` — and two towns
share a page, so the titles and the zone-shaped tables are paired in the order they appear.

**This is the 2025 study.** The 2026 volume for Vrancea is a scan with no text layer at all —
58 pages, not one extractable character — so there is nothing in it to read. Prahova is the
other 2025 county here for a different reason, and both travel with their year.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

M2_PER_HA = 10_000
# "din intravilanul orasului Odobesti", "din intavilanele orasului Marasesti" — the title
# that names the town its table is about. Spelling varies between annexes, including the
# missing "r" in "intavilanele", which is the document's own typo and appears twice.
TOWN_TITLE = re.compile(
    r"int[ra]+vilan\w*\s+(?:municipiului\s+|orasului\s+|localitatii\s+)?"
    r"([A-Z][A-Za-zĂÂÎȘŞȚŢăâîșşțţ\-]{3,})",
)
ZONE_TABLE = re.compile(r"denumirea\s+zonei", re.I)
EXTRA_TITLE = re.compile(r"SITUATE\s+IN\s+EXTRAVILANUL", re.I)
# The zone a row prices. The towns name their zones two ways — by fiscal letter and by
# position — and both appear inside the same annex.
ZONE_LETTER = re.compile(r"^\s*zona\s+([A-D])\b", re.I)
POSITION_ZONES = [("A", r"centr"), ("B", r"median"), ("C", r"periferic")]
# Rows that price something other than the locality's own land: access roads created by
# subdividing a plot, and land only just brought inside the boundary.
NOT_A_ZONE = re.compile(r"drumuri|lotizare|cartier|satele\s+aferente", re.I)
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
# "Com. Vinatori sat Vinatori" — the commune, then its seat, in one cell. The second word is
# taken only when it is capitalised, which is what separates "Slobozia Bradului" from the
# lower-case "sat" that introduces the seat.
COMMUNE_PREFIX = re.compile(r"^\s*com\.?\s+", re.I)
COMMUNE_CELL = re.compile(r"^([A-ZĂÂÎȘŞȚŢ][\w\-]+\.?(?:\s+[A-ZĂÂÎȘŞȚŢ][\w\-]+)?)", re.U)
# Annex 12's columns, asserted against its caption rather than assumed. Arable and pasture
# each have a quality zone in front of the price, which is why they are not adjacent.
EXTRA_COLUMNS = {"A": 3, "P+F": 5, "VII": 6, "LIVEZI": 8, "PADURE": 11}


def number(cell: str) -> float | None:
    """The first figure in a cell, which may hold several or none.

    A town's zone D reads "17 (terenurile construite din zona CCH = 6) 12" — three numbers,
    a price and two exceptions to it — and the price is the first.
    """
    for token in re.split(r"[^\d.,]+", cell):
        if re.fullmatch(r"\d{1,6}([.,]\d+)?", token):
            value = float(token.replace(",", "."))
            if 0 < value < 1_000_000:
                return value
    return None


def numbers(cells: list[str]) -> list[float]:
    return [v for v in (number(c) for c in cells) if v is not None]


def town_titles(text: str, is_local) -> list[str]:
    """The towns named on one page, in the order their annexes appear on it."""
    flat = re.sub(r"\s+", " ", text)
    found = []
    for match in TOWN_TITLE.finditer(flat):
        name = match.group(1)
        if is_local(name) and name not in found:
            found.append(name)
    return found


def read_zones(cells: list[list[str]]) -> dict[str, float]:
    """One town's zones, whether it names them by fiscal letter or by position."""
    zones: dict[str, float] = {}
    for row in cells:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        if len(line) < 3 or NOT_A_ZONE.search(line[1]):
            continue
        price = number(line[2])
        if price is None:
            continue
        letter = ZONE_LETTER.match(line[1])
        code = letter.group(1).upper() if letter else None
        if code is None:
            code = next((c for c, p in POSITION_ZONES if re.search(p, line[1], re.I)), None)
        if code:
            zones.setdefault(code, price)
    return zones


def read_extravilan(cells: list[list[str]], is_local) -> dict[str, dict[str, float]]:
    """Annex 12: every locality's agricultural land, converted from euro per hectare."""
    head = re.sub(r"\s+", " ", " ".join(c or "" for row in cells[:3] for c in row)).lower()
    if "arabil" not in head:
        return {}
    found: dict[str, dict[str, float]] = {}
    for row in cells:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        if len(line) <= max(EXTRA_COLUMNS.values()) or not NAME.match(line[1]):
            continue
        if not is_local(line[1]):
            continue
        values = {code: number(line[at]) for code, at in EXTRA_COLUMNS.items()}
        if values.get("A") is None:
            continue
        prices = {
            code: value / M2_PER_HA
            for code, value in values.items()
            if value is not None and code in ("A", "P+F", "PADURE")
        }
        # Vineyards and orchards are priced apart and share one code here, so they are
        # averaged rather than one of them standing in for both.
        pair = [values[c] for c in ("VII", "LIVEZI") if values[c] is not None]
        if pair:
            prices["V+L"] = sum(pair) / len(pair) / M2_PER_HA
        found[line[1].upper()] = prices
    return found


def read_communes(cells: list[list[str]], is_local) -> dict[str, list[float]]:
    """Every priced commune row out of one of the six geographic annexes.

    Column positions differ between the annexes and there is no caption they share, so the
    row is taken as a whole: the locality is the first cell the register recognises and the
    prices are every figure after it.
    """
    found: dict[str, list[float]] = {}
    for row in cells:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        at = None
        label = ""
        for index, cell in enumerate(line[:3]):
            match = COMMUNE_CELL.match(COMMUNE_PREFIX.sub("", cell))
            if match and is_local(match.group(1)):
                at, label = index, match.group(1)
                break
        if at is None:
            continue
        prices = [p for p in numbers(line[at + 1 :]) if p < 1000]
        if prices:
            found.setdefault(label.upper(), []).extend(prices)
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    towns: dict[str, dict[str, float]] = {}
    flat: dict[str, list[float]] = {}
    extravilan: dict[str, dict[str, float]] = {}
    pages_of: dict[str, int] = {}
    in_extravilan = False

    for index, page in enumerate(pages, start=1):
        if EXTRA_TITLE.search(page["text"]):
            in_extravilan = True
        tables = [[[c or "" for c in row] for row in t["cells"]] for t in page["tables"]]
        if in_extravilan:
            for cells in tables:
                extravilan.update(read_extravilan(cells, is_local))
            continue

        titles = town_titles(page["text"], is_local)
        for cells in tables:
            if not cells:
                continue
            head = re.sub(r"\s+", " ", " ".join(c for row in cells[:2] for c in row))
            if ZONE_TABLE.search(head):
                zones = read_zones(cells)
                if zones and titles:
                    town = titles.pop(0)
                    towns[town.upper()] = zones
                    pages_of.setdefault(town.upper(), index)
                continue
            for key, prices in read_communes(cells, is_local).items():
                flat.setdefault(key, []).extend(prices)
                pages_of.setdefault(key, index)

    zoned = [
        {
            "name": key.title(),
            "rank": None,
            "zones": sorted(prices),
            "intravilan": {"CC": prices},
            "extravilan": extravilan.get(key, {}),
            "page": pages_of.get(key, 1),
        }
        for key, prices in towns.items()
        if len(prices) >= 2
    ]
    communes = []
    for key, prices in flat.items():
        if key in towns:
            continue
        communes.append(
            {
                "name": key.title(),
                "villages": [
                    {"name": f"{key.title()} ({position})", "intravilan": {"CC": price}}
                    for position, price in enumerate(sorted(set(prices), reverse=True), start=1)
                ],
                "extravilan": extravilan.get(key, {}),
                "page": pages_of.get(key, 1),
            }
        )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    return zoned, communes, []

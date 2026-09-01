"""The CNP Oradea dialect for Satu Mare, where the county seat hides in the rural table.

This county was read once before and rejected. The parse reached 93,8% of its localities and
priced Satu Mare — a municipality of a hundred thousand — at 55 lei/m², below several of its own
communes. Coverage was fine and the answer was wrong, which is exactly the failure the
town-to-commune ratio was added to catch.

The cause is a row that is not what it looks like. The rural table is one line per village:

    Nr · Denumirea comunei · Denumirea satelor apartinatoare · Teren intravilan cu constructii
    1  · SATU MARE         · SĂTMAREL                        · 55
    2  · APA               · APA                             · 38
                           · LUNCA APEI                      · 23

The municipality appears in it — but as the **owner of its attached village**. The 55 is
Sătmarel's price, a village on the edge of the city, and reading it as the city's is reading the
wrong column of the right row. The city's own land is priced forty pages earlier, in a zone grid
of its own that the generic reader never looked for.

    Zona-Subzona · Teren liber sau ocupat de constructii (S<2.000 mp) · …
    Zona I       · 500
    Zona II      · 380

**The town's name is on the page before its table.** Each urban unit gets a run of building
tables headed `TABEL CENTRALIZATOR … ÎN MUNICIPIUL SATU MARE` or `… ÎN ORAȘ CAREI`, and the
land grid follows on the next page with no name on it at all. So the heading sets which town
the next land table belongs to, and six towns come out of six tables: Satu Mare at 500 lei/m²
in zone I, Carei at 180, Negrești-Oaș at 75, Tășnad at 65, Ardud at 55, Livada at 48.

Both halves are emitted. A town that also appears in the rural table keeps its zone grid,
because the shared value builder prefers a zoned entry over a village list for the same
locality — the zones price the town and the village list prices its outskirts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# "TABEL CENTRALIZATOR ... ÎN MUNICIPIUL SATU MARE /" and "... ÎN ORAȘ CAREI/IMOBILE" — the
# only place a land grid's town is named, and it is on the previous page.
TOWN_HEADING = re.compile(
    r"[ÎI]N\s+(?:MUNICIPIUL|ORA[ȘŞS]U?L?)\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,}?)\s*(?:/|$)",
    re.M,
)
# The land grid's own caption. "Zona-Subzona" alone is not enough: sixty-seven tables in this
# document carry it and sixty-one of them price buildings.
LAND_TABLE = re.compile(r"teren\s+(?:liber|ocupat)", re.I)
ZONE_ROW = re.compile(r"^\s*zona\s+([IVX]+)\s*$", re.I)
ROMAN = {"I": "A", "II": "B", "III": "C", "IV": "D", "V": "E"}
# The rural table, one row per village.
COMMUNE_TABLE = re.compile(r"denumirea\s+comunei", re.I)
# "Teren intravilan cu suprafata..." in one circumscription and a bare "Intravilan cu S <
# 2.000" in another. The word the two share is the one to match on.
BUILT_COLUMN = re.compile(r"(?:teren\s+)?intravilan\s+cu", re.I)
# Two of the county's four rural tables carry extravilan columns; the other two price building
# land and buildings only.
#
# **Both Romanian t's and both s's.** The heading is FÂNEAŢĂ with a cedilla — U+0163 — and the
# pattern was written with the comma-below ț, U+021B, which is the letter the 1993 orthography
# actually calls for. They look identical at this size and are different characters, so pasture
# and hayfield matched nothing at all and the column was silently never read.
T = "țţ"
S = "șş"
EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("A", r"arabil"),
    ("V+L", r"vii|livezi"),
    ("PADURE", r"p[ăa]duri"),
    ("P+F", rf"f[âa]nea[{T}]|f[âa]ne[{T}]e|p[ăa][{S}]un"),
]
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
# Each urban unit gets two small tables of its own beside its zone grid: arable split by
# whether the plot is inside or outside the first plan, and forest by species. They name the
# town in their first column, so unlike the zone grid they need no heading to be attributed.
TOWN_ARABLE = re.compile(r"terenuri\s+arabile", re.I)
TOWN_FOREST = re.compile(r"vegeta[țţt]ie\s+forestier", re.I)


def number(cell: str) -> float | None:
    """A price in lei; the thousands dot appears in the building columns, not the land ones."""
    text = re.sub(r"\s+", "", cell or "")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?", text):
        return None
    value = float(text.replace(".", "").replace(",", "."))
    return value if 0 < value < 100_000 else None


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def column_of(cells: list[list[str]], pattern: re.Pattern[str], rows: int = 2) -> int | None:
    """The index of the column whose caption matches, read down the header rows."""
    width = max((len(row) for row in cells[:rows]), default=0)
    for index in range(width):
        caption = " ".join(clean(row[index]) for row in cells[:rows] if index < len(row))
        if pattern.search(caption):
            return index
    return None


def read_town(cells: list[list[str]]) -> dict[str, float]:
    """One town's zones. The first land column is the one under 2 000 m², which is a plot."""
    target = column_of(cells, LAND_TABLE)
    if target is None:
        return {}
    zones: dict[str, float] = {}
    for row in cells:
        line = [clean(c) for c in row]
        if not line:
            continue
        roman = ZONE_ROW.match(line[0])
        price = number(line[target]) if target < len(line) else None
        if roman and price is not None:
            zones.setdefault(ROMAN.get(roman.group(1).upper(), roman.group(1).upper()), price)
    return zones


def read_extravilan(cells: list[list[str]], is_local) -> dict[str, dict[str, float]]:
    """Agricultural and forest prices, where the circumscription's table publishes them.

    Only one of the county's rural tables carries these columns. The others price building
    land and buildings and nothing else, which is the document's choice and not a gap in the
    reading.
    """
    mapped: dict[int, str] = {}
    for code, pattern in EXTRA_COLUMNS:
        index = column_of(cells, re.compile(pattern, re.I))
        if index is not None and index not in mapped:
            mapped[index] = code
    if "A" not in mapped.values():
        return {}
    found: dict[str, dict[str, float]] = {}
    current: str | None = None
    for row in cells:
        line = [clean(c) for c in row]
        if len(line) < 3:
            continue
        if line[1] and NAME.match(line[1]) and is_local(line[1]):
            current = line[1]
        if current is None:
            continue
        prices = {
            code: number(line[index])
            for index, code in mapped.items()
            if index < len(line) and number(line[index]) is not None
        }
        if prices:
            found.setdefault(current.upper(), prices)
    return found


def read_town_extravilan(cells: list[list[str]], is_local) -> dict[str, dict[str, float]]:
    """A town's own arable and forest, from the two small tables printed beside its zone grid.

    The arable table gives two figures — inside the first plan and outside it — and the dearer
    is taken, because it is the one for land next to the town, which is what a town's
    extravilan mostly is.
    """
    joined = " ".join(clean(c) for row in cells[:2] for c in row)
    arable = bool(TOWN_ARABLE.search(joined))
    forest = bool(TOWN_FOREST.search(joined))
    if not (arable or forest):
        return {}
    found: dict[str, dict[str, float]] = {}
    for row in cells:
        line = [clean(c) for c in row]
        if not line or not NAME.match(line[0]) or not is_local(line[0]):
            continue
        figures = [v for v in (number(c) for c in line[1:]) if v is not None]
        if not figures:
            continue
        found[line[0].upper()] = (
            {"A": max(figures)} if arable else {"PADURE": figures[-1]}
        )
    return found


def read_communes(cells: list[list[str]], is_local) -> dict[str, list[tuple[str, float]]]:
    """(village, price) per commune, out of the rural table.

    The commune cell is filled only on its first village and blank underneath, so the last one
    seen is carried forward — the same shape as every other chamber's rural annex.
    """
    if not COMMUNE_TABLE.search(" ".join(clean(c) for row in cells[:2] for c in row)):
        return {}
    target = column_of(cells, BUILT_COLUMN)
    if target is None:
        return {}
    found: dict[str, list[tuple[str, float]]] = {}
    current: str | None = None
    for row in cells:
        line = [clean(c) for c in row]
        if len(line) < 3:
            continue
        commune, village = line[1], line[2]
        if commune and NAME.match(commune) and is_local(commune):
            current = commune
        if current is None:
            continue
        price = number(line[target]) if target < len(line) else None
        if price is not None and village and NAME.match(village):
            found.setdefault(current.upper(), []).append((village, price))
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    towns: list[dict] = []
    communes: dict[str, list[tuple[str, float]]] = {}
    extravilan: dict[str, dict[str, float]] = {}
    pages_of: dict[str, int] = {}
    heading: str | None = None

    for index, page in enumerate(pages, start=1):
        found = TOWN_HEADING.findall(re.sub(r"\s+", " ", page["text"]))
        if found:
            heading = re.sub(r"\s+", " ", found[-1]).strip()
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 3:
                continue
            for key, rows in read_communes(cells, is_local).items():
                communes.setdefault(key, []).extend(rows)
                pages_of.setdefault(key, index)
            for key, prices in read_extravilan(cells, is_local).items():
                extravilan.setdefault(key, prices)
            for key, prices in read_town_extravilan(cells, is_local).items():
                extravilan.setdefault(key, {}).update(prices)
            zones = read_town(cells)
            # A land grid with no town named above it belongs to nobody, and guessing would
            # be guessing: this is the county where the wrong town cost the whole parse.
            if zones and heading and is_local(heading):
                towns.append(
                    {
                        "name": heading.title(),
                        "rank": None,
                        "zones": sorted(zones),
                        "intravilan": {"CC": zones},
                        "extravilan": {},
                        "page": index,
                        "key": heading.upper(),
                    }
                )

    # The towns' own extravilan is found in tables that may come after their zone grid, so it
    # is attached once everything has been read rather than as each town is built.
    for town in towns:
        town["extravilan"] = extravilan.get(town.pop("key"), {})

    entries = []
    for key, rows in communes.items():
        seen: set[tuple[str, float]] = set()
        villages = []
        for village, price in rows:
            if (village, price) in seen:
                continue
            seen.add((village, price))
            villages.append({"name": village, "intravilan": {"CC": price}})
        entries.append(
            {
                "name": key.title(),
                "villages": villages,
                "extravilan": extravilan.get(key, {}),
                "page": pages_of.get(key, 1),
            }
        )
    for position, entry in enumerate(entries, start=1):
        entry["index"] = position
    return towns, entries, []

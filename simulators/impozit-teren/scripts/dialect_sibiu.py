"""The CNP Alba Iulia dialect for Sibiu, which prints its captions sideways.

Sibiu's grids are two clean tables, and the generic reader reached neither of them properly
for the same reason: the column captions are printed **rotated**, so they arrive as their
letters reversed and interleaved — `lib a rA` is *Arabil*, `iru d ă P` is *Păduri*. No caption
matcher can read those, and a reader that gives up on captions has nothing left to go on.

What it does have is position, and here position is trustworthy in a way it usually is not:
both tables keep the same shape for their whole run, and the two captions that *are* printed
upright — COMUNA/SAT and Localitate/Amplasare — say which table is which. So the columns are
read by their offsets from a header this asserts rather than guesses at, and a table whose
header does not match is skipped rather than read hopefully.

    communes   COMUNA · SAT · construcţii centru · construcţii periferie · agricol ·
               arabil · păşuni-fâneţe · vii-livezi · păduri · alte terenuri
    towns      Localitate · Zona A–D · construcţii · alte terenuri · then extravilan

**Building land is priced twice for every village** — once for the centre and the main street,
once for the periphery — which none of the other chambers do. The two are averaged into the
single figure the shared model carries; the spread between them is real and is lost here,
which is worth knowing when Sibiu's band looks narrower than its neighbours'.

Towns carry their attached villages in the same table as unzoned rows, and those are kept:
they are the town's land as much as its centre is.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# Column offsets, asserted against the upright captions rather than assumed.
COMMUNE_COLUMNS = {"commune": 0, "village": 1, "centre": 2, "edge": 3}
COMMUNE_EXTRA = {"A": 5, "P+F": 6, "V+L": 7, "PADURE": 8, "NP": 9}
TOWN_COLUMNS = {"town": 0, "zone": 1, "cc": 2}
TOWN_EXTRA = {"A": 4, "V+L": 5, "P+F": 6, "NP": 7}
ZONE_CELL = re.compile(r"zona\s*([A-D])", re.I)
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)


def number(cell: str) -> float | None:
    text = cell.strip().replace(" ", "")
    if not re.fullmatch(r"\d{1,6}([.,]\d+)?", text):
        return None
    value = float(text.replace(",", "."))
    return value if 0 < value < 100_000 else None


def is_commune_table(cells: list[list[str]]) -> bool:
    head = re.sub(r"\s+", " ", " ".join(c for row in cells[:2] for c in row)).upper()
    return "COMUNA" in head and "SAT" in head and len(cells[0]) >= 9


def is_town_table(cells: list[list[str]]) -> bool:
    head = re.sub(r"\s+", " ", " ".join(c for row in cells[:2] for c in row)).lower()
    return "localitate" in head and "amplasare" in head and len(cells[0]) >= 7


def at(cells: list[str], index: int) -> str:
    """One cell, with its internal wrapping flattened.

    A name that does not fit its cell wraps inside it, so ARPAŞU DE JOS arrives with a
    newline in the middle. Every one of the eight communes this reader first missed had a
    multi-word name for exactly that reason.
    """
    if not 0 <= index < len(cells):
        return ""
    return re.sub(r"\s+", " ", cells[index]).strip()


def read_communes(cells: list[list[str]], is_local) -> list[dict]:
    found: list[dict] = []
    current: dict | None = None
    carried: list[float] = []
    for row in cells:
        line = [c.strip() for c in row]
        commune = at(line, COMMUNE_COLUMNS["commune"])
        village = at(line, COMMUNE_COLUMNS["village"])
        if commune and NAME.match(commune) and is_local(commune):
            current = {"name": commune, "villages": [], "extravilan": {}}
            found.append(current)
            carried = []
        if current is None or not village or not NAME.match(village):
            continue
        centre = number(at(line, COMMUNE_COLUMNS["centre"]))
        edge = number(at(line, COMMUNE_COLUMNS["edge"]))
        published = [x for x in (centre, edge) if x is not None]
        # A blank is a merged cell: the village shares the price printed above it. Without
        # this the county came back with 76 villages instead of about 160, because most rows
        # after a commune's first carry no price of their own.
        if published:
            carried = published
        else:
            published = carried
        if published:
            # The two readings of the same village averaged into the one figure the shared
            # model carries. Documented rather than silent: Sibiu is the only chamber that
            # prices a village's centre and its edge separately.
            current["villages"].append(
                {"name": village, "intravilan": {"CC": sum(published) / len(published)}}
            )
        extravilan = {
            code: number(at(line, index))
            for code, index in COMMUNE_EXTRA.items()
            if number(at(line, index)) is not None
        }
        if extravilan and not current["extravilan"]:
            current["extravilan"] = extravilan
    return [x for x in found if x["villages"]]


def read_towns(cells: list[list[str]], is_local) -> tuple[list[dict], list[dict]]:
    """Towns by zone, and the villages attached to them, which share the same table."""
    towns: list[dict] = []
    attached: list[dict] = []
    current: dict | None = None
    for row in cells:
        line = [c.strip() for c in row]
        label = at(line, TOWN_COLUMNS["town"])
        zone_cell = at(line, TOWN_COLUMNS["zone"])
        price = number(at(line, TOWN_COLUMNS["cc"]))
        if label and NAME.match(label) and is_local(label):
            current = {
                "name": label,
                "rank": None,
                "zones": [],
                "intravilan": {"CC": {}},
                "extravilan": {},
                "page": 0,
            }
            towns.append(current)
            extravilan = {
                code: number(at(line, index))
                for code, index in TOWN_EXTRA.items()
                if number(at(line, index)) is not None
            }
            current["extravilan"] = extravilan
        zone = ZONE_CELL.search(zone_cell)
        if current is not None and zone and price is not None:
            current["zones"].append(zone.group(1))
            current["intravilan"]["CC"][zone.group(1)] = price
        elif current is not None and not zone and price is not None and label and NAME.match(label):
            # A row with a name and a price but no zone is a village of the town above it.
            attached.append(
                {
                    "name": label,
                    "villages": [{"name": label, "intravilan": {"CC": price}}],
                    "extravilan": {},
                }
            )
    return [t for t in towns if t["zones"]], attached


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    communes: list[dict] = []
    towns: list[dict] = []
    for index, page in enumerate(pages):
        for table in page["tables"]:
            cells = table["cells"]
            if len(cells) < 4:
                continue
            if is_commune_table(cells):
                for entry in read_communes(cells, is_local):
                    entry["page"] = index + 1
                    communes.append(entry)
            elif is_town_table(cells):
                found, attached = read_towns(cells, is_local)
                for town in found:
                    town["page"] = index + 1
                    towns.append(town)
                for entry in attached:
                    entry["page"] = index + 1
                    communes.append(entry)
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    return towns, communes, []

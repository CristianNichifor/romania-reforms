"""Giurgiu, whose category assignment is a table and whose extravilan is priced three ways.

Same chamber and same conventions as Călărași — categories, the seven extravilan multipliers,
land under a building at 70% of free land — laid out differently enough to need its own reader.

**The assignment is a table, not prose**, and it carries both levels at once:

    Comuna / Categoria          Satul / Categoria
    Adunaţii Copăceni  cat. I   Adunaţii Copăceni  cat. I
                                Darasti Vlasca     cat. I
                                Mogosesti          cat. I
    Baneasa            cat. I   Baneasa            cat. I
                                Frasinu            cat. II

The commune cell is filled once and blank underneath, and a village may sit in a different
category from its own commune — Frasinu is II inside a commune that is I. So the village's own
category is used where it has one, which is the whole point of the table having two columns.

**Extravilan is priced by what the land could become, not only by what it is.** The table gives
three figures per locality under criteria rather than categories of soil:

    Amplasament   Categoria I           Categoria II        Categoria III
                  posibil de transferat situat în planul II destinaţie exclusiv
                  în intravilan                             agricolă
    Giurgiu       49.100                25.600              5.750

Nine times between the ends. **Categoria III is the one taken** — the hectares this simulator
prices are the land register's agricultural categories, and land that is *"posibil de
transferat în intravilan"* is a development option priced as one. Taking column I would have
valued Giurgiu's farmland at nine times what the study says farmland is worth.

**The two circumscriptions zone their towns differently.** Giurgiu town has numbered zones;
Mihăilești and Bolintin Vale are split by place instead — `Mihailesti centru`, `Mihailesti
lac`, `Mihailesti periferie` — with no zone numbering at all, and the lake is worth more than
the centre. Those are ordered by price and lettered, the same treatment Ilfov's towns get,
because a zone letter here means a value band and the document supplies no other ordering.

One commune is priced outside the categories: `Parcul Natural COMANA` appears as a column of
its own at 24,6 EUR/m² against 8,6 for category I.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnpb_common import (  # noqa: E402
    DOT_LEADER,
    OCCUPIED_SHARE,
    clean,
    county_pages,
    extravilan_from,
    fold,
    names_in,
    per_ha,
    per_m2,
    zone_letter,
)
from extract_cache import load  # noqa: E402

ASSIGNMENT_HEADER = re.compile(r"Comuna\s*/\s*Categoria", re.I)
RURAL_TABLE = re.compile(r"Categorie\s*localitate\s*rural", re.I)
VALUE_ROW = re.compile(r"Valoare\s+(?:minima|teren)", re.I)
TOWN_LAND = re.compile(r"^Teren\s+(.+)$", re.I)
EXTRA_TABLE = re.compile(r"Criterii\s+de\s+particularizare", re.I)
AGRICULTURAL_ONLY = re.compile(r"exclusiv", re.I)
FOREST_HEADING = re.compile(r"TERENURI\s+CU\s+VEGETATIE\s+FORESTIERA", re.I)


def read_assignment(pages: list[dict], within: list[int], is_local) -> dict[str, tuple[str, str]]:
    """Village to (category letter, its commune), from the two-column assignment table."""
    found: dict[str, tuple[str, str]] = {}
    for index in within:
        for table in pages[index - 1].get("tables") or []:
            cells = [[clean(c) for c in row] for row in table["cells"]]
            if not cells or not any(ASSIGNMENT_HEADER.search(c) for c in cells[0]):
                continue
            commune = ""
            for row in cells[1:]:
                # The commune is named once and left blank on its other villages, so the last
                # one seen is carried forward — the shape every rural annex in this repository
                # turns out to use.
                if len(row) >= 2 and row[0] and is_local(row[0]):
                    commune = row[0]
                if not commune or len(row) < 4:
                    continue
                village, label = row[2], row[3]
                letter = zone_letter(label)
                if village and letter:
                    found.setdefault(fold(village), (letter, commune))
    return found


def read_prices(page: dict, is_local) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """(towns to zones, category letter to price) from one circumscription's land page."""
    towns: dict[str, dict[str, float]] = {}
    categories: dict[str, float] = {}
    for table in page.get("tables") or []:
        cells = [[clean(c) for c in row] for row in table["cells"]]
        if len(cells) < 2:
            continue
        header, rows = cells[0], cells[1:]
        row = next((r for r in rows if any(VALUE_ROW.search(c) for c in r)), rows[0])

        if any(RURAL_TABLE.search(c) for c in header):
            for index, label in enumerate(header):
                if index >= len(row) or (price := per_m2(row[index])) is None:
                    continue
                letter = zone_letter(label)
                if letter:
                    categories[letter] = price
                else:
                    # A commune priced outside the categories, named in its own column.
                    for name in names_in(label, is_local):
                        towns.setdefault(name, {})["A"] = price
            continue

        # A town table: either "Teren <town>" with numbered zones, or one column per named
        # place within the town. Both end up as a value band lettered from the top.
        named = next((TOWN_LAND.match(c) for c in header if TOWN_LAND.match(c)), None)
        if named:
            town = clean(named.group(1))
            if not is_local(town):
                continue
            for index, label in enumerate(header):
                if index >= len(row) or (price := per_m2(row[index])) is None:
                    continue
                zone = re.search(r"Zona\s+([IVX]+|[A-F])", label, re.I)
                letter = zone_letter(f"Categoria {zone.group(1)}") if zone else "A"
                towns.setdefault(town, {}).setdefault(letter or "A", price)
            continue

        by_place: dict[str, list[float]] = {}
        for index, label in enumerate(header):
            price = per_m2(row[index]) if index < len(row) else None
            if price is None:
                continue
            for name in names_in(label, is_local):
                by_place.setdefault(name, []).append(price)
        for town, prices in by_place.items():
            ordered = sorted(set(prices), reverse=True)
            towns.setdefault(town, {}).update(
                {chr(ord("A") + position): value for position, value in enumerate(ordered)}
            )
    return towns, categories


SECOND_PLANE = re.compile(r"planul\s*II", re.I)
SPECIFICATION = re.compile(r"Specifica[țţt]ie", re.I)


def read_extravilan(
    pages: list[dict], within: list[int], is_local
) -> tuple[dict[str, float], float | None]:
    """(named localities, county-wide) euro per hectare for ordinary farmland.

    Two tables, and the county-wide one is the one that matters. The first prices only the
    three towns and a stretch of the DN5, under criteria rather than soil:

        Amplasament   Categoria I            Categoria II       Categoria III
                      posibil de transferat  situat în planul II  destinaţie exclusiv
                      în intravilan                               agricolă
        Giurgiu       49.100                 25.600               5.750

    Nine times between the ends, so **Categoria III is taken** — the hectares priced here are
    the register's agricultural ones, and land *"posibil de transferat în intravilan"* is a
    development option, not farmland. Column I would have valued Giurgiu's fields at nine
    times what this study says fields are worth.

    Everything else — all fifty-one communes — falls under the second table, which gives one
    figure for the county by position rather than by place: 6 560 at the edge of a locality,
    **5 300 in the second plane**, 2 920 unproductive. The second plane is where the hectares
    are, so that is the arable figure the communes take.

    Worth noting rather than smoothing over: the chamber's own unproductive figure, 2 920, is
    10% above what its published coefficient would give from 5 300 (0,5 × 5 300 = 2 650). The
    coefficients are used anyway, for consistency with the other counties of this volume, and
    the disagreement is the document's rather than this reader's.
    """
    named: dict[str, float] = {}
    county_wide: float | None = None
    for index in within:
        for table in pages[index - 1].get("tables") or []:
            cells = [[clean(c) for c in row] for row in table["cells"]]
            flat = " ".join(c for row in cells[:3] for c in row)
            if not EXTRA_TABLE.search(flat):
                continue

            column = None
            wanted = SPECIFICATION if any(SPECIFICATION.search(c) for c in cells[0]) else None
            for row in cells[:4]:
                for position, cell in enumerate(row):
                    if (wanted and SECOND_PLANE.search(cell)) or (
                        not wanted and AGRICULTURAL_ONLY.search(cell)
                    ):
                        column = position
                if column is not None:
                    break
            if column is None:
                continue

            for row in cells:
                price = per_ha(row[column]) if column < len(row) else None
                if price is None:
                    continue
                if wanted:
                    county_wide = county_wide or price
                    continue
                name = next((c for c in row[:2] if c and is_local(c)), None)
                if name:
                    named.setdefault(fold(name), price)
    return named, county_wide


def read_forest(pages: list[dict], within: list[int]) -> float | None:
    """One county-wide forest price: the median of the species the study lists."""
    for index in within:
        text = pages[index - 1].get("text") or ""
        if not FOREST_HEADING.search(text):
            continue
        prices = sorted(
            v
            for token in re.findall(r"\d{1,3}(?:\.\d{3})+", text)
            if (v := per_ha(token)) is not None and 1_000 <= v <= 50_000
        )
        if prices:
            middle = len(prices) // 2
            return (
                prices[middle]
                if len(prices) % 2
                else (prices[middle - 1] + prices[middle]) / 2
            )
    return None


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    within = county_pages(pages, "Giurgiu")
    if not within:
        return [], [], ["no page carries the county header"]

    arable, county_wide = read_extravilan(pages, within, is_local)
    forest = read_forest(pages, within)

    # Assignments and prices are matched **per circumscription**, in page order. Giurgiu's two
    # circumscriptions price the same three categories differently — 8,6 against 11,1 for the
    # first — and the assignment tables come pages before the prices that apply to them. A
    # single merged dictionary of categories priced every village in the county from whichever
    # circumscription happened to be read first, which is a third of a county silently wrong
    # and reads as nothing at all: the names all match and the numbers are all real.
    towns: dict[str, dict[str, float]] = {}
    assigned: dict[str, tuple[str, str]] = {}
    pending: dict[str, tuple[str, str]] = {}
    priced: dict[str, tuple[str, str, float]] = {}
    for index in within:
        page = pages[index - 1]
        text = page.get("text") or ""
        pending.update(read_assignment(pages, [index], is_local))
        if DOT_LEADER.search(text) or not re.search(r"\bteren", text, re.I):
            continue
        found_towns, categories = read_prices(page, is_local)
        for town, zones in found_towns.items():
            towns.setdefault(town, {}).update(zones)
        if not categories:
            continue
        for key, (letter, commune) in pending.items():
            price = categories.get(letter)
            if price is not None:
                priced.setdefault(key, (letter, commune, price))
        assigned.update(pending)
        pending.clear()

    def occupied(value: float) -> float:
        return round(value * OCCUPIED_SHARE, 4)

    extravilan_of = {key: extravilan_from(price) for key, price in arable.items()}
    fallback = extravilan_from(county_wide) if county_wide else {}
    if forest:
        for grid in (*extravilan_of.values(), fallback):
            if grid:
                grid["PADURE"] = round(forest / 10_000, 6)

    communes: dict[str, dict] = {}
    for key, (_letter, commune, price) in priced.items():
        entry = communes.setdefault(fold(commune), {"name": commune, "villages": []})
        entry["villages"].append({"name": key.title(), "intravilan": {"CC": occupied(price)}})

    zoned = [
        {
            "name": town,
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": {z: occupied(v) for z, v in zones.items()}},
            "extravilan": extravilan_of.get(fold(town), dict(fallback)),
            "page": 1,
        }
        for town, zones in towns.items()
    ]
    entries = []
    for position, (key, entry) in enumerate(sorted(communes.items()), start=1):
        entries.append(
            {
                "name": entry["name"],
                "villages": entry["villages"],
                "extravilan": extravilan_of.get(key, dict(fallback)),
                "page": 1,
                "index": position,
            }
        )
    notes = [] if priced else ["no village matched a priced category"]
    if pending:
        notes.append(f"{len(pending)} sate repartizate fără preț de categorie")
    del assigned
    return zoned, entries, notes

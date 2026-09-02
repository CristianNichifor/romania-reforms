"""Călărași, where the villages are named in prose and priced in a table three pages away.

This is the fourth chamber layout and it recombines pieces already met. Rural land is priced by
**category**, as in Vaslui, and the assignment is a numbered prose list rather than a table. The
extravilan grid is **one arable column and the chamber's published coefficients**, as in Ilfov —
same seven multipliers, same chamber. What is new is that the prose list works at *village*
level and names each village's parent commune, so the join is finer than anywhere else here:

    CATEGORIA I
    Sate
    1.Borcea
    2.Bogata-com.Gradistea
    9.Rasa-com.Gradistea 10.Roseti

Borcea is a commune seat; Bogata and Rasa are villages of Grădiștea. Two entries share the last
line, which is why this splits on the numbering rather than on line breaks.

**Three circumscriptions, and their section numbers do not line up.** Călărași uses 3.2.2 for
the rural zoning, Oltenița 4.2.2 and Lehliu Gară **5.2.4** — so the blocks are grouped by the
leading integer of whatever heading is found, and the headings are matched on their titles.
Matching on the number would have silently dropped the third circumscription's assignment and
left a third of the county's villages unpriced.

**The urban table changes shape between them**, which is the part that resists a fixed reader:

    Teren Calarasi        | Zona I | Zona II | Zona III          one town, roman zones
    Localitatea, Zona     | Oltenita Zona A | … | Oras Budesti   one zoned town plus a flat one
    Lehliu Gara Fundulea  | Zona I | Zona II | Zona III          two towns sharing one row

So a column header is read for a town name of its own first, and falls back to the towns named
in the corner cell — which may be two.

**Occupied land is 70% of free land, and the study says so**: *"Pentru terenurile ocupate de
constructii valorile inscrise in tabele se diminueaza cu 30%."* The tables print free land; the
hectares this simulator prices are the register's *Ocupată cu construcții*, so the ratio is
applied rather than assumed — the same 0,70 București uses, from the same chamber.

**Two agricultural tables sit on the same page and only one is wanted.** `x.5.2` prices land
adjacent to major roads — Fundulea at 31 400 EUR/ha — and `x.5.3` prices land that is
exclusively agricultural, at 7 500. Telling them apart by size would be guessing; they are told
apart by their columns, because the roadside table carries a `Calea rutiera` column and the
agricultural one does not.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# The county's own pages inside a volume that carries four counties.
COUNTY_HEADER = re.compile(r"valorile minime imobiliare [îi]n jud\.\s*([A-Za-zăâîșțĂÂÎȘȚ]+)", re.I)

HEADINGS = {
    "zonare": re.compile(
        r"^(\d+)\.[\d.]*\s*Zonarea\s+localitatilor\s+rurale", re.I
    ),
    "urban": re.compile(
        r"^(\d+)\.[\d.]*\s*Terenuri\s+intravilane\s+situate\s+in\s+mediul\s+URBAN", re.I
    ),
    "rural": re.compile(
        r"^(\d+)\.[\d.]*\s*Terenuri\s+intravilane\s+situate\s+in\s+mediul\s+RURAL", re.I
    ),
    "arabil": re.compile(
        r"^(\d+)\.[\d.]*\s*Terenuri\s+cu\s+destinatie\s+exclusiv\s+agricola", re.I
    ),
}
# The contents pages repeat every heading verbatim, followed by dot leaders and a page number,
# and they come first — so a scan that keeps the first match of each heading finds the index
# rather than the section, points every circumscription at page 7, and prices nothing at all.
DOT_LEADER = re.compile(r"\.{4,}")

CATEGORY_HEADING = re.compile(r"CATEGORIA\s+([IVX]+)\b")
# "1.Borcea", "2. Bogata-com.Gradistea", "10.Roseti" — several to a line.
ENTRY = re.compile(r"\d{1,2}\s*\.\s*([^0-9]+?)(?=\s*\d{1,2}\s*\.|$)")
# "Bogata-com.Gradistea", "Pasarea – com. Frumusani", "Gruiu – oras Budesti"
PARENT = re.compile(r"^(.*?)\s*[-–—]\s*(?:com\.?|oras(?:ul)?|orașul)\s*(.+)$", re.I)
ROMAN = {"I": "A", "II": "B", "III": "C", "IV": "D", "V": "E", "VI": "F"}
ZONE_IN_HEADER = re.compile(r"Zona\s+([A-F]|[IVX]+)\b", re.I)
VALUE_ROW = re.compile(r"Valoare\s+minima", re.I)
# "Categoria I", "Categoria I-a", "Categoria a II-a" — Romanian writes the ordinal both ways
# and the column headers use both in the same county. A pattern without the optional "a"
# matched the first category and not the second, which quietly priced every village of the
# second category at nothing.
CATEGORY_COLUMN = re.compile(r"Categoria\s+(?:a\s+)?([IVX]+)\s*(?:-\s*a)?\b", re.I)
ROADSIDE = re.compile(r"Calea\s+rutiera", re.I)
AMPLASAMENT = re.compile(r"Amplasament", re.I)
# The chamber's published corrections, identical across all four counties in this volume.
FROM_ARABLE: dict[str, float] = {
    "A": 1.0, "V+L": 1.1, "P+F": 0.8, "AP": 1.4, "DR": 0.7, "NP": 0.5,
}
# "valorile inscrise in tabele se diminueaza cu 30%" for land under a building.
OCCUPIED_SHARE = 0.70
M2_PER_HA = 10_000


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def per_m2(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:,\d{1,2})?", stripped):
        return None
    value = float(stripped.replace(",", "."))
    return value if 0 < value < 1_000 else None


def per_ha(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", stripped):
        return None
    value = float(stripped.replace(".", ""))
    return value if 100 <= value < 1_000_000 else None


def county_pages(pages: list[dict], county: str) -> list[int]:
    """The page numbers belonging to one county of a four-county volume."""
    wanted = fold(county)
    return [
        index
        for index, page in enumerate(pages, start=1)
        if (found := COUNTY_HEADER.search(page.get("text") or ""))
        and fold(found.group(1)) == wanted
    ]


def sections(pages: list[dict], within: list[int]) -> dict[int, dict[str, int]]:
    """Which page holds which heading, grouped by the circumscription's leading number."""
    found: dict[int, dict[str, int]] = {}
    for index in within:
        for line in (pages[index - 1].get("text") or "").splitlines():
            text = clean(line)
            if DOT_LEADER.search(text):
                continue
            for kind, pattern in HEADINGS.items():
                match = pattern.match(text)
                if match:
                    found.setdefault(int(match.group(1)), {}).setdefault(kind, index)
    return found


RURAL_HEADER = re.compile(r"Categorie\s*\n?\s*localitate|Categoria\s+[IVX]+", re.I)


def value_tables(page: dict) -> list[list[list[str]]]:
    """Every table on the page that has a `Valoare minima` row, cleaned."""
    found = []
    for table in page.get("tables") or []:
        cells = [[clean(c) for c in row] for row in table["cells"]]
        if any(any(VALUE_ROW.search(c) for c in row) for row in cells):
            found.append(cells)
    return found


def names_in(text: str, is_local) -> list[str]:
    """The localities named in a header cell, longest first.

    "Teren Calarasi" is one town and a noun; "Lehliu Gara Fundulea" is two towns, one of which
    is two words. Splitting on whitespace finds Fundulea and Calarasi and misses Lehliu-Gara;
    taking the whole cell finds nothing. So every run of consecutive words is offered to the
    register, longest first, and a match consumes the words it used.
    """
    words = [w for w in re.split(r"[\s,]+", clean(text)) if w]
    found: list[str] = []
    position = 0
    while position < len(words):
        for length in range(min(3, len(words) - position), 0, -1):
            candidate = " ".join(words[position : position + length])
            if is_local(candidate):
                found.append(candidate)
                position += length
                break
        else:
            position += 1
    return found


def read_categories(page: dict) -> dict[str, float]:
    """Category letter to euro per square metre, from the *rural* intravilan table.

    The urban and the rural table sit on the same page and both carry a `Valoare minima` row,
    so taking the first one read Călărași's three urban zones as though they were rural
    categories — and then no village matched a category at all. The rural one is the one whose
    header names categories.

    A commune given a column of its own comes back under `=its name`: Oltenița's table prices
    Frumușani beside its three categories, and that beats the category the village lists would
    otherwise give it.
    """
    for cells in value_tables(page):
        header = cells[0]
        if not any(RURAL_HEADER.search(c) for c in header) and not any(
            RURAL_HEADER.search(c) for c in cells[1] if len(cells) > 1
        ):
            continue
        row = next(r for r in cells if any(VALUE_ROW.search(c) for c in r))
        found: dict[str, float] = {}
        for index, label in enumerate(header):
            if index >= len(row) or (price := per_m2(row[index])) is None:
                continue
            category = CATEGORY_COLUMN.search(label)
            if category:
                found[ROMAN.get(category.group(1).upper(), category.group(1).upper())] = price
            elif label and "categorie" not in label.lower():
                found[f"={label}"] = price
        if found:
            return found
    return {}


def read_towns(page: dict, is_local) -> dict[str, dict[str, float]]:
    """Town to zone to price, from the *urban* intravilan table."""
    towns: dict[str, dict[str, float]] = {}
    for cells in value_tables(page):
        header = cells[0]
        if any(RURAL_HEADER.search(c) for c in header):
            continue
        row = next(r for r in cells if any(VALUE_ROW.search(c) for c in r))
        # The corner cell names the town or towns that the bare "Zona I" columns belong to.
        corner = names_in(header[0], is_local) if header else []
        for index, label in enumerate(header):
            if index >= len(row) or (price := per_m2(row[index])) is None:
                continue
            zone = ZONE_IN_HEADER.search(label)
            letter = ROMAN.get(zone.group(1).upper(), zone.group(1).upper()) if zone else "A"
            named = names_in(ZONE_IN_HEADER.sub("", label), is_local)
            for town in named or corner:
                towns.setdefault(town, {}).setdefault(letter, price)
    return towns


def read_assignment(
    pages: list[dict], first: int, last: int, is_local
) -> dict[str, tuple[str, str]]:
    """Village to (category letter, parent commune), from the numbered prose list."""
    found: dict[str, tuple[str, str]] = {}
    category: str | None = None
    for index in range(first, last + 1):
        for line in (pages[index - 1].get("text") or "").splitlines():
            text = clean(line)
            heading = CATEGORY_HEADING.search(text)
            if heading:
                category = ROMAN.get(heading.group(1).upper(), heading.group(1).upper())
                continue
            if category is None:
                continue
            for raw in ENTRY.findall(text):
                item = re.sub(r"\*+\)?", "", raw).strip(" .,-–—")
                if not item:
                    continue
                parent = PARENT.match(item)
                village = clean(parent.group(1)) if parent else item
                commune = clean(parent.group(2)) if parent else item
                if is_local(commune) and len(village) > 2:
                    found.setdefault(fold(village), (category, commune))
    return found


def read_arable(page: dict, is_local) -> dict[str, float]:
    """Locality to euro per hectare, from the exclusively-agricultural table.

    The roadside table shares the page and is six times dearer; it is excluded by its own
    `Calea rutiera` column rather than by being the smaller or the first.
    """
    found: dict[str, float] = {}
    for table in page.get("tables") or []:
        cells = [[clean(c) for c in row] for row in table["cells"]]
        header = " ".join(cells[0]) if cells else ""
        if ROADSIDE.search(header) or not AMPLASAMENT.search(header):
            continue
        where = next(
            (i for i, c in enumerate(cells[0]) if AMPLASAMENT.search(c)), None
        )
        if where is None:
            continue
        for row in cells[1:]:
            # By column, not by "the first cell that looks like a name": the row opens with a
            # sequence number, and a number is not a locality only because is_local says so.
            name = row[where] if where < len(row) else ""
            price = next((v for v in (per_ha(c) for c in row) if v is not None), None)
            if name and price and is_local(name):
                found.setdefault(fold(name), price)
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    document = load(name)
    pages = document["pages"]
    within = county_pages(pages, "Călărași")
    if not within:
        return [], [], ["no page carries the county header"]

    blocks = sections(pages, within)
    notes: list[str] = []
    towns: dict[str, dict[str, float]] = {}
    villages: dict[str, dict] = {}
    arable: dict[str, float] = {}

    ordered = sorted(blocks)
    for position, number in enumerate(ordered):
        block = blocks[number]
        # The prose list runs from wherever it starts to the page that prices the categories.
        if "zonare" in block and "rural" in block:
            found = read_assignment(pages, block["zonare"], block["rural"], is_local)
        else:
            found = {}
            notes.append(f"circumscripția {number}: fără listă de categorii")

        prices = read_categories(pages[block["rural"] - 1]) if "rural" in block else {}
        if "urban" in block:
            for town, zones in read_towns(pages[block["urban"] - 1], is_local).items():
                towns.setdefault(town, {}).update(zones)
        if "arabil" in block:
            arable.update(read_arable(pages[block["arabil"] - 1], is_local))

        for key, (category, commune) in found.items():
            # A commune named as its own column beats the category it would otherwise take.
            own = next(
                (
                    v
                    for label, v in prices.items()
                    if label.startswith("=") and fold(label[1:]) == key
                ),
                None,
            )
            price = own if own is not None else prices.get(category)
            if price is None:
                continue
            villages.setdefault(fold(commune), {"name": commune, "villages": []})
            villages[fold(commune)]["villages"].append(
                {"name": key.title(), "intravilan": {"CC": round(price * OCCUPIED_SHARE, 4)}}
            )
        del position

    extravilan_of = {
        key: {code: round(price * ratio / M2_PER_HA, 6) for code, ratio in FROM_ARABLE.items()}
        for key, price in arable.items()
    }

    zoned = [
        {
            "name": town,
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": {z: round(v * OCCUPIED_SHARE, 4) for z, v in zones.items()}},
            "extravilan": extravilan_of.get(fold(town), {}),
            "page": 1,
        }
        for town, zones in towns.items()
    ]
    communes = []
    for position, (key, entry) in enumerate(sorted(villages.items()), start=1):
        communes.append(
            {
                "name": entry["name"],
                "villages": entry["villages"],
                "extravilan": extravilan_of.get(key, {}),
                "page": 1,
                "index": position,
            }
        )
    return zoned, communes, notes

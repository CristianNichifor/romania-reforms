"""One reader for the chambers whose grids are a table of localities against categories.

Three readers exist for three chambers, and writing a fourth for each of the rest does not
finish. What the studies that *can* be read have in common is narrower than a layout and wider
than a chamber: somewhere in the document there is a table with a column of place names and
columns of prices, and the columns say what they hold.

So this reads captions rather than positions. It does not know how many columns a table has,
which of them is the village, or whether the commune is repeated on every row — it works all
three out per table:

    captions      the last non-empty caption above each column, so a sub-heading beats the
                  group heading it sits under ("Intravilan" spanning "Arabil | Curți")
    name columns  the columns that hold place names rather than numbers, leftmost first: two
                  of them means commune and village, one means the commune is its own row
    merged cells  a blank inherits from the row above, which is what a merged cell means

and then the register decides which of the names are real, which is what keeps a caption row
or a footnote from becoming a commune.

It will not reach every chamber. Craiova prices extravilan land per hectare for a whole county
and never per locality; Timișoara's grids are not ruled tables at all. Those are not layouts
this could learn — there is no per-locality price in the document to find.

**And finding the names is not the same as finding the prices.** On Satu Mare this reader
matched 93,8% of the county's localities and priced the county seat at 10 €/m², which is what
a village garden costs, not a city centre — it had locked onto a table of some other kind and
never found the town grids at all. Name coverage is a necessary check and a worthless
sufficient one. What caught it was the ordering test next door: building land in a town has to
cost more than building land in a commune, and here it did not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# Caption vocabulary, longest-winning. Ordered so that a more specific caption is tried before
# a more general one: "teren cu constructii" is building land, plain "intravilan" is the group
# heading above it and only counts when nothing more specific sits underneath.
CAPTIONS: list[tuple[str, str]] = [
    (
        "CC",
        r"cur[țţt]i\s*construc|de\s*construc|cu\s*construc|teren\s*construc|construc[țţ]ii",
    ),
    ("A", r"\barabil"),
    ("P+F", r"p[ăa][sșş]un|f[âa]ne[țţt]"),
    ("V+L", r"\bvii\b|vie\b|livezi|livad"),
    ("PADURE", r"p[ăa]duri|forestier"),
    ("NP", r"neproductiv|alte\s*terenuri|degradat"),
    ("AP", r"\bape\b|luciu\s*de\s*ap|b[ăa]l[țţt]i"),
    ("CC", r"\bintravilan\b"),
]
ZONE = re.compile(r"^\s*([A-F])\s*$")
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
NUMBER = re.compile(r"^\d{1,6}([.,]\d+)?$")
NOISE = re.compile(
    r"zona|zone|nr\.?\s*crt|total|categori|tipul|denumire|localitat|comuna$|satul$|"
    r"lei|euro|valoare|pre[țţ]|mp\b|m\.p|observ",
    re.I,
)


def number(cell: str) -> float | None:
    text = cell.strip().replace(" ", "")
    if not NUMBER.match(text):
        return None
    value = float(text.replace(",", "."))
    # A price per square metre. Four figures is a building, a page number or a year.
    return value if 0 < value < 100_000 else None


def caption_of(cell: str) -> str | None:
    text = re.sub(r"\s+", " ", cell).strip().lower()
    if not text:
        return None
    for code, pattern in CAPTIONS:
        if re.search(pattern, text):
            return code
    return None


def read_columns(table: list[list[str]]) -> dict[int, str]:
    """What each column holds, from the last caption printed above it."""
    columns: dict[int, str] = {}
    for row in table[:4]:
        for index, cell in enumerate(row):
            code = caption_of(cell)
            if code:
                columns[index] = code
    return columns


def name_columns(table: list[list[str]], columns: dict[int, str]) -> list[int]:
    """The columns holding place names, leftmost first.

    Counted rather than assumed: chambers put the commune in column 0, in column 1 behind a
    numbering column, or nowhere at all when every row is its own locality.
    """
    width = max((len(row) for row in table), default=0)
    scores = []
    for index in range(width):
        if index in columns:
            continue
        names = 0
        for row in table:
            if index >= len(row):
                continue
            cell = row[index].strip()
            if cell and NAME.match(cell) and not NOISE.search(cell) and number(cell) is None:
                names += 1
        if names >= 2:
            scores.append((index, names))
    scores.sort(key=lambda x: x[0])
    return [index for index, _ in scores[:2]]


def parse_table(table: list[list[str]], is_local) -> list[dict]:
    """Localities and their prices out of one table, with merged cells inherited."""
    columns = read_columns(table)
    if "CC" not in columns.values():
        return []
    names = name_columns(table, columns)
    if not names:
        return []

    found: list[dict] = []
    current: dict | None = None
    carried: dict[str, float] = {}
    for row in table:
        cells = [c.strip() for c in row]
        values: dict[str, float] = {}
        for index, code in columns.items():
            if index < len(cells):
                value = number(cells[index])
                if value is not None:
                    values.setdefault(code, value)
        # A blank price is a merged cell: it repeats what was printed above it.
        merged = {**carried, **values}
        if values:
            carried = merged

        labels = [cells[i] for i in names if i < len(cells) and cells[i]]
        labels = [x for x in labels if NAME.match(x) and not NOISE.search(x)]
        if not labels:
            continue
        # Two name columns: the left is the commune, the right the village. One: the row is
        # its own locality, which is how the chambers that price only communes print it.
        commune = labels[0] if len(labels) > 1 else None
        village = labels[-1]
        if commune and is_local(commune):
            current = {"name": commune, "villages": [], "extravilan": {}}
            found.append(current)
            carried = dict(values)
            merged = dict(values)
        if current is None:
            if not is_local(village):
                continue
            current = {"name": village, "villages": [], "extravilan": {}}
            found.append(current)
        if "CC" in merged:
            current["villages"].append({"name": village, "intravilan": {"CC": merged["CC"]}})
        extravilan = {k: v for k, v in merged.items() if k in ("A", "P+F", "V+L", "NP", "AP")}
        if extravilan and not current["extravilan"]:
            current["extravilan"] = extravilan
    return [x for x in found if x["villages"]]


def parse_zoned(table: list[list[str]], is_local) -> list[dict]:
    """A town priced by zone: a row of zone letters and a row of prices under them."""
    zones: dict[int, str] = {}
    for row in table[:4]:
        for index, cell in enumerate(row):
            match = ZONE.match(cell)
            if match:
                zones[index] = match.group(1)
    if len(zones) < 3:
        return []
    towns = []
    for row in table:
        cells = [c.strip() for c in row]
        labels = [c for c in cells if NAME.match(c) and not NOISE.search(c) and is_local(c)]
        if not labels:
            continue
        prices = {
            zones[i]: number(cells[i])
            for i in zones
            if i < len(cells) and number(cells[i]) is not None
        }
        if len(prices) >= 3:
            towns.append(
                {
                    "name": labels[0],
                    "rank": None,
                    "zones": sorted(prices),
                    "intravilan": {"CC": prices},
                    "extravilan": {},
                    "page": 0,
                }
            )
    return towns


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    communes: dict[str, dict] = {}
    towns: dict[str, dict] = {}
    for index, page in enumerate(pages):
        for table in page["tables"]:
            cells = table["cells"]
            if len(cells) < 3:
                continue
            for town in parse_zoned(cells, is_local):
                town["page"] = index + 1
                towns.setdefault(town["name"].upper(), town)
            for entry in parse_table(cells, is_local):
                entry["page"] = index + 1
                entry["index"] = len(communes) + 1
                existing = communes.get(entry["name"].upper())
                if existing is None:
                    communes[entry["name"].upper()] = entry
                else:
                    # The same commune can run across several tables and pages.
                    seen = {v["name"] for v in existing["villages"]}
                    existing["villages"].extend(
                        v for v in entry["villages"] if v["name"] not in seen
                    )
                    if not existing["extravilan"]:
                        existing["extravilan"] = entry["extravilan"]
    return list(towns.values()), list(communes.values()), []

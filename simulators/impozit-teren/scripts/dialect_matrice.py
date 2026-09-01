"""The "Matrice" dialect: Dâmbovița and Buzău, which are nothing like Prahova.

One chamber, one year, three counties, two layouts. CNP Ploiești publishes Prahova as a single
zoned matrix and its other two counties as this — named after the documents themselves,
`Matrice_Dambovita_2025.pdf` and `Matrice_Buzau_2025.pdf`, because the layout is the
document's and not the chamber's. The Prahova reader finds nothing here at all.

**Buzău exists only as a 2025 document.** The Ploiești chamber published no 2026 land study,
so this is the whole of what there is for the county, and it is why the year travels with the
data rather than being assumed in common.

Each is organised as one annex per urban unit and then one for the whole rural county:

    Anexa 3.6 … 8.6   a town each, priced by zone, six columns of what the land is used for
    Anexa 9.6         every commune, one row per village group, intravilan
    Anexa 9.7         the same rows again, extravilan

**A town's name is in its chapter heading, not in the table.** The document is cut into
numbered chapters — `4. MUNICIPIUL RÂMNICU SĂRAT`, `6. ORAȘELE PĂTÂRLAGELE și NEHOIU` — and a
chapter's land annex can be twenty pages below the heading that names it. A heading naming two
towns prices both from one table.

An earlier version read the town out of the footnote under each table instead, which is the
same fact stated twice and is the wrong one of the two: Buzău's chapters 5 and 6 carry an
identical footnote naming Pogoanele, because the document copy-pasted it. That attributed
Pătârlagele's and Nehoiu's land to a town forty pages away and left both of them unpriced.
The heading is the document's structure; the footnote is prose about it.

**The row index is the structure.** In the rural annex a commune occupies as many rows as it
has village groups, and only the first carries a number in the `Nr. Crt.` column. Attributing
by "the last name the register recognised" instead would have been wrong in a way that is hard
to see: several of Dâmbovița's villages are called after communes elsewhere in the county, so a
village row would have quietly re-opened a commune fifty rows above it. A row with no index is
a continuation of the row above, whatever names it contains.

Numbers in the rural annex are required to carry a decimal point. Every price in it has one —
`16.43`, `0.13` — and the only bare integers on those rows are the index itself, so demanding
the point is what keeps commune 82 from being read as eighty-two euro a square metre. It is
not a general rule for this document: the urban annexes price in whole euro and are read
without it.

The forestry table at the foot of the rural annex is skipped, and not only because the shared
vocabulary has no code for woodland: it prints `3,265` for three thousand two hundred and
sixty-five, using the comma as a thousands separator on the same page where the table above
uses the dot as a decimal.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# "4. MUNICIPIUL RÂMNICU SĂRAT", "8. ORAȘELE FIENI SI RĂCARI" — the chapter heading, which is
# where the document says which urban unit the pages under it are about.
CHAPTER = re.compile(
    r"^\s*\d+\.\s*(?:MUNICIPI\w+|ORA[ȘŞS]\w*)\s+(.+?)\s*$",
    re.M,
)
# Two towns sharing one chapter, and one table between them.
# "și" is written with a comma below in the 1993 orthography and with a cedilla by half the
# software that produced these documents; the two look identical and are different characters.
CHAPTER_SPLIT = re.compile(r"\s+(?:si|[șş]i)\s+", re.I)
ZONE_TABLE = re.compile(r"zona\s*-\s*subzona", re.I)
CC_COLUMN = re.compile(r"teren\s*liber|cur[țţt]i\s*construc", re.I)
ZONE_ROW = re.compile(r"^\s*zona\s+([A-F])\b", re.I)
RURAL_HEAD = re.compile(r"(INTRAVILAN|EXTRAVILAN)", re.I)
FORESTRY = re.compile(r"vegetatie\s+forestiara", re.I)
INDEX_CELL = re.compile(r"^\d{1,3}$")
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
# Intravilan prints Cc, Ar, Vie/Lv, Fn/Ps, Tn; extravilan drops the first of those.
INTRAVILAN_ORDER = ["CC", "A", "V+L", "P+F", "NP"]
EXTRAVILAN_ORDER = ["A", "V+L", "P+F", "NP"]


def footnoteless(cell: str) -> str:
    """A label without the asterisk that sends the reader to a note under the table."""
    return re.sub(r"\s*\*+\s*$", "", cell).strip()


def decimal(cell: str) -> float | None:
    """A price from the rural annex, which always writes one — see the module docstring."""
    text = cell.strip()
    if not re.fullmatch(r"\d{1,5}\.\d+", text):
        return None
    value = float(text)
    return value if 0 < value < 10_000 else None


def whole(cell: str) -> float | None:
    """A price from an urban annex, where whole euro are normal."""
    text = cell.strip()
    if not re.fullmatch(r"\d{1,5}(\.\d+)?", text):
        return None
    value = float(text)
    return value if 0 < value < 10_000 else None


def read_town(cells: list[list[str]]) -> dict[str, float]:
    """One town's zones, from the column the header calls free building land."""
    header = [re.sub(r"\s+", " ", c or "").strip() for c in cells[0]]
    at = next((i for i, c in enumerate(header) if CC_COLUMN.search(c)), None)
    if at is None:
        return {}
    zones: dict[str, float] = {}
    for row in cells[1:]:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        letter = ZONE_ROW.match(line[0] if line else "")
        price = whole(line[at]) if at < len(line) else None
        if letter and price is not None:
            zones.setdefault(letter.group(1).upper(), price)
    return zones


def read_rural(
    cells: list[list[str]], order: list[str], is_local
) -> list[tuple[str | None, dict[str, float]]]:
    """(commune or None, prices) per row; None means the row continues the one above it.

    A row that opens a commune is reported **even when it carries no prices**. Buzău wraps a
    long village list over two or three lines and puts the figures on one of the later ones,
    so dropping the numberless opening row did not merely lose that commune — it left the
    reader still pointing at the commune above, and handed Cernătești's prices to Cătina.
    A gap is visible; a silent transfer between two real communes is not.
    """
    found: list[tuple[str | None, dict[str, float]]] = []
    for row in cells:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        filled = [c for c in line if c]
        opens = bool(filled) and INDEX_CELL.match(filled[0]) is not None
        label = None
        if opens:
            # The commune column is not always filled, and is not always right. Row 48 leaves
            # it blank and names the commune only at the head of its village list — "Morteni,
            # Neajlovo" — and row 10 spells it Buciuneni where the village list beside it
            # spells it Buciumeni. So a whole cell is tried first and the head of a list
            # second, which recovers both without letting a village name open a commune.
            candidates = [c for c in line if c] + [
                c.split(",")[0].strip() for c in line if "," in c
            ]
            label = next(
                (c for c in (footnoteless(x) for x in candidates) if NAME.match(c) and is_local(c)),
                None,
            )
        values = [v for v in (decimal(c) for c in line) if v is not None]
        if not values and label is None:
            continue
        found.append((label, dict(zip(order, values, strict=False))))
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    towns: dict[str, dict[str, float]] = {}
    intravilan: dict[str, list[float]] = {}
    extravilan: dict[str, dict[str, float]] = {}
    pages_of: dict[str, int] = {}
    mode: str | None = None
    current: str | None = None
    chapter: list[str] = []

    for index, page in enumerate(pages, start=1):
        for match in CHAPTER.finditer(page["text"]):
            found = [
                part.strip()
                for part in CHAPTER_SPLIT.split(match.group(1))
                if is_local(part.strip())
            ]
            if found:
                chapter = found
        heading = RURAL_HEAD.search(
            " ".join(
                c or ""
                for table in page["tables"]
                for row in table["cells"][:4]
                for c in row
            )
        )
        if heading:
            mode = heading.group(1).upper()
            current = None

        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 2:
                continue
            head = re.sub(r"\s+", " ", " ".join(c for row in cells[:2] for c in row))
            if FORESTRY.search(head):
                continue
            if ZONE_TABLE.search(head):
                zones = read_town(cells)
                for town in chapter:
                    if zones:
                        towns[town.upper()] = zones
                        pages_of.setdefault(town.upper(), index)
                continue
            if mode is None:
                continue
            order = INTRAVILAN_ORDER if mode == "INTRAVILAN" else EXTRAVILAN_ORDER
            for label, values in read_rural(cells, order, is_local):
                if label:
                    current = label.upper()
                    pages_of.setdefault(current, index)
                if current is None:
                    continue
                if mode == "INTRAVILAN":
                    if "CC" in values:
                        intravilan.setdefault(current, []).append(values["CC"])
                else:
                    extravilan.setdefault(
                        current,
                        {k: v for k, v in values.items() if k in ("A", "P+F", "V+L")},
                    )

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
    for key, prices in intravilan.items():
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

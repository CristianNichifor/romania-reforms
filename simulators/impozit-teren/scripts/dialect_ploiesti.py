"""The CNP Ploiești dialect: a locality per row, priced across four zones twice over.

Prahova's grid is the tidiest of the lot. One table, one row per locality, and eight figures:
building land in zones A to D, then agricultural land in the same four zones.

    Localitate   Zona A  Zona B  Zona C  Zona D   Zona A  Zona B  Zona C  Zona D
                 └── curți construcții ────┘      └── arabil, livadă, vie ──┘
    Campina         65      53      29       9       58      37      21       6
    Sinaia          69      54      28      12       59      38      20       8

So every locality arrives zoned, which no other chamber manages outside its towns, and the
band this simulator reports is for once the document's own rather than an average across
villages.

**It is the 2025 study.** The Ploiești chamber published nothing for 2026 beyond covering
letters, so Prahova is a year older than the six counties beside it. The year travels with the
data and the value builder reads whichever edition exists rather than assuming a common one.

The chamber covers Buzău and Dâmbovița as well and this reader does not reach them: their
volumes carry no table of this shape at all. One chamber, one year, three counties, two
layouts — which by now is the expected outcome rather than a surprising one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

ZONES = ["A", "B", "C", "D"]
# The two county-wide annexes: one intravilan, one extravilan, both a row per commune.
#   17.6  Nr · Comuna · Sate componente · Cc · Ar · Fn/Ps · Lv · Vie · Tn
#   17.7  Nr · Comuna · Sate componente ·      Ar · Fn/Ps · Lv · Vie · Tn
# The heading that opens them is on the page, not in the table, so it sets a mode the rows
# below inherit.
ANNEX_MODE = re.compile(r"Piata\s+terenurilor\s+(INTRAVILAN|EXTRAVILAN)", re.I)
INTRA_ORDER = ["CC", "A", "P+F", "LV", "VIE", "NP"]
EXTRA_ORDER = ["A", "P+F", "LV", "VIE", "NP"]
ZONE_CELL = re.compile(r"^\s*Zona\s+([A-D])\s*$", re.I)
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
NOISE = re.compile(r"localitate|zona|total|intravilan|extravilan|curti|arabil", re.I)


def number(cell: str) -> float | None:
    text = cell.strip().replace(" ", "")
    if not re.fullmatch(r"\d{1,6}([.,]\d+)?", text):
        return None
    value = float(text.replace(",", "."))
    return value if 0 < value < 100_000 else None


def zone_layout(cells: list[list[str]]) -> tuple[dict[int, str], dict[int, str]] | None:
    """The two runs of zone columns: building land first, agricultural land second.

    Read off the header row rather than assumed, because the second run only exists where the
    chamber prices agricultural land inside the intravilan — and where it does not, the table
    still has to be usable for the first.
    """
    for row in cells[:4]:
        found = [(index, ZONE_CELL.match(cell)) for index, cell in enumerate(row)]
        marks = [(index, match.group(1).upper()) for index, match in found if match]
        if len(marks) < len(ZONES):
            continue
        built = dict(marks[: len(ZONES)])
        farmed = dict(marks[len(ZONES) : 2 * len(ZONES)])
        return built, farmed
    return None


def read_county_rows(
    cells: list[list[str]], order: list[str], is_local
) -> dict[str, dict[str, float]]:
    """One row per commune out of a county-wide annex, keyed by commune."""
    found: dict[str, dict[str, float]] = {}
    for row in cells:
        # Wrapping flattened: a two-word commune is printed on two lines inside its cell —
        # "Albesti / Paleologu" — and a name with a newline in it matches nothing.
        line = [re.sub(r"\s+", " ", c).strip() for c in row]
        # Columns are located per row rather than assumed. The first page of each annex
        # carries the header in two extra leading columns, which shifts the commune from
        # index 1 to index 3 — and cost the first nineteen communes of the county, twice.
        numbered = next((i for i, c in enumerate(line) if re.fullmatch(r"\d{1,3}", c)), None)
        if numbered is None:
            continue
        label = ""
        after = numbered + 1
        for position, cell in enumerate(line[numbered + 1 :], start=numbered + 1):
            if cell and NAME.match(cell) and is_local(cell):
                label, after = cell, position + 1
                break
        if not label:
            continue
        values = [v for v in (number(c) for c in line[after:]) if v is not None]
        if len(values) < len(order) - 1:
            continue
        named = dict(zip(order, values, strict=False))
        # Orchards and vineyards are priced apart here and share one code in the shared
        # vocabulary, so they are averaged rather than one of them standing for both.
        pair = [named.pop(k) for k in ("LV", "VIE") if k in named]
        if pair:
            named["V+L"] = sum(pair) / len(pair)
        found[label.upper()] = named
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    zoned: dict[str, dict] = {}
    intra: dict[str, dict[str, float]] = {}
    extra: dict[str, dict[str, float]] = {}
    mode: str | None = None
    for page in pages:
        heading = ANNEX_MODE.search(page["text"])
        if heading:
            mode = heading.group(1).upper()
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if mode == "INTRAVILAN":
                intra.update(read_county_rows(cells, INTRA_ORDER, is_local))
            elif mode == "EXTRAVILAN":
                extra.update(read_county_rows(cells, EXTRA_ORDER, is_local))
    communes = []
    for key, values in intra.items():
        if "CC" not in values:
            continue
        communes.append(
            {
                "name": key.title(),
                "villages": [{"name": key.title(), "intravilan": {"CC": values["CC"]}}],
                "extravilan": {
                    k: v for k, v in extra.get(key, {}).items() if k in ("A", "P+F", "V+L", "NP")
                },
                "page": 1,
            }
        )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position

    for index, page in enumerate(pages):
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 4:
                continue
            layout = zone_layout(cells)
            if layout is None:
                continue
            built, farmed = layout
            for row in cells:
                line = [c.strip() for c in row]
                label = next(
                    (c for c in line[:2] if NAME.match(c) and not NOISE.search(c)), ""
                )
                if not label or not is_local(label):
                    continue
                prices = {
                    zone: number(line[column])
                    for column, zone in built.items()
                    if column < len(line) and number(line[column]) is not None
                }
                if len(prices) < 2:
                    continue
                farm = [
                    number(line[column])
                    for column, _ in farmed.items()
                    if column < len(line) and number(line[column]) is not None
                ]
                # One caption covers arable, orchard and vineyard here, so the three share a
                # price rather than one of them being invented for the other two.
                average = sum(farm) / len(farm) if farm else None
                zoned.setdefault(
                    label.upper(),
                    {
                        "name": label,
                        "rank": None,
                        "zones": sorted(prices),
                        "intravilan": {"CC": prices},
                        "extravilan": (
                            {"A": average, "P+F": average, "V+L": average} if average else {}
                        ),
                        "page": index + 1,
                    },
                )
    return list(zoned.values()), communes, []

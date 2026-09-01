"""A county-wide forest price, for the studies that publish only one.

Forest is priced three ways across these documents. Some chambers give it per locality, in the
same table as arable and pasture, and their readers pick it up like any other category. Others
give one figure for the whole county — a small table of tree species with a price per hectare,
sitting on its own page away from the grid:

    Nr. Crt. · Familia            · EURO/Ha        Nr. Crt. · Specia arborilor · euro / ha
    1        · Padure de conifere · 5.500          1        · Conifere         · 3.265
    2        · Padure de foioase  · 6.500          2        · Foioase lemn tare· 4.134

and Buzău gives it as a column beside "Agricol" in each town's extravilan block. None of the
three is a per-locality price, so this finds whichever the document has and hands back a single
figure the importer applies to every commune in the county — recorded as county-wide rather
than passed off as local.

**Species are averaged, not chosen.** The register counts forest hectares without saying what
grows on them, so there is no way to weight conifer against broadleaf and picking one would be
picking a number. The mean of the published species is the least wrong single figure, and the
spread between them is small — Bacău's two are 5 500 and 6 500 euro a hectare.

**The unit is checked against the answer, not the caption.** Dâmbovița prints the same species
table twice, once captioned `euro / mp` with values of 15 and 16 and once `euro / ha` with
3 265 and 4 134. The first caption is wrong — 15 euro a square metre is 150 000 a hectare, which
is not a Romanian forest — so a result outside a plausible band is rejected whatever the header
says, and the table that survives is the one that means what it claims.

**And the separator is checked the same way.** Bacău writes five and a half thousand as `5.500`
and Prahova writes three and a quarter thousand as `3,265`, in tables that are otherwise the
same table. Neither convention can be assumed, so both readings of every figure are tried and
the one that lands inside the plausible band is the one taken. Where both would land inside it
the figure is refused rather than guessed — that has not happened in these documents, because
the two readings differ by a factor of a thousand and no band is that wide.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

M2_PER_HA = 10_000
# The species table, however it names its first column.
SPECIES_TABLE = re.compile(r"specia\s+arborilor|\bfamilia\b", re.I)
SPECIES_ROW = re.compile(r"conifere|foioase|p[ăa]dure", re.I)
PER_HECTARE = re.compile(r"euro\s*/?\s*ha|eur\s*/?\s*ha", re.I)
PER_M2 = re.compile(r"euro\s*/?\s*mp|eur\s*/?\s*mp", re.I)
# Buzău's shape: a header cell naming the category, the figure directly beneath it.
FOREST_CELL = re.compile(r"^\s*p[ăa]dure\s*$", re.I)
# What a hectare of Romanian forest can plausibly cost, in euro. Wide on purpose — it is a
# guard against a misread unit, not an estimate.
PLAUSIBLE_EUR_PER_HA = (500.0, 20_000.0)


def number(cell: str) -> float | None:
    text = re.sub(r"\s+", "", cell or "")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+([.,]\d+)?", text):
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        return float(text.replace(".", ""))
    return float(text.replace(",", "."))


def readings(cell: str) -> list[float]:
    """Every way this figure could be meant, separator conventions being what they are."""
    text = re.sub(r"\s+", "", cell or "")
    if not re.fullmatch(r"[\d.,]+", text) or not any(c.isdigit() for c in text):
        return []
    found = []
    for separator in (".", ","):
        if re.fullmatch(rf"\d{{1,3}}(\{separator}\d{{3}})+", text):
            found.append(float(text.replace(separator, "")))
    plain = number(text)
    if plain is not None:
        found.append(plain)
    return found


def _plausible(values: list[float], per_hectare: bool) -> float | None:
    """The mean of the species, in euro per m², or None if the unit cannot be right."""
    if not values:
        return None
    mean = sum(values) / len(values)
    per_ha = mean if per_hectare else mean * M2_PER_HA
    if not PLAUSIBLE_EUR_PER_HA[0] <= per_ha <= PLAUSIBLE_EUR_PER_HA[1]:
        return None
    return per_ha / M2_PER_HA


def from_species_table(cells: list[list[str]]) -> float | None:
    flat = [re.sub(r"\s+", " ", c or "").strip() for row in cells for c in row]
    joined = " ".join(flat)
    if not SPECIES_TABLE.search(joined):
        return None
    per_hectare = bool(PER_HECTARE.search(joined))
    if not per_hectare and not PER_M2.search(joined):
        return None
    # Every candidate reading of the last figure on each species row, kept apart so the
    # plausible band can choose between the separator conventions rather than a regex.
    per_row: list[list[float]] = []
    for row in cells:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        if not any(SPECIES_ROW.search(c) for c in line):
            continue
        figures = [readings(c) for c in line]
        figures = [f for f in figures if f and max(f) > 1]
        if figures:
            per_row.append(figures[-1])
    if not per_row:
        return None
    for index in range(max(len(f) for f in per_row)):
        values = [f[index] for f in per_row if index < len(f)]
        found = _plausible(values, per_hectare)
        if found is not None:
            return found
    return None


def from_labelled_column(cells: list[list[str]]) -> float | None:
    """Buzău: a "Padure" header cell with its figure in the row underneath."""
    for index, row in enumerate(cells[:-1]):
        for column, cell in enumerate(row):
            if not FOREST_CELL.match(re.sub(r"\s+", " ", cell or "").strip()):
                continue
            below = cells[index + 1]
            if column < len(below):
                value = number(below[column])
                # Published per square metre in this shape.
                if value is not None and _plausible([value], per_hectare=False) is not None:
                    return value
    return None


def county_price(document: str) -> tuple[float, str] | tuple[None, None]:
    """One forest price in euro per m² for the whole county, and where it came from."""
    try:
        pages = load(document)["pages"]
    except SystemExit:
        return None, None
    for index, page in enumerate(pages, start=1):
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 2:
                continue
            found = from_species_table(cells)
            if found is not None:
                return found, f"tabelul speciilor forestiere, pagina {index}"
            found = from_labelled_column(cells)
            if found is not None:
                return found, f"coloana „Pădure” din blocul extravilan, pagina {index}"
    return None, None

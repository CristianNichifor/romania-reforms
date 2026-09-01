"""The CNP Cluj dialect: the whole county on one page, twenty-one columns wide.

Cluj publishes a single master table — flats, land, buildings, garages and annexes side by
side, one row per group of localities — and everything this simulator needs is four of its
twenty-one columns.

    NR · CIRCUMSCRIPȚIE · LOCAŢIA · | flats ×3 | teren intravilan ×4 | buildings ×6 |
                                      teren extravilan ×5

**A row is a group, not a place.** `APAHIDA, BACIU, CHINTENI…` share one line and one set of
prices, and the line under it — `Satele aparținând…` — prices the villages of those same
communes lower. So a row is split on its commas and every locality in it takes the row's
figures, with the villages' line widening the band rather than replacing it.

The chamber covers Bistrița-Năsăud, Maramureș and Sălaj as well, and none of their volumes
contains a table of this shape. Four counties, one chamber, one year, and the layout is
Cluj's alone.

Numbers here are Romanian in both directions at once: `5.900` is five thousand nine hundred
and `5,25` is five and a quarter, in the same row.

**Not landed.** This reaches 85% of the county's localities and none of its five towns —
Cluj-Napoca, Turda, Dej, Gherla, Câmpia Turzii — which is the wrong 15% to be missing, because
a county's land value is concentrated in exactly those. Cluj-Napoca is priced in a second
table by neighbourhood (`Centru`, `Bună Ziua`, `Andrei Mureşanu`) with the city named only in
a column beside them, and three attempts at attributing those rows moved the figure not at
all. Kept because it is most of a working reader, and because the gap is documented rather
than guessed at.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# The county table names its intravilan block; the city table names only the sub-columns
# under it — "Pentru partea de suprafață…", "Fără utilităţi în apropiere" — and skipping a
# table for want of the group caption left Cluj-Napoca itself unpriced.
INTRA_GROUP = re.compile(
    r"teren\s*intravilan|pentru\s*partea\s*de\s*suprafa|f[ăa]r[ăa]\s*utilit",
    re.I,
)
EXTRA_GROUP = re.compile(r"teren\s*extravilan", re.I)
BUILDING = re.compile(r"construc[țţ]ie|anexe|ap\.\s*su", re.I)
# The unit tells land from building, and it is the only thing that does so in every one of the
# chamber's four counties. Ground is priced per square metre; a building is priced per square
# metre of *built* area — mpSd. In Bistrița-Năsăud, Maramureș and Sălaj the construction
# columns carry no caption in the header block at all, so the intravilan run swallowed five of
# them and put Baia Mare's land at the price of its houses.
BUILT_AREA_UNIT = re.compile(r"mp\s*sd", re.I)
EXTRA_CAPTIONS: list[tuple[str, str]] = [
    ("A", r"agricol"),
    ("NP", r"neproductiv"),
    ("V+L", r"livad|vie"),
    ("PADURE", r"p[ăa]dure"),
]
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
VILLAGES_ROW = re.compile(r"satele?\s+apar[țţ]in", re.I)
# "comune: AGRIJ, BUCIUMI, COȘEIU, …" — Sălaj labels its grouped rows, and the label came out
# of the comma split attached to the first commune, so that one never matched the register and
# the rest of the row went with it.
LIST_PREFIX = re.compile(r"^\s*(?:comune|localit[ăa][țţ]i|sate)\s*:\s*", re.I)


def number(cell: str) -> float | None:
    """A Romanian figure: dot groups thousands, comma marks the decimal, both in one row."""
    text = re.sub(r"\s+", "", cell)
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?", text):
        return None
    value = float(text.replace(".", "").replace(",", "."))
    return value if 0 < value < 1_000_000 else None


def header_rows(cells: list[list[str]]) -> int:
    """How deep the caption block goes, found rather than assumed.

    A fixed window of eight rows held for three of the chamber's four counties and not for
    Sălaj, which carries one more blank row and so pushed its `lei/mpSd` unit line out of
    view — and with it the only thing that tells a building column from a land one. The
    caption block ends where the numbers start.
    """
    for index, row in enumerate(cells[:14]):
        figures = sum(1 for cell in row if number(re.sub(r"\s+", " ", cell).strip()) is not None)
        if figures >= 3:
            return max(index, 1)
    return min(len(cells), 10)


def columns(cells: list[list[str]]) -> tuple[list[int], dict[int, str]] | None:
    """The intravilan columns and the extravilan ones, from the two rows of captions.

    Read rather than counted: the table carries three price blocks and only the captions say
    where one ends and the next begins.
    """
    group: dict[int, str] = {}
    sub: dict[int, str] = {}
    depth = header_rows(cells)
    for row in cells[:depth]:
        for index, cell in enumerate(row):
            text = re.sub(r"\s+", " ", cell).strip()
            if not text:
                continue
            # First caption wins, as it does for the sub-captions below. A column's group is
            # named once, at the top; the rows under it qualify that name. Assigning instead
            # of setting-default let "zona limitrofă cu intravilanul" — a sub-caption of the
            # *extravilan* block — relabel column 16 as intravilan, which silently discarded
            # every extravilan price in the county.
            if INTRA_GROUP.search(text):
                group.setdefault(index, "intra")
            elif EXTRA_GROUP.search(text):
                group.setdefault(index, "extra")
            elif BUILDING.search(text):
                group.setdefault(index, "other")
            else:
                sub.setdefault(index, text)
    if "intra" not in group.values():
        return None

    starts = sorted(group)
    intra_at = next(i for i in starts if group[i] == "intra")
    after_intra = next((i for i in starts if i > intra_at and group[i] != "intra"), len(cells[0]))
    intra = [
        index
        for index in range(intra_at, after_intra)
        if not BUILT_AREA_UNIT.search(sub.get(index, ""))
        and not any(
            BUILT_AREA_UNIT.search(re.sub(r"\s+", " ", row[index]).strip())
            for row in cells[:depth]
            if index < len(row)
        )
    ]
    if not intra:
        return None

    extra: dict[int, str] = {}
    extra_at = next((i for i in starts if group[i] == "extra"), len(cells[0]))
    for index in range(extra_at, len(cells[0])):
        caption = sub.get(index, "")
        for code, pattern in EXTRA_CAPTIONS:
            if re.search(pattern, caption, re.I):
                extra[index] = code
                break
    return intra, extra


# A row carrying one cell and nothing else. In this document that is always a section header,
# and the section is what says which town the rows under it price.
SECTION_SPLIT = re.compile(r"\s*\+\s*|\s+[șş]i\s+", re.I)
# Rural if it says communes or villages — which covers Cluj's "COMUNE / ORAȘE / SATE" and the
# other three counties' "SATE / COMUNE" alike. Checked first, because both spellings also
# contain the word for towns and testing that first sent every rural block into town mode.
RURAL_SECTION = re.compile(r"COMUNE|SATE", re.I)
# "ORAȘE / LOCALITĂȚI": one block for all of a county's towns, each row naming its own in the
# circumscription column. Cluj instead gives every town a section header of its own, so the
# same table is laid out two ways inside one chamber and the mode has to be read, not assumed.
URBAN_SECTION = re.compile(r"ORA[ȘŞS]E", re.I)
# "BAIA MARE - ZONA 1", "ZALĂU - ZONA 3" — the seat's own rows carry a zone after the name.
ZONE_SUFFIX = re.compile(r"\s*[-–]\s*ZONA\b.*$", re.I)


def section_of(line: list[str]) -> str | None:
    """The header this row is, or None if it is an ordinary row."""
    filled = [c for c in line if c]
    if len(filled) != 1 or len(filled[0]) > 40:
        return None
    return filled[0]


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    communes: dict[str, dict] = {}
    pages_of: dict[str, int] = {}

    for page_index, page in enumerate(pages):
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 5:
                continue
            layout = columns(cells)
            if layout is None:
                continue
            intra_columns, extra_columns = layout
            # Which town the rows below belong to, and whether we have reached the rural
            # block. Both come from the same one-cell header rows.
            current: list[str] = []
            mode = "none"
            previous: list[str] = []

            for row in cells:
                line = [re.sub(r"\s+", " ", c).strip() for c in row]
                header = section_of(line)
                if header is not None:
                    if RURAL_SECTION.search(header):
                        mode, current = "rural", []
                    elif URBAN_SECTION.search(header):
                        mode, current = "towns", []
                    else:
                        named = [
                            part.strip()
                            for part in SECTION_SPLIT.split(header)
                            if is_local(part.strip())
                        ]
                        if named:
                            mode, current = "town", named
                    continue
                if len(line) < 4:
                    continue

                prices = [
                    number(line[i]) for i in intra_columns if i < len(line)
                ]
                prices = [p for p in prices if p is not None]
                if not prices:
                    continue
                extravilan: dict[str, float] = {}
                for index, code in extra_columns.items():
                    value = number(line[index]) if index < len(line) else None
                    if value is not None:
                        extravilan.setdefault(code, value)
                # One agricultural figure covers arable and pasture alike here.
                if "A" in extravilan:
                    extravilan.setdefault("P+F", extravilan["A"])

                if mode == "towns":
                    # Column 1 is the *circumscription*, not the town: eight of Maramureș's
                    # eleven towns sit under BAIA MARE and were being priced as Baia Mare.
                    # The locality is column 2, minus the zone the seat's own rows carry
                    # after it; where that is not a place — "cartiere/zone aparținătoare" —
                    # the row belongs to the circumscription seat carried forward.
                    named = ZONE_SUFFIX.sub("", line[2] if len(line) > 2 else "").strip()
                    seat = line[1] if len(line) > 1 else ""
                    if named and NAME.match(named) and is_local(named):
                        current = [named]
                    elif seat and NAME.match(seat) and is_local(seat):
                        current = [seat]
                if mode in ("town", "towns"):
                    # A town's neighbourhoods, each a reading of the same place — carried as
                    # village rows rather than as a zone grid, because the document names
                    # districts and the shared model's zones are the Fiscal Code's letters.
                    # Writing "Centru" into a zone field would be inventing a correspondence
                    # the study does not make, and the schema is right to refuse it.
                    for town in current:
                        pages_of.setdefault(town.upper(), page_index + 1)
                        entry = communes.setdefault(
                            town.upper(),
                            {
                                "name": town.title(),
                                "villages": [],
                                "extravilan": {},
                                "page": page_index + 1,
                            },
                        )
                        district = line[2] if len(line) > 2 else ""
                        for position, price in enumerate(prices, start=1):
                            entry["villages"].append(
                                {
                                    "name": f"{district or town} ({position})",
                                    "intravilan": {"CC": price},
                                }
                            )
                        if not entry["extravilan"]:
                            entry["extravilan"] = extravilan
                    continue

                label_cell = line[2] if len(line) > 2 else ""
                # "Satele aparținând ..." prices the villages of the localities named above,
                # so it belongs to them and widens their band rather than naming new places.
                if VILLAGES_ROW.search(label_cell):
                    names = previous
                else:
                    names = [
                        part.strip()
                        for part in re.split(r"[,;]", LIST_PREFIX.sub("", label_cell))
                        if NAME.match(part.strip()) and is_local(part.strip())
                    ]
                    if names:
                        previous = names
                if not names:
                    continue
                for locality in names:
                    entry = communes.setdefault(
                        locality.upper(),
                        {
                            "name": locality.title(),
                            "villages": [],
                            "extravilan": {},
                            "page": page_index + 1,
                        },
                    )
                    for position, price in enumerate(prices, start=len(entry["villages"]) + 1):
                        entry["villages"].append(
                            {
                                "name": f"{locality.title()} ({position})",
                                "intravilan": {"CC": price},
                            }
                        )
                    if not entry["extravilan"]:
                        entry["extravilan"] = extravilan

    for position, entry in enumerate(communes.values(), start=1):
        entry["index"] = position
    return [], list(communes.values()), []

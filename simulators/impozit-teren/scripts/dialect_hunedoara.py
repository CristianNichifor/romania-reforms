"""The CNP Alba Iulia dialect for Hunedoara: twenty land tables, no two the same shape.

This is the **third** reader for one chamber. CNP Alba Iulia publishes Alba with merged cells
and rotated captions, Sibiu with its captions printed sideways and its columns read by
position, and Hunedoara like this — and no two of the three share a line of code. By now that
is the expectation rather than the surprise, but Hunedoara is the clearest case of it: the
same chamber, the same year, three counties, three layouts.

Hunedoara does not have a land annex. It has a chapter per court circumscription — Deva,
Brad, Hațeg, Petroșani, Orăștie — and inside each, land is priced in whatever table happened
to be convenient: beside the houses, beside the flats, in a street list, or in a table of its
own. Twenty tables, and the locality column lands at a different index in most of them.

What is constant is the **caption**. Every one of them names its building-land column some
variant of *Teren Intravilan Curți-construcții*, so that is what this reads, and it reads the
caption as the whole column of header cells joined downwards because the words are printed
stacked. The variants are the document's own typing rather than a family of layouts:

    Teren Intrav Curti-constr        Teren Intravilan Cuticonstr
    Teren Intrav Curti- const        Teren Intravil Curti-Ctii
    Teren Intrav Curti- constctii    Teren Intrav Curticonst

which is why the pattern is deliberately loose about what comes after "curti" and deliberately
strict about "intravilan" preceding it — *Teren Intravilan Agricol* sits in the next column
along in almost every one of these tables, and a looser pattern reads the county's gardens as
its house plots.

**A street is not a locality.** Brad, Hațeg and Orăștie are priced street by street, with the
town named only in the table's own header — `BRAD,rang II Strada` — so a table whose rows name
no locality the register knows takes the town out of its caption instead. Rows still carry
their zone letter, so those three towns come out zoned like the others.

**Extravilan is published for eleven localities, not for the county.** The agricultural table
appears once per court circumscription and prices only its seat — Deva, Brad, Hațeg, Călan,
Hunedoara and so on — so fifty-four communes here carry building land and nothing else. That
is the document's limit rather than this reader's: there is no per-commune arable price in
Hunedoara to read. It travels as a gap in the data rather than as a figure borrowed from a
neighbouring county.

**This is the 2026 study, and it has to be.** Hunedoara's 2025 volume is two PDFs of 51 and 41
pages containing zero extractable characters — a scan. Buzău is the opposite case in the same
survey: it exists only as 2025. Neither county has a choice of edition, and they point in
opposite directions, which is the argument for the year travelling with the data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# "intravilan" then "curti", however the typist spelled the second. The order matters: it is
# what keeps *Teren Intravilan Agricol* out.
CC_CAPTION = re.compile(r"int(?:r)?av\w*[^|]{0,30}?c\w*ti", re.I)
AGRICOL = re.compile(r"agricol", re.I)
ZONE_CAPTION = re.compile(r"^\s*z\s*o\s*n\s*a\s*$", re.I)
# The extravilan table, which names itself and prices by category rather than by locality.
EXTRA_TABLE = re.compile(r"tipul\s*terenului", re.I)
# Any word that means "this row of cells is a caption". A continuation page has none of them,
# which is what makes it a continuation page and not a new table.
IS_A_HEADER = re.compile(
    r"teren|case?\b|casa|apartam|garaj|anexe|spatii|localitat|zona|comuna|\bsat\b|vechime|strada",
    re.I,
)
EXTRA_CAPTIONS: list[tuple[str, str]] = [
    ("A", r"arabil"),
    ("P+F", r"p[ăa]suni|f[âa]nete|fanete"),
    ("V+L", r"livezi|livada|\bvie\b"),
    ("PADURE", r"forestier|p[ăa]duri"),
    ("NP", r"alte\s+(terenuri|categorii)"),
]
# "Centre de Comuna" and "Sate" — rows that price every commune of the circumscription rather
# than one named place. They are the reason this county went from 17% of its hectares priced
# to nearly all of them: the extravilan table looked like it covered five town seats, and it
# always covered the whole county, in two rows nobody had read because they name nobody.
GENERIC_COMMUNE = re.compile(r"centre?\s+de\s+comun", re.I)
# "BRAD,rang II Strada", "Hateg, rang III Strada" — the town a street table belongs to.
HEADER_TOWN = re.compile(r"^\s*([A-Za-zĂÂÎȘŞȚŢăâîșşțţ\- ]{3,}?)\s*,?\s*rang\b", re.I)
# "Deva zona A", "Deva-localit apartinatoare" — the locality, then where in it.
# "Deva zona A", "Hunedoara A", "Deva-localit apartinatoare" — the locality, then where in
# it. The bare trailing letter is a zone too: this chapter drops the word "zona" and prints
# the letter alone, which left the county's second city unpriced.
# The bare letter must be preceded by a space. Written without one it matched the last
# letter of any name ending in A–F and turned Dobra into "Dobr", Ilia into "Ili" and Balsa
# into "Bals" — twenty-four communes lost to a regex that was right about Hunedoara A.
PLACE_TAIL = re.compile(
    r"\s*[-–]\s*localit\w*\s*apartin\w*.*$|\s+zona\b.*$|\s+[A-F]$",
    re.I,
)
ZONE_IN_LABEL = re.compile(r"\bzona\s+([A-F])\b|\s([A-F])$", re.I)
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
# "Comuna Bunila", "Orasul Geoagiu" — the rank is printed into the locality column here.
RANK_PREFIX = re.compile(r"^\s*(?:municipiul|orasul|ora[șş]ul|comuna|satul|sat)\s+", re.I)
ZONE_CELL = re.compile(r"^\s*([A-F])\s*$")


def number(cell: str) -> float | None:
    """The first price in a cell, where the same table writes 3,0 and 1.5 for the same thing.

    Both separators appear as decimals in this document and neither ever groups thousands in
    a land column, so that distinction is not worth preserving here.

    **Whitespace is not squeezed out.** Hațeg's last two zones share one row, so its price
    cell reads `50 30` — two zones' prices, not five thousand and thirty — and squeezing put
    the town's land at 5 030 lei/m², seventeen times Deva's. This is the same defect that
    once read Bacău's `256 123 48 35` as one number; a cell with two numbers in it is two
    numbers, and the first is the one this column is about.
    """
    tokens = [t for t in re.split(r"\s+", clean(cell)) if t]
    if not tokens or not re.fullmatch(r"\d{1,5}(?:[.,]\d{1,2})?", tokens[0]):
        return None
    value = float(tokens[0].replace(",", "."))
    return value if 0 < value < 10_000 else None


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def header_depth(cells: list[list[str]]) -> int:
    """How many rows the caption occupies, found rather than assumed.

    These tables run from one header row to four, and a fixed guess of four swallowed the
    first data rows into the caption. That did not break the column match — the words are
    still in there — but it did break every test written against the caption's *shape*, and
    "ZO NA" stopped being a zone column the moment "A B C D" was glued onto the end of it.
    """
    for index, row in enumerate(cells[:5]):
        figures = sum(1 for c in row if number(clean(c)) is not None)
        if figures >= 2:
            return max(index, 1)
    return min(len(cells), 4)


def captions(cells: list[list[str]], rows: int | None = None) -> dict[int, str]:
    """Each column's caption, joined downwards — the words are printed stacked."""
    depth = rows if rows is not None else header_depth(cells)
    width = max((len(row) for row in cells[:depth]), default=0)
    joined: dict[int, str] = {}
    for index in range(width):
        parts = [clean(row[index]) for row in cells[:depth] if index < len(row)]
        joined[index] = " ".join(p for p in parts if p)
    return joined


def header_town(cells: list[list[str]], is_local):
    """The town a street table is about, named in its own caption and nowhere else."""
    for row in cells[:3]:
        for cell in row:
            match = HEADER_TOWN.match(clean(cell))
            if match and is_local(match.group(1).strip()):
                return match.group(1).strip()
    return None


def generic_extravilan(cells: list[list[str]]) -> dict[str, float]:
    """The circumscription's price for any commune centre, from the row that names none.

    Returned apart from the named rows because it applies to a different thing: not to a
    locality but to every commune in the court's circumscription that the table does not name
    individually, which in Hunedoara is almost all of them.
    """
    heads = captions(cells)
    if not any(EXTRA_TABLE.search(caption) for caption in heads.values()):
        return {}
    mapped: dict[int, str] = {}
    for index, caption in heads.items():
        for code, pattern in EXTRA_CAPTIONS:
            if code not in mapped.values() and re.search(pattern, caption, re.I):
                mapped[index] = code
                break
    for row in cells:
        line = [clean(c) for c in row]
        if not line or not GENERIC_COMMUNE.search(line[0]):
            continue
        found = {
            code: number(line[index])
            for index, code in mapped.items()
            if index < len(line) and number(line[index]) is not None
        }
        if found:
            return found
    return {}


def read_extravilan(cells: list[list[str]], is_local) -> dict[str, dict[str, float]]:
    """The per-circumscription table of agricultural prices, keyed by locality."""
    heads = captions(cells)
    if not any(EXTRA_TABLE.search(c) for c in heads.values()):
        return {}
    mapped: dict[int, str] = {}
    for index, caption in heads.items():
        for code, pattern in EXTRA_CAPTIONS:
            if code not in mapped.values() and re.search(pattern, caption, re.I):
                mapped[index] = code
                break
    if "A" not in mapped.values():
        return {}
    found: dict[str, dict[str, float]] = {}
    for row in cells:
        line = [clean(c) for c in row]
        if not line:
            continue
        label = RANK_PREFIX.sub("", PLACE_TAIL.sub("", line[0])).strip()
        if not label or not NAME.match(label) or not is_local(label):
            continue
        prices = {
            code: number(line[index])
            for index, code in mapped.items()
            if index < len(line) and number(line[index]) is not None
        }
        if prices:
            found.setdefault(label.upper(), {}).update(
                {k: v for k, v in prices.items() if k not in found.get(label.upper(), {})}
            )
    return found


def read_intravilan(
    cells: list[list[str]], is_local, carried: tuple[int, int, int | None] | None = None
) -> tuple[list[tuple[str, str | None, float]], tuple[int, int, int | None] | None]:
    """(locality, zone, building-land price) per priced row, and the layout that was used.

    The layout is returned so the caller can carry it onto the next page. A commune table
    here runs for three or four pages and prints its header **once**, on the first of them,
    so a reader that insists on finding a caption in every table reads the first page of each
    table and abandons the rest. That was two thirds of the county: 39% coverage, with the
    missing communes clustered exactly on the continuation pages.
    """
    heads = captions(cells)
    width = max((len(row) for row in cells), default=0)
    target = next(
        (
            i
            for i, caption in heads.items()
            if CC_CAPTION.search(caption) and not AGRICOL.search(caption)
        ),
        None,
    )
    zone_at = next((i for i, caption in heads.items() if ZONE_CAPTION.match(caption)), None)
    if target is None:
        # Carried **as an offset from the right edge**, not as a column index. A continuation
        # page picks up a phantom empty column often enough that insisting on equal widths
        # blocked the carry on a third of them — p49 is seven columns where p48, the page it
        # continues, is six. The land columns sit at the end of these tables and keep their
        # distance from it; the artefacts appear on the left.
        if carried is None or abs(carried[0] - width) > 2:
            return [], carried
        # A table that captions itself is a new table, not a continuation — even when none of
        # its captions is the one being looked for. Hunedoara's commercial-space table says
        # "SPATII COMERCIALE Lei/mp/sd Nu include teren" and sits directly under a land table
        # of the same width; carrying onto it put the city of Hunedoara's land at 2 500 lei/m²,
        # eight times Deva's, out of a column the document says excludes land entirely.
        if any(IS_A_HEADER.search(c) for c in heads.values()):
            return [], carried
        previous_width, previous_target, zone_at = carried
        target = width - (previous_width - previous_target)
        if not 0 <= target < width:
            return [], carried
    fallback = header_town(cells, is_local)

    found: list[tuple[str, str | None, float]] = []
    current: str | None = None
    for row in cells:
        line = [clean(c) for c in row]
        price = number(line[target]) if target < len(line) else None
        # The locality is wherever it lands in this particular table, so it is looked for
        # rather than indexed — but only ahead of the price column, because the columns after
        # it hold figures and the odd stray word.
        def place_of(cell: str) -> str:
            return RANK_PREFIX.sub("", PLACE_TAIL.sub("", cell)).strip()

        label = next(
            (
                place_of(c)
                for c in line[:target]
                if NAME.match(place_of(c)) and is_local(place_of(c))
            ),
            None,
        )
        if label:
            current = label
        if price is None:
            continue
        zone = None
        if zone_at is not None and zone_at < len(line):
            cell = ZONE_CELL.match(line[zone_at])
            zone = cell.group(1).upper() if cell else None
        if zone is None:
            inline = next(
                (m for m in (ZONE_IN_LABEL.search(c) for c in line[: target + 1] if c) if m),
                None,
            )
            zone = (inline.group(1) or inline.group(2)).upper() if inline else None
        place = current or fallback
        if place:
            found.append((place, zone, price))
    return found, (width, target, zone_at)


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    zoned: dict[str, dict[str, float]] = {}
    flat: dict[str, list[float]] = {}
    extravilan: dict[str, dict[str, float]] = {}
    pages_of: dict[str, int] = {}
    generic: list[tuple[int, dict[str, float]]] = []
    carried: tuple[int, int, int | None] | None = None

    for index, page in enumerate(pages, start=1):
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 2:
                continue
            for key, values in read_extravilan(cells, is_local).items():
                extravilan.setdefault(key, {}).update(values)
            shared = generic_extravilan(cells)
            if shared:
                generic.append((index, shared))
            rows, carried = read_intravilan(cells, is_local, carried)
            for label, zone, price in rows:
                key = label.upper()
                pages_of.setdefault(key, index)
                if zone:
                    zoned.setdefault(key, {}).setdefault(zone, price)
                else:
                    flat.setdefault(key, []).append(price)

    towns = [
        {
            "name": key.title(),
            "rank": None,
            "zones": sorted(prices),
            "intravilan": {"CC": prices},
            "extravilan": extravilan.get(key, {}),
            "page": pages_of.get(key, 1),
        }
        for key, prices in zoned.items()
        if len(prices) >= 2
    ]
    priced = {t["name"].upper() for t in towns}
    communes = []
    for key, prices in flat.items():
        if key in priced:
            continue
        # A locality with a single zone letter is not a zoned town; its one reading joins the
        # flat ones rather than being dropped for failing to be a grid.
        prices = prices + list(zoned.get(key, {}).values())
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
    for key, prices in zoned.items():
        if key in priced or key in flat:
            continue
        communes.append(
            {
                "name": key.title(),
                "villages": [
                    {"name": f"{key.title()} ({position})", "intravilan": {"CC": price}}
                    for position, price in enumerate(sorted(set(prices.values()), reverse=True), 1)
                ],
                "extravilan": extravilan.get(key, {}),
                "page": pages_of.get(key, 1),
            }
        )
    # The circumscription's generic prices, given to every commune that has none of its own.
    # Matched by nearest page, because the document is laid out chapter by chapter and a
    # commune's own rows sit within a few pages of the table that prices its circumscription.
    if generic:
        for entry in [*communes, *towns]:
            if entry["extravilan"]:
                continue
            page = entry.get("page", 1)
            entry["extravilan"] = dict(
                min(generic, key=lambda pair: abs(pair[0] - page))[1]
            )

    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    return towns, communes, []

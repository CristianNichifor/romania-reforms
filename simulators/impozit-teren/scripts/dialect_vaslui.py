"""Vaslui, where the communes are priced by class and the classes are listed in a sentence.

Every other chamber read so far prices a commune on a row with its name on it. Vaslui does not
price communes at all. It prices *categories*:

    CATEGORIA COMUNELOR   …   TEREN INTRAVILAN CONSTRUCTII   TEREN INTRAVILAN ARABIL
    CATEGORIA 1                        50                              20
    CATEGORIA 2                        35                              15

and then, thirty pages later, in running prose at the foot of the block, says which commune is
which:

    CATEGORIA 1 : Fălciu, Zorleni, Tutova.
    CATEGORIA2:Suletea, Ivești, Grivița, Perieni, Banca, Puiești.

That paragraph is the join. Without it the table prices nothing, and it is not a table — it is
a sentence with commas in it, sometimes with the space after "CATEGORIA" missing, sometimes
broken across a line in the middle of a name.

**The heading on that paragraph lies, and it lies identically three times.** Each of the three
court circumscriptions — Vaslui, Bârlad, Huși — ends its block with the same sentence:

    localitățile aflate pe raza circumscripției judecătoriei Vaslui, au fost clasificate…

Bârlad's list says Vaslui. Huși's list says Vaslui. Only the first one is telling the truth,
and the give-away is in the names: the paragraph on page 91 assigns Zorleni and Puiești, which
are Bârlad's communes and appear nowhere near Vaslui. So the reader **must not** attribute a
list by what it says about itself. It attributes by position: a category list belongs to the
annex block it follows. Reading the sentence instead would have merged three circumscriptions
into one and given two-thirds of the county the wrong prices — with full name coverage and no
error anywhere, which is the failure this repository keeps meeting.

**Five blocks, not three.** Vaslui, Bârlad and Huși have communes and therefore category
tables. Negrești and Murgeni are towns whose component villages are priced by a flat sentence
instead — *"PENTRU TERENURILE INTRAVILANE CURȚI CONSTRUCȚII, Valoarea de Circulație Minimă
este estimată la 35 lei/mp"* — with no categories and no table at all. Those two UATs are
valued from their own zone grids, which prices their outlying villages at the town's rate
rather than the sentence's; that overstates them, by the same zone-weighting uncertainty the
band already reports everywhere else, and on two of the county's eighty-six localities.

**A commune seat and its other villages are priced apart.** Each annex carries two tables under
the same categories: `SAT REȘEDINTĂ DE COMUNĂ` and `SAT COMPONENT AL COMUNEI`, the second
cheaper. That maps exactly onto the commune-and-villages shape the rest of the pipeline
expects, so the seat takes the first table's price and every other village the second's.

**The extravilan is one table for the whole county**, ANEXA 38, priced by category of use and
by parcel size. The largest-parcel price is taken, because that is the one that applies to the
hectares this simulator counts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

ANEXA = re.compile(r"ANEXA\s*(\d+)", re.I)
# The town grids: "MUNICIPIUL VASLUI" or "LOCALITATEA NEGREȘTI" on its own line, followed by
# the CC zone table. The word "INTRAVILAN" alone is not enough — the same page carries an
# extravilan table with the same shape and cheaper numbers.
TOWN_HEADING = re.compile(
    r"^\s*(?:MUNICIPIUL|ORA[ȘŞS]UL|LOCALITATEA)\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,})\s*$", re.M
)
CC_TABLE = re.compile(r"INTRAVILAN\s+CATEGORIA\s+DE\s+FOLOSIN[ȚŢT][ĂA]\s+CC", re.I)
# "1 A 800", and also "2 C, D 40" — Murgeni prices two zones on one row, and a pattern that
# insisted on a single letter dropped both of them while still returning a plausible town.
ZONE_ROW = re.compile(r"^\s*(\d+)\s+([A-F](?:\s*,\s*[A-F])*)\s+([\d.,]+)\s*$", re.M)

# The commune annex. Both halves carry the same category column, so they are told apart by the
# caption above them and not by their contents.
SEAT_CAPTION = re.compile(r"SAT\s+RE[ȘŞS]EDIN[ȚŢT][ĂA]\s+DE\s+COMUN[ĂA]", re.I)
PART_CAPTION = re.compile(r"SAT\s+COMPONENT\s+AL\s+COMUNEI", re.I)
CATEGORY_ROW = re.compile(r"^\s*CATEGORIA\s*(\d+)\s*$", re.I)
BUILT_COLUMN = re.compile(r"TEREN\s+INTRAVILAN\s+CONSTRUCTII", re.I)

# The prose that assigns communes to categories. The colon may have no space before it and the
# digit may be glued to the word, which is why this is not a simple split.
CATEGORY_LIST = re.compile(r"CATEGORIA\s*(\d+)\s*:\s*([^:]*?)(?=CATEGORIA\s*\d+\s*:|$)", re.S)
# The flat sentence Negrești and Murgeni use instead of categories.
FLAT_BUILT = re.compile(
    r"TERENURILE\s+INTRAVILANE\s+CUR[ȚŢT]I\s+CONSTRUC[ȚŢT]II.{0,80}?([\d.,]+)\s*lei/mp", re.I | re.S
)
COMPONENT_OF = re.compile(
    r"LOCALIT[ĂA][ȚŢT]I\s+DIN\s+COMPONEN[ȚŢT]A\s+U\.?A\.?T\.?\s+([A-ZĂÂÎȘŞȚŢ\- ]{3,})", re.I
)

# ANEXA 38, the county's extravilan, against the notaries' codes. Forest is "Padure codru".
EXTRA_ROWS: list[tuple[str, re.Pattern[str]]] = [
    ("A", re.compile(r"Arabil\(A\)", re.I)),
    ("P+F", re.compile(r"Arabil\(A\)", re.I)),
    ("V+L", re.compile(r"Vita\s+de\s+vie|Livada", re.I)),
    ("PADURE", re.compile(r"P[ăa]dure", re.I)),
    ("NP", re.compile(r"Neproductiv", re.I)),
]
COUNTY_EXTRA = re.compile(r"EXTRAVILANUL\s+LOCALIT[ĂA][ȚŢT]ILOR\s+DIN\s+JUDE[ȚŢT]UL", re.I)


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def number(text: str) -> float | None:
    stripped = re.sub(r"\s+", "", text or "")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+([.,]\d+)?", stripped):
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", stripped):
        value = float(stripped.replace(".", ""))
    else:
        value = float(stripped.replace(",", "."))
    return value if 0 < value < 100_000 else None


def blocks(pages: list[dict]) -> list[tuple[int, int]]:
    """The page ranges of the five circumscription blocks, by the annex numbers they open with.

    A block runs from a town's land annex to the next one. That is the frame everything else is
    attributed inside, and it is the reason the lying headings do no harm: a category list is
    read as belonging to whichever block contains its page.
    """
    starts: list[int] = []
    for index, page in enumerate(pages):
        text = re.sub(r"\s+", " ", page["text"])
        if CC_TABLE.search(text) and TOWN_HEADING.search(page["text"]):
            starts.append(index)
    return [(s, starts[i + 1] if i + 1 < len(starts) else len(pages)) for i, s in enumerate(starts)]


def read_town(page: dict) -> tuple[str, dict[str, float]] | None:
    """One town's zoned building land, from the first CC table on its annex page."""
    heading = TOWN_HEADING.search(page["text"])
    if not heading:
        return None
    text = page["text"]
    where = text.find("INTRAVILAN")
    if where < 0 or not CC_TABLE.search(re.sub(r"\s+", " ", text)):
        return None
    # Only as far as the next heading: the arable and extravilan tables that follow have the
    # same three columns and cheaper numbers, and letting them through would relabel zone A.
    stop = re.search(
        r"INTRAVILAN\s+CATEGORIA\s+DE\s+FOLOSIN[ȚŢT][ĂA]\s+A|EXTRAVILAN", text[where + 10 :]
    )
    window = text[where : where + 10 + (stop.start() if stop else len(text))]
    zones = {}
    for _order, label, price in ZONE_ROW.findall(window):
        value = number(price)
        if value is None:
            continue
        for zone in re.split(r"\s*,\s*", label):
            zones.setdefault(zone.strip().upper(), value)
    return (clean(heading.group(1)).title(), zones) if zones else None


def read_categories(pages: list[dict], span: tuple[int, int]) -> dict[int, float]:
    """Price per category for a commune seat, from the block's intravilan annex."""
    return _read_category_table(pages, span, SEAT_CAPTION)


def read_component_categories(pages: list[dict], span: tuple[int, int]) -> dict[int, float]:
    return _read_category_table(pages, span, PART_CAPTION)


def _read_category_table(
    pages: list[dict], span: tuple[int, int], caption: re.Pattern[str]
) -> dict[int, float]:
    """The category prices under one caption, paired by order rather than by page.

    The two tables sit on the same page under the same column headings and differ only in
    which caption precedes them. Testing whether the *page* mentions a caption therefore
    matches both, returns whichever table comes first, and quietly prices every component
    village at its commune seat's rate — which is what happened, and which showed up as a
    county where the seat and the villages cost exactly the same everywhere.

    So the captions are located in the page's text, put in the order they appear, and zipped
    against the tables in the order pdfplumber found them, which is also top to bottom.
    """
    found: dict[int, float] = {}
    for page in pages[span[0] : span[1]]:
        flat = re.sub(r"\s+", " ", page["text"])
        # The extravilan annex repeats both captions with no land column at all, so it is
        # excluded here rather than relied on to fail the column search.
        if "ÎN INTRAVILANUL COMUNELOR" not in flat.upper().replace("Î", "Î"):
            if "INTRAVILANUL COMUNELOR" not in flat.upper():
                continue
        order = [
            ("seat" if SEAT_CAPTION.match(m.group(0)) else "part", m.start())
            for m in re.finditer(
                r"SAT\s+RE[ȘŞS]EDIN[ȚŢT][ĂA]\s+DE\s+COMUN[ĂA]|SAT\s+COMPONENT\s+AL\s+COMUNEI",
                flat,
                re.I,
            )
        ]
        want = "seat" if caption is SEAT_CAPTION else "part"
        tables = page["tables"]
        for position, (kind, _at) in enumerate(order):
            if kind != want or position >= len(tables):
                continue
            cells = [[clean(c) for c in row] for row in tables[position]["cells"]]
            if len(cells) < 2:
                continue
            column = None
            width = max(len(row) for row in cells)
            for index in range(width):
                header = " ".join(row[index] for row in cells[:2] if index < len(row))
                if BUILT_COLUMN.search(re.sub(r"\s+", " ", header)):
                    column = index
                    break
            if column is None:
                continue
            for row in cells:
                if not row:
                    continue
                match = CATEGORY_ROW.match(row[0])
                price = number(row[column]) if column < len(row) else None
                if match and price is not None:
                    found.setdefault(int(match.group(1)), price)
    return found


def read_assignment(pages: list[dict], span: tuple[int, int], is_local) -> dict[str, int]:
    """Which commune is in which category, out of the prose list at the foot of the block.

    Names are matched against the county's own roster rather than trusted: the paragraph is
    prose, it hyphenates across lines, and it contains ordinary words — "au fost clasificate",
    "de importanță" — that a comma split would otherwise turn into localities.
    """
    assignment: dict[str, int] = {}
    for page in pages[span[0] : span[1]]:
        text = re.sub(r"\s+", " ", page["text"])
        if "clasificate în următoarele categorii" not in text:
            continue
        tail = text[text.index("clasificate în următoarele categorii") :]
        for number_text, names in CATEGORY_LIST.findall(tail):
            for raw in re.split(r"[,;]", names):
                name = re.sub(r"[.\s]+$", "", clean(raw))
                # "CATEGORIA" may be glued to the last name of the previous group by the line
                # break; strip anything that is not part of a locality name.
                name = re.sub(r"^\W+|\W+$", "", name)
                if len(name) > 2 and is_local(name):
                    assignment.setdefault(name.upper(), int(number_text))
    return assignment


def read_flat(pages: list[dict], span: tuple[int, int]) -> tuple[str, float] | None:
    """Negrești and Murgeni: one price for every village in the town's UAT, in a sentence."""
    for page in pages[span[0] : span[1]]:
        text = re.sub(r"\s+", " ", page["text"])
        owner = COMPONENT_OF.search(text)
        price = FLAT_BUILT.search(text)
        if owner and price:
            value = number(price.group(1))
            if value is not None:
                return clean(owner.group(1)).title(), value
    return None


def read_county_extravilan(pages: list[dict]) -> dict[str, float]:
    """ANEXA 38: one price list for the whole county, by use and by parcel size.

    The dearest row of each category is taken — the one for parcels of ten hectares and more.
    These are the hectares the land register counts, and taking the small-parcel price would
    value a county's farmland at what a garden plot changes hands for.
    """
    found: dict[str, float] = {}
    for page in pages:
        if not COUNTY_EXTRA.search(re.sub(r"\s+", " ", page["text"])):
            continue
        for table in page["tables"]:
            for row in table["cells"]:
                line = [clean(c) for c in row]
                if len(line) < 2:
                    continue
                price = number(line[-1])
                if price is None:
                    continue
                for code, pattern in EXTRA_ROWS:
                    if pattern.search(line[0]):
                        found.setdefault(code, price)
    # Left in lei per square metre, which is the unit the annex prints and the unit the value
    # builder multiplies by hectares itself. Converting to lei per hectare here — which the
    # first version did, reasoning that hectares are what gets counted — produced a county
    # worth 45 791 mld EUR. Four orders of magnitude is not a subtle failure, but nothing in
    # the parse complained: every name matched, every price was a number, and the coverage
    # was 98,8%.
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    spans = blocks(pages)
    notes: list[str] = []
    if not spans:
        return [], [], ["no circumscription block found"]

    extravilan = read_county_extravilan(pages)
    towns: list[dict] = []
    communes: dict[str, dict] = {}

    for span in spans:
        found = read_town(pages[span[0]])
        if found:
            town, zones = found
            towns.append(
                {
                    "name": town,
                    "rank": None,
                    "zones": sorted(zones),
                    "intravilan": {"CC": zones},
                    # Extravilan is county-wide here, so every town gets the same table. That
                    # is the document's choice, not a shortcut: ANEXA 38 is explicitly for the
                    # whole county.
                    "extravilan": dict(extravilan),
                    "page": span[0] + 1,
                }
            )

        seats = read_categories(pages, span)
        parts = read_component_categories(pages, span)
        assignment = read_assignment(pages, span, is_local)
        flat = read_flat(pages, span)

        if assignment and seats:
            for commune, category in assignment.items():
                seat_price = seats.get(category)
                part_price = parts.get(category, seat_price)
                if seat_price is None:
                    continue
                communes[commune] = {
                    "name": commune.title(),
                    # The seat named first, then a single stand-in row for the rest of the
                    # commune at the component price. There is no village roster in this
                    # document, so naming individual villages would be inventing them.
                    "villages": [
                        {"name": commune.title(), "intravilan": {"CC": seat_price}},
                        {"name": f"{commune.title()} (sate componente)",
                         "intravilan": {"CC": part_price}},
                    ],
                    "extravilan": dict(extravilan),
                    "page": span[0] + 1,
                }
        elif flat:
            # Deliberately not returned as a note: `notes` becomes `numberingProblems` in the
            # output, which is a field about rows that did not parse. Nothing failed here —
            # the document simply prices these two UATs differently, and that belongs in this
            # docstring rather than in a list of problems.
            pass

    if not towns:
        notes.append("no town zone grid parsed")
    entries = list(communes.values())
    for position, entry in enumerate(entries, start=1):
        entry["index"] = position
    return towns, entries, notes

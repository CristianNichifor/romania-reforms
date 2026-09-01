"""The CNP Alba Iulia dialect, read as tables rather than as text.

Bacău's study can be parsed from flattened text because every value sits on the same line as
the thing it prices. Alba's cannot, and the reason is worth stating precisely: its tables use
**merged cells**, and merging is invisible once a PDF is flattened to lines.

The county's extravilan grid is the clean example. Flattened, a row reads

    A 28 8.7 24.0 4

under a header of six categories — Arabil, Fânețe și pășuni, Livezi, Vii, Păduri, Alte
terenuri. Four numbers, six columns, and nothing in the text says which two are missing. Read
positionally the 4 lands on Vii and everything after it shifts. Read as a table it is

    ['A', '28', '8.7', '24.0', '', '', '4']

— Vii and Păduri are genuinely empty, and `Alte terenuri` is 4. The blanks are the data.

The same applies to the rural table, where a value spans several villages:

    ['ALMAŞUL MARE', 'Almaşul Mare', '540', '7.6', '2.4', '2', '3.0', '3.0', '3.2', '1.5']
    ['',             'Almaşul Mic',  '380', '5.9', '',    '',  '',    '',    '',    ''   ]
    ['',             'Brădet',       '',    '',    '',    '',  '',    '',    '',    ''   ]

Brădet is not a village without a price. It shares Almaşul Mic's, because the cell is merged
down the column — so a blank inherits from above, and that inheritance is the whole reason
this file exists.

**The values are lei/m², not euro.** Bacău's chamber prices in euro and Alba's in lei, which
is why currency travels with the study rather than being a constant of the repository.

Two categories of the Fiscal Code's world collapse here: the study prices Livezi and Vii
separately where the notaries' shared vocabulary has one code for both, so the two are
averaged when both are published and taken singly when only one is.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# Where the study's own extravilan categories land in the shared vocabulary. Livezi and Vii
# are averaged into V+L; "alte terenuri" covers water and unproductive land alike, so it
# prices both rather than leaving one of them unvalued.
EXTRAVILAN_TO_NOTARY = {"A": ["A"], "P+F": ["P+F"], "ALTE": ["NP", "AP"]}

# Internal spaces are literal: with \s the name ran past the line break and swallowed the
# "APARTAMENTE ÎN BLOCURI" heading that follows it.
TOWN_NAME = re.compile(r"(MUNICIPIUL|ORA[ŞS]UL)[ \t]+([A-Za-zĂÂÎŞŞȚŢăâîșşțţ][\w \t\-\.]*)")
ZONES = ["A", "B", "C", "D"]
LINE_TABLE = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}


def number(cell: str | None) -> float | None:
    """A cell of the study, or None when it is blank — which means merged, not zero."""
    if not cell:
        return None
    text = cell.strip().replace(" ", "")
    # Both separators appear, sometimes on facing pages of the same document.
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", text):
        return None
    return float(text)


def _merge_vine_and_orchard(values: dict[str, float]) -> dict[str, float]:
    published = [values[key] for key in ("LIVEZI", "VII") if values.get(key) is not None]
    if published:
        values["V+L"] = sum(published) / len(published)
    # LIVEZI and VII are spent — they became V+L. PADURE is dropped because forest is valued
    # per hectare in a table of its own and its area is carried separately. ALTE terenuri is
    # kept: it is the only price the study gives for water and unproductive land, and
    # dropping it here left both unpriced in every commune and every town.
    return {k: v for k, v in values.items() if k not in ("LIVEZI", "VII")}



class Table:
    """One table out of the cache, with the geometry the reader needs.

    A stand-in for pdfplumber's own object so the reading logic did not have to change when
    the source moved from the PDF to the cache. It carries exactly what the merged-cell
    recovery uses — the column edges, each row's box, and the extracted cells.
    """

    def __init__(self, raw: dict) -> None:
        self.bbox = raw["bbox"]
        self.column_edges = raw["columns"]
        self.row_boxes = raw["rows"]
        self._cells = raw["cells"]

    def extract(self) -> list[list[str]]:
        return self._cells


class Page:
    """One page out of the cache: its text, its tables and its words with their boxes."""

    def __init__(self, raw: dict) -> None:
        self._raw = raw
        self.tables = [Table(t) for t in raw["tables"]]

    def extract_text(self) -> str:
        return self._raw["text"]

    def extract_tables(self, _settings: dict | None = None) -> list[list[list[str]]]:
        return [t.extract() for t in self.tables]

    def find_tables(self, _settings: dict | None = None) -> list[Table]:
        return self.tables

    def extract_words(self) -> list[dict]:
        return [
            {"text": text, "x0": x0, "x1": x1, "top": top}
            for text, x0, x1, top in self._raw["words"]
        ]


def rows_from_words(page, table) -> list[list[str]]:
    """Rebuild a table's rows from word positions and its own column edges.

    pdfplumber's cell extraction drops rows it cannot fit to ruling lines, and it does so
    silently. On one page of Alba's study that cost the commune of Ponor entirely: its label
    and its five extravilan values sit inside the table's own bounding box, at coordinates
    the extractor simply did not return a cell for.

    The geometry is not in doubt, though — the table knows where its columns are, and every
    word knows its x. So the rows are rebuilt by assigning each word to the column whose span
    contains it and grouping words that share a baseline. Nothing is inferred: a word lands in
    the column it is printed in.
    """
    edges = sorted({*table.column_edges, table.bbox[2]})
    if len(edges) < 4:
        return []
    # A little above the table, because a row that straddles its top edge is exactly the kind
    # the cell extractor loses. Not so far as to reach the page banner.
    top = table.bbox[1] - 40
    words = [
        word
        for word in page.extract_words()
        if edges[0] - 2 <= word["x0"] < edges[-1] and top <= word["top"] <= table.bbox[3]
    ]
    lines: dict[int, list[dict]] = {}
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        key = next((k for k in lines if abs(k - word["top"]) <= 3), round(word["top"]))
        lines.setdefault(key, []).append(word)

    rows: list[list[str]] = []
    for key in sorted(lines):
        cells = [""] * (len(edges) - 1)
        for word in lines[key]:
            middle = (word["x0"] + word["x1"]) / 2
            for index in range(len(edges) - 1):
                if edges[index] <= middle < edges[index + 1]:
                    cells[index] = f"{cells[index]} {word['text']}".strip()
                    break
        if any(cells):
            rows.append(cells)
    return rows


def repair(page, found, is_commune) -> list[list[str]]:
    """The extracted table, with what the cell extractor lost put back from word positions.

    Two losses, both real and both silent. pdfplumber drops rows it cannot fit to ruling
    lines, and where a commune's cell is merged down several villages it returns one tall row
    and no commune name at all — on page 61 of Alba's study that lost Ponor entirely.

    Cells stay the source of truth for structure, because they join wrapped text and word
    positions cannot: GÎRDA DE / SUS is one commune printed on two lines, and reading every
    row from words splits half the county's names in two. Words are used only to fill a blank
    row, or an empty commune cell from a label printed inside that row's own vertical span.
    The commune label sits vertically centred in its merged cell, which is why it can appear
    two villages below the row it belongs to and why the span, not the baseline, is what
    decides.
    """
    extracted = [[(c or "").strip() for c in row] for row in found.extract()]
    rows = found.row_boxes
    rebuilt = [row for row in rows_from_words(page, found) if any(row)]
    if not rebuilt or len(rows) != len(extracted):
        return extracted

    spare = [row for row in rebuilt]
    for index, row in enumerate(extracted):
        if not any(row) and spare:
            extracted[index] = (spare.pop(0) + [""] * len(row))[:len(row)]

    # A merged commune cell comes back empty, so the label is read out of the words printed
    # in the first column — the table's own geometry, not a guess. Each label is then spent
    # once, on the first row whose box contains it: a merged cell spans every village of the
    # commune, so filling every row it covers would restart the commune at each village and
    # turn one commune into eight.
    edges = sorted({*found.column_edges, found.bbox[2]})
    if len(edges) < 2:
        return extracted
    column_words = sorted(
        (
            word
            for word in page.extract_words()
            if edges[0] - 2 <= (word["x0"] + word["x1"]) / 2 < edges[1]
            and found.bbox[1] <= word["top"] <= found.bbox[3]
        ),
        key=lambda w: (w["top"], w["x0"]),
    )
    # A name can wrap onto a second or third printed line — GÎRDA DE / SUS, ROŞIA / MONTANĂ,
    # and on a continuation page a third line reading CONTINUARE. Rather than guess a line
    # spacing that separates a wrap from the next commune, every run of up to three lines is
    # offered and the register decides: a label is only accepted if it names a commune the
    # county actually has. Guessing thresholds produced AVRAM and IANCU as two communes.
    labels: list[tuple[float, str]] = []
    for start in range(len(column_words)):
        for length in (3, 2, 1):
            group = column_words[start : start + length]
            if len(group) < length or group[-1]["top"] - group[0]["top"] > 40:
                continue
            text = " ".join(word["text"] for word in group)
            if is_commune(text):
                # A continuation page repeats the commune under it as "X CONTINUARE". The
                # marker is a word of its own, so it never survives the register check that
                # accepted the name — and without it the three communes whose tables run onto
                # a second page were each read twice.
                tail = column_words[start + length : start + length + 2]
                if any(
                    word["text"].upper().startswith("CONTINUARE")
                    and word["top"] - group[-1]["top"] <= 40
                    for word in tail
                ):
                    text = f"{text} CONTINUARE"
                labels.append((group[0]["top"], text))
                break

    def flat(text: str) -> str:
        return re.sub(r"[^a-z]", "", text.lower())

    already = {flat(row[0]) for row in extracted if row and row[0]}
    for top, text in labels:
        # A label the extractor already placed is not a second commune. Without this every
        # correctly-read commune was found again in the next empty cell its merged box
        # covered, and the county came back with 130 communes instead of 67.
        if flat(text) in already:
            continue
        for index, cells in enumerate(extracted):
            box = rows[index]
            if cells and not cells[0] and box[0] <= top <= box[1]:
                cells[0] = text
                already.add(flat(text))
                break
    return extracted


def compact(table: list[list[str | None]]) -> list[list[str]]:
    """Drop columns that are empty in every row, then read the rest from the left.

    The same table is drawn three widths in one document: ten columns where it starts, nine
    where it runs onto the next page and loses "alte terenuri", and thirteen in the Câmpeni
    circumscription where empty spacer columns sit between the captions. Compacting first
    makes all three the same table, which is cheaper and steadier than deriving column
    indices from a header that most pages of the table do not repeat.
    """
    rows = [[(c or "").strip() for c in row] for row in table]
    width = max((len(row) for row in rows), default=0)
    rows = [row + [""] * (width - len(row)) for row in rows]
    keep = [i for i in range(width) if any(row[i] for row in rows)]
    return [[row[i] for i in keep] for row in rows]


CAPTIONS: list[tuple[str, str]] = [
    ("CC", r"valoarea\s+teren\s+intravilan"),
    ("A", r"^arabil"),
    ("P+F", r"^f[âa]ne[țţ]e"),
    ("LIVEZI", r"^livezi"),
    ("VII", r"^vii"),
    ("PADURE", r"^p[ăa]duri"),
    ("ALTE", r"^alte\s+terenuri"),
    ("CONSTRUCTII", r"valorile\s+pentru\s+construc"),
    ("SATUL", r"^satul$"),
    ("COMUNA", r"^comuna$"),
]


def read_layout(table: list[list[str]]) -> dict[str, int] | None:
    """Which column holds what, read from the table's own captions.

    Not positional. The same table is drawn at three widths in one document, and where a
    middle column is blank — Vii and Păduri are empty for most of the Apuseni communes —
    counting from the left slides "alte terenuri" into "vii" and prices orchards as scrub.
    The captions are the only thing that says which column is which.
    """
    found: dict[str, int] = {}
    for row in table[:8]:
        for index, cell in enumerate(row):
            text = re.sub(r"\s+", " ", cell).strip().lower()
            if not text:
                continue
            for key, pattern in CAPTIONS:
                if key not in found and re.search(pattern, text):
                    found[key] = index
    if "A" not in found:
        return None

    # The left-hand captions — COMUNA, SATUL, the two value columns — are printed rotated on
    # about half the pages, so they arrive as their letters stacked one per line and no
    # pattern matches them. Their positions are fixed relative to Arabil, which is always
    # printed the right way up, so they are counted back from it rather than read.
    arabil = found["A"]
    for offset, key in ((1, "CC"), (2, "CONSTRUCTII"), (3, "SATUL")):
        found.setdefault(key, arabil - offset)
    found.setdefault("COMUNA", 0)
    # Same for the extravilan captions, which a continuation page can also lose.
    for offset, key in enumerate(("P+F", "LIVEZI", "VII", "PADURE", "ALTE"), start=1):
        found.setdefault(key, arabil + offset)
    if found["SATUL"] <= found["COMUNA"]:
        return None
    return found


def prices_villages(table: list[list[str]], layout: dict[str, int]) -> bool:
    """Whether this table actually prices villages, judged through its own layout.

    The earlier version guessed that the village sat in column 1, which is true of most pages
    and false of the Câmpeni circumscription, where a spacer column survives compaction
    because the page number sits in it. Asking the layout instead costs nothing and stops the
    check disagreeing with the parse.
    """
    priced = 0
    for cells in table:
        village = cells[layout["SATUL"]] if layout["SATUL"] < len(cells) else ""
        value = cells[layout["CC"]] if layout["CC"] < len(cells) else ""
        if village and number(village) is None and number(value) is not None:
            priced += 1
    return priced >= 2


def parse_rural(pages: list[Page], is_commune) -> tuple[list[dict], list[str]]:
    """Communes and their villages, with merged cells inherited down the column."""
    communes: list[dict] = []
    problems: list[str] = []
    current: dict | None = None
    last_intravilan: dict[str, float] = {}
    # A continuation page repeats no captions, so the layout of the page that opened the
    # table is carried until a new header appears.
    carried: dict[str, int] | None = None

    for index, page in enumerate(pages):
        for found in page.find_tables(LINE_TABLE):
            table = compact(repair(page, found, is_commune))
            layout = read_layout(table) or carried
            if layout is None or not prices_villages(table, layout):
                continue
            carried = layout

            def at(cells: list[str], key: str, layout: dict[str, int] = layout) -> str:
                index = layout.get(key, -1)
                return cells[index] if 0 <= index < len(cells) else ""

            for cells in table:
                commune_cell = at(cells, "COMUNA")
                village_cell = at(cells, "SATUL")
                has_village = bool(
                    village_cell and re.search(r"[A-Za-zĂÂÎȘŞȚŢăâîșşțţ]", village_cell)
                )
                # A header row repeats the column captions inside the table body.
                if has_village and village_cell.lower().startswith(("satul", "sat")):
                    has_village = False
                # The column captions are printed rotated, so they arrive as single letters
                # stacked with newlines — "L\nU\nT\nA\nS" is the word SATUL on its side.
                if "\n" in village_cell or len(village_cell.replace(" ", "")) < 3:
                    has_village = False
                if re.match(r"(TERENURI|VALOAREA?|ZONA|COMUNA)\b", village_cell, re.I):
                    has_village = False

                # A table that runs onto the next page repeats its commune as "X
                # CONTINUARE". That is the same commune, not a new one, and reading it as new
                # both invented a commune and orphaned the villages under it.
                continuation = bool(re.search(r"\bCONTINUARE\b", commune_cell, re.I))
                commune_cell = re.sub(r"\s*CONTINUARE\s*$", "", commune_cell, flags=re.I).strip()
                # The register decides what is a commune. Without it the table's own caption
                # rows — "COMUNA", and the paragraph introducing each circumscription — were
                # read as twenty-three communes the county does not have.
                if commune_cell and not continuation and is_commune(commune_cell):
                    current = {
                        "name": re.sub(r"\s+", " ", commune_cell).strip(),
                        "villages": [],
                        "extravilan": {},
                        "page": index + 1,
                    }
                    communes.append(current)
                    last_intravilan = {}
                if current is None:
                    if has_village:
                        problems.append(
                            f"village {village_cell!r} before any commune, page {index + 1}"
                        )
                    continue

                named = {key: number(at(cells, key)) for key, _ in CAPTIONS}
                # A commune's extravilan can be printed on the row that carries only its
                # label — Ponor's is — so it is read before the village check rather than
                # after it. Skipping label-only rows left two communes priced for building
                # land and for nothing else.
                extravilan = {
                    k: v
                    for k, v in named.items()
                    if v is not None and k in ("A", "P+F", "LIVEZI", "VII", "PADURE", "ALTE")
                }
                if extravilan and not current["extravilan"]:
                    folded = _merge_vine_and_orchard(dict(extravilan))
                    spread: dict[str, float] = {}
                    for key, value in folded.items():
                        for code in EXTRAVILAN_TO_NOTARY.get(key, [key]):
                            spread[code] = value
                    current["extravilan"] = spread
                if not has_village:
                    continue

                intravilan = {"CC": named["CC"]} if named.get("CC") is not None else {}
                # A blank is a merged cell: the village shares the price printed above it.
                if not intravilan:
                    intravilan = dict(last_intravilan)
                else:
                    last_intravilan = dict(intravilan)
                if intravilan:
                    current["villages"].append(
                        {"name": re.sub(r"\s+", " ", village_cell), "intravilan": intravilan}
                    )

    return communes, problems


def parse_towns(pages: list[Page]) -> list[dict]:
    """Towns, priced by zone letter in a table of their own, a page or two after their name."""
    towns: list[dict] = []
    pending_name = ""
    for index, page in enumerate(pages):
        text = page.extract_text() or ""
        found = TOWN_NAME.search(text)
        if found:
            pending_name = re.sub(r"\s+", " ", found.group(2)).strip(" .-")

        tables = page.extract_tables()
        intravilan: dict[str, float | None] = {}
        extravilan_by_zone: dict[str, dict[str, float]] = {}
        for table in tables:
            flat = [(c or "").strip() for row in table for c in row]
            # The heading has to be in the table, not merely on the page. Every town's land
            # table is preceded by tables of the same shape for flats, houses and commercial
            # space — all "LEI/mp" against zones A to D — so matching the shape alone priced
            # Alba Iulia's land at 3.200 lei/m², which is what a flat costs there, not a
            # square metre of ground.
            heading = any("TERENURI INTRAVILANE" in c.upper() for c in flat)
            if heading and any(c.upper().startswith("LEI/MP") for c in flat):
                for row in table:
                    cells = [(c or "").strip() for c in row]
                    if cells and cells[0].upper().startswith("LEI/MP"):
                        # The zone values, skipping blanks: most towns carry an empty spacer
                        # cell straight after "LEI/mp", and slicing positionally read that
                        # blank as zone A and dropped ten of the county's eleven towns.
                        values = [v for v in (number(c) for c in cells[1:]) if v is not None]
                        if len(values) >= len(ZONES):
                            intravilan = dict(zip(ZONES, values[: len(ZONES)], strict=True))
            head = [c.strip() for c in (table[0] if table else []) if c]
            if head and head[0].lower() == "zona" and any("Arabil" in c for c in head):
                captions = [c.strip() for c in table[0]]
                for row in table[1:]:
                    cells = [(c or "").strip() for c in row]
                    if cells[0] not in ZONES:
                        continue
                    values: dict[str, float] = {}
                    for caption, cell in zip(captions[1:], cells[1:], strict=False):
                        value = number(cell)
                        if value is None:
                            continue
                        low = caption.lower()
                        key = (
                            "A" if low.startswith("arabil")
                            else "P+F" if "pășuni" in low or "pasuni" in low
                            else "LIVEZI" if "livezi" in low
                            else "VII" if low.startswith("vii")
                            else "ALTE" if "alte" in low
                            else None
                        )
                        if key:
                            values[key] = value
                    if values:
                        extravilan_by_zone[cells[0]] = values

        if intravilan and pending_name:
            # The extravilan grid varies by zone where the shared model carries one price per
            # locality, so the zones are averaged. Stated rather than hidden: it is the same
            # kind of unweighted average the rest of this simulator reports as a band.
            merged: dict[str, list[float]] = {}
            for values in extravilan_by_zone.values():
                for key, value in _merge_vine_and_orchard(dict(values)).items():
                    merged.setdefault(key, []).append(value)
            spread: dict[str, float] = {}
            for key, series in merged.items():
                for code in EXTRAVILAN_TO_NOTARY.get(key, [key]):
                    spread[code] = round(sum(series) / len(series), 4)
            towns.append(
                {
                    "name": pending_name,
                    "rank": None,
                    "zones": ZONES,
                    "intravilan": {"CC": intravilan},
                    "extravilan": spread,
                    "page": index + 1,
                }
            )
            pending_name = ""
    return towns


def parse(name: str, is_commune) -> tuple[list[dict], list[dict], list[str]]:
    """Read one chamber's study out of the cache. No PDF is opened here.

    That is the whole point of the cache: extraction takes thirty seconds and is the same
    every time, so it happens once for the country and a reader iterates against the result
    in about fifty milliseconds.
    """
    pages = [Page(raw) for raw in load(name)["pages"]]
    return parse_towns(pages), *parse_rural(pages, is_commune)

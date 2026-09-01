"""The CNP Târgu Mureș dialect: the same three columns, printed once per category.

Mureș and Harghita are the tidiest grids in the whole set, and they are also the ones where
the shape of the table says least. Every land table is the same three columns —

    LOCALITATEA · ZONA · VALOARE UNITARĂ

— repeated for building land and then once for each cadastral category, so the table alone
cannot tell arable from pasture from a town centre. What the category *is* is printed above
the table as a page heading, and nowhere else:

    TERENURI SITUATE ÎN INTRAVILANUL LOCALITĂȚILOR
    TERENURI SITUATE ÎN EXTRAVILANUL LOCALITĂŢILOR
    CATEGORIA DE FOLOSINŢĂ ARABIL

A section runs on past its heading — Mureș's arable block is pages 248 and 249, and only the
first says what it holds — so the heading sets a mode that the pages after it inherit until
the next heading replaces it.

**Case is the whole distinction between a heading and a mention.** The same words open the
contents page (`Categoria de folosinţă arabil ....... 170`) and the prose chapters that explain
what counts as arable, forty pages before any price. Matching them case-insensitively set the
mode from the table of contents and again from a sentence, and put building-land prices into
the arable column. Only the upper-case form is a heading; that is not a heuristic, it is how
the document is typeset.

Rows come in two shapes under one header. A municipality is priced zone by zone and a commune
by a single figure, and the rows are told apart by whether the ZONA column holds anything —
the `Municipiu` / `Oraşe` / `Comune` lines that separate them are captions, not places, and
fall out on their own because the register does not know a locality called `Comune`.

Both counties are in **lei per square metre**, forests included. Forest used to be read and
thrown away here and in every other reader, on the grounds that the shared vocabulary had no
code for it — which put a third of the county's surface into the land value at zero. It has a
code now.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# Upper-case only, and deliberately so — see the module docstring. The trailing text is
# allowed to wrap ("PĂDURI ŞI ALTE TERENURI CU / VEGETAŢIE FORESTIERĂ" breaks mid-heading).
INTRA_HEAD = re.compile(r"TERENURI SITUATE ÎN INTRAVILANUL")
EXTRA_HEAD = re.compile(r"TERENURI SITUATE ÎN EXTRAVILANUL")
CATEGORY_HEAD = re.compile(r"CATEGORIA DE FOLOSIN[ŢT][ĂA]\s+(.+)")
CATEGORIES: list[tuple[str, str]] = [
    ("A", r"ARABIL"),
    ("P+F", r"P[ĂA][ŞS]UNI"),
    ("V+L", r"VII|LIVEZI"),
    ("PADURE", r"P[ĂA]DURI"),
]
HEADER = re.compile(r"LOCALITATEA", re.I)
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
ZONE_CELL = re.compile(r"^([A-F])$", re.I)
# "Satul Izvoru Mureşului, comuna Voşlobeni" — a village priced apart from its commune, and
# the commune is the second half of the label rather than the first.
VILLAGE_OF = re.compile(r"comuna\s+(.+)$", re.I)
# "Joseni, inclusiv Borzont", "Gheorgheni + staţiunea Lacul Roşu" — the commune, then the
# villages that share its price. Ten of Harghita's communes are named only this way.
TAIL = re.compile(r"\s*(?:,|\+|\binclusiv\b).*$", re.I)


def head(label: str) -> str:
    """The locality a row is about, out of a label that also lists what shares its price."""
    village = VILLAGE_OF.search(label)
    return TAIL.sub("", village.group(1) if village else label).strip()


def number(cell: str) -> float | None:
    """A price in lei: comma marks the decimal, a dot groups thousands."""
    text = re.sub(r"\s+", "", cell)
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?", text):
        return None
    value = float(text.replace(".", "").replace(",", "."))
    return value if 0 < value < 100_000 else None


def mode_of(text: str, current: str | None) -> str | None:
    """The section this page belongs to, or the one carried over from the page before.

    Read in the order the headings appear so a page that closes the extravilan preamble and
    opens the arable block — which is how every circumscription starts its extravilan run —
    ends on the category rather than on the generic caption above it.
    """
    mode = current
    for match in re.finditer(
        r"TERENURI SITUATE ÎN INTRAVILANUL|TERENURI SITUATE ÎN EXTRAVILANUL"
        r"|CATEGORIA DE FOLOSIN[ŢT][ĂA]\s+(.+)",
        text,
    ):
        if INTRA_HEAD.match(match.group(0)):
            mode = "CC"
        elif EXTRA_HEAD.match(match.group(0)):
            # A caption with no category under it yet; the category heading follows on the
            # same page and replaces this. Held so a stray extravilan page cannot keep
            # writing into whatever category was last seen.
            mode = None
        else:
            caption = (match.group(1) or "").upper()
            mode = next((code for code, p in CATEGORIES if re.search(p, caption)), None)
    return mode


def rows(cells: list[list[str]], is_local) -> list[tuple[str, str | None, float]]:
    """(locality, zone, price) for every priced row of one table."""
    found: list[tuple[str, str | None, float]] = []
    for row in cells:
        line = [re.sub(r"\s+", " ", c or "").strip() for c in row]
        if len(line) < 3:
            continue
        label, zone, price = head(line[0]), line[1], number(line[2])
        if price is None or not NAME.match(label) or not is_local(label):
            continue
        letter = ZONE_CELL.match(zone)
        found.append((label, letter.group(1).upper() if letter else None, price))
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    zoned: dict[str, dict[str, float]] = {}
    flat: dict[str, list[float]] = {}
    extravilan: dict[str, dict[str, float]] = {}
    pages_of: dict[str, int] = {}
    mode: str | None = None

    for index, page in enumerate(pages, start=1):
        mode = mode_of(page["text"], mode)
        if mode is None:
            continue
        for table in page["tables"]:
            cells = [[c or "" for c in row] for row in table["cells"]]
            if len(cells) < 3 or len(cells[0]) != 3:
                continue
            # The header is not always the first row: about a third of these tables open with
            # an empty one, and looking only at row zero lost eighteen of Mureș's communes
            # and the whole of the Luduș circumscription's building land.
            if not any(HEADER.search(c) for row in cells[:3] for c in row):
                continue
            for label, zone, price in rows(cells, is_local):
                key = label.upper()
                if mode == "CC":
                    pages_of.setdefault(key, index)
                    if zone:
                        zoned.setdefault(key, {})[zone] = price
                    else:
                        flat.setdefault(key, []).append(price)
                else:
                    extravilan.setdefault(key, {}).setdefault(mode, price)

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
    communes = []
    for key, prices in flat.items():
        if key in zoned:
            # A town whose attached villages are priced flat below its zoned rows; its zones
            # already carry it and the villages would otherwise re-enter as a commune of the
            # same name.
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
    return towns, communes, []

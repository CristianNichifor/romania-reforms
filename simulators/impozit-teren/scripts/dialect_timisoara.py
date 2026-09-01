"""The CNP Timișoara dialect: read by geometry, because there is no table to read.

Timiș publishes its land in two annexes that pdfplumber finds no table in at all — there are no
ruling lines, so there is nothing for it to detect. Flattened to text the pages are unreadable
in a different way, because four independent columns of `Localitate · Valoare` sit side by side
and every line interleaves all four:

    Jimbolia          zona A 38   Cenei 7   Giarmata 40   Albina 25
    zona B 15                     Bobda 6   Cerneteaz 35  Moșnița Veche  zona A 95

Read as a line, "zona B 15 Bobda 6" is one row of something. It is two halves of two different
communes. So this reads the **word coordinates** instead — the only dialect here that does —
and recovers the columns from where the words actually are on the page. The header row gives
the boundaries: four `Localitate` labels at x ≈ 33, 209, 384 and 558, and everything between
one and the next belongs to that column.

The geometry is regular enough to trust: each of the four value columns carries the same count
of numbers per page, give or take the last one on the final page.

**A zone row continues the locality above it, in its own column.** `Giroc zona A 140` then
`zona B 75` beneath — but "beneath" means beneath *within that column*, which is exactly what a
line-based reader cannot see and what makes this county worth the geometry.

Two annexes, and between them the whole county:

    anexa 14   intravilan, euro/m², by locality and where zoned by zone
    anexa 15   extravilan arable, euro/ha, by locality

Pasture and hayfield are not published as a column. They are published as a sentence — *90% din
terenul arabil* — so they are derived from arable at the rate the document states rather than
left empty or guessed at.

The county is five files, one per court circumscription, so this finds its own siblings in the
cache the way the Bihor reader does.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import CACHE, load  # noqa: E402

M2_PER_HA = 10_000
# The five circumscriptions the county is published in.
SIBLINGS = ("Timisoara", "Lugoj", "Deta", "Faget", "Sannicolau_Mare")
# What this reader needs fetched before it can run, matched against the chamber's own file
# list in sources/studies-<year>.json.
#
# `siblings()` below globs the *cache*, which is right once everything is extracted and wrong
# on a clean checkout: the importer primed only the document it was asked for, this found one
# annex of five, and the county came out at 36,4% instead of 93,9%. Nothing errored — four
# fifths of Timiș simply were not there. The coverage gate caught it, which is what it is for,
# but the reader has to be able to say what it wants rather than discover it by globbing.
NEEDS = re.compile(rf"^Anexe_(?:{'|'.join(SIBLINGS)})_\d{{4}}", re.I)
INTRAVILAN_ANNEX = re.compile(r"euro\s*/\s*mp", re.I)
EXTRAVILAN_ANNEX = re.compile(r"euro\s*/\s*ha", re.I)
COLUMN_LABEL = re.compile(r"^Localitate$", re.I)
# "zona A", "zona B" — a row that continues the locality above it rather than naming one.
ZONE_ROW = re.compile(r"^\s*zona\s+([A-F])\b", re.I)
NUMBER = re.compile(r"^\d{1,6}$")
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.']{2,}$", re.U)
# Pasture and hayfield, as the document defines them: a share of the arable price.
PASTURE_SHARE = 0.9
# Footer and note lines sit in the same word stream and must not be read as data.
NOISE = re.compile(r"romprice|e-mail|www\.|tel:|circumscrip|anexa|^\d+\.$", re.I)
# The seat's own annex. It prices the city by zone under a bare `Localizare` heading and names
# nobody — the city is the circumscription in the page header. Identified by its note, which
# is the only line that says what the numbers are.
SEAT_ANNEX = re.compile(r"parcelele\s+de\s+teren\s+intravilan", re.I)
SEAT_OF = re.compile(r"Circumscrip[țţ]ia\s+Judec[ăa]toriei\s+([A-ZĂÂÎȘŞȚŢ][\w \-]+)")
# The seat's annex names it outright, above the table.
SEAT_NAMED = re.compile(r"^(?:Municipiul|Ora[șş]ul)\s+(.+)$", re.I)
# The two halves of the seat's annex, captioned rather than columned.
SEAT_INTRA = re.compile(r"^teren\s+intravilan$", re.I)
SEAT_EXTRA = re.compile(r"^teren\s+extravilan$", re.I)
# "Zona 0", "Centrală", "Mediană", "Periferică" — the seat's zones, in order of value.
# "Zona 0", "Zona 4, 5", "Centrală", "Toate zonele". Timișoara numbers its zones from nought,
# so the label itself contains a digit — which is why the value has to be taken as the last
# token on the row rather than as the only number on it.
SEAT_ZONE = re.compile(
    r"^\s*(?:zona\s+[\w,\s]*|toate\s+zonele|(?:central|median|periferic)\w*)\s*$", re.I
)
ZONE_LETTERS = "ABCDEF"


def rows_of(words: list[list], tolerance: float = 6.0) -> list[list[tuple[float, str]]]:
    """Words grouped into visual rows by vertical proximity.

    Clustered rather than bucketed. Rounding the vertical position into fixed bins split the
    first row of every page — `Jimbolia … Cenei … Giarmata` landed in one bin and their
    prices `38 … 7 … 40` in the next, because a digit's baseline sits a point or two off a
    letter's and the bin edge happened to fall between them. A row is a run of words with no
    real vertical gap, not a rounded coordinate.
    """
    ordered = sorted(words, key=lambda word: word[3])
    grouped: list[list[tuple[float, str]]] = []
    anchor: float | None = None
    for text, x0, _x1, top in ordered:
        if anchor is None or top - anchor > tolerance:
            grouped.append([])
            anchor = top
        grouped[-1].append((x0, text))
    return [sorted(row) for row in grouped]


def bands_of(rows: list[list[tuple[float, str]]]) -> list[float] | None:
    """The x where each column starts, taken from the row of `Localitate` headers."""
    for row in rows:
        starts = [x for x, text in row if COLUMN_LABEL.match(text)]
        if len(starts) >= 2:
            return sorted(starts)
    return None


def read_page(words: list[list]) -> list[tuple[str, str | None, float]]:
    """(locality, zone, value) for one page, column by column.

    The locality is carried forward per column, not per page: two columns run different
    communes down the same lines, and a zone row belongs to whichever column it sits in.
    """
    rows = rows_of(words)
    bands = bands_of(rows)
    if bands is None:
        return []
    edges = [*bands, float("inf")]
    carried: dict[int, str] = {}
    found: list[tuple[str, str | None, float]] = []

    for row in rows:
        for index in range(len(bands)):
            # A small tolerance to the left: a name can start a pixel or two before the
            # header it sits under.
            inside = [
                (x, text)
                for x, text in row
                if edges[index] - 6 <= x < edges[index + 1] - 6
            ]
            if not inside:
                continue
            tokens = [text for _x, text in inside]
            if any(NOISE.search(text) for text in tokens):
                continue
            values = [text for text in tokens if NUMBER.match(text)]
            if not values:
                continue
            label = " ".join(text for text in tokens if not NUMBER.match(text)).strip()
            value = float(values[-1])
            zone = ZONE_ROW.match(label)
            if zone:
                place = carried.get(index)
                if place:
                    found.append((place, zone.group(1).upper(), value))
                continue
            # A label with a zone after it — "Moșnița Veche zona A" — names the place and
            # prices one of its zones at once.
            inline = re.search(r"\bzona\s+([A-F])\b", label, re.I)
            place = re.sub(r"\s*zona\s+[A-F]\b.*$", "", label, flags=re.I).strip()
            if not place or not NAME.match(place):
                continue
            carried[index] = place
            found.append((place, inline.group(1).upper() if inline else None, value))
    return found


def read_seat(words: list[list]) -> tuple[str | None, list[float], float | None]:
    """The seat's own annex: (city, intravilan zones in order, extravilan price).

    Its rows carry a zone and a price and no locality, so the city comes from the
    `Municipiul …` line above the table. The two halves are told apart by their captions —
    `Teren intravilan` and `Teren extravilan` — and not by the size of the numbers: Timișoara's
    extravilan is 8 and its fifth zone is 50, so a threshold would have made the farmland a
    sixth zone of the city.
    """
    city: str | None = None
    zones: list[float] = []
    extra: float | None = None
    section: str | None = None
    for row in rows_of(words):
        tokens = [text for _x, text in row]
        if any(NOISE.search(text) for text in tokens):
            continue
        label = " ".join(text for text in tokens if not NUMBER.match(text)).strip()
        named = SEAT_NAMED.match(label)
        if named:
            city = named.group(1).strip()
            continue
        if SEAT_INTRA.match(label):
            section = "intra"
            continue
        if SEAT_EXTRA.match(label):
            section = "extra"
            continue
        if not tokens or not NUMBER.match(tokens[-1]):
            continue
        label = " ".join(tokens[:-1]).strip()
        if not SEAT_ZONE.match(label):
            continue
        value = float(tokens[-1])
        if section == "intra":
            zones.append(value)
        elif section == "extra":
            extra = value
    return city, zones, extra


def siblings(name: str) -> list[str]:
    """The county's other circumscription annexes, found beside the one asked for."""
    year = re.search(r"(\d{4})", name)
    suffix = year.group(1) if year else "2026"
    found = []
    for part in SIBLINGS:
        for path in sorted(CACHE.glob(f"Anexe_{part}_{suffix}*.json.gz")):
            found.append(path.name[: -len(".json.gz")])
    return found or [name]


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    intravilan: dict[str, dict[str, float]] = {}
    flat: dict[str, list[float]] = {}
    arable: dict[str, float] = {}
    pages_of: dict[str, int] = {}

    for document in siblings(name):
        try:
            pages = load(document)["pages"]
        except SystemExit:
            continue
        for index, page in enumerate(pages, start=1):
            words = page.get("words") or []
            if not words:
                continue
            header = page["text"][:400]
            # A per-locality annex first, always. The note that identifies the seat's own
            # table — "parcelele de teren intravilan" — is also printed under the per-locality
            # ones, so testing for it first swallowed those pages and took the county from 92%
            # of its localities to 28%. The four `Localitate` columns are what actually tell
            # the two apart.
            has_columns = bands_of(rows_of(words)) is not None
            if not has_columns and SEAT_ANNEX.search(page["text"]):
                city, zones, extra = read_seat(words)
                if not city:
                    named = SEAT_OF.search(page["text"])
                    city = named.group(1).strip() if named else ""
                if city and is_local(city) and zones:
                    key = city.upper()
                    pages_of.setdefault(key, index)
                    for position, value in enumerate(zones[: len(ZONE_LETTERS)]):
                        intravilan.setdefault(key, {})[ZONE_LETTERS[position]] = value
                    if extra is not None:
                        # The unit is not consistent between the seats: Timișoara prints its
                        # extravilan in euro per square metre and Lugoj in euro per hectare,
                        # in annexes of the same shape. A hectare of Romanian farmland does
                        # not cost a hundred euro, so a figure that small is already per
                        # square metre and one that large is per hectare.
                        arable.setdefault(key, extra if extra < 100 else extra / M2_PER_HA)
                continue
            is_intra = bool(INTRAVILAN_ANNEX.search(header))
            is_extra = bool(EXTRAVILAN_ANNEX.search(header))
            if not (is_intra or is_extra):
                continue
            for place, zone, value in read_page(words):
                if not is_local(place):
                    continue
                key = place.upper()
                pages_of.setdefault(key, index)
                if is_intra:
                    if zone:
                        intravilan.setdefault(key, {})[zone] = value
                    else:
                        flat.setdefault(key, []).append(value)
                else:
                    # Euro per hectare here, euro per square metre everywhere else.
                    arable.setdefault(key, value / M2_PER_HA)

    def extravilan_of(key: str) -> dict[str, float]:
        price = arable.get(key)
        if price is None:
            return {}
        return {"A": price, "P+F": round(price * PASTURE_SHARE, 6)}

    towns = [
        {
            "name": key.title(),
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": zones},
            "extravilan": extravilan_of(key),
            "page": pages_of.get(key, 1),
        }
        for key, zones in intravilan.items()
        if len(zones) >= 2
    ]
    priced = {t["name"].upper() for t in towns}
    communes = []
    for key in sorted(set(flat) | set(intravilan) | set(arable)):
        if key in priced:
            continue
        readings = sorted(
            {*flat.get(key, []), *intravilan.get(key, {}).values()}, reverse=True
        )
        if not readings:
            continue
        communes.append(
            {
                "name": key.title(),
                "villages": [
                    {"name": f"{key.title()} ({position})", "intravilan": {"CC": price}}
                    for position, price in enumerate(readings, start=1)
                ],
                "extravilan": extravilan_of(key),
                "page": pages_of.get(key, 1),
            }
        )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    return towns, communes, []

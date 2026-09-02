"""Galați, which prices its land in prose paragraphs grouped by court circumscription.

There is no annex and no grid. The study is a 142-page valuation report, and the land sits in
short blocks at the foot of the pages that describe each place:

    * TERENURI  în INTRAVILAN
    POZITIE DE AMPLASAMENT   Reședință de comuna   Sat TRĂIAN   Sate componente
      Teren Curți - Construcții        70    60    30   LEI/mp
      Teren AGRICOL                    40    30    20   LEI/mp
    * TERENURI  AGRICOLE în EXTRAVILAN
        CATEGORIE DE TEREN AGRICOL   arabil   vie   livadă   pășune   LEI/Ha
    CU acces la drum      31.500   33.000   32.400   17.500
    FĂRĂ acces la drum    22.500   25.000   23.600   15.800

**A block belongs to whichever localities the page before it named**, and the naming has two
forms that have to be told apart. A single place gets a heading in capitals — `• COMUNA
SMÂRDAN`, `* Oraș BEREȘTI` — and a group gets a list in lower case, `* comuna Frumușița *
comuna Băleni …`, eleven or twelve communes sharing one set of prices. The document is
consistent about the case, which is the only thing that distinguishes "this page is about
Șendreni" from "this page is about the twelve communes of the Târgu Bujor circumscription".

**Two of the lists are written as running text** rather than as bulleted names:

    LOCALITĂȚI: IVEȘTI-BUCEȘTI; INDEPENDENȚA; BARCEA; TUDOR VLADIMIRESCU;
    PISCU COSTACHE NEGRI; UMBRĂREȘTI; GRIVIȚA; HANU CONACHI

`PISCU COSTACHE NEGRI` is two communes with the semicolon missing between them, `IVEȘTI-BUCEȘTI`
is a commune and one of its villages, and `HANU CONACHI` is a village of Fundeni. Splitting on
the punctuation alone gets one of the eight right. So the names are matched greedily against the
county roster, longest run of words first, and whatever does not match a real locality is
dropped rather than guessed at.

**Galați city is priced by street zone, twenty-nine of them**, each a numbered section of the
report with its own paragraph of land prices — 1 650 lei/m² on the Faleza, 100 lei/m² west of
the ring road. They are read as the city's zone spread, which is what they are.

**The irrigated row is not the one used.** Each block prices farmland twice, with and without
access to irrigation or to a road, and the second is the ordinary case for most of a county's
hectares. Using the higher row would price every field as though it were served.

**Tecuci is not in this document.** Its circumscription — the city and eighteen communes, a
quarter of the county — is published as `EXPERTIZE_TECUCI_01_03_2026.pdf`, a 17 MB scan with not
one extractable character. Reading only this study leaves Galați at 70,8%, below the floor that
refuses to write a county at all, so the two are read together: `ocr_cache.py` puts the scan
through tesseract into the ordinary cache, and the second half of this file reads it.

That half is written for a source that gets digits wrong, because this one does. Every value it
produces was checked against the page, and the checking is what the design is for — see
`tecuci_rows` for the three ways a scanned table lies and what is done about each.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

M2_PER_HA = 10_000
RURAL_START = re.compile(r"COMUNE\s+LIMITROFE\s+MUNICIPIULUI", re.I)
CITY = "GALAȚI"

# The land blocks. `AGRICOL` in the same heading means the extravilan table, not this one.
INTRAVILAN_HEAD = re.compile(r"TERENURI\s+(?:Curți-Construcții\s+)?(?:în\s+)?INTRAVILAN", re.I)
EXTRAVILAN_HEAD = re.compile(r"TERENURI\s+AGRICOLE\s+în\s+EXTRAVILAN", re.I)
BUILDING_ROW = re.compile(
    r"TEREN(?:URI)?\s+(?:categ\.?\s*)?Cur[țţt]i\s*[-–]?\s*Construc[țţt]ii", re.I
)
AGRICULTURAL_ROW = re.compile(
    r"TEREN(?:URI)?\s+(?:categ\.?\s*)?(?:Cur[țţt]i\s*[-–]\s*)?agricol", re.I
)
# "CU acces la sistem de irigații", "FĂRĂ acces la drum" — the same row under two keys.
ACCESS_ROW = re.compile(r"^\s*(CU|F[ĂA]R[ĂA])\s+acces\b", re.I)
WITHOUT = re.compile(r"^\s*F[ĂA]R[ĂA]\b", re.I)
# A price, with the document's full stop as a thousands separator: `1.250`, `31.500`, `12800`.
PRICE = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d+(?:,\d+)?\b")
PER_M2 = re.compile(r"LEI\s*/\s*mp", re.I)

# A place named on its own, in capitals, is the subject of the page.
ALONE = re.compile(
    r"(?:^|[•*])\s*(?:COMUNA|Comuna|Oraș|Oras|Municipiul)\s+"
    r"([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,})",
    re.M,
)
# A place named in a list, in lower case, shares its prices with the others beside it.
IN_LIST = re.compile(r"[•*]\s*comuna\s+([^\n*•]{2,40})", re.I)
# Deliberately greedy past the line break: this list runs onto a second line, and stopping at
# the first newline drops Costache Negri, Umbrărești, Grivița and Ivești. Overshooting into the
# paragraph that follows is safe, because only names the roster recognises are kept and that
# paragraph names the same communes again.
NAMED_LIST = re.compile(r"LOCALIT[ĂA][ȚT]I\s*:\s*(.{10,600})", re.I | re.S)
# The last list is written as village enumerations in brackets, which are not localities.
BRACKETS = re.compile(r"\([^)]*\)")

# What the document says the categories are worth relative to the arable price it prints.
NEPRODUCTIV = 0.30

# ---------------------------------------------------------------------------------------------
# The Tecuci circumscription, which is a photograph.
#
# `EXPERTIZE_TECUCI_01_03_2026.pdf` carries the city and eighteen communes — the quarter of the
# county the main study leaves out — and has no text layer at all. `ocr_cache.py` reads it into
# the ordinary cache; what follows reads the cache.
#
# OCR is not a reliable source of digits and is not treated as one. Tesseract read Tecuci's vine
# price as 80.800 in one pass and 30.800 in another, and only the page settles it. So a row is
# accepted only when it carries the full count of values this table is known to have, and a row
# that lost one to the noise is left unpriced rather than shifted a column to the left.
TECUCI_STUDY = "EXPERTIZE_TECUCI_01_03_2026.pdf"
TECUCI_INTRAVILAN = re.compile(r"INTRAVILANUL\s+LOCALIT", re.I)
TECUCI_EXTRAVILAN = re.compile(r"EXTRAVILANUL\s+LOCALIT", re.I)
# "220 | Pasajul Unirii A 250" — a street, its zone letter and the zone's price.
TECUCI_STREET_ROW = re.compile(r"\b([A-F])\s+(\d{2,3})\s*$")
# Row numbers, OCR gravel and the value columns: `BRĂHĂŞEŞTI 40 i 35`, `4 COROD 24.000 ) 21.000`
TECUCI_NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+|\d{2,3}")
# Where the value columns sit, in PDF points. Both tables are ruled and neither moves down the
# page, so these are constants of the document rather than something to infer per row.
INTRAVILAN_COLUMNS = [337.0, 441.0]
EXTRAVILAN_COLUMNS = [287.0, 396.0, 478.0]
# The document's own rules for what it does not price directly.
TECUCI_VILLAGE_SHARE = 0.60
TECUCI_NEPRODUCTIV = 0.10


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def prices_in(line: str) -> list[float]:
    """Every number on a row, as lei. `-` is a category the document leaves unpriced."""
    found: list[float] = []
    for token in PRICE.findall(line):
        value = float(token.replace(".", "").replace(",", "."))
        # Years and the `25%` in the small-parcel note are not prices.
        if 0 < value < 500_000 and value != 25.0 or len(token) > 2:
            found.append(value)
    return found


def greedy(text: str, is_local) -> list[str]:
    """Pull real localities out of a run of names with the separators half missing.

    `PISCU COSTACHE NEGRI` is Piscu and Costache Negri. Taking the longest run of words that
    the county roster recognises, then continuing from where that ended, splits it correctly
    without a list of special cases — and drops `HANU CONACHI`, which is a village.
    """
    # Hyphens separate too: `IVEȘTI-BUCEȘTI` is a commune and one of its villages.
    words = [w for w in re.split(r"[\s;,\-–]+", BRACKETS.sub(" ", text)) if w]
    found: list[str] = []
    start = 0
    while start < len(words):
        for end in range(min(start + 3, len(words)), start, -1):
            candidate = " ".join(words[start:end])
            if len(candidate) > 2 and is_local(candidate):
                found.append(candidate)
                start = end
                break
        else:
            start += 1
    return found


def subjects_of(text: str, is_local) -> list[str]:
    """Which localities this page is about, preferring a heading over a list."""
    alone = [clean(n) for n in ALONE.findall(text)]
    alone = [n for n in alone if is_local(n)]
    if alone:
        # A page that names the group and then opens with the first member — p109 lists four
        # communes and then starts on Șendreni — is about the member, not the four.
        return alone[-1:]

    listed = [clean(n) for n in IN_LIST.findall(text)]
    listed = [n for n in listed if is_local(n)]
    if listed:
        return listed

    found = NAMED_LIST.search(text)
    if found:
        return greedy(found.group(1), is_local)
    # `* Nămoloasa (resedință; …` — a bulleted list with no keyword before the names.
    loose: list[str] = []
    for line in text.splitlines():
        stripped = clean(line)
        if stripped.startswith("*") and "(" in stripped:
            loose.extend(greedy(stripped.lstrip("* "), is_local))
    return loose


def land_of(text: str) -> tuple[list[float], dict[str, float]]:
    """The building-land prices and the extravilan rates published on one page."""
    building: list[float] = []
    arable: float | None = None
    vine: float | None = None
    orchard: float | None = None
    pasture: float | None = None
    section = ""

    for line in text.splitlines():
        stripped = clean(line)
        if not stripped:
            continue
        if EXTRAVILAN_HEAD.search(stripped):
            section = "extravilan"
            continue
        if INTRAVILAN_HEAD.search(stripped):
            section = "intravilan"
            # "TERENURI INTRAVILANE - Curți Construcții 940 LEI/mp" puts the price on the
            # heading itself in the city sections.
            if PER_M2.search(stripped):
                building.extend(prices_in(PRICE.sub(lambda m: m.group(0), stripped)))
            continue

        if stripped.startswith(("*", "•")):
            # Any other starred heading ends the land block. Without this the city sections
            # run on into `SPAȚII COMERCIALE` and price building floor area as though it were
            # land — 5 100 lei/m² alongside a genuine 1 250.
            section = ""
            continue

        if section == "intravilan":
            if AGRICULTURAL_ROW.search(stripped):
                continue
            if BUILDING_ROW.search(stripped) or PER_M2.search(stripped):
                building.extend(prices_in(stripped))
        elif section == "extravilan":
            found = ACCESS_ROW.match(stripped)
            if not found:
                continue
            # Both rows are read and the un-served one wins, so a page that prints only the
            # irrigated row still prices its fields.
            values = prices_in(stripped)
            if len(values) < 3:
                continue
            first_time = arable is None
            if first_time or WITHOUT.match(stripped):
                arable, vine, orchard = values[0], values[1], values[2]
                pasture = values[3] if len(values) > 3 else None

    rates: dict[str, float] = {}
    if arable:
        rates["A"] = arable / M2_PER_HA
        rates["NP"] = arable * NEPRODUCTIV / M2_PER_HA
    orchards = [v for v in (vine, orchard) if v]
    if orchards:
        rates["V+L"] = sum(orchards) / len(orchards) / M2_PER_HA
    if pasture:
        rates["P+F"] = pasture / M2_PER_HA
    return building, rates


def tecuci_rows(page: dict, is_local, columns: list[float]) -> dict[str, list[float]]:
    """One of the two Tecuci tables, read by where the columns are rather than by line.

    Three things go wrong when this table is read as text, and all three are silent:

    * OCR loses a value from a row — four of the nineteen extravilan rows — and counting the
      numbers on a line then shifts every later column one place to the left.
    * It puts a value on its own baseline, a point or two off its row, so a fixed band splits
      Corod's vine price away from Corod.
    * It glues a table rule onto a number: Cerțești's `15.400` reads as `115.400`, which is a
      plausible price in the wrong county.

    So each locality's name anchors its row, the row's height comes from the spacing of the
    names themselves rather than from a constant, every number is filed under the column it
    sits in, and a value an order of magnitude away from the same row's arable price is
    dropped as damage rather than recorded as a price.
    """
    words = page.get("words") or []
    left = min(columns) - 20

    # Two words of one name sit a fraction of a point apart, and which of them tesseract reports
    # first is not the order they are written in: `MĂRULUI` is listed above `VALEA`, and `TECUCI`
    # above `MUNICIPIUL`. A name assembled in the order the words arrive is `MĂRULUI VALEA`, and
    # matches nothing. They are put back in the order they appear across the page.
    anchors: list[tuple[float, list[tuple[float, str]]]] = []
    for text, x0, _x1, top in sorted(words, key=lambda w: w[3]):
        if x0 >= left or any(character.isdigit() for character in text):
            continue
        # Table rules read as punctuation sit in the same column as the names.
        label = clean(re.sub(r"[^A-Za-zĂÂÎȘŞȚŢăâîșşțţ ]+", " ", text))
        if len(label) < 4:
            continue
        if anchors and abs(top - anchors[-1][0]) < 4:
            anchors[-1][1].append((x0, label))
        else:
            anchors.append((top, [(x0, label)]))

    named = [
        (
            top,
            re.sub(
                r"^(?:MUNICIPIUL|ORA[ȘS]UL|COMUNA)\s+",
                "",
                " ".join(word for _, word in sorted(parts)),
                flags=re.I,
            ).strip(),
        )
        for top, parts in anchors
    ]
    named = [(top, label) for top, label in named if is_local(label)]
    if len(named) < 2:
        return {}
    gaps = sorted(b - a for (a, _), (b, _) in zip(named, named[1:], strict=False))
    spacing = gaps[len(gaps) // 2] or 12.0

    found: dict[str, list[float]] = {}
    for top, label in named:
        values: list[float | None] = [None] * len(columns)
        for text, x0, _x1, word_top in words:
            if abs(word_top - top) > spacing * 0.5:
                continue
            token = text.strip(" .,|_„:;!)(")
            if not TECUCI_NUMBER.fullmatch(token):
                continue
            distances = [abs(x0 - centre) for centre in columns]
            nearest = distances.index(min(distances))
            if distances[nearest] < 40 and values[nearest] is None:
                values[nearest] = float(token.replace(".", ""))
        first = values[0]
        if first is None:
            continue
        # An order-of-magnitude check against the row's own first column, not a tuned range:
        # every real value in these tables is within a factor of two of it. A value that fails
        # it is dropped on its own — losing Cerțești's vine price to a table rule is no reason
        # to throw away its arable price, which was read correctly.
        values = [
            None if value is not None and (value > first * 3 or value * 3 < first) else value
            for value in values
        ]
        found.setdefault(fold(label), values)
    return found


def tecuci(is_local) -> tuple[dict, dict, list[str]]:
    """The scanned circumscription, read from the cache `ocr_cache.py` writes."""
    try:
        pages = load(TECUCI_STUDY)["pages"]
    except SystemExit:
        return {}, {}, ["circumscripția Tecuci nu este în cache (rulează ocr_cache.py)"]

    intravilan: dict[str, list[float]] = {}
    extravilan: dict[str, list[float]] = {}
    votes: dict[str, list[float]] = {}
    for page in pages:
        text = page.get("text") or ""
        if TECUCI_INTRAVILAN.search(text):
            intravilan.update(tecuci_rows(page, is_local, INTRAVILAN_COLUMNS))
        elif TECUCI_EXTRAVILAN.search(text):
            extravilan.update(tecuci_rows(page, is_local, EXTRAVILAN_COLUMNS))
        # The city has no price table of its own. Every street carries its zone letter and
        # that zone's price, so the six prices are stated some three hundred times over — and
        # the price for a zone is taken as the one stated most often, which is what makes a
        # misread digit on one street a misread digit on one street rather than the city's
        # zone B. A page counts as part of this table when it holds ten such rows; the header
        # is not used, because OCR spells it differently on each pass.
        seen = [
            TECUCI_STREET_ROW.search(clean(line)) for line in text.splitlines()
        ]
        rows = [found.groups() for found in seen if found]
        if len(rows) >= 10:
            for letter, price in rows:
                votes.setdefault(letter, []).append(float(price))

    zones = {
        letter: max(set(prices), key=prices.count) for letter, prices in votes.items()
    }
    places: dict[str, dict] = {}
    for key, (building, _other) in intravilan.items():
        places.setdefault(key, {})["building"] = building
    for key, (arable, plantation, vine) in extravilan.items():
        rates = {"A": arable / M2_PER_HA}
        if plantation is not None:
            rates["P+F"] = plantation / M2_PER_HA
            rates["PADURE"] = plantation / M2_PER_HA
            rates["NP"] = plantation * TECUCI_NEPRODUCTIV / M2_PER_HA
        if vine is not None:
            # The middle column covers orchards, and vines are priced in the one beside it.
            pair = [vine] if plantation is None else [plantation, vine]
            rates["V+L"] = sum(pair) / len(pair) / M2_PER_HA
        places.setdefault(key, {})["extravilan"] = rates

    notes: list[str] = []
    if not places:
        notes.append("circumscripția Tecuci nu s-a citit din OCR")
    return places, zones, notes


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    texts = [page.get("text") or "" for page in pages]

    # The *last* page that announces the countryside, not the first. The first is the table of
    # contents on page 4, which repeats every heading in the report — taking it puts the
    # boundary three pages in and leaves the city's twenty-nine zones on the rural side, where
    # nothing looks for them.
    rural_pages = [index for index, text in enumerate(texts) if RURAL_START.search(text)]
    first_rural = rural_pages[-1] if rural_pages else len(texts)

    # The city, whose twenty-nine street zones are the pages before the countryside begins.
    city_zones: list[float] = []
    for text in texts[:first_rural]:
        building, _rates = land_of(text)
        city_zones.extend(building)

    urban: dict[str, dict] = {}
    rural: dict[str, dict] = {}
    subjects: list[str] = []
    notes: list[str] = []

    for index in range(first_rural, len(texts)):
        text = texts[index]
        named = subjects_of(text, is_local)
        if named:
            subjects = named
        building, rates = land_of(text)
        if not (building or rates) or not subjects:
            continue
        # A town gets its own heading with `Oraș` in front of it; everything else here is a
        # commune, however many price columns its circumscription publishes.
        town = re.search(r"[•*]\s*(?:Oraș|Oras|Municipiul)\s+([A-ZĂÂÎȘŞȚŢ \-]{3,})", text)
        target = urban if town and len(subjects) == 1 else rural
        for place in subjects:
            entry = target.setdefault(fold(place), {"name": place, "parts": [], "rates": {}})
            entry["parts"].extend(building)
            if rates:
                entry["rates"].update(rates)
            entry["page"] = index + 1

    tecuci_places, tecuci_zones, tecuci_notes = tecuci(is_local)
    notes.extend(tecuci_notes)
    for key, entry in tecuci_places.items():
        building = entry.get("building")
        rates = entry.get("extravilan", {})
        if key == fold("TECUCI"):
            if tecuci_zones:
                urban[key] = {
                    "name": "TECUCI",
                    "parts": [price for _letter, price in sorted(tecuci_zones.items())],
                    "rates": rates,
                    "page": 33,
                }
            continue
        if building is None:
            continue
        rural[key] = {
            "name": key.title(),
            # The seat and its villages, which the table prices at 60% of it.
            "parts": [building, building * TECUCI_VILLAGE_SHARE],
            "rates": rates,
            "page": 30,
        }

    if city_zones:
        urban[fold(CITY)] = {
            "name": CITY,
            "parts": city_zones,
            "rates": {},
            "page": 1,
        }
    else:
        notes.append("municipiul Galați nu s-a citit")

    zoned = [
        {
            "name": entry["name"],
            "rank": None,
            "zones": sorted(dict.fromkeys("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[: len(entry["parts"])])),
            "intravilan": {
                "CC": {
                    letter: price
                    for letter, price in zip(
                        "ABCDEFGHIJKLMNOPQRSTUVWXYZ", entry["parts"], strict=False
                    )
                }
            },
            "extravilan": entry["rates"],
            "page": entry["page"],
        }
        for entry in urban.values()
        if entry["parts"]
    ]

    communes = []
    for position, entry in enumerate(sorted(rural.values(), key=lambda e: e["name"]), start=1):
        if not entry["parts"]:
            continue
        communes.append(
            {
                "name": entry["name"],
                "villages": [
                    {"name": entry["name"] if not offset else f"{entry['name']} ({offset + 1})",
                     "intravilan": {"CC": price}}
                    for offset, price in enumerate(entry["parts"])
                ],
                "extravilan": entry["rates"],
                "page": entry["page"],
                "index": position,
            }
        )
    if not communes:
        notes.append("nicio comună nu s-a citit")
    notes.append(
        "circumscripția Tecuci este citită prin OCR dintr-un document scanat separat"
    )
    return zoned, communes, notes

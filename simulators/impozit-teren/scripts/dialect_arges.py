"""Argeș, whose every land table is printed sideways.

The study is a scan, read through `ocr_cache.py`, and each of its land tables is landscape: the
page has to be turned to read it, and turning the page transposes the table. What is a row on
paper is an x position in the file and what is a column on paper is a band of y positions. Read
as text it arrives as a heap, and the heap is dangerous rather than merely useless:

    Zona A
    …
    1000
    800
    600
    400

Those are not Pitești's four zones. They are *zone A of four different rows* — Pitești's built
land, Pitești's other land, Ștefănești's built land, Ștefănești's other land. Pitești's zones are
1000, 800, 600, 400 as well, read down the other axis. The two readings differ by a transpose and
agree on the first locality, which is exactly the coincidence that makes a wrong parse look
right for as long as anyone spot-checks the top of the page.

**Rows are found from the values, not the labels.** `Zona` is printed once per zone and OCR
returns it two or three times at slightly different heights, so counting label words gives eight
rows for four zones. The prices do not have that problem: every value of one field shares a
height, so clustering the numbers by height *is* the table's structure. The labels are then used
only to say which band is the extravilan one and which is the forest one — and the extravilan
band has to be found, because it is a merged cell centred between two columns and pooling its x
positions into the column detection puts a column exactly where the gap should be.

**Localities are matched to columns by position, not by order.** Each locality is printed twice,
as `C.C` — land with buildings on it — and as `A.T`, everything else, and its name sits in a
merged cell centred over both. So every value column is given to the name group nearest it, and
a locality whose second column the scan lost still gets its first. Matching by order instead
looks correct on a full table and silently shifts every locality by one on a table with a gap:
three earlier attempts here produced the right prices under the wrong names, at full coverage.

**One row is many communes.** `Poiana Lacului, Morărești, Cotmeana, Băbana, Vedea` share a price,
so the names are split against the county roster and each commune named takes the row's prices.

**The county is priced by court circumscription** — Pitești, Câmpulung, Curtea de Argeș,
Topoloveni, Costești — and the study reprints HG 337/1993 to say which commune belongs to which,
in the 1993 orthography. The tables say `Hîrseşti` and `Dîmbovicioara` where the register says
Hârsești and Dâmbovicioara; the importer's resolver already forgives an î for an â, which is the
only reason those twelve communes are found.

**Forest is mostly lost.** The `Pădure` column is a single digit per row and the scan renders
most of them as nothing at all, so the category stays unpriced rather than being filled in.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# Every value in these tables is lei per square metre, extravilan included: the tables say
# "Valoare unitara lei/1mp" and mean it for the whole page.
# The word order in these headings is not the word order on the page — `Evaluarea JUDECĂTORIEI
# intravilan terenului` is one heading — so a land table is recognised by the words it contains
# rather than by any phrase. Every other table in the study values buildings, and says so.
LAND_TABLE = re.compile(r"teren", re.I)
NOT_LAND = re.compile(r"spa[țţt]iilor|anexelor|apartament", re.I)
NUMBER = re.compile(r"^\d{1,4}$")
YEAR = re.compile(r"ANUL\s+(\d{4})", re.I)
EXTRAVILAN = re.compile(r"^Extravilan$", re.I)
FOREST = re.compile(r"^P[ăa]dure$", re.I)
WATER = re.compile(r"^Luciu$", re.I)
# `C.C` and `A.T` mark the two rows every locality gets. OCR turns them into almost anything,
# and each sits at the same x as the column it labels, so they have to be kept out of the names.
MARKER = re.compile(r"^(C\.?C|A\.?T|LL|CA|C\.?E|n|E|E:|ei|Cu)\.?$", re.I)
SPLIT = re.compile(r"[,;]|\bsi\b|\bși\b", re.I)
NOISE = re.compile(r"^(cartierele|satele|comunele|sat|oras|orasul|municipiul)$", re.I)
# Which court a page belongs to, from its own running head.
# A page says which court it belongs to, but not in that order: `Circu Judecătoriei de
# mscripţia Curtea Argeș TABEL 1` is one running head. So the head is searched for each court's
# own name instead, and one word of it is enough — the five are Pitești, Câmpulung, Curtea,
# Topoloveni and Costești, and no two begin alike.
# A row that names no locality but prices all of a circumscription's countryside at once.
COUNTRYSIDE = re.compile(r"comun|sate|localit", re.I)
# The study reprints HG 337/1993 to say which commune belongs to which court.
ASSIGNMENT_PAGE = re.compile(r"JUDEC[ĂA]TORIA", re.I)
COURT_SECTION = re.compile(
    r"\d{1,2}\s*[.)]\s*J\)?UDEC[ĂA]TORIA\s+(.{3,30}?)\s+cu\s+sediul", re.I | re.S
)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def loose(name: str) -> str:
    """`fold`, with an î read as an â — the 1993 orthography against today's.

    The decision this study reprints spells the court `Cîmpulung` and the study's own running
    head spells it `Câmpulung`. Without this the largest circumscription in the county matches
    nothing and its twenty-four communes go unpriced.
    """
    return fold(name).replace("I", "A")


def bands(values: list[float], gap: float) -> list[list[float]]:
    """Group positions into runs separated by more than `gap`."""
    grouped: list[list[float]] = []
    for value in sorted(values):
        if grouped and value - grouped[-1][-1] <= gap:
            grouped[-1].append(value)
        else:
            grouped.append([value])
    return grouped


def names_in(text: str, is_local) -> list[str]:
    """Every locality a label names, from a cell that may name five of them."""
    found: list[str] = []
    for piece in SPLIT.split(clean(text)):
        words = [word for word in piece.split() if not NOISE.match(word.strip(".,"))]
        start = 0
        while start < len(words):
            for end in range(min(start + 4, len(words)), start, -1):
                candidate = " ".join(words[start:end]).strip(" .,")
                if len(candidate) > 2 and is_local(candidate):
                    found.append(candidate)
                    start = end
                    break
            else:
                start += 1
    return found


def read_table(page: dict, is_local) -> list[tuple[list[str], list[float], float | None]]:
    """One transposed table, as (localities, intravilan prices, extravilan price)."""
    words = page.get("words") or []
    # The study's year is printed in every title — `ANUL 2026` — and is a four-digit number in
    # the same shape as a price. Left in, it pairs with whatever value shares its height and
    # invents a band; taken out, a real column of two values can be trusted as a column, which
    # matters because Câmpulung's zones B, C and D have exactly two values each.
    stamped = YEAR.search(page.get("text") or "")
    year = float(stamped.group(1)) if stamped else None
    numbers = [
        (x0, top, float(clean(text)))
        for text, x0, _x1, top in words
        if NUMBER.match(clean(text)) and x0 > 60 and float(clean(text)) != year
    ]
    if len(numbers) < 4:
        return []

    rows: list[list[tuple[float, float, float]]] = []
    for item in sorted(numbers, key=lambda value: value[1]):
        if rows and item[1] - rows[-1][-1][1] <= 10:
            rows[-1].append(item)
        else:
            rows.append([item])
    fields = [row for row in rows if len(row) >= 2]
    if not fields:
        return []

    # A field's label sits in its own narrow column, just left of the first value. The word
    # `pădure` also appears in this page's title and `luciu` in its footnote, at the far left
    # and the far right — and both fall within a few points of a zone band, so a label search
    # that ignores x classifies Zona A as the water column and Zona B as the forest one, and
    # the table then reads as though the city had two zones.
    # From the table's own bands, not from every number on the page: the year in the title is
    # a four-digit number far to the left of the first column, and taking it as the reference
    # puts the label window off the edge of the table.
    left = min(x for x, _t, _v in max(fields, key=len))

    def labelled(top: float, pattern: re.Pattern) -> bool:
        return any(
            pattern.match(clean(text))
            and abs(word_top - top) < 34
            and left - 110 <= x0 <= left - 15
            for text, x0, _x1, word_top in words
        )

    extra = next((row for row in fields if labelled(row[0][1], EXTRAVILAN)), None)
    aside = {id(extra)} | {
        id(row)
        for row in fields
        if labelled(row[0][1], FOREST) or labelled(row[0][1], WATER)
    }
    # The intravilan grid is every band that is not one of the single-column ones. Their x
    # positions are the table's columns; the extravilan band's are not, because that cell is
    # merged across a locality's two rows and sits in the gap between them.
    grid = [row for row in fields if id(row) not in aside]
    if not grid:
        return []
    grid.sort(key=lambda row: -row[0][1])
    # The `Nr. crt.` column is a band like any other once the page is turned, and it is the
    # deepest one — deeper than the names. Left in, it contributes a column of 1, 2, 3 and
    # pushes the search for the names past the names. It is recognised by being a run of small
    # integers that ascends across the page, which no column of prices in this study does.
    if len(grid) > 1:
        deepest_row = sorted(grid[0])
        values = [value for _x, _t, value in deepest_row]
        if all(value <= 30 for value in values) and values == sorted(set(values)):
            grid = grid[1:]

    columns = [
        sum(group) / len(group)
        for group in bands([x for row in grid for x, _t, _v in row], 12)
    ]
    if not columns:
        return []

    # The names sit below every value on the turned page, in a cell centred over the two
    # columns they own.
    deepest = max(row[0][1] for row in grid)
    edge = max(columns)
    labels: dict[float, list[tuple[float, str]]] = {}
    for text, x0, _x1, top in words:
        token = clean(text)
        if top < deepest + 20 or NUMBER.match(token) or MARKER.match(token.strip(".,")):
            continue
        if x0 < min(columns) - 45 or x0 > edge + 40:
            continue
        # Rounded, because a line of the name cell is a single x only to within a fraction
        # of a point: `Poiana` lands at 227.9 and `Lacului,` at 227.7, and keyed exactly they
        # become two lines and the commune's two words are never adjacent.
        labels.setdefault(round(x0 / 3) * 3, []).append((top, token))

    groups: list[tuple[float, list[str]]] = []
    for cluster in bands(list(labels), 20):
        # A wrapped name cell reads down the page's x and back up its y: one line of the cell
        # is a single x, and the words along it descend rather than ascend, because that is
        # which way this scan was turned. Read the other way `Poiana Lacului, Morărești,`
        # comes out as `Lacului, Morărești, Poiana` and the commune is never found.
        pieces = [
            " ".join(token for _top, token in sorted(labels[x0], reverse=True))
            for x0 in cluster
        ]
        label = " ".join(pieces)
        found = names_in(label, is_local)
        # A cluster that names nothing is kept only when it is the row that prices a whole
        # circumscription's countryside. Otherwise stray marks — a column number left over as
        # `4)` — become groups of their own and take the column belonging to the row beside
        # them, which moves a locality's prices onto its neighbour.
        if found or (COUNTRYSIDE.search(label) and not label.upper().startswith("NOTA")):
            groups.append((sum(cluster) / len(cluster), found, label))
    if not groups:
        return []

    # Every column goes to the name nearest it. A locality that lost a column to the scan keeps
    # the one it has; the alternative, handing out columns in order, moves every later locality
    # up by one and reads as a complete table.
    owned: dict[int, list[float]] = {}
    for column in columns:
        index = min(
            range(len(groups)), key=lambda position: abs(groups[position][0] - column)
        )
        if abs(groups[index][0] - column) <= 40:
            owned.setdefault(index, []).append(column)

    results = []
    for index, (centre, places, label) in enumerate(groups):
        mine = sorted(owned.get(index, []))
        if not mine:
            continue
        built = mine[0]
        prices = [
            value
            for row in grid
            for x, _t, value in sorted(row)
            if abs(x - built) < 9
        ]
        farmland = None
        if extra:
            near = min(extra, key=lambda item: abs(item[0] - centre))
            if abs(near[0] - centre) < 22:
                farmland = near[2]
        if prices:
            results.append((places, prices, farmland, label))
    return results


def courts_of(pages: list[dict], is_local) -> dict[str, list[str]]:
    """Which communes each court covers, from the 1993 decision the study reprints.

    Câmpulung, Curtea de Argeș, Topoloveni and Costești each price their whole countryside in
    one row — `Comunele / Sate de centru 17`, `Alte sate 10` — and name none of the communes,
    because this page has already named them. Without it those four circumscriptions
    contribute their town and nothing else, which is most of the county.
    """
    for page in pages:
        text = page.get("text") or ""
        if len(ASSIGNMENT_PAGE.findall(text)) < 3:
            continue
        found: dict[str, list[str]] = {}
        cuts = list(COURT_SECTION.finditer(text))
        for index, cut in enumerate(cuts):
            stop = cuts[index + 1].start() if index + 1 < len(cuts) else len(text)
            body = re.sub(r"\d{1,2}\s*\.", " ", text[cut.end() : stop])
            # Keyed on the first word of the court's name, which is what a running head can be
            # relied on to contain somewhere.
            found[loose(clean(cut.group(1)).split()[0])] = names_in(body, is_local)
        if found:
            return found
    return {}


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    courts = courts_of(pages, is_local)
    priced: dict[str, dict] = {}
    shared: dict[str, list[tuple[list[float], float | None]]] = {}
    notes: list[str] = []

    def record(place: str, prices: list[float], farmland: float | None) -> None:
        # Keyed loosely, because the same locality reaches this from two documents with two
        # spellings — the tables say Câmpulung and the 1993 decision says Cîmpulung — and a
        # strict key makes them two places, one of which then collects the price meant for
        # the countryside around it.
        entry = priced.setdefault(loose(place), {"name": place, "parts": [], "rates": {}})
        entry["parts"].extend(prices)
        if farmland:
            # The study prices extravilan as one figure per locality, so every category that
            # is not built on and not forest takes it.
            for code in ("A", "P+F", "V+L", "NP"):
                entry["rates"].setdefault(code, farmland)

    for page in pages:
        head = (page.get("text") or "")[:400]
        if not LAND_TABLE.search(head) or NOT_LAND.search(head):
            continue
        folded = loose(head)
        where = next((key for key in courts if key and key in folded), "")
        for places, prices, farmland, label in read_table(page, is_local):
            if places:
                for place in places:
                    record(place, prices, farmland)
            elif where and COUNTRYSIDE.search(label) and not label.upper().startswith("NOTA"):
                shared.setdefault(where, []).append((prices, farmland))

    # The rows that named no locality belong to every commune of their court that no row named.
    for where, rows in shared.items():
        for place in courts.get(where, []):
            if loose(place) in priced:
                continue
            for prices, farmland in rows:
                record(place, prices, farmland)

    if not priced:
        notes.append("niciun tabel de teren nu s-a citit")
    if not courts:
        notes.append("lista circumscripțiilor nu s-a citit")

    communes = []
    for position, entry in enumerate(sorted(priced.values(), key=lambda e: e["name"]), start=1):
        prices = sorted(dict.fromkeys(entry["parts"]), reverse=True)
        communes.append(
            {
                "name": entry["name"],
                "villages": [
                    {
                        "name": entry["name"] if not offset else f"{entry['name']} ({offset + 1})",
                        "intravilan": {"CC": price},
                    }
                    for offset, price in enumerate(prices)
                ],
                "extravilan": entry["rates"],
                "page": 31,
                "index": position,
            }
        )
    return [], communes, notes

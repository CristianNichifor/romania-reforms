"""Brașov and Covasna, dismissed here at "4%" and then misread at 91%. Third attempt.

The 4% came from counting tables whose first row mentions land. This study puts land inside
annexes titled after buildings — *"Clădiri de locuit individuale, anexe gospodărești **și
terenuri situate în intravilanul localităţilor**"* — so the count found four tables in a volume
that prices every locality in two counties. That was the third time that measurement was wrong,
after Suceava and Botoșani.

The second attempt was worse, because it looked like it worked: **91,4% coverage and impossible
numbers.** Brașov came out with zone B dearer than zone A — 5 500 against 1 500 — where the page
says 1.150 / 980 / 800 / 630. Two mistakes, both worth naming because both are generic:

* the town reader accepted **any** table whose header carried `ZONA`, and the building tables
  carry it too, so it read a construction price and called it land;
* the rural reader took the first numeric cell of a row as its price, and the first cell of
  these rows is the **row number** — `| 1 | Comunele Hărman… | 242,0 |` gave 1,0.

Coverage was 91% throughout. That is the failure this repository is built around, and it got
past the gate because coverage is not correctness.

**Towns.** Ten in Brașov, five in Covasna, one table each. The land row is the one that begins
*"Teren intravilan categorie de folosință «curți-construcții»"*, and the rows under it are
*"Teren intravilan agricol"*, which is a different thing:

    Destinație/utilizare                       ZONA A   ZONA B   ZONA C   ZONA D
    Teren intravilan „curți-construcții”        1.150      980      800      630
    Teren intravilan agricol …                    630      540      440      350

**The countryside is priced differently in the two counties**, which is why one reader has two
rural branches rather than one:

*Brașov* prices by court circumscription, seat and villages apart, with three communes named
out of the scheme at nearly twice their neighbours — Hărman, Sânpetru and Cristian, the ring
around the city:

    1  Comunele Hărman, Sânpetru, Cristian și satele …     242,0
    2  Comunele din circumscripția Judecătoriei Brașov     131,0
    3  Satele aparținătoare comunelor din circumscripția…   98,0

*Covasna* prices in three columns instead — a named list, then everything else:

    Destinație/utilizare   Localitățile: Malnaș, Reci,   Comune (sate de     Sate altele
                           Balvanyoș, Ozunka băi …       reședință) altele   decât col.1
    Teren intravilan …           33,7                        28,2              18,8

Brașov's version needs to know which commune sits in which circumscription. The study does not
say, because the decision that says so is law — HG 1217/2023 — and this repository already
carries it in `arondare-2023.json`. That is the one place a reader here reaches into another
simulator, and it beats retyping a government annex.

**Extravilan is per locality by name**, several to a row where they share a price, and forest
is one figure for the county.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARONDARE = ROOT.parents[1] / "simulators" / "justitie" / "data" / "arondare-2023.json"

COUNTY_LINE = re.compile(r"^\s*JUDE[ŢT]UL\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ ]{2,})\s*$", re.M)
TOWN_LINE = re.compile(
    r"^\s*(?:MUNICIPIUL|ORA[ȘŞS]UL)\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,})\s*$", re.M
)
ZONE_HEADER = re.compile(r"ZONA\s*[”\"„]?\s*([A-F])", re.I)
# The land row, and the rows immediately under it that are NOT it. "categorie de folosință"
# is what separates building land from the agricultural land inside the same intravilan.
BUILT_ROW = re.compile(r"Teren\s+intravilan\s+categorie\s+de\s+folosin", re.I)
AGRICULTURAL_ROW = re.compile(r"Teren\s+intravilan\s+agricol", re.I)

SEAT_ROW = re.compile(r"^Comunele\s+din\s+circumscrip[țţt]ia\s+Judec[ăa]toriei\s+(.+)$", re.I)
VILLAGE_ROW = re.compile(
    r"^Satele\s+apar[țţt]in[ăa]toare\s+comunelor\s+din\s+circumscrip[țţt]ia\s+"
    r"Judec[ăa]toriei\s+(.+)$",
    re.I,
)
NAMED_ROW = re.compile(r"^Comunele\s+([^,]+(?:,\s*[^,]+)*?)\s+[șş]i\s+satele", re.I)
LOCALITIES_COLUMN = re.compile(r"Localit[ăa][țţt]ile\s*:", re.I)
OTHER_SEATS = re.compile(r"Comune\s*\(sate\s+de\s+re[șş]edin[țţt][ăa]\)", re.I)
OTHER_VILLAGES = re.compile(r"Sate\s+altele\s+dec[âa]t", re.I)

EXTRA_HEADER = re.compile(r"Localitate,\s*zon[ăa]\s*amplasare", re.I)
FOREST_ANNEX = re.compile(r"TERENURI\s+CU\s+VEGETA[ȚŢT]IE\s+FORESTIER", re.I)
PLACE = re.compile(
    r"(?:Municipiul|Ora[șş]ul|Comuna)\s+"
    r"([A-ZĂÂÎȘŞȚŢ][\wăâîșşțţ\-]+(?:\s+(?:de\s+|din\s+)?[A-ZĂÂÎȘŞȚŢ][\wăâîșşțţ\-]+){0,2})"
)
EXTRA_CODES = ("A", "P+F", "V+L")


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def number(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?", stripped):
        return None
    value = float(stripped.replace(".", "").replace(",", "."))
    return value if 0 < value < 100_000 else None


def courts_of(county: str) -> dict[str, str]:
    """SIRUTA to court, from HG 1217/2023 as the justice simulator imported it."""
    if not ARONDARE.exists():
        return {}
    document = json.loads(ARONDARE.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for court in document["courts"]:
        if court["county"] != county:
            continue
        name = fold(re.sub(r"^Judec[ăa]toria\s+", "", court["name"]))
        for siruta in court["localities"]:
            found[str(siruta)] = name
    return found


def court_key(label: str) -> str:
    """The court's name out of a row label, with its qualifiers stripped.

    "Comunele din circumscripția Judecătoriei Brașov, altele decât poz. 1" names the Brașov
    circumscription; keeping the qualifier gave a key of BRASOVALTELEDECATPOZ, which matched
    no court, so every commune around the county town silently fell through to nothing.
    """
    cut = re.split(r",|\baltele\b|\bși\b", label, maxsplit=1)[0]
    return fold(cut)


def rows_of(table: dict) -> list[list[str]]:
    return [[clean(c) for c in row] for row in table["cells"]]


def built_row(cells: list[list[str]]) -> list[str] | None:
    """The `curți-construcții` row, and only it.

    Explicitly not "the first data row": the same table holds agricultural intravilan
    underneath, and a table of building prices on another page has the same zone header.
    """
    return next(
        (
            row
            for row in cells
            if row
            and BUILT_ROW.search(row[0])
            and not AGRICULTURAL_ROW.search(row[0])
        ),
        None,
    )


def read_town_zones(page: dict) -> dict[str, float]:
    for table in page.get("tables") or []:
        cells = rows_of(table)
        if len(cells) < 2:
            continue
        row = built_row(cells)
        if row is None:
            continue
        letters = [ZONE_HEADER.search(c) for c in cells[0]]
        zones: dict[str, float] = {}
        for position, found in enumerate(letters):
            if found and position < len(row):
                value = number(row[position])
                if value is not None:
                    zones[found.group(1).upper()] = value
        if zones:
            return zones
    return {}


def read_rural_brasov(page: dict) -> tuple[dict[str, list], dict[str, float]]:
    """(court -> [seat, village], named commune -> price) from Brașov's rural annex."""
    by_court: dict[str, list] = {}
    named: dict[str, float] = {}
    for table in page.get("tables") or []:
        cells = rows_of(table)
        # Only the building-land table. The agricultural one on the same page has the same row
        # labels — the circumscriptions are the same — and four price columns instead of one,
        # so reading both mixed 17,5 and 23,6 in among 242 and 131 and nothing complained.
        header = " ".join(c for row in cells[:3] for c in row)
        if not BUILT_ROW.search(header) or AGRICULTURAL_ROW.search(header):
            continue
        for row in cells:
            label = next((c for c in row if len(c) > 15), None)
            if label is None:
                continue
            # After the label, never before: the first cell is the row number, and taking the
            # first numeric cell in the row read every price as 1, 2, 3 …
            after = row[row.index(label) + 1 :]
            value = next((v for v in (number(c) for c in after) if v is not None), None)
            if value is None:
                continue
            village = VILLAGE_ROW.match(label)
            seat = SEAT_ROW.match(label)
            if village:
                by_court.setdefault(court_key(village.group(1)), [None, None])[1] = value
            elif seat:
                by_court.setdefault(court_key(seat.group(1)), [None, None])[0] = value
            else:
                found = NAMED_ROW.match(label)
                if found:
                    for token in re.split(r"[,;]", found.group(1)):
                        key = fold(token)
                        if len(key) > 3:
                            named[key] = value
    return by_court, named


def read_rural_covasna(page: dict) -> tuple[dict[str, float], float | None, float | None]:
    """(named locality -> price, other seats, other villages) from Covasna's rural annex."""
    named: dict[str, float] = {}
    seats = villages = None
    for table in page.get("tables") or []:
        cells = rows_of(table)
        row = built_row(cells)
        if row is None:
            continue
        header = cells[0]
        listed = None
        for position, cell in enumerate(header):
            if LOCALITIES_COLUMN.search(cell):
                listed = position
            elif OTHER_SEATS.search(cell) and position < len(row):
                seats = number(row[position]) or seats
            elif OTHER_VILLAGES.search(cell) and position < len(row):
                villages = number(row[position]) or villages
        if listed is not None:
            # The named localities spill down the column over several rows.
            spill = " ".join(
                line[listed] for line in cells if listed < len(line) and line[listed]
            )
            price = next(
                (v for v in (number(c) for c in row[listed:]) if v is not None), None
            )
            if price is not None:
                for token in re.split(r"[,;]| și ", spill):
                    key = fold(re.sub(r"Localit[ăa][țţt]ile\s*:?", "", token))
                    if len(key) > 3:
                        named.setdefault(key, price)
    return named, seats, villages


def read_extravilan(page: dict) -> dict[str, dict[str, float]]:
    found: dict[str, dict[str, float]] = {}
    for table in page.get("tables") or []:
        cells = rows_of(table)
        if not cells or not any(EXTRA_HEADER.search(c) for c in cells[0]):
            continue
        for row in cells[1:]:
            label = next((c for c in row if PLACE.search(c)), "")
            values = [v for v in (number(c) for c in row) if v is not None]
            if not label or len(values) < 2:
                continue
            prices = dict(zip(EXTRA_CODES, values, strict=False))
            for place in PLACE.findall(label):
                found.setdefault(fold(place), prices)
    return found


def read_forest(pages: list[dict], label: str) -> float | None:
    here = ""
    for page in pages:
        found = COUNTY_LINE.search(page.get("text") or "")
        if found:
            here = fold(found.group(1))
        if here != fold(label) or not FOREST_ANNEX.search(page.get("text") or ""):
            continue
        prices = sorted(
            v
            for table in page.get("tables") or []
            for row in table["cells"]
            for v in (number(clean(c)) for c in row)
            if v is not None and 0.2 <= v <= 50
        )
        if prices:
            return prices[len(prices) // 2]
    return None


def parse_county(name: str, is_local, county: str, label: str, siruta_of):
    pages = load(name)["pages"]
    courts = courts_of(county)

    towns: dict[str, dict[str, float]] = {}
    by_court: dict[str, list] = {}
    named: dict[str, float] = {}
    other_seats = other_villages = None
    extravilan: dict[str, dict[str, float]] = {}

    here = ""
    town = ""
    for page in pages:
        text = page.get("text") or ""
        found = COUNTY_LINE.search(text)
        if found:
            here = fold(found.group(1))
        if here != fold(label):
            continue
        heading = TOWN_LINE.search(text)
        if heading and is_local(clean(heading.group(1))):
            town = clean(heading.group(1))

        zones = read_town_zones(page)
        if zones and town:
            towns.setdefault(town, {}).update(zones)

        courts_here, one_off = read_rural_brasov(page)
        for key, pair in courts_here.items():
            slot = by_court.setdefault(key, [None, None])
            slot[0] = slot[0] if slot[0] is not None else pair[0]
            slot[1] = slot[1] if slot[1] is not None else pair[1]
        named.update(one_off)

        listed, seats, villages = read_rural_covasna(page)
        named.update(listed)
        other_seats = other_seats or seats
        other_villages = other_villages or villages

        extravilan.update(read_extravilan(page))
    forest = read_forest(pages, label)

    zoned = [
        {
            "name": place,
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": zones},
            "extravilan": extravilan.get(fold(place), {}),
            "page": 1,
        }
        for place, zones in towns.items()
    ]
    town_keys = {fold(t["name"]) for t in zoned}

    communes: list[dict] = []
    for siruta, court in courts.items():
        place = siruta_of(siruta)
        if not place:
            continue
        key = fold(place)
        if key in town_keys:
            continue
        seat = named.get(key)
        village = seat
        if seat is None:
            pair = by_court.get(court)
            if pair and pair[0] is not None:
                seat, village = pair[0], pair[1] if pair[1] is not None else pair[0]
            elif other_seats is not None:
                seat, village = other_seats, other_villages or other_seats
        if seat is None:
            continue
        grid = dict(extravilan.get(key, {}))
        if forest:
            grid["PADURE"] = forest
        communes.append(
            {
                "name": place,
                "villages": [
                    {"name": place, "intravilan": {"CC": seat}},
                    {"name": f"{place} (sate)", "intravilan": {"CC": village}},
                ],
                "extravilan": grid,
                "page": 1,
            }
        )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    notes = [] if communes else ["no commune matched a rural price"]
    return zoned, communes, notes

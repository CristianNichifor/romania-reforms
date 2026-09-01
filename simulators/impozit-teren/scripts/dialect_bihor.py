"""The CNP Oradea dialect: one county published as five separate documents.

Bihor is not one study but five, one per court circumscription — Oradea, Aleșd, Beiuș,
Marghita, Salonta — each a PDF of its own. So this reader is the first that has to read a
county out of several files and add them up, which is why it finds its own siblings in the
cache rather than being handed one name.

It also classifies land differently from every other chamber. Where the others price the
cadastral categories a land tax is written in — arabil, pășuni, vii, livezi — Bihor prices
**what is on the land and how big the parcel is**:

    intravilan   teren ocupat de construcții · teren liber · alei și drumuri ·
                 teren aferent spațiilor comerciale / industriale / agricole
    extravilan   teren agricol (arabil) · teren neagricol (pășuni) · păduri · livezi și vii

Forest is kept. It used to be read and discarded here as everywhere else, on the grounds that
the shared vocabulary had no code for it — which left 183 000 hectares of Bihor, a third of the
county, valued at nothing.

The intravilan side maps cleanly: *teren ocupat de construcții* is building land and that is
what a land tax mostly falls on. The extravilan side maps with one loss worth stating — Bihor
publishes a single agricultural price where the shared vocabulary distinguishes arable from
pasture, so both take the same figure here and the distinction that exists in other counties
is simply not published in this one.

The captions are printed stacked, one word per row — `Teren` / `agricol` / `(arabil)` — so a
column's caption is the whole column of header cells joined, not any single one of them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import CACHE, load  # noqa: E402

# Column captions, matched against the joined header column. Ordered so a more specific
# caption wins: "teren aferent spatiilor agricole" is a building plot, not farmland.
INTRAVILAN_CC = re.compile(r"ocupat\s*de\s*construc", re.I)
EXTRA_CAPTIONS: list[tuple[str, str]] = [
    ("A", r"agricol.*arabil|arabil"),
    # Both s-with-comma and s-with-cedilla: they render alike and are different characters,
    # and a class carrying only one of them silently matched no column at all in Satu Mare.
    ("P+F", r"neagricol|p[ăa][sșş]un"),
    ("PADURE", r"p[ăa]duri"),
    ("V+L", r"livezi|\bvii\b"),
]
NAME = re.compile(r"^[A-ZĂÂÎȘŞȚŢ][\w \-\.'‐]{2,}$", re.U)
# "A+B", "C", and Oradea's own "Zona Aa" — a zone label, never a place name.
ZONE_ONLY = re.compile(r"^(zona[\s‐-]*)?([A-D][a-b]?)(\+[A-D][a-b]?)?$", re.I)
# Each annex is titled after the town whose circumscription it covers, and that town's own
# price table is labelled by zone alone — the locality is the volume itself.
ANNEX_TOWN = re.compile(r"Anexa_\d_([A-Za-zĂÂÎȘŞȚŢăâîșşțţ]+)", re.I)


# The five annexes this reader merges, for the same reason Timișoara declares its own: a
# clean checkout has only the document the importer was asked for, and globbing the cache
# would quietly read one annex of five.
NEEDS = re.compile(r"BIHOR_\d{4}.*Anexa_\d", re.I)


def number(cell: str) -> float | None:
    """The first number in a cell — never the digits of two numbers run together.

    Squeezing the whitespace out first turned a cell holding "40 40" into 4 040 and put half
    the county's communes above Oradea, which the town-to-commune ratio caught before any of
    it was written. A cell with two numbers in it is two numbers.
    """
    tokens = [t for t in re.split(r"\s+", cell.strip()) if t]
    if not tokens or not re.fullmatch(r"\d{1,6}([.,]\d+)?", tokens[0]):
        return None
    value = float(tokens[0].replace(",", "."))
    return value if 0 < value < 100_000 else None


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell).strip()


def header_columns(cells: list[list[str]], rows: int = 6) -> dict[int, str]:
    """Each column's caption, built by joining the header cells stacked above it.

    Bihor prints its captions one word to a row, so no single cell says what a column holds
    and the caption only exists as the column read downwards.
    """
    width = max((len(row) for row in cells[:rows]), default=0)
    joined = {}
    for index in range(width):
        parts = [clean(row[index]) for row in cells[:rows] if index < len(row)]
        joined[index] = " ".join(p for p in parts if p).lower()
    return joined


def read_extravilan(cells: list[list[str]]) -> dict[str, dict[str, float]]:
    """Per-locality agricultural prices, from the four-category table."""
    columns = header_columns(cells)
    mapped: dict[int, str] = {}
    for index, caption in columns.items():
        for code, pattern in EXTRA_CAPTIONS:
            if code not in mapped.values() and re.search(pattern, caption):
                mapped[index] = code
                break
    if "A" not in mapped.values():
        return {}
    found: dict[str, dict[str, float]] = {}
    for row in cells:
        line = [clean(c) for c in row]
        label = next((c for c in line[:2] if NAME.match(c)), "")
        if not label:
            continue
        values = {
            code: number(line[i]) for i, code in mapped.items() if i < len(line) and number(line[i])
        }
        if values:
            # Bihor publishes one agricultural price; the shared vocabulary wants three.
            if "A" in values:
                values.setdefault("V+L", values["A"])
            found[label.upper()] = values
    return found


def read_intravilan(
    cells: list[list[str]], is_local, fallback: str | None = None
) -> list[tuple[str | None, str, float]]:
    """Building-land prices as (commune, locality, price), commune None where not split."""
    columns = header_columns(cells)
    target = next((i for i, caption in columns.items() if INTRAVILAN_CC.search(caption)), None)
    if target is None:
        return []
    head = " ".join(columns.values())
    split = "comuna" in head and "satul" in head

    # A town's own rows carry a zone code where a village would carry its name, and the town's
    # name is merged across them and printed vertically centred — so it can sit *below* the
    # zone rows it belongs to. Attribution is therefore by nearest label in the table, not by
    # the last one seen: reading downwards only gave every town its cheapest attached village
    # and priced Oradea below the communes around it.
    labels_at: dict[int, str] = {}
    for position, row in enumerate(cells):
        line = [clean(c) for c in row]
        for cell in line[: 2 if split else 1]:
            # Only a name the register knows. Without this the table's own caption — "TABEL
            # CENTRALIZATOR" — was the nearest label to every one of Oradea's zone rows and
            # took the city's prices with it.
            if NAME.match(cell) and not ZONE_ONLY.match(cell) and is_local(cell):
                labels_at.setdefault(position, cell)
                break

    def nearest(position: int) -> str | None:
        if not labels_at:
            return None
        return labels_at[min(labels_at, key=lambda p: (abs(p - position), p))]

    found: list[tuple[str | None, str, float]] = []
    commune: str | None = None
    for position, row in enumerate(cells):
        line = [clean(c) for c in row]
        price = number(line[target]) if target < len(line) else None
        if price is None:
            continue
        own = labels_at.get(position)
        # Zone codes are not in a fixed column: a town's block can carry them in the third
        # or fourth, behind the columns its villages use for names. Scanned across the front
        # of the row rather than at one offset, which is what left Oradea unpriced.
        zoned = any(ZONE_ONLY.match(c) for c in line[:5] if c)
        if split and own and NAME.match(line[0] if line else ""):
            commune = line[0]
        # A table whose only labels are zone codes belongs to the town the annex is named
        # after: Oradea's own grid names no locality anywhere on the page.
        label = own or (nearest(position) if zoned else None) or (fallback if zoned else None)
        if not label:
            continue
        found.append((commune if split and own else None, label, price))
    return found


def annexes(name: str) -> list[str]:
    """This county's other volumes, found in the cache beside the one that was asked for.

    A revised annex supersedes the original of the same number, which is why the newest file
    per annex wins rather than both being read and added together.
    """
    stem = re.match(r"(.*BIHOR_\d{4})", name, re.I)
    if not stem:
        return [name]
    by_annex: dict[str, str] = {}
    for path in sorted(CACHE.glob("*BIHOR*.json.gz")):
        found = path.name[: -len(".json.gz")]
        number_of = re.search(r"Anexa_(\d)", found, re.I)
        if not number_of:
            continue
        key = number_of.group(1)
        if key not in by_annex or "revizuit" in found.lower():
            by_annex[key] = found
    return list(by_annex.values()) or [name]


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    intravilan: list[tuple[str | None, str, float]] = []
    extravilan: dict[str, dict[str, float]] = {}
    pages_of: dict[str, int] = {}

    for volume in annexes(name):
        try:
            document = load(volume)
        except SystemExit:
            continue
        named = ANNEX_TOWN.search(volume)
        town_of = named.group(1).upper() if named and is_local(named.group(1)) else None
        for index, page in enumerate(document["pages"]):
            for table in page["tables"]:
                cells = [[c or "" for c in row] for row in table["cells"]]
                if len(cells) < 3:
                    continue
                extravilan.update(read_extravilan(cells))
                for commune, locality, price in read_intravilan(cells, is_local, town_of):
                    intravilan.append((commune, locality, price))
                    pages_of.setdefault(locality.upper(), index + 1)

    communes: dict[str, dict] = {}
    for commune, locality, price in intravilan:
        owner = commune if commune and is_local(commune) else locality
        if not is_local(owner):
            continue
        entry = communes.setdefault(
            owner.upper(),
            {
                "name": owner,
                "villages": [],
                "extravilan": {},
                "page": pages_of.get(locality.upper(), 1),
            },
        )
        # Deduplicated on the price as well as the name. A town's zones all resolve to the
        # same locality, so keying on the name alone kept only the dearest of Oradea's six
        # and collapsed its band to a point — the simulator's whole output is a band, and a
        # locality priced at one number is a locality claiming certainty it does not have.
        if all((v["name"], v["intravilan"]["CC"]) != (locality, price) for v in entry["villages"]):
            entry["villages"].append({"name": locality, "intravilan": {"CC": price}})

    for key, entry in communes.items():
        entry["extravilan"] = extravilan.get(key, {})
        if not entry["extravilan"]:
            for village in entry["villages"]:
                match = extravilan.get(village["name"].upper())
                if match:
                    entry["extravilan"] = match
                    break
    for position, entry in enumerate(communes.values(), start=1):
        entry["index"] = position
    return [], list(communes.values()), []

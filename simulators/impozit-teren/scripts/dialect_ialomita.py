"""Ialomița, which prices its land in a sentence under each annex and not in a table at all.

The correction tables at the front of this county refer to *"valoare teren liber conform
grilă"*, so a grid exists — but there is no land table anywhere in its 180 pages. The prices
are prose, one pair per annex page, under whichever locality and zone that page belongs to:

    Municipiul SLOBOZIA – Zona I
    …
    Terenuri intravilane in zona : Teren liber = 99,2 euro/mp ;
    Teren ocupat = 76,2 euro/mp.

**This is the one county in the set that publishes the occupied price directly.** Everywhere
else in this chamber the tables print free land and a sentence says to take 30% off; here both
figures are printed, so the occupied one is read rather than derived. The two are not in a
constant ratio either — Slobozia zone I is 0,768 and its zone IV is 0,735 — which is a small
argument that the 30% rule applied elsewhere is a convention rather than a measurement.

**Rural land is by category**, three per circumscription, and the assignment is prose again:

    Incadrarea localitatilor rurale apartinand circumscriptiei Judecatoriei Slobozia in categorii
    Categoria I-a
    Localitatea Andrăşeşti      Localitatea Griviţa
    Localitatea Bucu            Localitatea Orboeşti – com. Andrăşeşti

Two entries to a line, so this splits on the `Localitatea` keyword rather than on line breaks.
The three circumscriptions price the same categories differently — 10,8 / 8,1 / 11,0 EUR/m²
for category I — so each is closed against its own prices, as in Giurgiu.

**The extravilan table covers the five towns and nothing else**, by road access:

    Municipiul SLOBOZIA
    I    cu acces direct la DE60, posibil de transferat …   21.730
    III  situat in planul II al retelelor rutiere            7.000

Three times between the ends, and the *planul II* row is the one that is farmland rather than
a development option. Its fifty-odd communes are given no figure at all, and leaving them at
zero would value most of a heavily agricultural county at nothing — so each commune takes the
cheapest *planul II* price published in its own circumscription. That is an approximation and
is carried as one: it is the document's own number for ordinary farmland in that
circumscription, applied to land the document does not price, and it is a town's surroundings
being used for a county's fields.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cnpb_common import (  # noqa: E402
    clean,
    county_pages,
    extravilan_from,
    fold,
    per_ha,
    zone_letter,
)
from extract_cache import load  # noqa: E402

OCCUPIED = re.compile(r"Teren\s+ocupat\s*=?\s*([\d,]+)\s*euro/mp", re.I)
FREE = re.compile(r"Teren\s+liber\s*=?\s*([\d,]+)\s*euro/mp", re.I)
# "Municipiul SLOBOZIA, Zona I", "Oras TANDAREI – Zona III", "Oras FIERBINTI-TARG"
TOWN_PAGE = re.compile(
    r"^(?:Municipiul|Oras(?:ul)?)\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,}?)"
    r"(?:\s*[,–-]\s*Zona\s+([IVX]+)(?:\s*(?:si|și)\s*Zona\s+([IVX]+))?)?\s*$",
    re.M,
)
RURAL_PAGE = re.compile(r"Localitati\s+rurale\s*[–-]\s*Categoria\s+(?:a\s+)?([IVX]+)", re.I)
ASSIGNMENT_PAGE = re.compile(r"Incadrarea\s+localitatilor\s+rurale", re.I)
CATEGORY_HEADING = re.compile(r"^Categoria\s+(?:a\s+)?([IVX]+)\s*-?\s*a?\s*$", re.I)
# "Localitatea Bucu", "Localitatea Orboeşti – com. Andrăşeşti" — two to a line.
LOCALITY = re.compile(r"Localitatea\s+([^\n]+?)(?=\s*Localitatea\s|$)")
PARENT = re.compile(r"^(.*?)\s*[-–—]\s*com\.?\s*(.+)$", re.I)
EXTRA_HEADER = re.compile(r"CATEGORIE\s+TEREN", re.I)
SECOND_PLANE = re.compile(r"planul\s*II", re.I)
TOWN_ROW = re.compile(r"^(?:Municipiul|Orasul|Oras)\s+(.+)$", re.I)


def per_m2(text: str) -> float | None:
    value = float(clean(text).replace(",", "."))
    return value if 0 < value < 1_000 else None


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    within = county_pages(pages, "Ialomița")
    if not within:
        return [], [], ["no page carries the county header"]

    towns: dict[str, dict[str, float]] = {}
    priced: dict[str, tuple[str, float]] = {}
    pending: list[tuple[str, str, str]] = []
    categories: dict[str, float] = {}
    town_arable: dict[str, float] = {}
    circumscription_arable: list[float] = []
    fallback_for: dict[str, float] = {}
    notes: list[str] = []

    def close() -> None:
        """Bind the assignments read so far to the prices that follow them."""
        if not (pending and categories):
            return
        cheapest = min(circumscription_arable) if circumscription_arable else None
        for village, letter, commune in pending:
            price = categories.get(letter)
            if price is None:
                continue
            priced.setdefault(fold(village), (commune, price))
            if cheapest is not None:
                fallback_for.setdefault(fold(commune), cheapest)
        pending.clear()
        categories.clear()
        circumscription_arable.clear()

    for index in within:
        page = pages[index - 1]
        text = page.get("text") or ""

        if ASSIGNMENT_PAGE.search(text):
            # A new circumscription's list begins, so the previous one is complete.
            close()
            letter = None
            for line in text.splitlines():
                stripped = clean(line)
                heading = CATEGORY_HEADING.match(stripped)
                if heading:
                    letter = zone_letter(f"Categoria {heading.group(1)}")
                    continue
                if letter is None:
                    continue
                for raw in LOCALITY.findall(stripped):
                    item = clean(raw).strip(" .,;")
                    parent = PARENT.match(item)
                    village = clean(parent.group(1)) if parent else item
                    commune = clean(parent.group(2)) if parent else item
                    if village and is_local(commune):
                        pending.append((village, letter, commune))
            continue

        occupied = OCCUPIED.search(text)
        if occupied:
            price = per_m2(occupied.group(1))
            rural = RURAL_PAGE.search(text)
            if rural and price is not None:
                letter = zone_letter(f"Categoria {rural.group(1)}")
                if letter:
                    categories[letter] = price
                continue
            found = TOWN_PAGE.search(text)
            if found and price is not None and is_local(found.group(1)):
                town = clean(found.group(1))
                for group in (found.group(2), found.group(3)):
                    if group:
                        letter = zone_letter(f"Categoria {group}")
                        if letter:
                            towns.setdefault(town, {}).setdefault(letter, price)
                if not found.group(2):
                    towns.setdefault(town, {}).setdefault("A", price)
            continue

        for table in page.get("tables") or []:
            cells = [[clean(c) for c in row] for row in table["cells"]]
            if not cells or not any(EXTRA_HEADER.search(c) for c in cells[0]):
                continue
            where = ""
            for row in cells[1:]:
                header = next((TOWN_ROW.match(c) for c in row if TOWN_ROW.match(c)), None)
                if header:
                    where = clean(header.group(1))
                    continue
                if not where or not SECOND_PLANE.search(" ".join(row)):
                    continue
                value = next((v for v in (per_ha(c) for c in row) if v is not None), None)
                if value is None:
                    continue
                circumscription_arable.append(value)
                if is_local(where):
                    town_arable.setdefault(fold(where), value)
    close()

    if not town_arable:
        notes.append("nicio valoare extravilană citită")
    extravilan_of = {key: extravilan_from(v) for key, v in town_arable.items()}
    fallback_of = {key: extravilan_from(v) for key, v in fallback_for.items()}

    zoned = [
        {
            "name": town,
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": zones},
            "extravilan": extravilan_of.get(fold(town), {}),
            "page": 1,
        }
        for town, zones in towns.items()
    ]
    communes: dict[str, dict] = {}
    for village, (commune, price) in priced.items():
        entry = communes.setdefault(fold(commune), {"name": commune, "villages": []})
        entry["villages"].append({"name": village.title(), "intravilan": {"CC": price}})
    entries = []
    for position, (key, entry) in enumerate(sorted(communes.items()), start=1):
        entries.append(
            {
                "name": entry["name"],
                "villages": entry["villages"],
                "extravilan": extravilan_of.get(key) or fallback_of.get(key, {}),
                "page": 1,
                "index": position,
            }
        )
    return zoned, entries, notes

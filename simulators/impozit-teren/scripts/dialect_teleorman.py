"""Teleorman, the largest of the four and the only one that prices its countryside properly.

Ninety-seven localities across five circumscriptions, and — unlike Ialomița, which prices
extravilan for its five towns and nothing else — Teleorman publishes an agricultural figure
**per circumscription** as well as per town:

    Nr  Amplasament                  Categoria I    Categoria II   Categoria III
                                     posibil de     situat în      destinaţie exclusiv
                                     transferat     planul II      agricolă
    1.  Alexandria                   12.200         6.000          4.800
    1.  Circum.Jud. Alexandria        7.500         5.500          4.000

So a commune takes its own circumscription's agricultural rate rather than a town's
surroundings standing in for a county's fields. **Categoria III is the column taken**, for the
same reason as in Giurgiu: land *"posibil de transferat în intravilan"* is a development option
priced as one, and the hectares counted here are the register's agricultural categories.

**The rural land price is one number per annex**, and there are eleven annexes for what is
really six numbers — category I, II or III, each in a `ZONA CENTRU` and a `ZONA PERIFERIE`
variant, split further by building type in ways that do not change the land:

    Anexa VI-2/1   Categoria I    ZONA CENTRU      Teren curti constructii  3,6
    Anexa VI-2/2   Categoria I    ZONA PERIFERIE                            2,4
    Anexa VI-2/8   Categoria III  ZONA CENTRU                               2,0

The dearest reading of each (category, zone) pair is kept, and the two zones become the two
letters a rural locality gets.

**The assignment is prose again, and this one separates communes from villages explicitly:**

    CATEGORIA I
    Comune
    Vitanesti, Bujoreni, Draganesti Vlasca, Poroschia, …
    Sate
    Orbeasca de Sus – com Orbeasca, Orbeasca de Jos – com. Orbeasca

Comma-separated under two headings, one list per circumscription, five circumscriptions.

**The towns are named by their circumscription, not by their tables.** A land table carries
only `Starea terenului | Zona I | Zona II | …` with no place on it; the place is the seat named
in the `CIRCUMSCRIPTIA JUDECATORIEI X` heading that opened that stretch of the volume, so the
reader carries it forward — the same running-heading trick Satu Mare needed, one level up.
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

# "I. Circumscriptia JUDECATORIEI ALEXANDRIA" at the head of a section — case-insensitive
# because Alexandria's is the only one in mixed case, and requiring the roman numeral because
# the contents pages carry the same words. Contents lines end in a page number, and that is
# what excludes them: without it the index set the seat to Videle and Alexandria's own land
# table, twenty pages later, was published under Videle's name with Alexandria's prices.
CIRCUMSCRIPTION = re.compile(
    r"^\s*[IVX]+\.\s*Circumscriptia\s+JUDECATORIEI\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,}?)\s*$",
    re.I | re.M,
)
LAND_ROW = re.compile(r"Teren\s+curti[\s-]*constructii", re.I)
# "Zona I", "Zona III-IV" — and, in Zimnicea and one Videle annex, "Zona Centru" / "Zona
# Periferie" instead. Two towns' land tables label their zones in words, so a pattern that
# insisted on a numeral found their tables and read nothing out of them.
ZONE_HEADER = re.compile(r"Zona\s+([IVX]+)(?:\s*-\s*([IVX]+))?|Zona\s+(Centr|Perifer)", re.I)
RURAL_ANNEX = re.compile(r"Anexa\s+VI\s*-\s*2\s*/\s*\d+", re.I)
CATEGORY_OF = re.compile(r"Categoria\s+(I{1,3})\b")
ZONE_OF = re.compile(r"ZONA\s+(CENTRU|CENTRALA|PERIFERIE|PERIFEICA)", re.I)
# "Zonarea localitatilor rurale aparţinând de Judecătoria Alexandria" — the page names its own
# circumscription, which is the only reliable way to know it. Carrying forward the seat from
# the last section heading instead gave all five lists the same circumscription, and then every
# commune in the county drew the same agricultural rate from it.
ASSIGNMENT_PAGE = re.compile(
    r"Zonarea\s+localitatilor\s+rurale\s+apar[țţt]in[âaă]nd\s+de\s+Judec[ăa]toria\s+([^\n]+)",
    re.I,
)
CATEGORY_HEADING = re.compile(r"^CATEGORIA\s+(I{1,3})\s*$")
KIND_HEADING = re.compile(r"^(Comune|Sate)\s*:?\s*$", re.I)
PARENT = re.compile(r"^(.*?)\s*[-–—]\s*com\.?\s*(.+)$", re.I)
EXTRA_ROW = re.compile(r"Circum\.?\s*Jud\.?\s*(.+)$", re.I)
AGRICULTURAL = re.compile(r"exclusiv", re.I)


def per_m2(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:,\d{1,2})?", stripped):
        return None
    value = float(stripped.replace(",", "."))
    return value if 0 < value < 1_000 else None


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    within = county_pages(pages, "Teleorman")
    if not within:
        return [], [], ["no page carries the county header"]

    towns: dict[str, dict[str, float]] = {}
    rural: dict[tuple[str, str], float] = {}
    assignment: dict[str, tuple[str, str, str]] = {}
    town_arable: dict[str, float] = {}
    circuit_arable: dict[str, float] = {}
    notes: list[str] = []

    seat = ""
    circuit = ""
    for index in within:
        page = pages[index - 1]
        text = re.sub(r"\s+", " ", page.get("text") or "")

        found = CIRCUMSCRIPTION.search(page.get("text") or "")
        if found:
            candidate = clean(found.group(1))
            if is_local(candidate):
                seat = candidate
                circuit = fold(candidate)

        belongs = ASSIGNMENT_PAGE.search(text)
        if belongs:
            where = clean(belongs.group(1)).split("CATEGORIA")[0]
            where = clean(re.split(r"\s{2,}|Anexa", where)[0])
            circuit = fold(where) if is_local(where) else circuit
            letter = None
            kind = ""
            for line in (page.get("text") or "").splitlines():
                stripped = clean(line)
                heading = CATEGORY_HEADING.match(stripped)
                if heading:
                    letter = zone_letter(f"Categoria {heading.group(1)}")
                    continue
                if KIND_HEADING.match(stripped):
                    kind = stripped.lower()
                    continue
                if letter is None or not kind:
                    continue
                for raw in stripped.split(","):
                    item = clean(raw).strip(" .;:")
                    if not item or len(item) < 3:
                        continue
                    parent = PARENT.match(item)
                    village = clean(parent.group(1)) if parent else item
                    commune = clean(parent.group(2)) if parent else item
                    if is_local(commune):
                        assignment.setdefault(fold(village), (letter, commune, circuit))
            continue

        is_rural = bool(RURAL_ANNEX.search(text))
        for table in page.get("tables") or []:
            rows = [[clean(c) for c in row] for row in table["cells"]]
            values = next((r for r in rows if any(LAND_ROW.search(c) for c in r)), None)
            if values is None:
                continue
            if is_rural:
                category = CATEGORY_OF.search(text)
                zone = ZONE_OF.search(text)
                price = next((v for v in (per_m2(c) for c in values) if v is not None), None)
                if category and zone and price is not None:
                    letter = zone_letter(f"Categoria {category.group(1)}")
                    where = "A" if zone.group(1).upper().startswith("CENTR") else "B"
                    # Eleven annexes for six numbers: the same (category, zone) appears more
                    # than once, split by building type in ways that do not change the land.
                    if letter:
                        rural[(letter, where)] = max(rural.get((letter, where), 0.0), price)
                continue
            if not seat:
                continue
            header = next((r for r in rows if any(ZONE_HEADER.search(c) for c in r)), None)
            if header is None:
                continue
            for position, label in enumerate(header):
                if position >= len(values):
                    continue
                price = per_m2(values[position])
                zone = ZONE_HEADER.search(label)
                if price is None:
                    continue
                if zone is None:
                    # A bare "Zona" with no numeral: the last column of Alexandria's and
                    # Videle's tables loses its numeral in extraction, and skipping it dropped
                    # each town's cheapest zone — 19,4 of 70,6 and 5,6 of 11,4 — which narrows
                    # the published band from the bottom and makes a town look dearer than it
                    # is. It is the next zone after the last one read, so it is lettered so.
                    if clean(label).lower() == "zona" and towns.get(seat):
                        used = towns[seat]
                        towns[seat].setdefault(chr(ord(max(used)) + 1), price)
                    continue
                if zone.group(3):
                    letter = "A" if zone.group(3).upper().startswith("CENTR") else "B"
                    towns.setdefault(seat, {}).setdefault(letter, price)
                    continue
                for group in (zone.group(1), zone.group(2)):
                    if group:
                        letter = zone_letter(f"Categoria {group}")
                        if letter:
                            towns.setdefault(seat, {}).setdefault(letter, price)

        for table in page.get("tables") or []:
            rows = [[clean(c) for c in row] for row in table["cells"]]
            column = None
            for row in rows[:4]:
                for position, cell in enumerate(row):
                    if AGRICULTURAL.search(cell):
                        column = position
                if column is not None:
                    break
            if column is None:
                continue
            for row in rows:
                price = per_ha(row[column]) if column < len(row) else None
                if price is None:
                    continue
                # The Amplasament cell alone. Joining the row swept the price into the name —
                # "Circum.Jud. Alexandria 7.500" — and then nothing matched the register, so
                # every commune in the county came out with no extravilan at all.
                label = row[1] if len(row) > 1 else ""
                circ = EXTRA_ROW.search(label)
                if circ:
                    where = clean(circ.group(1)).strip(" .")
                    if is_local(where):
                        circuit_arable.setdefault(fold(where), price)
                else:
                    place = next((c for c in row[:3] if c and is_local(c)), None)
                    if place:
                        town_arable.setdefault(fold(place), price)

    if not rural:
        notes.append("nicio valoare rurală citită")

    communes: dict[str, dict] = {}
    for village, (letter, commune, where) in assignment.items():
        price = rural.get((letter, "A"))
        if price is None:
            continue
        entry = communes.setdefault(
            fold(commune), {"name": commune, "villages": [], "circuit": where}
        )
        entry["villages"].append({"name": village.title(), "intravilan": {"CC": price}})

    zoned = [
        {
            "name": town,
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": zones},
            "extravilan": extravilan_from(town_arable[fold(town)])
            if fold(town) in town_arable
            else {},
            "page": 1,
        }
        for town, zones in towns.items()
    ]
    entries = []
    for position, (_key, entry) in enumerate(sorted(communes.items()), start=1):
        arable = circuit_arable.get(entry["circuit"])
        entries.append(
            {
                "name": entry["name"],
                "villages": entry["villages"],
                "extravilan": extravilan_from(arable) if arable else {},
                "page": 1,
                "index": position,
            }
        )
    return zoned, entries, notes

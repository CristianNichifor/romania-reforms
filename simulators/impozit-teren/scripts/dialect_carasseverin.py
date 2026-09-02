"""Caraș-Severin, the other county this repository said had no land in its annexes.

It has all of it, on four pages, and the pieces only make sense together.

**Towns** are priced by zone, with the last two zones sharing a cell — `30/13` is zone C and
zone D, not a fraction:

    Localizare        Zona A   Zona B   Zona C/D
    Reșița               80       50      30/13
    Băile Herculane     100       55         25

**The countryside is priced by zone too, and by whether a place is a commune seat or one of
its villages** — the only county in the set to make that distinction in this shape:

    Localizare                                Zona I   Zona II   Zona III
    Comune (curți construcții)                     7         5         4
    Sate (curți construcții)                       5         4         2
    Comune/sate (alte categorii folosință)         3         2         1

**Which locality is in which zone is annex 24**, a plain list — `Armeniș I`, `Berzasca I`,
`Bolvașnița I` — with the towns' own street zoning in annexes 20 to 23, which this reader does
not need.

**Extravilan is annex 16**: eight towns named with their own arable price, `Alte localități` by
the same three zones, and then a table of ratios to arable that the chamber publishes rather
than prices — pășuni and livezi at 60%, curți-construcții at 200%, forest at 90%, fish ponds at
150%, alpine pasture at 200%, unproductive at 70%.

**Annex 15's second page is a trap.** It carries five prices in euro per square metre —
Gărâna 20, Brebu Nou 22, Crivaia 27 — and they are *tourist zones*, not the county's
localities. Reading that page as the intravilan grid would price five mountain resorts and
nothing else, at four times what the villages around them are worth.

The earlier verdict on this county was "annexes contain no land at all", from counting tables.
This document's land is in tables; the count simply looked for the word in the wrong row.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

M2_PER_HA = 10_000
ANNEX = re.compile(r"anexa\s*(\d+)", re.I)
TOWN_HEADER = re.compile(r"Localizare\s+Zona\s+A\b", re.I)
RURAL_HEADER = re.compile(r"Localizare\s+Zona\s+I\b", re.I)
SEAT_ROW = re.compile(r"^Comune\s*\(cur[țţt]i", re.I)
VILLAGE_ROW = re.compile(r"^Sate\s*\(cur[țţt]i", re.I)
OTHER_PLACES = re.compile(r"^Alte\s+localit", re.I)
ZONE_ROMAN = {"I": "A", "II": "B", "III": "C"}
# Annex 24 assigns every rural locality to one of the three zones.
ASSIGNMENT = re.compile(r"^\s*\d{1,3}\s+(.+?)\s+(I{1,3})\s*$")
# The chamber's published ratios to arable, from the extravilan annex.
FROM_ARABLE: dict[str, float] = {
    "A": 1.0,
    "P+F": 0.6,
    "V+L": 0.6,
    "PADURE": 0.9,
    "AP": 1.5,
    "NP": 0.7,
}


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def number(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    # This county writes its hectare prices unseparated — `6000`, not `6.000` — so a pattern
    # built around thousands separators rejects every extravilan figure in the document.
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{1,6}(?:,\d{1,2})?", stripped):
        return None
    value = float(stripped.replace(".", "").replace(",", "."))
    return value if 0 < value < 100_000 else None


def cells_of(text: str) -> list[float]:
    """Every price on a line, including the `30/13` that is two zones and not a fraction."""
    found: list[float] = []
    for token in clean(text).split():
        if "/" in token:
            found.extend(v for v in (number(p) for p in token.split("/")) if v is not None)
        else:
            value = number(token)
            if value is not None:
                found.append(value)
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    towns: dict[str, dict[str, float]] = {}
    seats: list[float] = []
    villages: list[float] = []
    town_arable: dict[str, float] = {}
    other_arable: list[float] = []
    zone_of: dict[str, str] = {}
    notes: list[str] = []

    for page in pages:
        text = page.get("text") or ""
        found = ANNEX.search(text[:120])
        annex = int(found.group(1)) if found else 0
        lines = [clean(line) for line in text.splitlines() if clean(line)]

        if annex == 15 and TOWN_HEADER.search(text):
            section = ""
            for line in lines:
                if TOWN_HEADER.search(line):
                    section = "town"
                    continue
                if RURAL_HEADER.search(line):
                    section = "rural"
                    continue
                values = cells_of(line)
                label = clean(re.sub(r"[\d,./]+", " ", line))
                if section == "town" and len(values) >= 3 and is_local(label):
                    towns[label] = {
                        letter: value
                        for letter, value in zip("ABCD", values, strict=False)
                    }
                elif section == "rural" and len(values) >= 3:
                    if SEAT_ROW.match(line):
                        seats = values[:3]
                    elif VILLAGE_ROW.match(line):
                        villages = values[:3]

        elif annex == 16:
            for line in lines:
                values = cells_of(line)
                label = clean(re.sub(r"[\d,./]+", " ", line))
                if OTHER_PLACES.match(line) and len(values) >= 3:
                    other_arable = values[:3]
                elif len(values) == 1 and is_local(label):
                    town_arable.setdefault(fold(label), values[0])

        elif annex == 24:
            for line in lines:
                found = ASSIGNMENT.match(line)
                if not found:
                    continue
                # "Sate Moldova Nouă, Oțelu Roșu I" names two towns' villages at once.
                for token in re.split(r",", re.sub(r"^Sate\s+", "", found.group(1))):
                    key = fold(token)
                    zone = ZONE_ROMAN.get(found.group(2).upper())
                    if len(key) > 3 and zone:
                        zone_of.setdefault(key, zone)

    if not seats or not other_arable:
        notes.append("prețurile rurale nu s-au citit")

    def extravilan_for(key: str, zone: str | None) -> dict[str, float]:
        arable = town_arable.get(key)
        if arable is None and zone and other_arable:
            arable = other_arable["ABC".index(zone)] if zone in "ABC" else None
        if arable is None:
            return {}
        return {
            code: round(arable * ratio / M2_PER_HA, 6)
            for code, ratio in FROM_ARABLE.items()
        }

    zoned = [
        {
            "name": place,
            "rank": None,
            "zones": sorted(zones),
            "intravilan": {"CC": zones},
            "extravilan": extravilan_for(fold(place), None),
            "page": 1,
        }
        for place, zones in towns.items()
    ]
    town_keys = {fold(t["name"]) for t in zoned}

    communes: list[dict] = []
    for key, zone in sorted(zone_of.items()):
        if key in town_keys or not seats:
            continue
        position = "ABC".index(zone) if zone in "ABC" else 0
        seat = seats[position] if position < len(seats) else seats[0]
        village = villages[position] if position < len(villages) else seat
        communes.append(
            {
                "name": key.title(),
                "villages": [
                    {"name": key.title(), "intravilan": {"CC": seat}},
                    {"name": f"{key.title()} (sate)", "intravilan": {"CC": village}},
                ],
                "extravilan": extravilan_for(key, zone),
                "page": 1,
            }
        )
    for index, entry in enumerate(communes, start=1):
        entry["index"] = index
    return zoned, communes, notes

"""Brăila, whose 2026 study is a covering letter with nothing attached.

`Braila_554.pdf` is one scanned page from the president of CNP Galați — *"Vă transmitem, în
anexă, Studiul de piata … aferent anului 2026"* — and the annex it transmits is not in the
chamber's index. So this reads `braila_2025.pdf`, the study those values replace, and is
registered as a 2025 grid rather than dressed up as a 2026 one. Every other county here is
2026; Brăila and Vrancea are a year behind because that is what their chamber has published.

It is a scan, read through `ocr_cache.py`, and it is a tidy one. The county is split by land
registry office, each with a pair of tables:

    Terenuri intravilane, Arondate FĂUREI      Terenuri extravilane, Arondate B.C.P.I. FĂUREI
    1  FĂUREI                    45            1  FĂUREI    33.000   15.000   20.000
       SATE ARONDATE             20            2  IANCA     40.000   15.000   20.000

**The commune and its villages are two rows, not two columns.** A locality line carries the
seat's price and the `SATE ARONDATE` line beneath it carries the villages', so the second row
belongs to whichever locality was named last.

**The extravilan table has three columns and four categories.** `AGRICOL`, then
`Neproductiv / alte categ.`, then `PĂDURE` — so pasture, hay, vines and orchards are all priced
by the middle column, at 15 000 lei/ha across the entire county. That is the document's own
grouping and not a simplification made here.

**Municipiul Brăila and Ianca are printed sideways.** Their pages are landscape scans of street
lists, and tesseract returns them as words in the right places and sentences in the wrong order.
Brăila's five zones survive that — `Zona 750`, `Zona 625` — because a zone and its price stay on
one line. Ianca's do not: its zone A and B prices sit in a street table that reads as prose, and
only its zone C and its villages come through. Ianca is priced from those, which understates it,
and it is the one locality in the county where that is true.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402
from zones import zone_labels  # noqa: E402

M2_PER_HA = 10_000

CITY_PAGE = re.compile(r"MUNICIPIUL", re.I)
INTRAVILAN_TABLE = re.compile(r"terenuri\s+intravilane|intravilane\s+din\s+localitatile", re.I)
EXTRAVILAN_TABLE = re.compile(r"terenuri\s+extravilane", re.I)

# "O Zona 750", "1 Zona 625", "A Zona + 250" — the city's zones, one to a line with its price.
# Not anchored to the end of the line: the last zone reads as `A Zona + 250 , i |`, and an
# anchor there loses the cheapest zone in the city and with it the bottom of its range.
CITY_ZONE = re.compile(r"\bZona\b[^\d]{0,12}(\d{2,4})\b", re.I)
CITY_EXTRA = re.compile(r"Extravilan[^\d]{0,20}([\d.]{4,9})", re.I)

# "1. CHISCANI, LACU SARAT 100", "2. FRECATEI comuna 10", "10 |SALCIA TUDOR 33.000 15.000 20.000"
ROW = re.compile(r"^\s*(\d{1,2})\s*[.,)]?\s*\|?\s*(.+?)\s+([\d.,\s]+)$")
VILLAGES = re.compile(r"^\s*[-|]?\s*(?:celelalalte\s+|alte\s+|Sate\s+|SATE\s+|sate\s+)*"
                      r"(?:sate|SATE|Sate)\s+(?:arondate|ARONDATE|Arondate)\s*(\d{1,4})\s*$")
# Row labels carry the rank and sometimes a village bolted on with a plus.
LABEL = re.compile(r"\s*[-–]?\s*(?:comuna|COMUNA|oras(?:ul)?|ORAS(?:UL)?)\s*$", re.I)
# `33.000` is one number and `10` is another. The grouped form has to be tried first, or the
# hectare prices come back as a 33 and an 000 and every commune price of 10 or 20 is invisible.
EXTRA_SPLIT = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def numbers(text: str) -> list[float]:
    found = []
    for token in EXTRA_SPLIT.findall(text):
        value = float(re.sub(r"[.,]", "", token))
        if 0 < value <= 200_000:
            found.append(value)
    return found


def label_of(text: str, is_local) -> str:
    """A row's locality, with its rank and whatever else the row carries removed.

    `CHISCANI, LACU SARAT` is one commune and one of its villages, and `SURDILA GĂISEANCA + sat
    FILIPESTI` is another pair, so the row is tried whole and then cut back to its first name.
    """
    name = clean(text).split("+")[0]
    name = LABEL.sub("", name)
    name = re.sub(r"[,–-]\s*(?:comuna|oras).*$", "", name, flags=re.I)
    whole = clean(name.strip(" ,.|-–"))
    if whole and is_local(whole):
        return whole
    first = clean(whole.split(",")[0].strip(" .|-–"))
    return first if first and is_local(first) else whole


def city_of(pages: list[dict], is_local) -> tuple[list[float], float | None]:
    for page in pages:
        text = page.get("text") or ""
        if not (CITY_PAGE.search(text[:400]) and "TERENURI" in text[:400]):
            continue
        if not is_local("BRAILA"):
            continue
        zones = [
            float(found.group(1))
            for found in (CITY_ZONE.search(clean(line)) for line in text.splitlines())
            if found
        ]
        extra = CITY_EXTRA.search(clean(text))
        hectare = float(re.sub(r"[.,]", "", extra.group(1))) if extra else None
        if zones:
            return sorted(zones, reverse=True), hectare
    return [], None


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    intravilan: dict[str, list[float]] = {}
    extravilan: dict[str, dict[str, float]] = {}
    notes: list[str] = []

    for page in pages:
        text = page.get("text") or ""
        head = text[:400]
        is_intra = bool(INTRAVILAN_TABLE.search(head))
        is_extra = bool(EXTRAVILAN_TABLE.search(head))
        if not (is_intra or is_extra):
            continue
        last = ""
        for line in text.splitlines():
            stripped = clean(line)
            villages = VILLAGES.match(stripped)
            if villages and last and is_intra:
                intravilan.setdefault(last, []).append(float(villages.group(1)))
                continue
            # `MOVILA MIRESII` is printed on its own line with `- comuna 12` beneath it, so a
            # line that is only a locality name names the rows that follow it.
            bare = re.sub(r"^\s*\d{1,2}\s*[.,)]?\s*\|?\s*", "", stripped)
            if is_intra and bare and not any(c.isdigit() for c in bare):
                alone = label_of(bare, is_local)
                if alone and is_local(alone):
                    last = fold(alone)
                    intravilan.setdefault(last, [])
                    continue
            headless = re.match(r"^\s*[-–|]?\s*(?:comuna|COMUNA)\s+(\d{1,4})\s*$", stripped)
            if headless and last and is_intra:
                intravilan.setdefault(last, []).insert(0, float(headless.group(1)))
                continue
            row = ROW.match(stripped)
            if not row:
                continue
            place = label_of(row.group(2), is_local)
            if not place or not is_local(place):
                continue
            values = numbers(row.group(3))
            if not values:
                continue
            key = fold(place)
            if is_intra:
                intravilan.setdefault(key, []).append(values[0])
                last = key
            elif len(values) >= 3:
                # AGRICOL, then the column the document heads `Neproductiv / alte categ.`,
                # then PĂDURE. Pasture, hay, vines and orchards have no column of their own.
                arable, other, forest = values[0], values[1], values[2]
                extravilan[key] = {
                    "A": arable / M2_PER_HA,
                    "NP": other / M2_PER_HA,
                    "P+F": other / M2_PER_HA,
                    "V+L": other / M2_PER_HA,
                    "PADURE": forest / M2_PER_HA,
                }

    city_zones, city_hectare = city_of(pages, is_local)
    if city_zones:
        intravilan[fold("BRAILA")] = city_zones
        if city_hectare:
            extravilan.setdefault(
                fold("BRAILA"), {"A": city_hectare / M2_PER_HA}
            )
    else:
        notes.append("municipiul Brăila nu s-a citit")
    if not extravilan:
        notes.append("nicio valoare extravilană citită")

    zoned = []
    communes = []
    for key, prices in sorted(intravilan.items()):
        rates = extravilan.get(key, {})
        if key == fold("BRAILA"):
            zoned.append(
                {
                    "name": "BRAILA",
                    "rank": None,
                    "zones": zone_labels(len(prices)),
                    "intravilan": {
                        "CC": dict(zip(zone_labels(len(prices)), prices, strict=False))
                    },
                    "extravilan": rates,
                    "page": 23,
                }
            )
            continue
        communes.append(
            {
                "name": key.title(),
                "villages": [
                    {
                        "name": key.title() if not offset else f"{key.title()} ({offset + 1})",
                        "intravilan": {"CC": price},
                    }
                    for offset, price in enumerate(prices)
                ],
                "extravilan": rates,
                "page": 33,
            }
        )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    return zoned, communes, notes

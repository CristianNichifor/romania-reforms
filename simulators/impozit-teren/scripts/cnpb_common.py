"""What the București chamber does the same way in every county, and what it does not.

Its four southern counties share one 596-page volume, and each of the four is laid out
differently inside it — different section numbering, different table shapes, different places
to hide the category assignment. What they *do* share is a set of conventions the chamber
applies everywhere, and those belong in one place rather than copied into four readers:

* **Extravilan is one arable price and seven published multipliers.** The chamber prices arable
  land per locality and states what every other category is worth as a ratio of it. The same
  table appears in Călărași, Giurgiu, Ialomița and Teleorman, and in Ilfov, and it is the
  chamber's arithmetic rather than this repository's.
* **Land under a building is 70% of free land.** *"Pentru terenurile ocupate de constructii
  valorile inscrise in tabele se diminueaza cu 30%."* The tables print free land; the hectares
  this simulator prices are the register's *Ocupată cu construcții*. Not every county in the
  volume prints the sentence, so it is applied only where it is found.
* **Prices are euro**, per square metre for intravilan and per hectare for extravilan, with a
  decimal comma and a thousands dot.

Kept deliberately small. The temptation with four counties from one chamber is to write one
reader with four modes; that was resisted because the differences are not modes but layouts —
Călărași's assignment is prose and Giurgiu's is a table, and no flag makes those the same code.
"""

from __future__ import annotations

import re
import unicodedata

# The chamber's published corrections, from the table headed "CORECTII SUPLIMENTARE APLICATE
# TERENURILOR EXTRATRAVILANE" — identical in all four counties of the volume and in Ilfov.
FROM_ARABLE: dict[str, float] = {
    "A": 1.0,
    "V+L": 1.1,
    "P+F": 0.8,
    "AP": 1.4,
    "DR": 0.7,
    "NP": 0.5,
}
OCCUPIED_SHARE = 0.70
M2_PER_HA = 10_000

# "Categoria I", "Categoria I-a", "Categoria a II-a" — Romanian writes the ordinal both ways
# and the same table uses both. A pattern without the optional "a" matched the first category
# and not the second, which priced every locality of the second at nothing.
CATEGORY = re.compile(r"Categoria\s+(?:a\s+)?([IVX]+)\s*(?:-\s*a)?\b", re.I)
ROMAN = {"I": "A", "II": "B", "III": "C", "IV": "D", "V": "E", "VI": "F"}
# The contents pages repeat every heading verbatim with dot leaders and a page number, and they
# come first — a scan keeping the first match of a heading finds the index, not the section.
DOT_LEADER = re.compile(r"\.{4,}")
COUNTY_HEADER = re.compile(
    r"valorile minime imobiliare [îi]n jud\.\s*([A-Za-zăâîșțĂÂÎȘȚ]+)", re.I
)


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def fold(name: str) -> str:
    """A join key: the same locality is spelled differently in two tables three pages apart."""
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def zone_letter(label: str) -> str | None:
    """The category letter a column header names, or None if it names no category."""
    found = CATEGORY.search(label or "")
    return ROMAN.get(found.group(1).upper(), found.group(1).upper()) if found else None


def per_m2(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:,\d{1,2})?", stripped):
        return None
    value = float(stripped.replace(",", "."))
    return value if 0 < value < 1_000 else None


def per_ha(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", stripped):
        return None
    value = float(stripped.replace(".", ""))
    return value if 100 <= value < 1_000_000 else None


def county_pages(pages: list[dict], county: str) -> list[int]:
    """The pages of one county inside the four-county volume, by their running header."""
    wanted = fold(county)
    return [
        index
        for index, page in enumerate(pages, start=1)
        if (found := COUNTY_HEADER.search(page.get("text") or ""))
        and fold(found.group(1)) == wanted
    ]


def extravilan_from(arable: float) -> dict[str, float]:
    """The whole extravilan grid for one locality, in euro per square metre.

    Per square metre because that is the unit the value builder multiplies by hectares. The
    annexes print euro per hectare. Getting this backwards valued one county at 20 727 mld EUR
    with full coverage and no warning, so the conversion lives here rather than in each reader.
    """
    return {
        code: round(arable * ratio / M2_PER_HA, 6) for code, ratio in FROM_ARABLE.items()
    }


def names_in(text: str, is_local) -> list[str]:
    """The localities named in a header cell, longest run of words first.

    "Teren Calarasi" is one town and a noun; "Lehliu Gara Fundulea" is two towns, one of them
    two words. Splitting on whitespace finds Fundulea and loses Lehliu-Gara; taking the whole
    cell finds neither. So consecutive runs are offered to the register longest-first and a
    match consumes the words it used.
    """
    words = [w for w in re.split(r"[\s,]+", clean(text)) if w]
    found: list[str] = []
    position = 0
    while position < len(words):
        for length in range(min(3, len(words) - position), 0, -1):
            candidate = " ".join(words[position : position + length])
            if is_local(candidate):
                found.append(candidate)
                position += length
                break
        else:
            position += 1
    return found

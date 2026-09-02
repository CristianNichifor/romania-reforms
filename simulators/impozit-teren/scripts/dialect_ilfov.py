"""Ilfov, where the whole extravilan grid is one column and seven published coefficients.

Ilfov is the ring around Bucharest and the last county the national estimate had to leave out,
on the grounds that its land is priced by a city that is not in it. Its chamber — the București
one, publishing on `srv.cnpb.ro` rather than through unnpr.ro — gives it one annex per locality
for all 40 UATs.

**Intravilan** sits at the foot of each locality's annex, four rows and two columns:

                            TEREN LIBER:   TEREN OCUPAT:
    Zona CENTRALA:                 44,8            31,4
    Zona MEDIANA:                  36,7            25,7
    Zona PERIFERICA:               23,0            16,1
    In AFARA localitatii:          18,2            12,7

The study's own methodology names those four zones A, B, C and D, so they are emitted as such
rather than under the labels the annex prints. The column taken is TEREN OCUPAT, because the
hectares being priced are the land register's *Ocupată cu construcții*; TEREN LIBER is carried
in the same table for anyone who wants the redevelopment reading.

**Extravilan is a single arable column and a table of ratios.** The study prices arable land
per locality, in EUR/ha, and then states outright what every other category is worth:

    Curți-construcții                      1,5 × arabil
    Vii sau Livezi                         1,1 × arabil
    Pășuni, Fânețe                         0,8 × arabil
    Amenajări piscicole                    1,4 × arabil
    Drumuri tehnologice și de exploatare   0,7 × arabil
    Terenuri neproductive                  0,5 × arabil

So one number per locality yields the whole extravilan grid, and the coefficients are the
chamber's own rather than this repository's. Forest is the exception and has a table of its
own, by species, county-wide.

**Arable is priced twice, by distance from a road.** *Plan I* is land within 100 m of a
modernised road and *Plan II* is everything beyond it. Plan II is taken, because it is where
most of a county's hectares are and because it is the lower of the two; Plan I is carried
alongside. The difference is not small — Voluntari is 57 900 EUR/ha on the first plan and
40 500 on the second.

**The extravilan table prints two localities side by side.** Left names at x≈53 with values at
215 and 260, right names at x≈314 with values at 476 and 521, so a line reads
`BRAGADIRU 26.600 18.600 GANEASA 15.100 10.600` and is two different communes. Split by x, as
in Timiș — this is the third document here to interleave columns on a line.

**Ilfov's farmland is not farmland priced as farmland.** Arable runs 11 200 to 57 900 EUR/ha
against a national median near 5 900. That is not an error to correct; it is what land costs
in the ring around a capital, and it is the reason this county could never have been predicted
from the size of its largest town.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# "ANEXA 9 - Localitatea: 1 DECEMBRIE", "ANEXA 8.4 - Orasul: VOLUNTARI"
ANNEX = re.compile(
    r"ANEXA\s+[\d.]+\s*[-–]\s*(?:Localitatea|Orasul|Ora[șş]ul|Comuna)\s*:\s*(.+?)\s*$",
    re.I | re.M,
)
# The four rows of the intravilan block, in the study's own order, against the zone letters
# its methodology assigns them.
ZONE_ROWS: list[tuple[str, re.Pattern[str]]] = [
    ("A", re.compile(r"Zona\s+CENTRALA", re.I)),
    ("B", re.compile(r"Zona\s+MEDIANA", re.I)),
    ("C", re.compile(r"Zona\s+PERIFERICA", re.I)),
    ("D", re.compile(r"[ÎI]n\s+AFARA\s+localitatii", re.I)),
]
LAND_BLOCK = re.compile(r"TEREN\s+LIBER\s*:", re.I)
# Intravilan prices are euro per square metre with a decimal comma: "44,8".
PER_M2 = re.compile(r"^\d{1,3}(?:,\d{1,2})?$")
# Extravilan prices are euro per hectare with a thousands dot: "26.600".
PER_HA = re.compile(r"^\d{1,3}(?:\.\d{3})+$")

EXTRA_TABLE = re.compile(r"SITUATE\s+IN\s+EXTRAVILAN", re.I)
FOREST_TABLE = re.compile(r"UNUI\s+HECTAR\s+DE\s+TEREN\s+CU\s+VEGETATIE\s+FORESTIERA", re.I)
# The chamber's own multipliers, published as a table of corrections rather than as prices.
# Kept as data because they are the document's, not this repository's.
FROM_ARABLE: dict[str, float] = {
    "A": 1.0,
    "V+L": 1.1,
    "P+F": 0.8,
    "AP": 1.4,
    "DR": 0.7,
    "NP": 0.5,
}
M2_PER_HA = 10_000
# Where the left half of the two-column extravilan table ends.
COLUMN_SPLIT = 300.0
# What is *not* part of a name: the prices, and the column headings the table repeats. A name
# is then whatever is left on that half of the row. Requiring each token to look like a name —
# capital letter, three or more characters — silently dropped "1 DECEMBRIE" for starting with
# a digit and "ȘTEFĂNEȘTII DE JOS" for containing a two-letter word, and the loss showed up
# only as three communes with no arable price rather than as anything failing.
NOT_A_NAME = re.compile(r"^(?:Plan|I|II|LOCALITATEA|TEREN|ARABIL|EUR/ha)$", re.I)


def rows_of(words: list, tolerance: float = 3.0) -> list[tuple[float, list]]:
    ordered = sorted(words, key=lambda w: (w[3], w[1]))
    grouped: list[tuple[float, list]] = []
    for word in ordered:
        if grouped and abs(word[3] - grouped[-1][0]) <= tolerance:
            grouped[-1][1].append(word)
        else:
            grouped.append((word[3], [word]))
    return [(top, sorted(items, key=lambda w: w[1])) for top, items in grouped]


def fold(name: str) -> str:
    """A join key for the two tables, which do not spell a locality the same way.

    The annex heading and the extravilan table are typeset separately and disagree about
    hyphens, diacritics and spacing — "DRAGOMIRESTI - VALE" against "Dragomirești-Vale" — so
    matching on the printed string joined 39 localities of 40 and left the fortieth with no
    arable price and no complaint.
    """
    stripped = unicodedata.normalize("NFKD", name)
    return re.sub(r"[^A-Z0-9]", "", stripped.upper())


def per_m2(text: str) -> float | None:
    if not PER_M2.match(text or ""):
        return None
    value = float(text.replace(",", "."))
    return value if 0 < value < 1_000 else None


def per_ha(text: str) -> float | None:
    if not PER_HA.match(text or ""):
        return None
    value = float(text.replace(".", ""))
    return value if 100 <= value < 1_000_000 else None


def read_intravilan(page: dict) -> list[float]:
    """Every occupied-land price on one annex page, in euro per square metre.

    Not keyed by the zone the annex prints, because the annexes disagree about where that
    label lives. A commune's four zones are four rows, each carrying its own label and its own
    pair of prices. A town's zones are one *page* each — `ANEXA 8.1` to `8.4` for Voluntari —
    with the zone named once in the middle of the page and the rows underneath split by
    landmark instead:

        ZONA CENTRALA   la Est de Autostrada A3 …    167,9   117,5
                        la Vest de Autostrada A3 …   308,2   215,8

    So Voluntari has six prices across four pages, not four across one, and the dearest is
    nearly twice the next. A reader keyed on the row label finds nothing on those pages; one
    that stops at the first page of a locality keeps a sixth of the town.

    The pair is also not reliably on one baseline — `167,9` and `117,5` are three points apart
    and belong to the same row — so the columns are found from the header instead: anything
    right of the midpoint between `TEREN LIBER:` and `TEREN OCUPAT:`, and below them, is an
    occupied price. Below matters: the building tables above carry five numbers a row, two of
    which fall on the right of that midpoint.
    """
    words = page.get("words") or []
    free = next((w for w in words if w[0].upper().startswith("LIBER")), None)
    occupied = next((w for w in words if w[0].upper().startswith("OCUPAT")), None)
    if not free or not occupied:
        return []
    midpoint = (free[1] + occupied[1]) / 2
    floor = min(free[3], occupied[3])
    # The note under the table repeats "EURO/mp" and nothing below it is a price.
    ceiling = min(
        (w[3] for w in words if w[0].upper().startswith("NOTA")), default=float("inf")
    )
    return [
        value
        for w in words
        if w[1] > midpoint
        and floor < w[3] < ceiling
        and (value := per_m2(w[0])) is not None
    ]


def read_extravilan(pages: list[dict], is_local) -> dict[str, float]:
    """Arable EUR/ha per locality, from the two-column annex, on the second plan."""
    found: dict[str, float] = {}
    for page in pages:
        if not EXTRA_TABLE.search(page.get("text") or ""):
            continue
        for _top, items in rows_of(page.get("words") or []):
            for lo, hi in ((0.0, COLUMN_SPLIT), (COLUMN_SPLIT, 1e4)):
                half = [w for w in items if lo <= w[1] < hi]
                # No length floor: "1 DECEMBRIE" is a commune whose first token is one
                # character, and requiring two dropped it. The hyphen in "DRAGOMIREȘTI - VALE"
                # is tokenised apart by the extractor and rejoined here, or the name never
                # matches the register's "DRAGOMIRESTI-VALE".
                name = re.sub(
                    r"\s*-\s*",
                    "-",
                    " ".join(
                        w[0]
                        for w in half
                        if per_ha(w[0]) is None and not NOT_A_NAME.match(w[0])
                    ),
                ).strip()
                values = [v for v in (per_ha(w[0]) for w in half) if v is not None]
                # Plan I then Plan II; the second is where most of a county's hectares are.
                if len(values) == 2 and name and is_local(name):
                    found.setdefault(fold(name), values[1])
    return found


def read_forest(pages: list[dict]) -> float | None:
    """One county-wide forest price, from the species table.

    The median of the species listed rather than a pick: Ilfov's woodland is lowland mixed and
    the table runs from 4 000 for unnamed broadleaf to 9 000 for oak, with no areas to weight
    them by. Naming one species would be choosing the answer.
    """
    for page in pages:
        if not FOREST_TABLE.search(page.get("text") or ""):
            continue
        prices = sorted(
            v
            for _top, items in rows_of(page.get("words") or [])
            for v in (per_ha(w[0]) for w in items)
            if v is not None and 1_000 <= v <= 50_000
        )
        if prices:
            middle = len(prices) // 2
            return (
                prices[middle]
                if len(prices) % 2
                else (prices[middle - 1] + prices[middle]) / 2
            )
    return None


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    notes: list[str] = []

    arable = read_extravilan(pages, is_local)
    forest = read_forest(pages)

    # Prices first, merged across every annex page a locality has, and only then turned into
    # zones. A town is four pages and a commune is one, so nothing can be decided page by page.
    found: dict[str, list[float]] = {}
    where: dict[str, int] = {}
    for index, page in enumerate(pages, start=1):
        heading = ANNEX.search(page.get("text") or "")
        if not heading:
            continue
        locality = re.sub(r"\s+", " ", heading.group(1)).strip()
        if not is_local(locality):
            continue
        prices = read_intravilan(page)
        if prices:
            found.setdefault(locality, []).extend(prices)
            where.setdefault(locality, index)

    towns: list[dict] = []
    for locality, prices in found.items():
        # Dearest first, which is what a zone letter means everywhere else in this repository.
        # The annex's own labels — CENTRALA, MEDIANA, PERIFERICA, and the landmark splits
        # inside them — do not fit six values into four letters, and ordering by price says
        # the same thing without inventing a hierarchy the document does not print.
        ordered = sorted({round(v, 2) for v in prices}, reverse=True)[:6]
        zones = {chr(ord("A") + position): value for position, value in enumerate(ordered)}

        # Per square metre, because that is the unit the value builder multiplies by hectares.
        # This annex prints EUR/ha, so it is divided; Vaslui's annex prints per square metre
        # and needed nothing. Getting it wrong is not subtle in its effect and is completely
        # silent in its symptoms — the first run of this reader valued Ilfov at 20 727 mld EUR
        # with 100% coverage, every name matched and no warning anywhere.
        extravilan: dict[str, float] = {}
        price = arable.get(fold(locality))
        if price:
            extravilan = {
                code: round(price * ratio / M2_PER_HA, 6)
                for code, ratio in FROM_ARABLE.items()
            }
        if forest:
            extravilan["PADURE"] = round(forest / M2_PER_HA, 6)

        towns.append(
            {
                "name": locality.title(),
                "rank": None,
                "zones": sorted(zones),
                "intravilan": {"CC": zones},
                "extravilan": extravilan,
                "page": where[locality],
            }
        )

    priced = sum(1 for t in towns if t["extravilan"].get("A"))
    if priced < len(towns):
        notes.append(f"{len(towns) - priced} localități fără preț arabil în anexa extravilanului")
    return towns, [], notes

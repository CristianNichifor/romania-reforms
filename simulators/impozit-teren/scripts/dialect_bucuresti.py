"""București, which is one locality with 275 zones instead of a county with 275 localities.

Every other reader here answers "what is each commune worth". This one answers "what is each
part of one city worth", because the capital is a single administrative unit — SIRUTA 179132,
23 787 hectares, one row in the land register — priced by the chamber across 59 cadastral
zones subdivided into 275 subzones, from 47 EUR/m² on the eastern edge to 1 745 in the north.

**The document is on the chamber's own server, not on unnpr.ro.** This repository previously
recorded that the București chamber publishes nothing, which was wrong: `srv.cnpb.ro` carries
studies for all six of its counties and unnpr.ro simply does not index it. That server also
omits the intermediate certificate that signs its own, which is what `tls_chain.py` is for.

**There are no ruling lines, so this reads word coordinates.** The five price columns sit at
stable x positions and the row label at the left:

    ZONA@65  4-A3@103   384@179   269@240   188@322   422@411   346@498
             ↑ label    liber     ocupat    alei      comercial industrial

**A value row binds to the nearest label, not to the one on its own line.** Digits and letters
sit on slightly different baselines — `ZONA 25-A2` is at 310,7 and its prices at 308,7, *above*
it — and two subzones carry a label that wraps onto a second line, pushing their prices below:

    ZONA 25-A3 la NORD de        649 …
    CF București - Băneasa
    ZONA 25-A3 la SUD de       1 350 …
    CF București - Băneasa

So zones 25-A3 and 25-B3 are each split by the Băneasa railway and priced twice, and south of
the line is worth **twice** what north of it is. Reading by line, or assuming one row per
label, loses that and silently prices half of two zones at the cheaper figure.

**The column taken is TEREN OCUPAT DE CONSTRUCTII, not TEREN LIBER.** The hectares being
priced are the land register's *Ocupată cu construcții* — land with a building on it — and
that is the column for it. TEREN LIBER is exactly 1/0,70 higher and is the right column for a
redevelopment reading; it is carried in the output so anyone who wants that can have it
without re-reading the PDF.

**The grid is one number and four coefficients.** Every row satisfies

    ocupat = 0,70 × liber      alei = 0,49 × liber
    comercial = 1,10 × liber   industrial = 0,90 × liber

to the rounding, on all 275 rows. So the chamber does not price commercial land by observing
commercial land; it applies a coefficient. Worth knowing before anyone reads that column as a
market signal — and useful here, because it makes every row self-checking.

**What this does not read.** The study prices no extravilan land at all, so Bucharest's 2 566
hectares of arable, 611 of forest and 908 of water go unpriced and are reported as the gap
they are. It prices roads per zone — 3 306 hectares of the city — but the pipeline carries one
extravilan figure per code rather than a zoned one, and inventing a single median road price
would be worse than leaving it out.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# The page carries both, and both are needed: the same volume prices parking spaces and
# apartments in tables of the same shape.
UNIT = re.compile(r"Valori\s+in\s+EUR/mp", re.I)
LAND_PAGE = re.compile(r"TERENURI\s+INTRAVILANE", re.I)
# "ZONA 4-A3", "ZONA 25-A3 la NORD de". The label always begins at the far left.
LABEL = re.compile(r"^ZONA\s*$", re.I)
SUBZONE = re.compile(r"^(\d{1,3})\s*-\s*([AB])(\d)$")
NORTH = re.compile(r"NORD", re.I)
SOUTH = re.compile(r"SUD", re.I)
# The label column ends well before the first price column, which starts near x=175.
LABEL_EDGE = 172.0
# Prices are whole euros with a thousands dot: "1.350" is 1350.
NUMBER = re.compile(r"^\d{1,3}(?:\.\d{3})*$")
# The four coefficients the chamber applies to TEREN LIBER, used to check every row it reads.
COEFFICIENTS = (1.0, 0.70, 0.49, 1.10, 0.90)
# Two euro a square metre would be a village and two thousand is the dearest land in Romania;
# outside that the row is not a price row.
FLOOR, CEILING = 2.0, 5_000.0


def number(text: str) -> float | None:
    if not NUMBER.match(text or ""):
        return None
    value = float(text.replace(".", ""))
    return value if FLOOR <= value <= CEILING else None


def rows_of(words: list) -> list[tuple[float, list]]:
    """Words grouped into rows by proximity, not by a fixed grid.

    Same reason as Timiș: a digit's baseline sits a point or two off a letter's, so bucketing
    by a rounded coordinate splits a row's label from its own prices. Three points is under
    half the gap between rows, which are twenty-one apart.
    """
    ordered = sorted(words, key=lambda w: (w[3], w[1]))
    grouped: list[tuple[float, list]] = []
    for word in ordered:
        if grouped and abs(word[3] - grouped[-1][0]) <= 3.0:
            grouped[-1][1].append(word)
        else:
            grouped.append((word[3], [word]))
    return [(top, sorted(items, key=lambda w: w[1])) for top, items in grouped]


def read_page(page: dict) -> list[tuple[str, list[float]]]:
    """(subzone, five prices) for one page of the grid."""
    words = page.get("words") or []
    if not words:
        return []
    labels: list[tuple[float, str]] = []
    prices: list[tuple[float, list[float]]] = []

    for top, items in rows_of(words):
        left = [w for w in items if w[1] < LABEL_EDGE]
        right = [w for w in items if w[1] >= LABEL_EDGE]
        text = " ".join(w[0] for w in left)
        found = next((SUBZONE.match(w[0]) for w in left if SUBZONE.match(w[0])), None)
        if found and any(LABEL.match(w[0]) for w in left):
            zone = f"{found.group(1)}-{found.group(2)}{found.group(3)}"
            # A zone split by a landmark is two zones with two prices, and which side must
            # survive into the key or half of it is priced at the other half's figure.
            if NORTH.search(text):
                zone += " N"
            elif SOUTH.search(text):
                zone += " S"
            labels.append((top, zone))
        values = [v for v in (number(w[0]) for w in right) if v is not None]
        if len(values) == 5:
            prices.append((top, values))

    # Each price row to the nearest label that has not already taken one. Nearest rather than
    # "the label above", because the offset goes both ways: a one-line label sits *below* its
    # own prices and a wrapped one sits above them.
    taken: set[int] = set()
    found_rows: list[tuple[str, list[float]]] = []
    for top, values in prices:
        best = None
        for index, (label_top, zone) in enumerate(labels):
            if index in taken:
                continue
            distance = abs(label_top - top)
            if best is None or distance < best[0]:
                best = (distance, index, zone)
        # Half a row's spacing. Beyond that the pairing is a guess, and a mispaired row is a
        # zone priced at its neighbour's figure with nothing to show for it.
        if best and best[0] <= 10.0:
            taken.add(best[1])
            found_rows.append((best[2], values))
    return found_rows


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    zones: dict[str, float] = {}
    free: dict[str, float] = {}
    notes: list[str] = []
    off_pattern = 0

    for page in pages:
        text = page.get("text") or ""
        if not (UNIT.search(text) and LAND_PAGE.search(text)):
            continue
        for zone, values in read_page(page):
            # Every row is checkable against the chamber's own coefficients, so a row that
            # does not satisfy them was misread — a column shifted, a label mispaired — and is
            # dropped rather than published. Nothing else here can tell a wrong price from a
            # right one.
            liber = values[0]
            if any(
                abs(values[i] - liber * c) > max(1.0, liber * c * 0.01)
                for i, c in enumerate(COEFFICIENTS)
            ):
                off_pattern += 1
                continue
            zones.setdefault(zone, values[1])
            free.setdefault(zone, liber)

    if off_pattern:
        notes.append(f"{off_pattern} rânduri nu respectă coeficienții grilei și au fost lăsate")
    if not zones:
        return [], [], ["no price rows parsed"]

    town = {
        "name": "București",
        "rank": "municipii",
        "zones": sorted(zones),
        "intravilan": {"CC": zones},
        # The study prices no extravilan land anywhere in its 457 pages.
        "extravilan": {},
        "page": 1,
    }
    return [town], [], notes

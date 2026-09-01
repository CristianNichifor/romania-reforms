"""The CNP Iași dialect: a price per *kind* of village, and a kind for every village.

Bacău prints a price against each village and Alba prints one against each merged block. Iași
does something different and, for a reader, much better: it sorts every village in the county
into one of thirteen tiers — APP, AP, A through L — publishes one price table for the tiers,
and then lists which tier each village is in.

    tier table   APP  intravilan 59 €/m² · arabil 9 · pășuni 5,50 · vii 6,00
                 ...
                 L    intravilan  4 €/m² · arabil 0,51 · pășuni 0,48 · vii 0,55

    mapping      3. ARONEANU     1. ARONEANU    A
                                 2. Dorobanţ    AP
                                 3. Rediu Aldei D

So the county's whole rural grid is thirteen rows and a list, and every village comes out with
a full set of categories rather than the partial rows the other chambers print. The tier table
is read as a table; the mapping is read from the flattened text, where it is unambiguous.

Towns are priced separately and conventionally — zone A to D in euro per square metre, with a
single lumped value for the villages attached to them.

**One thing the tiers cost.** A commune's villages can sit in different tiers, and they usually
do: Aroneanu is A, its neighbour Dorobanț is AP, and Rediu Aldei is D. Intravilan prices are
therefore genuinely per village, which is what this simulator wants. Extravilan is not — the
shared model carries one set per commune — so the commune's seat decides it, the seat being the
village the study numbers first and prints in capitals.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# The tier table's columns, after the tier letter itself. "Alte categorii" is intravilan land
# that is not building land; the shared vocabulary has no code for it, so it is read and
# dropped rather than folded onto a neighbour.
TIER_COLUMNS: list[str | None] = [None, "CC", "A", "P+F", "V+L", "PADURE"]
TIERS = re.compile(r"^(APP|AP|[A-L])$")

# "1. ALEXANDRU I. CUZA   1. ALEXANDRU I CUZA   D" — commune, its first village and the tier,
# all on one line; then the rest of its villages one per line without the commune.
COMMUNE_AND_VILLAGE = re.compile(
    r"^\s*(\d{1,3})\.\s*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \.\-]{2,}?)\s+"
    r"(\d{1,3})\.\s*(.+?)\s+(APP|AP|[A-L])\s*$"
)
VILLAGE_ONLY = re.compile(r"^\s*(\d{1,3})\.\s*(.+?)\s+(APP|AP|[A-L])\s*$")
# Most communes share a line with their first village; seven in the county do not, and print
# their name alone before the list starts.
COMMUNE_ONLY = re.compile(r"^\s*(\d{1,3})\.\s*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \.\-]{2,})\s*$")

TOWN_HEAD = re.compile(r"^\s*(MUNICIPIUL|ORA[ŞS])\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]*?)\s*$")
ZONE_ROW = re.compile(r"^\s*\d+\s+([A-D])\s+([\d.,]+)\s*$")
EXTRA_ROW = re.compile(r"^\s*\d+\s+extravilan\s*([^\d]*?)\s+([\d.,]+)\s*$", re.I)
SUBURB_ROW = re.compile(r"^\s*\d+\s+intravilan[^\d]*?\s+([\d.,]+)\s*$", re.I)
ZONES = ["A", "B", "C", "D"]


def number(text: str) -> float | None:
    cleaned = text.strip().replace(" ", "")
    if not re.fullmatch(r"\d+([.,]\d+)?", cleaned):
        return None
    return float(cleaned.replace(",", "."))


def read_tiers(pages: list[dict]) -> dict[str, dict[str, float]]:
    """The thirteen-row price table, which is the whole rural grid of the county."""
    for page in pages:
        for table in page["tables"]:
            # Whitespace-normalised: the captions wrap inside their cells, so "Curti
            # constructii" arrives with a newline in the middle of it.
            flat = re.sub(r"\s+", " ", " ".join(c for row in table["cells"][:2] for c in row))
            if "Tipul localitatii" not in flat or "Curti constructii" not in flat:
                continue
            tiers: dict[str, dict[str, float]] = {}
            for row in table["cells"]:
                cells = [c.strip() for c in row]
                if not cells or not TIERS.match(cells[0]):
                    continue
                values = {}
                for column, cell in zip(TIER_COLUMNS, cells[1:], strict=False):
                    value = number(cell)
                    if column and value is not None:
                        values[column] = value
                if "CC" in values:
                    tiers[cells[0]] = values
            if len(tiers) >= 8:
                return tiers
    return {}


def read_mapping(pages: list[dict]) -> list[dict]:
    """Which tier each village is in, read from the flattened text.

    Read as text rather than as a table because the list is not ruled: the commune sits in the
    same visual column as its first village and the tier letter trails at the end of the line,
    which a cell extractor turns into a column of blanks and a column of letters with nothing
    tying them together.
    """
    communes: list[dict] = []
    current: dict | None = None
    for index, page in enumerate(pages):
        for line in page["text"].splitlines():
            both = COMMUNE_AND_VILLAGE.match(line)
            if both:
                current = {
                    "index": int(both.group(1)),
                    "name": re.sub(r"\s+", " ", both.group(2)).strip(" .-"),
                    "villages": [],
                    "page": index + 1,
                }
                communes.append(current)
                current["villages"].append(
                    {"name": re.sub(r"\s+", " ", both.group(4)).strip(), "tier": both.group(5)}
                )
                continue
            alone = COMMUNE_ONLY.match(line)
            if alone:
                current = {
                    "index": int(alone.group(1)),
                    "name": re.sub(r"\s+", " ", alone.group(2)).strip(" .-"),
                    "villages": [],
                    "page": index + 1,
                }
                communes.append(current)
                continue
            one = VILLAGE_ONLY.match(line)
            if one and current is not None:
                name = re.sub(r"\s+", " ", one.group(2)).strip()
                # A tier letter can end a line that is not a village at all; a name of one or
                # two characters is punctuation that survived, not a place.
                if len(name.replace(" ", "")) >= 3:
                    current["villages"].append({"name": name, "tier": one.group(3)})
    return [c for c in communes if c["villages"]]


def read_towns(pages: list[dict]) -> list[dict]:
    """Towns, priced by zone in euro per square metre, with their own extravilan lines."""
    towns: list[dict] = []
    pending = ""
    found_on = 1
    zones: dict[str, float] = {}
    extravilan: dict[str, float] = {}

    def flush() -> None:
        nonlocal pending, zones, extravilan
        if pending and zones:
            towns.append(
                {
                    "name": pending,
                    "rank": None,
                    "zones": [z for z in ZONES if z in zones],
                    "intravilan": {"CC": {z: zones[z] for z in ZONES if z in zones}},
                    "extravilan": dict(extravilan),
                    "page": found_on,
                }
            )
        pending, zones, extravilan = "", {}, {}

    for index, page in enumerate(pages):
        for line in page["text"].splitlines():
            head = TOWN_HEAD.match(line)
            if head:
                flush()
                pending = re.sub(r"\s+", " ", head.group(2)).strip(" .-")
                found_on = index + 1
                continue
            zone = ZONE_ROW.match(line)
            if zone and pending:
                value = number(zone.group(2))
                if value is not None:
                    zones.setdefault(zone.group(1), value)
                continue
            extra = EXTRA_ROW.match(line)
            if extra and pending:
                value = number(extra.group(2))
                if value is None:
                    continue
                label = extra.group(1).lower()
                # "extravilan" alone means every category at one price.
                codes = (
                    ["A"] if "arabil" in label
                    else ["P+F"] if "pasun" in label or "păşun" in label or "fine" in label
                    else ["A", "P+F", "V+L"] if not label.strip()
                    else []
                )
                for code in codes:
                    extravilan.setdefault(code, value)
    flush()
    return towns


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    tiers = read_tiers(pages)
    problems: list[str] = []
    if not tiers:
        return [], [], ["the tier price table did not parse"]

    towns = read_towns(pages)
    communes = []
    for entry in read_mapping(pages):
        if not is_local(entry["name"]):
            continue
        villages = []
        for village in entry["villages"]:
            prices = tiers.get(village["tier"])
            if prices:
                villages.append({"name": village["name"], "intravilan": {"CC": prices["CC"]}})
        if not villages:
            continue
        # The seat's tier decides the commune's extravilan: the shared model carries one set
        # per commune, and the seat is the village the study numbers first.
        seat = tiers.get(entry["villages"][0]["tier"], {})
        communes.append(
            {
                "index": entry["index"],
                "name": entry["name"],
                "villages": villages,
                "extravilan": {
                    k: v for k, v in seat.items() if k in ("A", "P+F", "V+L", "PADURE")
                },
                "page": entry["page"],
            }
        )
    return towns, communes, problems

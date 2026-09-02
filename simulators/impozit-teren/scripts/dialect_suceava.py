"""Suceava, which this repository wrote off and should not have.

The earlier verdict was "42 land tables for 114 localities, ceiling 37%" — arrived at by
counting tables. That is the wrong question, and it is the same measurement that would have
written off Ialomița, whose study contains **no land table at all** and reads at 100% because
its prices are prose. Counting tables asks how the document is typeset. What matters is whether
it says which localities each price applies to, and Suceava says so twice over.

**The countryside is priced in buckets that name their own members, with a catch-all.**

    MEDIUL RURAL 1
    (piața specifică pentru localitățile : ȘCHEIA, SF.ILIE, MOARA NICA, BULAI, FRUMOASA,
     IPOTEȘTI, TIȘĂUȚI, LISAURA, PLOPENI, PRELIPCA, BOSANCI, MITOCUL DRAGOMIRNEI,
     MIHOVENI, DUMBRĂVENI)

    MEDIUL RURAL 2
    (excepție localitățile: ȘCHEIA, SF.ILIE, … )

Between them those two cover every rural locality of the circumscription by construction: one
is a list and the other is its complement. That is an assignment, not a gap.

**And the study publishes its own circumscription rosters**, numbered, under Municipii / Orașe /
Comune, citing HG 1217/2023. So the complement can be resolved without leaving the document —
the repository's `arondare-2023.json` says the same thing and is kept as a cross-check rather
than as the source.

**Towns are priced individually and in more detail than most chambers manage**: building land
by zone *and by plot size*, other intravilan categories by zone, and a full extravilan table.

    TEREN INTRAVILAN - CURȚI CONSTRUCȚII, LEI/MP
    ZONA    S ≤ 300 mp   300 < S ≤ 700 mp   S > 700 mp
    A            977            732             489

The largest-plot column is taken, for the reason the same choice was made in Vaslui: it is the
one that applies to the hectares this simulator counts, and the small-plot price is what a
garden strip changes hands for.

**A trap worth naming.** The circumscription heading is letter-spaced — `SUCEA V A` — so a name
read literally matches nothing. Names are folded to letters before comparison, which is also
what makes `Mitocu Dragomirnei` in the roster meet `MITOCUL DRAGOMIRNEI` in the bucket list.

**What is lost.** A bucket list mixes commune seats with villages of other communes — `SF.ILIE`
and `LISAURA` are Șcheia's, `MOARA NICA` and `BULAI` are Moara's. A village named there whose
commune is not also named leaves that commune in the catch-all bucket, which prices it lower
than the study intends. Moara is the case in point. It is a handful of communes per
circumscription and it errs downwards, which is the direction this repository prefers to err.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import load  # noqa: E402

# "CIRCUMSCRIPȚIA" and, on one page, "CICIRCUMSCRIPȚIA". The name follows on the next line and
# may be letter-spaced.
# The word itself is unreliable — it is spelled "CICIRCUMSCRIPȚIA" once, and on two pages it
# does not sit on a line of its own. What every roster page does carry is the sentence citing
# the government decision, so that is the trigger. Anchoring on the word found four of six.
CIRCUMSCRIPTION = re.compile(r"care\s+fac\s+parte\s+din\s+circumscrip", re.I)
ROSTER_KIND = re.compile(r"^\s*(Municipii|Ora[șşs]e|Comune)\s*$", re.M | re.I)
# The roster prints two columns to a line — " 1 Arbore 15 Iaslovăț" — so every numbered entry
# on the line is captured, not just one. Requiring the line to end after a name matched the
# left column only where it happened to be alone, and glued the two together everywhere else:
# "Arboreiaslovat" is not a commune.
ROSTER_ROW = re.compile(
    r"\b\d{1,2}\s+([A-ZĂÂÎȘŞȚŢ][\w \-.']*?)(?=\s+\d{1,2}\s+[A-ZĂÂÎȘŞȚŢ]|\s*$)"
)
TOWN_HEADING = re.compile(
    r"^\s*(?:MUNICIPIUL|ORA[ȘŞS]UL)\s*\n?\s*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,})\s*$", re.M
)
# The smaller towns are not introduced at all — Solca, Cajvana, Vicovu de Sus and five others
# carry their name as a bare running header over their own pages, the way Satu Mare's land
# grids do. A bare capitalised line is accepted as a town only if the county register knows
# it, which is what keeps "MEDIUL RURAL" and the category headings out.
BARE_HEADING = re.compile(r"^\s*([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-]{2,28})\s*$", re.M)
NOT_A_PLACE = re.compile(r"MEDIU|RURAL|TEREN|ZONA|CATEGORI|LEI|VALORI|SPA[ȚŢT]II", re.I)
BUCKET = re.compile(r"MEDIU(?:L)?\s+RURAL\s*(\d+)?", re.I)
SPECIFIC = re.compile(r"pia[țţt]a\s+specific[ăa]\s+pentru\s+localit[ăa][țţt]ile\s*:?([^)]*)", re.I)
EXCEPTION = re.compile(r"excep[țţt]ie\s+localit[ăa][țţt]ile\s*:?([^)]*)", re.I)

CC_TABLE = re.compile(r"TEREN\s+INTRAVILAN\s*-\s*CUR[ȚŢT]I", re.I)
EXTRA_TABLE = re.compile(r"TEREN\s+EXTRAVILAN", re.I)
INTRA_TABLE = re.compile(r"TEREN\s+INTRAVILAN", re.I)
ZONE_ROW = re.compile(r"^[A-F]$")

# The study's own category names against the codes the rest of the repository uses.
CATEGORIES: list[tuple[str, re.Pattern[str]]] = [
    ("CC", re.compile(r"cur[țţt]i\s+construc", re.I)),
    ("A", re.compile(r"arabil", re.I)),
    ("V+L", re.compile(r"liv(ad[ăa]|ezi)|vie|vii", re.I)),
    ("P+F", re.compile(r"p[ăa][șşs]une|f[âa]nea", re.I)),
    ("PADURE", re.compile(r"p[ăa]dure|lizier", re.I)),
    ("NP", re.compile(r"neproductiv", re.I)),
    ("AP", re.compile(r"b[ăa]l[țţt]i|iazuri", re.I)),
]


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def resolve(name: str, is_local) -> str | None:
    """The register's name for a heading, allowing for letter-spacing.

    Headings in this study are letter-spaced for emphasis — `SUCEA V A`, `V ATRA DORNEI` —
    so the name as printed matches nothing. Collapsing the spaces is tried second, because
    a real two-word name (`Vicovu de Sus`) must not be collapsed into one.
    """
    for candidate in (clean(name), clean(name).replace(" ", "")):
        if is_local(candidate):
            return candidate
    return None


def fold(name: str) -> str:
    """Letters only — the headings are letter-spaced (`SUCEA V A`) and the diacritics vary."""
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def number(text: str) -> float | None:
    stripped = clean(text).replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?", stripped):
        return None
    value = float(stripped.replace(".", "").replace(",", "."))
    return value if 0 < value < 100_000 else None


def code_of(label: str) -> str | None:
    for code, pattern in CATEGORIES:
        if pattern.search(label):
            return code
    return None


def read_town_zones(page: dict) -> dict[str, float]:
    """A town's building land by zone, from the largest-plot column."""
    for table in page.get("tables") or []:
        cells = [[clean(c) for c in row] for row in table["cells"]]
        if not any(CC_TABLE.search(c) for row in cells[:3] for c in row):
            continue
        zones: dict[str, float] = {}
        for row in cells:
            if not row or not ZONE_ROW.match(row[0]):
                continue
            values = [v for v in (number(c) for c in row[1:]) if v is not None]
            # S ≤ 300, 300 < S ≤ 700, S > 700 — the last is the one that applies to a plot
            # rather than to a strip of garden.
            if values:
                zones[row[0]] = values[-1]
        if zones:
            return zones
    return {}


def read_category_table(page: dict, want_extravilan: bool) -> dict[str, float]:
    """Category to lei per square metre, from a two-column CATEGORII/VALOARE table."""
    found: dict[str, float] = {}
    for table in page.get("tables") or []:
        cells = [[clean(c) for c in row] for row in table["cells"]]
        head = " ".join(c for row in cells[:3] for c in row)
        if not INTRA_TABLE.search(head) and not EXTRA_TABLE.search(head):
            continue
        # The rural tables put intravilan on the left and extravilan on the right of one
        # table; a town's extravilan is a table of its own. Splitting at the column where
        # "TEREN EXTRAVILAN" sits handles both.
        split = None
        for row in cells[:3]:
            for position, cell in enumerate(row):
                if EXTRA_TABLE.search(cell):
                    split = position
        for row in cells:
            for position, cell in enumerate(row):
                code = code_of(cell)
                if code is None:
                    continue
                right = split is not None and position >= split
                if right != want_extravilan:
                    continue
                value = next(
                    (
                        v
                        for v in (number(c) for c in row[position + 1 :])
                        if v is not None
                    ),
                    None,
                )
                if value is not None:
                    found.setdefault(code, value)
    return found


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    notes: list[str] = []

    towns: dict[str, dict] = {}
    blocks: list[dict] = []
    block: dict | None = None
    place: tuple[str, str] | None = None

    for page in pages:
        text = page.get("text") or ""
        flat = re.sub(r"\s+", " ", text)

        if CIRCUMSCRIPTION.search(flat):
            kind = ""
            roster: set[str] = set()
            for line in text.splitlines():
                stripped = clean(line)
                found = ROSTER_KIND.match(stripped)
                if found:
                    kind = found.group(1).lower()
                    continue
                if kind == "comune":
                    for row in ROSTER_ROW.finditer(stripped):
                        # Checked against the county register, not taken on trust. The study
                        # spells three communes its own way — Bălcăuți, Forăști and a "Fundu
                        # Moldonei" that is Fundu Moldovei with a letter wrong — and feeding
                        # those through as localities put names in the output that no register
                        # knows, which is what the duplicate-and-roster gate exists to stop.
                        if resolve(row.group(1), is_local):
                            key = fold(row.group(1))
                            if len(key) > 2:
                                roster.add(key)
            block = {"roster": roster, "specific": {}, "exception": {}, "named": set()}
            blocks.append(block)
            place = None
            continue

        heading = TOWN_HEADING.search(text)
        if heading:
            town = resolve(heading.group(1), is_local)
            if town:
                place = ("town", town)
        else:
            for bare in BARE_HEADING.finditer(text):
                label = clean(bare.group(1))
                if NOT_A_PLACE.search(label):
                    continue
                town = resolve(label, is_local)
                if town:
                    place = ("town", town)
                    break

        if BUCKET.search(flat):
            specific = SPECIFIC.search(flat)
            # EXCEPTION is not read: a section without a "specific" list is the catch-all
            # whether or not it says so, and two circumscriptions say so in a heading the
            # pattern does not see.
            # Only three circumscriptions split their countryside in two. The other three —
            # Fălticeni, Câmpulung, Vatra Dornei, Gura Humorului, Siret — have one unnumbered
            # "MEDIUL RURAL" section with no list at all, which is the whole of that
            # circumscription's countryside. Requiring a list left forty-four communes, four
            # entire circumscriptions' worth, with no price.
            place = ("rural", "specific" if specific else "exception")
            if block is not None and specific:
                for token in re.split(r"[,;]", specific.group(1)):
                    key = fold(token)
                    if key and key in block["roster"]:
                        block["named"].add(key)

        if place is None or block is None and place[0] == "rural":
            continue

        if place[0] == "town":
            zones = read_town_zones(page)
            intravilan = read_category_table(page, want_extravilan=False)
            extravilan = read_category_table(page, want_extravilan=True)
            entry = towns.setdefault(place[1], {"zones": {}, "flat": None, "extravilan": {}})
            entry["zones"].update(zones)
            # Only the larger towns get a zone grid. Liteni, Salcea, Dolhasca and eight others
            # are priced the way the countryside is — one figure per category — so their
            # building land is a single zone rather than none at all. Reading only the zone
            # grid left eleven of sixteen towns unpriced.
            if entry["flat"] is None and "CC" in intravilan:
                entry["flat"] = intravilan["CC"]
            for code, value in extravilan.items():
                entry["extravilan"].setdefault(code, value)
        elif block is not None:
            target = block[place[1]]
            for code, value in read_category_table(page, want_extravilan=False).items():
                target.setdefault(("intra", code), value)
            for code, value in read_category_table(page, want_extravilan=True).items():
                target.setdefault(("extra", code), value)

    zoned = [
        {
            "name": town,
            "rank": None,
            "zones": sorted(entry["zones"] or {"A": 0}),
            "intravilan": {"CC": entry["zones"] or {"A": entry["flat"]}},
            "extravilan": {k: v for k, v in entry["extravilan"].items() if k != "CC"},
            "page": 1,
        }
        for town, entry in towns.items()
        if entry["zones"] or entry["flat"]
    ]

    communes: list[dict] = []
    for block in blocks:
        for key in sorted(block["roster"]):
            bucket = block["specific"] if key in block["named"] else block["exception"]
            if not bucket:
                bucket = block["exception"] or block["specific"]
            built = bucket.get(("intra", "CC"))
            if built is None:
                continue
            communes.append(
                {
                    "name": key.title(),
                    "villages": [{"name": key.title(), "intravilan": {"CC": built}}],
                    "extravilan": {
                        code: value
                        for (side, code), value in bucket.items()
                        if side == "extra" and code != "CC"
                    },
                    "page": 1,
                }
            )
    for position, entry in enumerate(communes, start=1):
        entry["index"] = position
    if not communes:
        notes.append("no rural bucket produced a price")
    return zoned, communes, notes

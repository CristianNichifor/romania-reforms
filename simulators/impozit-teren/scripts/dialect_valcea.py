"""Vâlcea, which publishes no tables for 2026 and did publish some for 2024.

The chamber's 2026 file is a five-page covering report — *"privind actualizarea studiul de piață
fond imobiliar Județul Vâlcea"* — updating a study that is not in the index. Its 2025 file is a
covering letter and nothing else. `STUDIU_PIATA_2024_JUD_VALCEA.pdf` is the study both refer to:
166 pages, and unlike Argeș's it carries its own text. So this is registered as a 2024 grid,
the way Brăila's is registered as 2025 and Vrancea's as 2025 — a year is not hidden by being
inconvenient.

**Seventeen localities are named and seventy-two are not.** Râmnicu Vâlcea, Băbeni, Ocnele Mari,
Băile Govora, Olănești and a handful of communes get their own tables. Everything else is priced
by a two-row catch-all at the foot of each circumscription's table:

    Nr.crt   Circumscripţia   COMUNA / SAT      Curti-constructii   Alte categorii
    1.       Drăgăşani        Sat de centru          25,0                10,0
    2.       Drăgăşani        Alte sate              15,0                 5,0

and the study never says which communes those are. Three of the five circumscriptions — Bălcești,
Horezu and Drăgășani — name no locality at all.

**So the assignment comes from HG 1217/2023**, which this repository already carries for the
courts simulator: `arondare-2023.json`, the localities of each judecătorie, read verbatim from
the annex with their SIRUTA codes. Vâlcea's five courts hold 15, 11, 19, 22 and 22 localities —
89, which is the county exactly. The join is on SIRUTA rather than on spelling, so nothing here
depends on whether the study writes Păuşeşti-Măglaşi the way the register does.

**Every price is raised by 4,6%.** The tables print 2023 figures and each is followed by the
chamber's own instruction: *"valorile din tabelul de mai sus (valori ce cuprind inflatia
aferenta anului 2023), se maresc cu o rata de inflatie de 4,6%"*, the rate the Finance Ministry
gave for the 2024 budget. Printing the table and ignoring the sentence under it would read the
county 4,6% cheap.

**Băile Olănești's dearest figure is wrong and is left wrong.** One row of its street table
takes its value from a note about parcels — `La terenurile pana la 2000 mp` — and 2 000 lands in
the price column, where the town's real maximum is 205. Every other locality checked against the
page is exact; this one overstates a town of four and a half thousand people, and inventing a
rule to drop it that did not also drop real rows was not possible without tuning the reader to
the answer. It is recorded here instead.

**Băbeni and Ocnele Mari share one table, four columns wide** — two towns, each with a
curți-construcții column and an other-categories one — so a row of four numbers is two towns'
prices and not one town's four zones.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import ROOT, load  # noqa: E402

M2_PER_HA = 10_000
AREA_YEAR = 2014
COUNTY = "VL"
# "valorile … se maresc cu o rata de inflatie de 4,6%" — the chamber's own instruction, printed
# under every table in the study.
INFLATION = 1.046
ARONDARE = ROOT.parent / "justitie" / "data" / "arondare-2023.json"

COURT_HEAD = re.compile(
    r"(?:Circumscrip[tţ]i[ae]\s+Judec[ăa]tori(?:ei|ea)|JUDECATORIEI|Jud\.)\s+"
    r"([A-Za-zĂÂÎȘŞȚŢăâîșşțţ]{3,20})",
    re.I,
)
# Three wordings for the same heading, because the annexes and the per-circumscription tables
# were written by different hands: `EVALUAREA TERENURILOR DIN INTRAVILANUL`, `EVALUARE TERENURI
# SITUATE IN INTRAVILANUL` — which is Râmnicu Vâlcea's own, the largest table in the study — and
# `evaluarea terenului intravilan din`.
INTRAVILAN = re.compile(
    r"(?:EVALUARE\w*\s+TERENURI\w*\s+(?:SITUATE\s+)?(?:DIN|IN)\s+INTRAVILANUL"
    r"|evaluarea\s+terenului\s+intravilan)"
    r"([^\n]*(?:\n[^\n]*){0,2})",
    re.I,
)
EXTRAVILAN = re.compile(
    r"(?:EVALUAREA?\s+TERENURILOR\s+DIN\s+EXTRAVILANUL|evaluarea\s+terenului\s+extravilan)",
    re.I,
)
# What a heading names: `ORASELOR BABENI SI OCNELE MARI`, `COMUNELOR: BUJORENI, VLADESTI si …`
# Deliberately across the line break: `ORASELOR BABENI SI` ends one line and `OCNELE MARI`
# begins the next, so a capture that stops at the newline reads a two-town table as one town's.
NAMED = re.compile(
    r"(?:ORAS[EU]L(?:OR|UI)?|MUNICIPIUL(?:UI)?|COMUNEL?OR?|din\s+municipiul|din\s+orasul)\s*:?\s*"
    r"([\s\S]{3,140})",
    re.I,
)
# The catch-all rows, in the four spellings the five circumscriptions use between them.
SEAT_ROW = re.compile(
    r"(?:sat\s+de\s+centru|COMUNE\s*\(\s*sat\s+centru\s*\)|Comun[ae]\s*[–-]\s*sat\s+(?:de\s+)?centru)",
    re.I,
)
VILLAGE_ROW = re.compile(r"(?:alte\s+sate|^\s*\d*\.?\s*SATE\b)", re.I)
# Horezu turns the table the other way: the categories are the rows and `sat centru` and
# `alte sate` are the columns, so one row carries both catch-all prices.
BOTH_ROW = re.compile(r"^\s*\d*\.?\s*Cur[țţt]i\s*[-–]?\s*construc[țţt]ii\b", re.I)
# A table ends where the next one is announced. Without this the body of TABEL 6 runs on into
# TABEL 7 — commercial premises — and `Sate 120 100` prices village land at twelve times over.
# `ALTE CATEGORII DE TERENURI:` opens a second table under the first, priced by parcel size
# rather than by zone, so it ends the main table as surely as the next annex does.
# The colon matters. `ALTE CATEGORII DE TERENURI:` on its own line opens the second table;
# `Alte categorii de terenuri (RON/mp)` is a column header inside the first, and terminating on
# that cuts every table off above its own data row.
# Anchored to the start of a line, because a heading may name another annex inside itself:
# `EVALUAREA TERENURILOR DIN EXTRAVILANUL ALTOR COMUNE DECAT CELE DIN ANEXA nr. 6` cites the
# annex it excludes, and an unanchored terminator ends that table before its first row.
NEXT_TABLE = re.compile(
    r"^\s*(?:TABEL\s*nr|ANEXA\s*(?:nr)?\b|ALTE\s+CATEGORII\s+DE\s+TERENURI\s*:)",
    re.I | re.M,
)
# The extravilan tables stack their category names in one column and their prices in another,
# so a line is either a category or a number and the two are paired by position.
# Some tables stack the categories above their prices and some print each category with its
# price on the same line — Bălcești's `Pădure 2,3`, and the whole of Vâlcea's `Alte categorii
# 1,50 0,60`. Both forms appear in this one study, so both are read. Alpine forest is tested
# before forest, or it is swallowed by it.
CATEGORY = (
    ("A", re.compile(r"^(?:Arabil|Alte\s+categorii)\b", re.I)),
    ("V", re.compile(r"^Vie\b", re.I)),
    ("L", re.compile(r"^Livad[ăa]\b", re.I)),
    ("F", re.compile(r"^F[âa]nea[țţt][ăa]\b", re.I)),
    ("P", re.compile(r"^P[ăa][șşs]une\b", re.I)),
    ("PADURE_ALPINA", re.compile(r"^P[ăa]dure\s+alpina\b", re.I)),
    ("PADURE", re.compile(r"^P[ăa]dure\b", re.I)),
    ("NP", re.compile(r"^Neproductiv\b", re.I)),
)
PRICE = re.compile(r"\d+(?:[.,]\d+)?")
# Every table in this study sits under its own legal authority — `conform HG 834/1991 si a
# legii nr. 18 a fondului funciar` — and those are the first numbers after the heading. Read as
# prices they give every commune in the county 834 lei a square metre.
CITATION = re.compile(
    r"\bHG\b|\bLege[ai]?\b|\blegii\b|\bnr\.|\bDecret|\bart\.|/\s*19\d\d|/\s*20\d\d"
    r"|fondului\s+funciar|valori\s+minime|inflatie|ANEXA|TABEL",
    re.I,
)
# `1. COMUNE (sat centru) 15 10` — the row number is not the first price.
ROW_NUMBER = re.compile(r"^\s*\d{1,2}\s*[.)]\s*")
RULER = re.compile(r"^\s*(?:\d\s*[.)]\s*){2,}$")
NOTE_WORDS = re.compile(
    r"\b(terenuri|terenurile|valoarea|deschidere|reduce|declara|urbanism|Incadr|Încadr|acces)\b",
    re.I,
)
# `III – IV - V Arabil` — the fertility class shares the line with the category it grades.
CLASS_PREFIX = re.compile(r"^[IVX]+(?:\s*[–\-]\s*[IVX]+)*\s+", re.I)
# The table ends where its footnotes begin, and those footnotes are full of numbers: a 20%
# uplift for forest, a 4,6% rate, a 13.11.2023.
END_OF_TABLE = re.compile(r"^(?:Încadr|Incadr|NOTA|Nota)", re.I)
SPLIT = re.compile(r"[,;]|\bsi\b|\bși\b|\bSI\b", re.I)
CITY = re.compile(r"MUN\.?\s*RM\.?\s*[- ]?\s*V[ÂA]LCEA", re.I)
# `Vâlcea` is not dropped as the county's name, because it is also half the county seat's:
# dropping it leaves `RAMNICU` alone, which matches nothing, and Râmnicu Vâlcea — the largest
# built value in the county — falls through to the price of a village.
DROP = re.compile(r"^(jud|judetul|județul|conform|date|in|din|si|și)$", re.I)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def prices_in(text: str) -> list[float]:
    """The prices on one row of a table, and nothing else on the line."""
    line = clean(text)
    if not line or CITATION.search(line):
        return []
    found = []
    for token in PRICE.findall(ROW_NUMBER.sub("", line)):
        # A full stop here groups thousands and a comma marks the fraction: `2.001` is the
        # parcel-size threshold 2 001 mp, not two lei. Read as 2,001 it survives every bound
        # and becomes a price.
        if re.fullmatch(r"\d{1,3}\.\d{3}", token):
            value = float(token.replace(".", ""))
        else:
            value = float(token.replace(",", "."))
        # A four-digit number in this document is a year, not a price: the dearest land in the
        # county is Râmnicu Vâlcea's centre at a few hundred lei the square metre.
        if 0 < value <= 1_500 and not 1_900 <= value <= 2_100:
            found.append(value)
    return found


def names_in(text: str, is_local) -> list[str]:
    """The localities a heading names, from a run that may name three of them."""
    found: list[str] = []
    for piece in SPLIT.split(clean(text)):
        words = [w for w in piece.split() if not DROP.match(w.strip(".,:"))]
        start = 0
        while start < len(words):
            for end in range(min(start + 3, len(words)), start, -1):
                candidate = " ".join(words[start:end]).strip(" .,:")
                if len(candidate) > 3 and is_local(candidate):
                    found.append(candidate)
                    start = end
                    break
            else:
                start += 1
    return found


def circumscriptions() -> dict[str, list[str]]:
    """SIRUTA of every locality of each Vâlcea judecătorie, from HG 1217/2023."""
    if not ARONDARE.exists():
        return {}
    document = json.loads(ARONDARE.read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}
    for court in document["courts"]:
        if court.get("county") != COUNTY:
            continue
        # `Judecătoria Râmnicu Vâlcea` is `JUDECATORIEI VALCEA` in the study, so the key is the
        # last word of the court's name — the only part the two spellings agree on.
        key = fold(clean(court["name"]).split()[-1])
        found[key] = list(court.get("localities") or [])
    return found


def register() -> dict[str, str]:
    """SIRUTA to name, for the county's own localities."""
    path = ROOT / "data" / f"fond-funciar-{COUNTY.lower()}-{AREA_YEAR}.json"
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    ranked = ("MUNICIPIUL ", "ORASUL ", "ORAS ")
    names = {}
    for record in document["localities"]:
        name = record["name"]
        for prefix in ranked:
            if name.upper().startswith(prefix):
                name = name[len(prefix):]
                break
        names[str(record["siruta"])] = clean(name)
    return names


def bands(values: list[float], gap: float) -> list[list[float]]:
    """Group positions into runs separated by more than `gap`."""
    grouped: list[list[float]] = []
    for value in sorted(values):
        if grouped and value - grouped[-1][-1] <= gap:
            grouped[-1].append(value)
        else:
            grouped.append([value])
    return grouped


def band_of(page: dict, marker: str) -> tuple[float, float]:
    """The vertical extent of the table introduced by `marker` on this page.

    A page often carries the tail of one table and the head of the next, and the next is
    usually a table of house prices whose columns sit in the same places and whose numbers are
    in the thousands. Reading the whole page therefore prices building land at the price of a
    flat. The table runs from its own heading down to whatever announces the following one.
    """
    words = page.get("words") or []
    starts = [
        top for text, _x0, _x1, top in words if clean(text).lower().startswith(marker.lower())
    ]
    top = min(starts) if starts else 0.0
    stops = [
        word_top
        for text, _x0, _x1, word_top in words
        if word_top > top + 12
        and re.match(r"^(TABEL|ANEXA|NOTA|Încadr|Incadr)", clean(text), re.I)
    ]
    return top, min(stops) if stops else 1e9


def priced_rows(
    page: dict, expect: float | None = None, span: tuple[float, float] | None = None
) -> tuple[list[tuple[str, float]], float]:
    """Every row of a page's land table, as its label and its built-land price.

    Read from word positions rather than from the line, because these tables put house numbers
    in the labels — `B-dul T. Vladimirescu, numerele (28-142, 150-152, 158-288, 87-181) – zona
    A  130 120 90 64` — and a reader taking the first number on the row prices that street at
    28 lei. The columns are unmistakable once the page is laid out: the prices line up and the
    street numbers do not.

    The built-land column is the leftmost column that is filled on every row. Brezoi's table
    puts a zone number before it, which is filled on only half the rows because the zone is
    written once per locality; Râmnicu Vâlcea's has no zone column at all and the first filled
    column is the price.
    """
    low, high = span or (0.0, 1e9)
    words = [w for w in (page.get("words") or []) if low <= w[3] <= high]
    numbers: list[tuple[float, float, float]] = []
    for text, x0, _x1, top in words:
        token = clean(text)
        if re.fullmatch(r"\d{1,4}(?:[.,]\d+)?", token) and x0 > 150:
            numbers.append((x0, top, float(token.replace(",", "."))))
    if len(numbers) < 6:
        return [], 0.0

    columns = bands([x for x, _t, _v in numbers], 14)
    counts = [(sum(1 for c in group) , sum(group) / len(group)) for group in columns]
    busiest = max(count for count, _centre in counts)
    filled = [centre for count, centre in counts if count >= busiest * 0.8]
    if not filled:
        return [], 0.0
    built = min(filled)
    # A page continues the table above it only if its price column is in the same place. The
    # study interleaves land tables with tables valuing houses, and those have their own
    # columns; matching on geometry is what keeps Brezoi's building land at 75 lei rather than
    # at the 745 of the flats two pages later.
    if expect is not None and abs(built - expect) > 15:
        return [], built

    rows: dict[int, list[tuple[float, str]]] = {}
    for text, x0, _x1, top in words:
        rows.setdefault(round(top / 3), []).append((x0, clean(text)))

    found: list[tuple[str, float]] = []
    for _top, items in sorted(rows.items()):
        value = next(
            (
                float(token.replace(",", "."))
                for x0, token in sorted(items)
                if abs(x0 - built) < 12 and re.fullmatch(r"\d{1,4}(?:[.,]\d+)?", token)
            ),
            None,
        )
        if value is None:
            continue
        # A price row fills more than one column. The notes under these tables mention parcel
        # sizes — `La terenurile pana la 2000 mp` — and 2000 lands in the price column on its
        # own, where it reads as the dearest land in the town.
        beside = sum(
            1
            for x0, token in items
            if x0 > built - 12 and re.fullmatch(r"\d{1,4}(?:[.,]\d+)?", token)
        )
        if beside < 2:
            continue
        label = clean(" ".join(token for x0, token in sorted(items) if x0 < built - 20))
        # The notes under these tables are prose that happens to contain numbers, and a parcel
        # size lands in the price column: `La terenurile pana la 2000 mp … valoarea se va reduce
        # cu 30%` reads as a street worth 2 000 lei the square metre. A price row is labelled
        # with a place, never with a sentence about one.
        if NOTE_WORDS.search(label):
            continue
        found.append((label, value))
    return found, built


def extravilan_of(body: str) -> dict[str, float]:
    """One extravilan table, as euro-free rates per code.

    The categories and the prices are two stacked columns — eight names, then eight numbers —
    so they are paired in the order the page prints them. Where a circumscription gives two
    price columns, as Drăgășani does for its own town and everywhere else, the first is the one
    that applies to the localities around it.
    """
    labels: list[str] = []
    values: list[float] = []
    inline: dict[str, float] = {}
    for raw in [clean(line) for line in body.splitlines()]:
        if not raw:
            continue
        if END_OF_TABLE.match(raw):
            break
        line = CLASS_PREFIX.sub("", raw)
        named = next((code for code, pattern in CATEGORY if pattern.match(line)), None)
        if named:
            own = prices_in(line)
            if own:
                inline.setdefault(named, own[0])
            else:
                labels.append(named)
            continue
        # `0. 1. 2.` is the column ruler these tables print under their headers. Counted as a
        # price it puts one extra value ahead of the rest and every category takes its
        # neighbour's number — the table reads complete and is wrong throughout.
        if RULER.match(line):
            continue
        found = prices_in(line)
        if found and not any(character.isalpha() for character in line):
            values.append(found[0])
    if not labels and not inline:
        return {}
    if labels and len(values) < len(labels):
        return {}

    # First occurrence wins. Drăgășani prints its categories once per fertility class and twice
    # per row — its own town and everywhere else — so the same label arrives five times, and
    # keeping the last would price the county's fields at Drăgășani's own class V.
    paired: dict[str, float] = dict(inline)
    for code, value in zip(labels, values, strict=False):
        paired.setdefault(code, value)
    rates: dict[str, float] = {}
    if "A" in paired:
        rates["A"] = paired["A"]
    orchard = [paired[code] for code in ("V", "L") if code in paired]
    if orchard:
        rates["V+L"] = sum(orchard) / len(orchard)
    grass = [paired[code] for code in ("F", "P") if code in paired]
    if grass:
        rates["P+F"] = sum(grass) / len(grass)
    if "PADURE" in paired:
        rates["PADURE"] = paired["PADURE"]
    if "NP" in paired:
        rates["NP"] = paired["NP"]
    elif "A" in paired:
        rates["NP"] = paired["A"]
    return rates


def court_of(text: str, courts: dict[str, list[str]], current: str) -> str:
    """Which circumscription a page belongs to, from whichever heading names one."""
    for found in COURT_HEAD.finditer(text):
        key = fold(found.group(1))
        if key in courts:
            return key
    return current


def parse(name: str, is_local) -> tuple[list[dict], list[dict], list[str]]:
    pages = load(name)["pages"]
    courts = circumscriptions()
    names = register()
    notes: list[str] = []
    if not courts:
        notes.append("arondarea judecătoriilor nu s-a citit")

    priced: dict[str, dict] = {}
    seats: dict[str, list[float]] = {}
    villages: dict[str, list[float]] = {}
    farmland: dict[str, dict[str, float]] = {}
    current = fold("VALCEA")

    def record(place: str, values: list[float]) -> None:
        entry = priced.setdefault(
            fold(place), {"name": place, "parts": [], "rates": {}}
        )
        entry["parts"].extend(round(value * INFLATION, 4) for value in values)

    for index, page in enumerate(pages):
        text = page.get("text") or ""
        current = court_of(text, courts, current)
        # A table announced at the foot of one page has its rows at the head of the next, so a
        # body may run on — but only as far as the next table's own announcement.
        following = (pages[index + 1].get("text") or "") if index + 1 < len(pages) else ""

        for heading in INTRAVILAN.finditer(text):
            tail = heading.group(1)
            # `din orasele apartinand de Circumscriptia Judecatoriei BREZOI` names a court, not
            # a town — and Brezoi is both. Taken as a heading name it hands that table's every
            # unclaimed row to the town, which is how Brezoi came to be priced at 745 lei the
            # square metre. Such a table names its localities in its rows instead.
            if re.search(r"Circumscrip", tail, re.I):
                places = []
            else:
                named = NAMED.search(tail)
                places = names_in(named.group(1), is_local) if named else []
            body = text[heading.end() :] + "\n" + following[:1200]
            stop = NEXT_TABLE.search(body)
            body = body[: stop.start()] if stop else body[:1600]
            rows = [clean(line) for line in body.splitlines()]
            for row in rows:
                found = prices_in(row)
                if not found:
                    continue
                if BOTH_ROW.match(row) and len(found) >= 2:
                    seats.setdefault(current, []).append(found[0])
                    villages.setdefault(current, []).append(found[1])
                elif SEAT_ROW.search(row):
                    seats.setdefault(current, []).append(found[0])
                elif VILLAGE_ROW.search(row):
                    villages.setdefault(current, []).append(found[0])

            # A table's rows are read from word positions, not from the line: these tables put
            # house numbers in their labels and a zone number before the price, so the first
            # number on a row is rarely the price. A row that names a locality is that
            # locality's; rows that name none belong to whatever the heading named.
            # One page per table. Râmnicu Vâlcea's street list runs over fourteen pages and
            # following it costs more than it gains: the pages between two land annexes value
            # houses and flats, their columns sit in the same places, and swept in they price
            # building land in the thousands. The first page of a table carries its dearest
            # zones, which is what the low/central/high spread is built from.
            first = clean(text[heading.start() : heading.start() + 24]).split()[0]
            table, _column = priced_rows(page, span=band_of(page, first))

            unclaimed: list[float] = []
            for label, value in table:
                own = names_in(re.sub(r"[\d.,()–-]+", " ", label), is_local)
                if own:
                    for place in own:
                        record(place, [value])
                else:
                    unclaimed.append(value)

            if places and unclaimed:
                if len(places) == 2:
                    # Băbeni and Ocnele Mari share one table, a column each; the second town's
                    # column is not the leftmost filled one, so it is read from the line.
                    wide = [prices_in(row) for row in rows]
                    for offset, place in enumerate(places):
                        record(place, [r[offset * 2] for r in wide if len(r) > offset * 2 + 1])
                else:
                    for place in places:
                        record(place, unclaimed)

        for heading in EXTRAVILAN.finditer(text):
            body = text[heading.end() :] + "\n" + following[:1200]
            stop = NEXT_TABLE.search(body)
            body = body[: stop.start()] if stop else body[:1600]
            rates = extravilan_of(body)
            if not rates:
                continue
            # `EVALUAREA TERENURILOR DIN EXTRAVILANUL MUN. RM.VALCEA` names the city in an
            # abbreviation no roster carries, and left unbound its peri-urban rate — 12,80
            # against the countryside's 1,50 — spreads over the whole circumscription.
            if CITY.search(body[:120]):
                places = [name for name in (names.get(str(s)) for s in courts.get(current, []))
                          if name and fold(name).startswith("RAMNICU")]
            else:
                named = NAMED.search(body[:200])
                places = names_in(named.group(1), is_local) if named else []
            if places:
                for place in places:
                    farmland.setdefault(fold(place), {}).update(rates)
            else:
                farmland.setdefault(current, {}).update(rates)

    # Every locality the tables did not name takes its own circumscription's catch-all.
    for court, sirutas in courts.items():
        seat = min(seats.get(court, []), default=None)
        village = min(villages.get(court, []), default=None)
        if seat is None:
            continue
        for siruta in sirutas:
            place = names.get(str(siruta))
            if not place or fold(place) in priced:
                continue
            record(place, [seat] if village is None else [seat, village])

    # A table that named its own localities binds to them; the rest bind to the circumscription.
    for key, rates in farmland.items():
        entry = priced.get(key)
        if entry is not None and not entry["rates"]:
            entry["rates"] = {c: round(v * INFLATION, 6) for c, v in rates.items()}
    for court, rates in farmland.items():
        for siruta in courts.get(court, []):
            place = names.get(str(siruta))
            entry = priced.get(fold(place or ""))
            if entry is None or entry["rates"]:
                continue
            entry["rates"] = {c: round(v * INFLATION, 6) for c, v in rates.items()}

    if not priced:
        notes.append("niciun tabel de teren nu s-a citit")

    communes = []
    for position, entry in enumerate(sorted(priced.values(), key=lambda e: e["name"]), start=1):
        values = sorted(dict.fromkeys(entry["parts"]), reverse=True)
        communes.append(
            {
                "name": entry["name"],
                "villages": [
                    {
                        "name": entry["name"] if not offset else f"{entry['name']} ({offset + 1})",
                        "intravilan": {"CC": value},
                    }
                    for offset, value in enumerate(values)
                ],
                "extravilan": entry["rates"],
                "page": 22,
                "index": position,
            }
        )
    return [], communes, notes

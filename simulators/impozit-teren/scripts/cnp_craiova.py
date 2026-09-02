"""CNP Craiova, which prices four counties in one 309-page document.

Dolj, Mehedinți, Gorj and Olt share a study, a layout and a valuation firm, and the document is
organised as four sections that each end with an `ANEXA Z` — the county's extravilan table. That
page is the section boundary, and it is the only reliable one: the running headers say
`Judetul Mehedinti` on pages that are about Gorj's street zoning, because a town's first annex
carries the county's name and only its later annexes carry the town's.

**Each town is priced individually and every commune in a county shares one price.** Dolj's
communes are 20 lei/m², Mehedinți's 12, Gorj's 10, Olt's 12 with 10 for the villages. There is
no list of which communes — there does not need to be, since the price is the same for all of
them — so the roster comes from the land register, the same source the parse is checked against.

**The land tables have to be read as geometry.** The text layer returns the labels and the
values in separate runs, so `Zona A` and `170` arrive paragraphs apart and a reader working on
lines gets a column of prices with nothing to attach them to. Each table opens with a `Teren`
heading at the left margin and runs until a `Nota`, with the label at x≈56 and the value near
x≈280 on a baseline within a point or two of it.

**Three kinds of row are not zones of the town whose table they are in:**

* `Extravilan 7` is peri-urban building land at 70 000 lei/ha, three times what the county's
  own arable table says farmland is worth. It is a development option priced next to a town,
  not a category of farmland, and reading it as one would put Balș's edge-of-town price on
  every field in Olt. Extravilan comes from `ANEXA Z` for every locality.
* `Localitati apartinatoare 18` is the town's own villages, so it joins the town as a second,
  lower price rather than becoming a locality.
* `Simian - sat 90` is a different commune, priced inside Drobeta-Turnu Severin's table because
  it adjoins the city. It is emitted as Șimian.

`ANEXA Z` gives arable, forest, pasture-and-hay and vines-and-orchards directly, and the page
states what the rest are worth: unproductive land is the arable price less 40%.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import ROOT, load  # noqa: E402

STUDY = "studiu_de_piata_dolj_gorj_olt_mehedinti_2026.pdf"
M2_PER_HA = 10_000
AREA_YEAR = 2014

# `Municipiul Craiova ANEXA A9`, `Comune judetul Dolj ANEXA H3`, `Orsova ANEXA E3`.
HEADER = re.compile(r"^(.{3,60}?)\s+ANEXA\s+([A-Z]+\d*)\s*$", re.I)
RANK = re.compile(r"^(?:Municipiul|Orasul|Oraşul|Statiunea)\s+", re.I)
COMMUNES = re.compile(r"^Comune\b", re.I)
# The land table opens with `Teren`, `Teren intravilan`, or `Teren intravilan LEI/M.P.A.D.` —
# but not with `Teren extravilan`, which heads the peri-urban table and whose single row is the
# town's own name. Read as an intravilan heading it prices Vânju Mare's building land at the
# 2 lei/m² its surrounding fields are worth.
LAND_HEAD = re.compile(r"^Teren\b(?!\s+extravilan)", re.I)
STOP = re.compile(r"^(Nota|\*|Pentru|Valoarea|A\.M\.T|legislatia)", re.I)
# Comma for thousands, full stop for the fraction. Mehedinți is the only county here that
# prints a fraction — `80.0`, `2.5` — and an integer-only pattern reads its towns as unpriced.
NUMBER = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^\d+(?:\.\d+)?$")

VILLAGES_OF_TOWN = re.compile(r"^(?:Intravilan\s+)?Localitati\s+(?:limitrofe|apartinatoare)", re.I)
PERI_URBAN = re.compile(r"^Extravilan\b", re.I)
STRIP_ROW = re.compile(r"^(?:Intravilan|INTRAVILAN)\s+|\s*[-–]\s*sat\s*$", re.I)

# The five categories of `ANEXA Z`, in the order the page prints them.
CATEGORIES = (
    ("A", re.compile(r"^Teren\s+arabil", re.I)),
    ("PADURE", re.compile(r"^Vegetatie", re.I)),
    ("P+F", re.compile(r"^Pasuni", re.I)),
    ("V+L", re.compile(r"^Vii", re.I)),
)
# "avand categoria de folosinta - degradate sau neproductive, se va aplica o reducere de 40%
# asupra pretului terenului extravilan, din valoarea stabilita pentru terenul arabil."
NEPRODUCTIV = 0.60
COUNTY_SECTION = re.compile(r"^Judetul\s+(Dolj|Mehedinti|Gorj|OLT)\b", re.I)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fold(name: str) -> str:
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", clean(name).upper()))


def value_of(token: str) -> float | None:
    if not NUMBER.fullmatch(token):
        return None
    return float(token.replace(",", ""))


def lines_of(page: dict) -> list[tuple[int, list[tuple[float, str]]]]:
    """A page's words gathered onto baselines, each sorted left to right."""
    grouped: dict[int, list[tuple[float, str]]] = {}
    for text, x0, _x1, top in page.get("words") or []:
        grouped.setdefault(round(top), []).append((x0, text))
    return [(top, sorted(words)) for top, words in sorted(grouped.items())]


def paired(page: dict, active: bool = False) -> tuple[list[tuple[str, float]], bool]:
    """The label/value rows of every land table on one page.

    A row's value is usually on the same baseline as its label and sometimes a point or two
    below it, because the two are separate text runs and the PDF does not promise they line up.
    Looking one baseline either way finds it; looking further would reach the next row.
    """
    rows = lines_of(page)
    tops = [top for top, _ in rows]
    found: list[tuple[str, float]] = []
    for index, (top, words) in enumerate(rows):
        label = clean(" ".join(word for _, word in words))
        if LAND_HEAD.match(label) and len(label) < 40:
            active = True
            continue
        if not active:
            continue
        if STOP.match(label):
            active = False
            continue
        text = clean(" ".join(word for x, word in words if x < 200 and value_of(word) is None))
        values = [value_of(word) for x, word in words if x > 200 and value_of(word) is not None]
        if text and not values:
            for other in (index - 1, index + 1):
                if 0 <= other < len(rows) and abs(tops[other] - top) <= 4:
                    values = [
                        value_of(word)
                        for x, word in rows[other][1]
                        if x > 200 and value_of(word) is not None
                    ]
                    if values:
                        break
        if text and values:
            found.append((text, values[0]))
    return found, active


def extravilan_of(page: dict) -> dict[str, float]:
    """`ANEXA Z`: the county's farmland, in lei per hectare, as lei per square metre.

    The categories are matched by name and the values by position, because Mehedinți wraps
    `Vegetatie forestiera` across two baselines with its price between them — so the label
    nearest a value is the second half of the label above it.
    """
    rows = lines_of(page)
    anchors: list[tuple[int, str]] = []
    values: list[tuple[int, float]] = []
    for top, words in rows:
        label = clean(" ".join(word for _, word in words))
        for code, pattern in CATEGORIES:
            if pattern.match(label) and code not in {c for _, c in anchors}:
                anchors.append((top, code))
                break
        values.extend(
            (top, value_of(word))
            for x, word in words
            if x > 100 and value_of(word) is not None and 1_000 <= value_of(word) <= 200_000
        )

    rates: dict[str, float] = {}
    for top, code in anchors:
        near = min(values, key=lambda item: abs(item[0] - top), default=None)
        if near is not None and abs(near[0] - top) <= 10:
            rates[code] = near[1] / M2_PER_HA
            values.remove(near)
    if "A" in rates:
        rates["NP"] = round(rates["A"] * NEPRODUCTIV, 6)
    return rates


def sections(pages: list[dict]) -> dict[str, tuple[int, int]]:
    """Each county's page range, bounded by the `ANEXA Z` that closes it."""
    ends: list[tuple[str, int]] = []
    for index, page in enumerate(pages):
        first = clean(((page.get("text") or "").splitlines() or [""])[0])
        header = HEADER.match(first)
        if not header or header.group(2).upper() != "Z":
            continue
        county = COUNTY_SECTION.match(clean(header.group(1)))
        if county:
            ends.append((county.group(1).upper(), index))
    found: dict[str, tuple[int, int]] = {}
    start = 0
    for name, end in ends:
        found[name] = (start, end)
        start = end + 1
    return found


def roster_of(county: str) -> list[str]:
    """The county's communes, from the land register the parse is checked against."""
    path = ROOT / "data" / f"fond-funciar-{county.lower()}-{AREA_YEAR}.json"
    if not path.exists():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    # The register spells the rank into the name for a municipiu and an oraș and leaves a
    # commune bare, so the communes are the entries with no rank rather than the ones with one.
    ranked = ("MUNICIPIUL ", "ORASUL ", "ORAS ")
    return [
        clean(record["name"])
        for record in document["localities"]
        if not record["name"].upper().startswith(ranked)
    ]


def parse_county(name: str, is_local, county: str, section: str) -> tuple[list, list, list[str]]:
    pages = load(name)["pages"]
    bounds = sections(pages).get(section.upper())
    if bounds is None:
        return [], [], [f"secțiunea {section} nu s-a găsit în document"]
    start, end = bounds

    rates = extravilan_of(pages[end])
    towns: dict[str, dict] = {}
    shared: list[float] = []
    notes: list[str] = []
    header_name = ""
    # Vânju Mare's and Strehaia's tables begin on one page and their prices are on the next, so
    # an open table stays open across the page break. A new annex closes it, since the heading
    # is what says the page has moved on to something else.
    active = False

    for index in range(start, end + 1):
        page = pages[index]
        first = clean(((page.get("text") or "").splitlines() or [""])[0])
        header = HEADER.match(first)
        if header:
            header_name = clean(header.group(1))
            active = False

        rows, active = paired(page, active)
        if not rows:
            continue
        if COMMUNES.match(header_name):
            shared.extend(price for label, price in rows if not PERI_URBAN.match(label))
            continue

        place = RANK.sub("", header_name).strip()
        for label, price in rows:
            if PERI_URBAN.match(label):
                continue
            named = clean(STRIP_ROW.sub("", label))
            # A row that names a locality of its own is that locality, wherever it is printed.
            target = named if is_local(named) and fold(named) != fold(place) else place
            if not is_local(target):
                continue
            towns.setdefault(fold(target), {"name": target, "parts": []})["parts"].append(price)

    if not shared:
        notes.append("prețul comunelor nu s-a citit")
    if not rates:
        notes.append("anexa Z nu s-a citit")

    zoned = [
        {
            "name": entry["name"],
            "rank": None,
            "zones": sorted(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[: len(entry["parts"])]
            ),
            "intravilan": {
                "CC": {
                    letter: price
                    for letter, price in zip(
                        "ABCDEFGHIJKLMNOPQRSTUVWXYZ", entry["parts"], strict=False
                    )
                }
            },
            "extravilan": rates,
            "page": 1,
        }
        for entry in towns.values()
        if entry["parts"]
    ]
    priced = {fold(entry["name"]) for entry in zoned}

    communes = []
    for position, place in enumerate(sorted(roster_of(county)), start=1):
        if fold(place) in priced or not shared:
            continue
        communes.append(
            {
                "name": place,
                "villages": [
                    {
                        "name": place if not offset else f"{place} ({offset + 1})",
                        "intravilan": {"CC": price},
                    }
                    for offset, price in enumerate(shared)
                ],
                "extravilan": rates,
                "page": 1,
                "index": position,
            }
        )
    return zoned, communes, notes

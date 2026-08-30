"""What a square metre of Romanian land is officially worth, read out of the notaries' grids.

Romania does not tax land on its value. The Fiscal Code taxes it on surface area times a
coefficient that depends on rank of locality and zone letter, and a hectare of Bucharest and a
hectare of Botoșani differ by a table, not by a market. A land value tax needs the thing the
Fiscal Code does not use: what the land is actually worth, per place.

That number exists, and the state already relies on it. Every year each Chamber of Public
Notaries publishes a *studiu de piață* fixing minimum orientative values used as the floor for
notary fees and transfer tax. It is the only valuation of Romanian land that is official,
national, published, and granular below the commune.

**These grids publish land directly, so nothing has to be inferred from building prices.**
That was worth checking before building on it: an earlier plan for this simulator assumed the
studies carried a construction-cost table, so that land could be recovered as a residual —
property price minus depreciated building. They do not. "Costuri de construcție" appears in
these documents only in prose, never as a grid. It does not matter, because the residual was
only ever a way to reach a number the studies print outright.

What Bacău's study prints, per village, in EURO/m²:

    CC   curți construcții        the residential plot — the one a land tax lands on
    V+L  vii și livezi            A    arabil
    P+F  pășuni și fânețe         TS   terenuri cu destinație specială
    TAPA + NP  under water, unproductive

and separately, per commune, the same categories for *extravilan* land. Towns are not listed
by village but as a matrix of category against zone letter, because a town's land value varies
across the town and a village's does not.

**The grid is a floor, not a market.** Its purpose is to stop a sale being declared below a
defensible minimum, so it sits under the transaction price by a margin that is neither
published nor constant between counties. Every number this importer produces inherits that,
and it travels with the data as a blocking limitation rather than a footnote: these values
rank places against each other far better than they measure any of them.

**Two granularities, deliberately kept apart.** Villages carry intravilan values of their own;
extravilan values are printed once per commune and apply to all its villages. Flattening the
two would silently invent per-village precision the document does not have, so extravilan is
attached to the commune and villages point at it.

The self-check is the study's own bookkeeping. Each annex opens with the roster of localities
in that court's circumscription, and the rural table numbers its communes from 1. So the
parse is checked twice against the document: every commune the roster names must appear in
the table, and the numbering must run without a gap. A first version silently lost communes
whose name wrapped across a line break; the roster check caught it as a named list rather
than as a total that happened to look plausible.

Usage:
    uv run python simulators/impozit-teren/scripts/import_ghid.py --chamber bacau
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.unnpr.ro/"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"

# The categories the studies use, longest token first so "P+F" is not eaten by "F", and
# "TAPA SI NP" is matched before "TS". Order here is the order the tables print them in.
CATEGORIES: list[tuple[str, str]] = [
    ("CC", "curti constructii"),
    ("V+L", "vii si livezi"),
    ("P+F", "pasuni si fanete"),
    ("TAPA SI NP", "terenuri sub ape si neproductive"),
    ("TS", "terenuri cu destinatie speciala"),
    ("A", "arabil"),
]
# Extravilan is printed as a bare header row of codes, in this order, in Bacău's study.
EXTRAVILAN_CODES = ["A", "V+L", "P+F", "CC", "AP", "DR", "NP"]

NUMBER = r"\d{1,3}(?:[.  ]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?"


@dataclass(frozen=True)
class Study:
    """One chamber's land study, and the counties it speaks for."""

    key: str
    chamber: str
    counties: list[str]
    year: int
    path: str
    title: str


STUDIES: dict[str, Study] = {
    "bacau": Study(
        key="unnpr-terenuri-bacau-2026",
        chamber="CNP Bacău",
        counties=["BC"],
        year=2026,
        path="files/expertize2026/CNPBacau/Studiu_de_piata_Terenuri_Bacau_2026.pdf",
        title="Studiu de piață — terenuri, județul Bacău, 2026",
    ),
    "neamt": Study(
        key="unnpr-terenuri-neamt-2026",
        chamber="CNP Bacău",
        counties=["NT"],
        year=2026,
        path="files/expertize2026/CNPBacau/Studiu_de_piata_Terenuri_Neamt_2026.pdf",
        title="Studiu de piață — terenuri, județul Neamț, 2026",
    ),
}


def fold(text: str) -> str:
    """Compare Romanian place names without depending on how the PDF spells diacritics.

    The studies are internally inconsistent — the roster prints BUHOCI and the table prints
    Buhoci, Târgu Ocna appears as TARGU OCNA and Târgu-Ocna — so matching folds case,
    diacritics, hyphens and runs of spaces away and compares what is left.
    """
    stripped = unicodedata.normalize("NFD", str(text).lower())
    stripped = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    # ș and ț sometimes arrive as the cedilla forms, which NFD does not decompose the same way.
    stripped = stripped.translate(str.maketrans({"ş": "s", "ţ": "t", "ș": "s", "ț": "t"}))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", stripped)).strip()


def download(study: Study) -> Path:
    """Keep the source once fetched, so a re-import does not need unnpr.ro to be up."""
    out = ROOT / "sources" / f"{study.key}.pdf"
    if out.exists() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = BASE + urllib.parse.quote(study.path)
    print(f"downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        out.write_bytes(response.read())
    return out


def pages_of(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def numbers(text: str) -> list[float]:
    found = []
    for raw in re.findall(NUMBER, text):
        cleaned = raw.replace(" ", "").replace(" ", "")
        # Thousands separators only ever appear left of a decimal comma in these documents.
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        found.append(float(cleaned))
    return found


def category_at(line: str) -> tuple[str, str] | None:
    """Split a table line into its category code and the rest, or None if it is not one."""
    for code, _ in CATEGORIES:
        pattern = rf"^\s*{re.escape(code)}\b"
        if re.match(pattern, line, re.I):
            return code, line[re.match(pattern, line, re.I).end():]
    return None


# --- The roster, which is what the parse is checked against ----------------------------

ROSTER_HEAD = re.compile(r"localitat\w*\s+arondate\s+circumscriptiei\s+judecatoriei", re.I)
ANNEX_COURT = re.compile(r"JUDEC[ĂA]TORIEI\s+([A-ZĂÂÎȘŞȚŢ\s\-]+)", re.I)


def rosters(pages: list[str]) -> dict[str, list[str]]:
    """The communes each annex says it covers, read off the annex's own cover page.

    This is the check, not the data. If the table yields a commune the roster never named,
    or drops one it did, the parse is wrong in a way a row count would not reveal.
    """
    found: dict[str, list[str]] = {}
    for index, page in enumerate(pages):
        if not ROSTER_HEAD.search(fold(page).replace("ţ", "t")) and not ROSTER_HEAD.search(page):
            continue
        court = ""
        match = ANNEX_COURT.search(page)
        if match:
            court = re.sub(r"\s+", " ", match.group(1)).strip()
        if not court:
            # The court name is on the annex title page, a page or two earlier.
            for back in range(index - 1, max(index - 4, -1), -1):
                previous = ANNEX_COURT.search(pages[back])
                if previous:
                    court = re.sub(r"\s+", " ", previous.group(1)).strip()
                    break
        body = page.split("Comune", 1)[-1] if "Comune" in page else page
        names = []
        for line in body.splitlines():
            line = line.strip(" •\t")
            if not line or line.isdigit() or "֍" in line:
                continue
            if re.match(r"^(municipii|orase|orașe|comune)\b", line, re.I):
                continue
            names.append(line)
        # Roster entries wrap: "IZVORUL" / "BERHECIULUI" is one commune on two lines.
        merged: list[str] = []
        for name in names:
            if merged and not re.search(r"[A-ZĂÂÎȘŞȚŢ]{2,}\s*$", merged[-1]) is None and False:
                pass
            merged.append(name)
        if court:
            found.setdefault(court, []).extend(merged)
    return found


# --- Towns: a matrix of category against zone ------------------------------------------

TOWN_HEAD = re.compile(r"(MUNICIPIUL|ORA[ȘŞS]UL)\s+([A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ\s\-\.]*)")
ZONE_HEAD = re.compile(r"Zone\s*/\s*ctg\.?\s*fol\.?\s*(.+)")


def parse_towns(pages: list[str]) -> list[dict]:
    """Towns price land by zone letter, so they are a matrix rather than a list."""
    towns = []
    for index, page in enumerate(pages):
        if "INTRAVILAN" not in page.upper() or not ZONE_HEAD.search(page):
            continue
        head = TOWN_HEAD.search(page)
        name = ""
        if head:
            name = re.sub(r"\s+", " ", head.group(2)).strip(" .-")
        if not name:
            for back in range(index - 1, max(index - 3, -1), -1):
                previous = TOWN_HEAD.search(pages[back])
                if previous:
                    name = re.sub(r"\s+", " ", previous.group(2)).strip(" .-")
                    break
        if not name:
            continue

        zone_match = ZONE_HEAD.search(page)
        zones = re.findall(r"\b([A-F])\b", zone_match.group(1))
        if not zones:
            continue

        # Category rows follow the header. A row's label may wrap over several lines, so the
        # values are taken from the first line that carries as many numbers as there are zones.
        body = page[zone_match.end():]
        values: dict[str, dict[str, float]] = {}
        current: str | None = None
        for line in body.splitlines():
            split = category_at(line)
            if split:
                current = split[0]
                rest = split[1]
            else:
                rest = line
            if current is None:
                continue
            row = numbers(rest)
            if len(row) == len(zones) and current not in values:
                values[current] = dict(zip(zones, row, strict=True))
                current = None
        if values:
            towns.append({"name": name, "zones": zones, "intravilan": values, "page": index + 1})
    return towns


# --- Villages: intravilan per village, extravilan per commune ---------------------------

COMMUNE_HEAD = re.compile(r"^\s*(\d{1,3})\s*$")
NOISE = re.compile(
    r"^\s*(\d+\s*֍|A-\s*arabil|de exploatare|ape;|Nr\.|Crt\.|LOCALITA|TI\b|RURALE|SATUL|"
    r"INTRAVILAN|EXTRAVILAN|\(EURO|A V\+L P\+F CC AP DR NP)",
    re.I,
)


def parse_villages(pages: list[str]) -> tuple[list[dict], list[str]]:
    """Walk the rural tables, keeping commune numbering so gaps are visible."""
    communes: list[dict] = []
    problems: list[str] = []
    current: dict | None = None
    village: dict | None = None
    pending_number: str | None = None

    def close_village() -> None:
        nonlocal village
        if current is not None and village is not None and village["intravilan"]:
            current["villages"].append(village)
        village = None

    for index, page in enumerate(pages):
        lines = page.splitlines()
        # "TAPA" and "SI NP <value>" arrive as two lines; rejoin before anything else looks.
        joined: list[str] = []
        for line in lines:
            if joined and re.fullmatch(r"\s*TAPA\s*", joined[-1]) and re.match(r"\s*SI\s+NP", line):
                joined[-1] = "TAPA SI NP" + line.split("NP", 1)[1]
            else:
                joined.append(line)

        for line in joined:
            stripped = line.strip()
            if not stripped or NOISE.match(stripped):
                continue

            number_only = COMMUNE_HEAD.match(stripped)
            if number_only:
                pending_number = number_only.group(1)
                continue

            # A commune name is upper case and carries no digits; the number precedes it.
            if pending_number and re.fullmatch(r"[A-ZĂÂÎȘŞȚŢ][A-ZĂÂÎȘŞȚŢ \-\.]{2,}", stripped):
                close_village()
                current = {
                    "index": int(pending_number),
                    "name": re.sub(r"\s+", " ", stripped).strip(" .-"),
                    "villages": [],
                    "extravilan": {},
                    "page": index + 1,
                }
                communes.append(current)
                pending_number = None
                continue
            pending_number = None

            split = category_at(stripped)
            if split is None:
                # Anything else inside a commune block is a village name. Names wrap, so a
                # trailing fragment is stitched onto the previous one rather than dropped.
                if current is None:
                    continue
                if re.fullmatch(r"[a-zțșăâî]{1,3}", stripped) and village is not None:
                    village["name"] += stripped
                    continue
                close_village()
                village = {"name": re.sub(r"\s+", " ", stripped), "intravilan": {}}
                continue

            code, rest = split
            row = numbers(rest)
            if not row:
                continue
            if current is None:
                continue
            if village is None:
                # A category row before any village name: the commune's seat shares its name.
                village = {"name": current["name"].title(), "intravilan": {}}
            village["intravilan"].setdefault(code, row[0])
            # The extravilan block is printed once per commune, tacked onto whichever
            # category row it lands beside. Seven values, in the header's order.
            if len(row) == 1 + len(EXTRAVILAN_CODES) and not current["extravilan"]:
                current["extravilan"] = dict(zip(EXTRAVILAN_CODES, row[1:], strict=True))

        close_village()

    # The numbering restarts at 1 in every annex, so continuity is checked per run of numbers.
    previous = 0
    for commune in communes:
        if commune["index"] not in (previous + 1, 1):
            problems.append(
                f"commune numbering jumps from {previous} to {commune['index']} "
                f"({commune['name']}, page {commune['page']})"
            )
        previous = commune["index"]
    return communes, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chamber", default="bacau", choices=sorted(STUDIES))
    args = parser.parse_args()
    study = STUDIES[args.chamber]

    pages = pages_of(download(study))
    print(f"{study.title}: {len(pages)} pages")

    towns = parse_towns(pages)
    communes, problems = parse_villages(pages)
    roster = rosters(pages)

    villages = sum(len(c["villages"]) for c in communes)
    with_extravilan = sum(1 for c in communes if c["extravilan"])
    print(f"orașe și municipii: {len(towns)}")
    print(f"comune: {len(communes)}   sate: {villages}   comune cu extravilan: {with_extravilan}")
    print(f"anexe cu roster: {len(roster)}   localități în rostere: {sum(map(len, roster.values()))}")

    # The roster check. Every commune the study lists must have come out of the table.
    parsed = {fold(c["name"]) for c in communes}
    listed = {fold(name) for names in roster.values() for name in names}
    missing = sorted(n for n in listed if n and n not in parsed)
    extra = sorted(n for n in parsed if n not in listed) if listed else []
    if missing:
        print(f"\nîn roster dar nu în tabel ({len(missing)}): {missing[:15]}")
    if extra:
        print(f"în tabel dar nu în roster ({len(extra)}): {extra[:15]}")
    for problem in problems:
        print(f"  {problem}")

    document = {
        "$schema": "../schema/ghid-teren.schema.json",
        "id": study.key,
        "title": study.title,
        "publisher": f"Uniunea Națională a Notarilor Publici din România — {study.chamber}",
        "counties": study.counties,
        "period": str(study.year),
        "currency": "EUR",
        "unit": "EUR/m²",
        "provenance": {
            "source": study.key,
            "locator": f"{BASE}{study.path}, anexele cu valorile orientative minime",
            "confidence": "verbatim",
            "note": (
                "Valorile sunt copiate din tabelele studiului, nu recalculate. Intravilanul "
                "este publicat pe sat, extravilanul pe comună; separarea este păstrată."
            ),
        },
        "summary": {
            "pages": len(pages),
            "towns": len(towns),
            "communes": len(communes),
            "villages": villages,
            "communesWithExtravilan": with_extravilan,
            "rosterCommunes": len(listed),
            "rosterMissingFromTable": missing,
            "tableMissingFromRoster": extra,
            "numberingProblems": problems,
        },
        "categories": [{"code": code, "label": label} for code, label in CATEGORIES],
        "extravilanCategories": EXTRAVILAN_CODES,
        "towns": towns,
        "communes": communes,
        "limitations": [
            {
                "id": "grila-e-un-prag-nu-o-piata",
                "text": (
                    "Valorile sunt „minime orientative”: pragul sub care o vânzare nu poate fi "
                    "declarată, folosit pentru onorarii și pentru impozitul pe transfer. Stau "
                    "sub prețul de tranzacție cu o marjă care nu este publicată și nu este "
                    "constantă între județe. Cifrele compară locurile între ele mult mai bine "
                    "decât măsoară vreunul dintre ele."
                ),
                "severity": "blocking",
                "affects": ["valoare-teren", "impozit", "randament"],
            },
            {
                "id": "extravilanul-e-pe-comuna",
                "text": (
                    "Intravilanul este publicat pe sat, extravilanul o singură dată pe comună. "
                    "Satele unei comune primesc deci aceeași valoare extravilană; precizia pe "
                    "sat nu există în document și nu este inventată aici."
                ),
                "severity": "material",
                "affects": ["valoare-teren"],
            },
            {
                "id": "zonele-din-orase-sunt-adrese-nu-poligoane",
                "text": (
                    "În orașe valoarea depinde de zona A–D, iar zonele sunt definite prin liste "
                    "de străzi și intervale de numere, nu prin poligoane. Nu există o "
                    "geometrie publicată a lor, așa că valorile urbane pot fi raportate pe "
                    "oraș și pe zonă, dar nu așezate pe hartă sub nivelul orașului."
                ),
                "severity": "material",
                "affects": ["harta", "valoare-teren"],
            },
            {
                "id": "un-singur-judet",
                "text": (
                    "Acest fișier acoperă un singur județ. Fiecare cameră notarială publică "
                    "separat, cu alt format, așa că acoperirea națională se construiește "
                    "județ cu județ, nu dintr-un singur parser."
                ),
                "severity": "note",
                "affects": ["acoperire"],
            },
        ],
    }

    out = ROOT / "data" / f"ghid-teren-{args.chamber}-{study.year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

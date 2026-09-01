"""The tax Romania actually charges on land, read out of the Fiscal Code itself.

Article 465 of Legea 227/2015 never asks what a piece of land is worth. It multiplies hectares
by a figure from a table indexed on the **rank of the locality**, the **zone** the council has
drawn, and the **category of use**. A hectare of Bucharest and a hectare of Botoșani differ by
a row, and two neighbouring plots on the same street differ by nothing at all.

Five tables are needed to reproduce it, and they are read rather than typed:

    art. 465 (2)   intravilan, terenuri cu construcții — lei/ha by zone × rank
    art. 465 (4)   intravilan, every other category    — lei/ha by category × zone
    art. 465 (5)   correction coefficient by rank, applied to (4)
    art. 465 (7)   extravilan — lei/ha by category
    art. 457 (6)   correction coefficient by zone × rank, applied to (7)

**The Code does not state a tax; it states a range.** Article 465 (2) gives 8 282–20 706
lei/ha for zone A of a rank-0 locality, and paragraph (9) leaves the choice inside that range
to the local council. The same is true of the extravilan table. So "what Romania charges
today" is not one number either, and this file keeps both ends rather than picking a midpoint
and calling it the law.

Two of these tables were replaced with effect from 1 January 2026 by Legea 239/2025 — which is
exactly why they are parsed from the consolidated text on the official legislative portal
instead of being copied from a version of the Code that was current when the code was written.
The amendment notes travel with the tables so a reader can see which text was in force.

Usage:
    uv run python simulators/impozit-teren/scripts/import_cod_fiscal.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The consolidated Fiscal Code on the Ministry of Justice's legislative portal. The
# consolidated form matters more than the original: article 465's tables have been replaced
# three times since 2015, most recently with effect from 1 January 2026.
URL = "https://legislatie.just.ro/Public/DetaliiDocument/171282"
SOURCE = ROOT / "sources" / "cod-fiscal-consolidat.html"
# The portal serves an error page to anything that does not look like a browser.
UA = "Mozilla/5.0 (X11; Linux x86_64) romania-reforms/0.1 (+https://github.com/CristianNichifor)"

ZONES = ["A", "B", "C", "D"]
RANKS = ["0", "I", "II", "III", "IV", "V"]

# The Code's category names against the codes the notaries' grids use, so the two taxes can
# later be computed on the same hectares. Beach and "teren cu construcții" have no counterpart
# in the extravilan grid and are carried unmapped rather than forced onto a neighbour.
TO_NOTARY = {
    "Teren arabil": "A",
    "Pășune": "P+F",
    "Fâneață": "P+F",
    "Vie": "V+L",
    "Livadă": "V+L",
    "Pădure sau alt teren cu vegetație forestieră": "PADURE",
    "Teren cu apă": "AP",
    "Drumuri și căi ferate": "DR",
    "Teren neproductiv": "NP",
    "Teren cu construcții": "CC",
}


def download() -> str:
    """The consolidated Fiscal Code, retried, because the portal hangs up.

    A CI run died on `RemoteDisconnected: Remote end closed connection without response`
    partway through 7,6 MB from legislatie.just.ro. Nothing was wrong with the request — the
    same one succeeds on the next attempt — so a single hang-up must not fail a build.

    Not cached in git, unlike the pension law that this repository does commit for the same
    class of reason. That file is 235 KB and this one is 7,6 MB, which is a different trade:
    cheap insurance at a quarter of a megabyte, and a third of the repository at seven and a
    half. A partial write is deleted rather than left, because a truncated 7 MB page parses
    into a Fiscal Code with some articles missing and no error anywhere.
    """
    for retry in range(4):
        if SOURCE.exists():
            break
        print(f"downloading {URL} ...")
        try:
            request = urllib.request.Request(URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
                body = response.read()
            SOURCE.parent.mkdir(parents=True, exist_ok=True)
            SOURCE.write_bytes(body)
        except OSError as error:
            SOURCE.unlink(missing_ok=True)
            print(f"  attempt {retry + 1} failed: {error}", file=sys.stderr)
            time.sleep(5 * (retry + 1))
    if not SOURCE.exists():
        raise SystemExit(f"could not download {URL} after 4 attempts")
    return SOURCE.read_text(encoding="utf-8", errors="ignore")


def plain(page: str) -> str:
    """The portal's markup carries one table cell per element; strip to one per line."""
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]+", " ", text))


def section(text: str, start: str, end: str) -> str:
    first = text.find(start)
    if first < 0:
        raise SystemExit(f"Fiscal Code: cannot find {start!r}; the portal's text has changed")
    stop = text.find(end, first)
    return text[first : stop if stop > 0 else first + 40_000]


RANGE = re.compile(r"^(\d[\d ]*)\s*[-–]\s*(\d[\d ]*)$")
INTEGER = re.compile(r"^\d[\d ]*$")
DECIMAL = re.compile(r"^\d+,\d+$")


def cells(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if line.strip()]


def money(token: str) -> tuple[int, int]:
    """A cell of the Code is a range; a single figure is a range with no width."""
    match = RANGE.match(token)
    if match:
        return int(match.group(1).replace(" ", "")), int(match.group(2).replace(" ", ""))
    if INTEGER.match(token):
        value = int(token.replace(" ", ""))
        return value, value
    raise ValueError(token)


def table_465_2(text: str) -> dict:
    """Intravilan building land: lei/ha, zone against rank, as a range per cell."""
    block = section(text, "Zona în \ncadrul \nlocalității", "(2^1)")
    tokens = [t for t in cells(block) if RANGE.match(t) or INTEGER.match(t)]
    tokens = [t for t in tokens if t not in RANKS]
    if len(tokens) != len(ZONES) * len(RANKS):
        raise SystemExit(f"art. 465 (2): expected 24 cells, read {len(tokens)}")
    values: dict[str, dict[str, dict[str, int]]] = {}
    for row, zone in enumerate(ZONES):
        values[zone] = {}
        for column, rank in enumerate(RANKS):
            low, high = money(tokens[row * len(RANKS) + column])
            if low > high:
                raise SystemExit(f"art. 465 (2): {zone}/{rank} range runs backwards")
            values[zone][rank] = {"min": low, "max": high}
    return values


def table_465_4(text: str) -> dict:
    """Intravilan, other categories: lei/ha, category against zone, a single figure."""
    block = section(text, "Nr. crt.\nZona Categoria de folosință", "(5)")
    lines = cells(block)
    values: dict[str, dict[str, int]] = {}
    current: str | None = None
    row: list[int] = []
    for line in lines:
        if re.fullmatch(r"\d+\.", line):
            current, row = None, []
            continue
        if INTEGER.match(line) and current:
            row.append(int(line.replace(" ", "")))
            if len(row) == len(ZONES):
                values[current] = dict(zip(ZONES, row, strict=True))
                current, row = None, []
        elif not INTEGER.match(line) and line not in ZONES:
            current, row = line.strip(), []
    if len(values) < 9:
        raise SystemExit(f"art. 465 (4): expected 10 categories, read {sorted(values)}")
    return values


def coefficients_465_5(text: str) -> dict[str, float]:
    block = section(text, "Rangul localității\nCoeficientul de corecție", "(6)")
    numbers = [t for t in cells(block) if DECIMAL.match(t)]
    if len(numbers) != len(RANKS):
        raise SystemExit(f"art. 465 (5): expected 6 coefficients, read {len(numbers)}")
    values = dict(zip(RANKS, (float(n.replace(",", ".")) for n in numbers), strict=True))
    ordered = list(values.values())
    if ordered != sorted(ordered, reverse=True):
        raise SystemExit("art. 465 (5): coefficients are not ordered by rank")
    return values


def table_465_7(text: str) -> dict:
    """Extravilan: lei/ha by category, before the zone-and-rank coefficient."""
    block = section(text, "Nr. crt.\nCategoria de folosință\nImpozit (lei)", "(7^1)")
    lines = cells(block)
    values: dict[str, dict[str, int]] = {}
    current: str | None = None
    for line in lines:
        if re.fullmatch(r"\d+\.", line):
            current = None
            continue
        if (RANGE.match(line) or INTEGER.match(line)) and current:
            low, high = money(line)
            values[current] = {"min": low, "max": high}
            current = None
        elif not RANGE.match(line) and not INTEGER.match(line):
            current = line.strip()
    if len(values) < 10:
        raise SystemExit(f"art. 465 (7): expected 11 categories, read {sorted(values)}")
    return values


def coefficients_457_6(text: str) -> dict:
    """The zone-and-rank coefficient article 465 (7) borrows from the buildings article."""
    block = section(
        text,
        "Valoarea impozabilă a clădirii se ajustează în funcție de rangul localității",
        "(6^1)",
    )
    numbers = [t for t in cells(block) if DECIMAL.match(t)]
    if len(numbers) != len(ZONES) * len(RANKS):
        raise SystemExit(f"art. 457 (6): expected 24 coefficients, read {len(numbers)}")
    values: dict[str, dict[str, float]] = {}
    for row, zone in enumerate(ZONES):
        values[zone] = {
            rank: float(numbers[row * len(RANKS) + column].replace(",", "."))
            for column, rank in enumerate(RANKS)
        }
    return values


def normalise(name: str) -> str:
    """Match the Code's category names, which carry trailing spaces and qualifiers."""
    stripped = re.sub(r",.*$", "", name).strip()
    return stripped


def main() -> int:
    text = plain(download())
    land = section(text, "Calculul impozitului/taxei pe teren", "Articolul 466")
    # Article 457, whose zone-and-rank coefficient article 465 (7) borrows. Sliced first
    # because its own table also opens "Zona în cadrul localității" and sits earlier in the
    # document than article 465's — searching the whole text would read the wrong one.
    buildings = section(
        text,
        "Calculul impozitului pe clădirile rezidențiale aflate în proprietatea",
        "Articolul 458",
    )

    built = table_465_2(land)
    other = table_465_4(land)
    rank_coefficients = coefficients_465_5(land)
    extravilan = table_465_7(land)
    zone_rank_coefficients = coefficients_457_6(buildings)

    mapped = {normalise(k): v for k, v in other.items()}
    unmapped = sorted(k for k in mapped if k not in TO_NOTARY)
    print(f"art. 465 (2): {len(built) * len(RANKS)} celule, zone × ranguri")
    print(f"art. 465 (4): {len(other)} categorii × {len(ZONES)} zone")
    print(f"art. 465 (5): {rank_coefficients}")
    print(f"art. 465 (7): {len(extravilan)} categorii")
    print(f"art. 457 (6): {len(zone_rank_coefficients) * len(RANKS)} coeficienți")
    print(f"teren cu construcții, rang 0 / zona A: {built['A']['0']} lei/ha")
    print(f"teren cu construcții, rang V / zona D: {built['D']['V']} lei/ha")
    if unmapped:
        print(f"categorii fără corespondent notarial: {unmapped}")

    document = {
        "$schema": "../schema/cod-fiscal.schema.json",
        "id": "cod-fiscal-teren-2026",
        "title": "Impozitul pe teren — tabelele din Codul fiscal, forma consolidată",
        "publisher": "Parlamentul României",
        "period": "2026",
        "currency": "RON",
        "provenance": {
            "source": "legea-227-2015-cod-fiscal",
            "locator": f"{URL}, art. 465 alin. (2), (4), (5), (7) și art. 457 alin. (6)",
            "confidence": "verbatim",
            "note": (
                "Tabelele sunt citite din forma consolidată de pe portalul legislativ, nu "
                "copiate. Tabelele de la art. 465 alin. (4) și (7) au fost înlocuite de "
                "Legea nr. 239/2025, cu aplicare de la 1 ianuarie 2026."
            ),
        },
        "zones": ZONES,
        "ranks": RANKS,
        "categoryMapping": TO_NOTARY,
        "intravilanBuiltLeiPerHa": built,
        "intravilanOtherLeiPerHa": other,
        "rankCoefficient": rank_coefficients,
        "extravilanLeiPerHa": extravilan,
        "zoneRankCoefficient": zone_rank_coefficients,
        "unmappedCategories": unmapped,
        "limitations": [
            {
                "id": "codul-da-un-interval-nu-o-cota",
                "text": (
                    "Codul fiscal nu stabilește un impozit, ci un interval: art. 465 alin. (2) "
                    "dă 8.282–20.706 lei/ha pentru zona A a unei localități de rang 0, iar "
                    "alin. (9) lasă alegerea din interval consiliului local. La fel și pentru "
                    "extravilan. „Cât se plătește azi” nu este deci un număr, ci o plajă de "
                    "aproximativ 2,5×, iar hotărârile a 3.186 de consilii locale nu sunt "
                    "publicate într-un registru unic."
                ),
                "severity": "blocking",
                "affects": ["impozit"],
            },
            {
                "id": "zonarea-e-decizie-locala",
                "text": (
                    "Încadrarea unui teren în zona A–D este tot o hotărâre a consiliului local "
                    "și nu există un registru național al zonelor sau al suprafețelor lor. "
                    "Impozitul datorat depinde de ea la fel de mult ca de cotă."
                ),
                "severity": "blocking",
                "affects": ["impozit"],
            },
            {
                "id": "rangul-nu-e-in-codul-fiscal",
                "text": (
                    "Rangurile 0–V nu sunt definite în Codul fiscal, ci în Legea nr. 351/2001 "
                    "privind planul de amenajare a teritoriului național. Codul le folosește "
                    "fără să le enumere."
                ),
                "severity": "note",
                "affects": ["impozit"],
            },
        ],
    }

    out = ROOT / "data" / "cod-fiscal-teren-2026.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

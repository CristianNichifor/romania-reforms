"""The paper itself, in its own words, chapter by chapter.

An audit of the page found the imbalance this file exists to correct. Of everything the sidebar
says, 9% was about what the reform proposes and 91% about whether its numbers hold. The
proposals themselves lived in one fold that listed eight chapter headings and their page
numbers and no text at all. Chapters 1, 2, 3, 6, 17, 18 and 19 appeared nowhere except as rows
saying they were not covered.

That is a bad way round. A reader who already knows the proposal got an excellent fact-check; a
reader who did not could not learn from this page what the reform *is*, only that several of its
figures do not survive contact with the sources. It also makes the findings read worse than they
are: a correction looks like an attack when the thing being corrected is invisible.

So this extracts all nineteen chapters as text, and pairs each of the page's findings with the
sentence in the paper it actually tests.

**The claims are located, not retyped.** Each one is found in the chapter's own text by a needle
and sliced out, so a quote cannot drift from the document while the page goes on attributing it.
If a sentence the page argues with ever stops being in the paper, this build fails rather than
letting the argument stand against nothing.

**Which finding tests which sentence is a judgement.** The chapter texts are a reading; the
mapping from a fold to the claim it examines is mine, and it is marked `assumed` for the same
reason the coverage ledger is.

Usage:
    uv run --with pypdf python scripts/build_lucrarea.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "reforma-sistem-judiciar-romania.pdf"
OUT = ROOT / "data" / "lucrarea.json"

# Chapter number -> (title as the ledger prints it, a needle that finds the body heading).
CHAPTERS = {
    1: ("Introducere – De ce avem nevoie de reformă profundă", "Introducere"),
    2: ("Radiografia sistemului judiciar românesc", "Radiografia"),
    3: ("Probleme sistemice care blochează funcționalitatea", "Probleme sistemice"),
    4: ("Modelul danez", "Modelul danez"),
    5: ("Diferențe structurale România – Danemarca", "Diferente structurale"),
    6: ("Viziunea de reformă și principiile noului sistem", "Viziunea de reforma"),
    7: ("Noua arhitectură instituțională", "Noua arhitectura institutionala"),
    8: ("Administrația Națională a Instanțelor", "Administratia Nationala"),
    9: ("Reforma resurselor umane", "Reforma resurselor umane"),
    10: ("Reforma salarizării", "Reforma salarizarii"),
    11: ("Reforma pensiilor", "Reforma pensiilor"),
    12: ("Noua hartă judiciară", "Noua harta judiciara"),
    13: ("Digitalizare și infrastructură", "Digitalizare"),
    14: ("KPI și performanță", "KPI"),
    15: ("Plan de implementare", "Plan de implementare"),
    16: ("Resurse necesare", "Resurse necesare"),
    17: ("Impactul reformei", "Impactul reformei"),
    18: ("Concluzie", "Concluzie"),
    19: ("Sinteză", "Sinteza"),
}

# The contents repeats every heading, so the body is read from where chapter 1 is printed.
BODY_FROM_CHAPTER = 1

# Which finding on the page examines which sentence in the paper.
#
# The fold id, the chapter it argues with, and a needle that locates the sentence inside that
# chapter. The needle is deliberately a fragment: the extraction inserts spaces unpredictably
# around punctuation, and anchoring on a short distinctive run survives that where a whole
# sentence would not.
CLAIMS = {
    "eficienta-fold": (
        12,
        r"176\s*judecatorii\s*→\s*doar\s*20\s*functioneaza\s*eficient",
        "Premisa de eficiență",
    ),
    "danemarca-fold": (
        5,
        r"Romania\s*are\s*de\s*trei\s*ori\s*mai\s*multe\s*instante[^.]{0,90}",
        "Premisa de mărime",
    ),
    "arondare-fold": (
        12,
        r"Nivel\s*1:\s*42\s*judecatorii\s*\+\s*tribunale\s*comasate",
        "Harta de nivel 1",
    ),
    "incarcatura-fold": (
        12,
        r"fiecare\s*deserveste\s*150\.000[–\-\s]*200\.000\s*locuitori",
        "Mărimea unei instanțe",
    ),
    "apel-fold": (12, r"Nivel\s*3:\s*15\s*curti\s*de\s*apel", "Nivelul de apel"),
    "comasare-fold": (
        7,
        r"42\s*parchete\s*judetene\s*\(comasand\s*nivelul\s*de\s*judecatorii\s*\+\s*tribunal\)",
        "Parchetele, în oglindă",
    ),
    "sporuri-fold": (
        10,
        r"Sistemul\s*salarial\s*actual\s*este\s*plin\s*de",
        "Sporurile",
    ),
    "pensii-fold": (
        11,
        r"Pensia\s*=\s*pensie\s*contributiva\s*\+\s*supliment\s*maxim\s*20%",
        "Formula pensiei",
    ),
    "resurse-fold": (
        16,
        r"digitalizare:\s*200-300\s*mil\s*euro",
        "Resursele cerute",
    ),
}



def ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def strip_heading(text: str, title: str) -> str:
    """Remove a chapter's printed title from the head of its own body.

    Consumes leading words of the body for as long as they match the title's words with
    diacritics and punctuation ignored, and stops at the first word that does not. Titles here
    run from one word ("Concluzie") to eight, and the body spells them without diacritics.
    """
    wanted = [w for w in re.split(r"[^0-9A-Za-zĂÂÎȘȚăâîșț]+", ascii_fold(title)) if w]
    words = text.split()
    taken = 0
    for word in words:
        bare = re.sub(r"[^0-9a-z]", "", ascii_fold(word))
        if taken < len(wanted) and bare and bare == wanted[taken]:
            taken += 1
            continue
        break
    if not taken:
        return text.strip()
    # A title like "Introducere – De ce avem nevoie..." leaves its separator behind once the
    # first word matches and the dash does not.
    return re.sub(r"^[\s–—:.\-]+", "", " ".join(words[taken:])).strip()


def clean(text: str) -> str:
    """The extraction puts a newline between almost every word. Rebuild paragraphs.

    Bullets are kept as their own lines because the paper is largely bullet lists and running
    them together would turn a structured proposal into mush.
    """
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*●\s*", "\n● ", text)
    text = re.sub(r"\s*(\d+\.\d+(?:\.\d+)?)\s+", r"\n\n\1 ", text)
    # The PDF breaks numeric ranges across lines — "150.000–\n200.000", "4.000-\n6.000" — and
    # the reconstruction leaves the gap behind. Rejoin them so a range reads as one figure.
    text = re.sub(r"(\d)\s*([–-])\s*\n*\s*(\d)", r"\1\2\3", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main() -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")
    pages = [p.extract_text() or "" for p in PdfReader(str(SOURCE)).pages]
    flat = [re.sub(r"\s+", " ", p) for p in pages]

    def heading_page(number: int, needle: str) -> int:
        found = [
            i
            for i, text in enumerate(flat)
            if re.search(rf"(?<!\d){number}\.\s*{re.escape(needle[:16])}", text, re.I)
        ]
        if not found:
            raise SystemExit(f"chapter {number} ({needle}) is not in the paper")
        return found[-1]

    first_page = heading_page(BODY_FROM_CHAPTER, CHAPTERS[BODY_FROM_CHAPTER][1])

    # One string for the body, with a map from character offset back to the printed page, so a
    # chapter that shares a page with two others still gets the right number.
    body = ""
    page_at: list[tuple[int, int]] = []
    for index in range(first_page, len(pages)):
        page_at.append((len(body), index + 1))
        body += pages[index] + "\n"
    flat_body = re.sub(r"\s+", " ", body)

    # Offsets are taken on the whitespace-collapsed body and mapped back proportionally; the
    # two differ only by runs of whitespace, and the mapping is used for page numbers alone.
    ratio = len(body) / len(flat_body) if flat_body else 1

    def page_of(offset: int) -> int:
        raw = int(offset * ratio)
        page = page_at[0][1]
        for start, number in page_at:
            if start <= raw:
                page = number
            else:
                break
        return page

    # The table of contents runs onto the page chapter 1 starts on, so a first-match search
    # finds chapters 16-19 listed in the contents before chapter 1's actual heading. Anchor on
    # chapter 1's *last* occurrence — the contents lists it once, the body prints it once — and
    # then walk forward, taking each subsequent heading as the first one after the previous.
    # Monotone by construction, and it cannot re-enter the contents.
    def pattern(number: int, needle: str) -> str:
        return rf"(?<!\d){number}\.\s*{re.escape(needle[:16])}"

    first = [m.start() for m in re.finditer(pattern(1, CHAPTERS[1][1]), flat_body, re.I)]
    if not first:
        raise SystemExit("chapter 1 has no heading in the body")
    offsets: dict[int, int] = {1: first[-1]}
    cursor = first[-1]
    for number in sorted(CHAPTERS)[1:]:
        match = re.compile(pattern(number, CHAPTERS[number][1]), re.I).search(flat_body, cursor + 1)
        if not match:
            raise SystemExit(f"chapter {number} has no heading after chapter {number - 1}")
        offsets[number] = match.start()
        cursor = match.start()

    order = sorted(offsets, key=lambda n: offsets[n])
    if order != sorted(CHAPTERS):
        raise SystemExit(f"chapters are out of order in the body: {order}")

    chapters = []
    numbers = sorted(CHAPTERS)
    for i, number in enumerate(numbers):
        start = offsets[number]
        end = offsets[numbers[i + 1]] if i + 1 < len(numbers) else len(flat_body)
        # Drop the chapter's own heading from its body: the section that displays this already
        # shows the number and title, and printing them twice reads as a duplication bug.
        #
        # Done on the flat slice, before `clean` inserts the line breaks that make bullets
        # bullets — `strip_heading` rejoins on spaces, which silently flattened every list in
        # the paper into one paragraph when it ran second.
        #
        # Matched word by word rather than by a lookahead, because the body prints titles
        # without diacritics ("Noua harta judiciara") while the ledger's titles carry them, and
        # because a lookahead for a capital simply stops at the title's own first letter.
        raw = re.sub(rf"^{number}\.\s*", "", flat_body[start:end], count=1)
        text = clean(strip_heading(raw, CHAPTERS[number][0]))
        if len(text) < 40:
            raise SystemExit(f"chapter {number} came out {len(text)} characters long")
        chapters.append(
            {
                "number": number,
                "title": CHAPTERS[number][0],
                "page": page_of(start),
                "characters": len(text),
                "text": text,
            }
        )

    text_of = {c["number"]: c["text"] for c in chapters}
    claims = []
    for fold, (chapter, needle, label) in CLAIMS.items():
        match = re.search(needle, text_of[chapter])
        if not match:
            raise SystemExit(
                f"the sentence {fold} argues with is no longer in chapter {chapter}"
            )
        quote = re.sub(r"\s+", " ", match.group(0)).strip(" .,;")
        claims.append(
            {
                "fold": fold,
                "label": label,
                "chapter": chapter,
                "page": next(c["page"] for c in chapters if c["number"] == chapter),
                "quote": quote,
            }
        )

    total = sum(c["characters"] for c in chapters)
    print(f"{len(chapters)} capitole, {total:,} de caractere\n")
    for c in chapters:
        print(f"  {c['number']:>2}. p.{c['page']:<4}{c['title'][:44]:<46}{c['characters']:>7}")
    print(f"\n{len(claims)} afirmații legate de o secțiune a paginii:")
    for c in claims:
        print(f"  {c['fold']:<18} cap.{c['chapter']:<3} „{c['quote'][:56]}”")

    document = {
        "$schema": "../schema/lucrarea.schema.json",
        "id": "lucrarea",
        "title": "Lucrarea, capitol cu capitol",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": f"Corpul lucrării, de la p. {chapters[0]['page']}",
            "confidence": "verbatim",
            "note": (
                "Textul e extras din PDF și repaginat: extracția pune câte un rând între "
                "aproape fiecare cuvânt, iar aici sunt refăcute paragrafele și listele. "
                "Cuvintele sunt ale lucrării."
            ),
        },
        "chapters": chapters,
        "claims": claims,
        "claimsProvenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": "Citatele sunt localizate în textul capitolului, nu rescrise",
            "confidence": "assumed",
            "note": (
                "Ce afirmație testează fiecare secțiune a paginii e o judecată a autorului "
                "simulatorului. Citatul în sine e decupat din text, deci nu poate să se abată "
                "de la lucrare; asocierea cu o secțiune poate fi discutată."
            ),
        },
        "limitations": [
            {
                "id": "textul-e-repaginat",
                "text": (
                    "PDF-ul extrage cu un rând între aproape fiecare cuvânt, iar paragrafele și "
                    "listele sunt reconstruite aici după punctuație și după bulinele „●”. "
                    "Cuvintele sunt neatinse, așezarea lor în pagină nu."
                ),
                "severity": "material",
                "affects": ["chapters"],
            },
            {
                "id": "asocierea-afirmatie-sectiune-e-o-judecata",
                "text": (
                    "Care propoziție din lucrare e testată de care secțiune a paginii e o "
                    "judecată, nu o lectură. Citatele sunt decupate din text, deci exacte; "
                    "faptul că exact acea propoziție e miza unei secțiuni se poate contesta."
                ),
                "severity": "material",
                "affects": ["claims"],
            },
            {
                "id": "capitolele-fara-cifre-raman-necontrolate",
                "text": (
                    "Șapte capitole nu conțin mărimi de verificat — introducere, diagnostic, "
                    "viziune, impact, concluzie. Sunt reproduse aici integral, dar reproducerea "
                    "nu e o verificare: simulatorul nu are ce să le confrunte."
                ),
                "severity": "note",
                "affects": ["chapters"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The reform's institutional design, quoted and cited — the part no simulation can settle.

Most of the paper is not arithmetic. Whether a court administration should exist, what an ANIR
replaces, how magistrates should enter the profession, what a ten-year transition looks like —
these are design decisions. A simulator can show what they would cost or whom they would
reach; it cannot tell you whether they are right, and one that scored them would be inventing
authority it does not have.

So they are carried as text, quoted from the paper with the page they sit on, next to the
views that do compute something. The reader gets the argument and the arithmetic side by side
and can tell which is which — which is the whole point of keeping them apart.

Usage:
    uv run --with pypdf python scripts/build_design.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "reforma-sistem-judiciar-romania"
SOURCE_FILE = ROOT / f"sources/{SOURCE}.pdf"
OUT = ROOT / "data" / "design-reforma.json"

# The chapters that argue rather than measure. Chapter 12 is deliberately absent: the judicial
# map is modelled, so it belongs in the computed views and would be double-counted here.
CHAPTERS = [
    (7, "Noua arhitectura institutionala", "Noua arhitectură instituțională"),
    (8, "Administratia Nationala a Instantelor", "ANIR — administrația instanțelor"),
    (9, "Reforma resurselor umane", "Resurse umane: INM, acces lateral, personal auxiliar"),
    (10, "Reforma salarizarii", "Salarizarea magistraților"),
    (11, "Reforma pensiilor", "Pensiile de serviciu"),
    (13, "Digitalizare si infrastructura", "Digitalizare și infrastructură"),
    (14, "KPI si performanta", "KPI și performanță"),
    (15, "Plan de implementare", "Plan de implementare (10 ani)"),
]

WORDS = 55


def main() -> int:
    if not SOURCE_FILE.exists():
        raise SystemExit(f"Missing {SOURCE_FILE}")
    reader = PdfReader(str(SOURCE_FILE))
    pages = [
        re.sub(r"\s+", " ", (page.extract_text() or "").replace("\n", " "))
        for page in reader.pages
    ]

    chapters = []
    missing = []
    for number, needle, title in CHAPTERS:
        for index, text in enumerate(pages):
            # Skip the table of contents, which repeats every heading.
            if index < 5:
                continue
            found = re.search(rf"(?<!\d){number}\.\s+{needle}", text, re.I)
            if not found:
                continue
            tail = text[found.end() :].split()
            # The heading often runs past what the pattern matches — "7. Noua arhitectura
            # institutionala" continues "a sistemului judiciar" — so the excerpt would open
            # mid-title. Drop the lower-case tail until a sentence actually starts.
            while tail and not tail[0][:1].isupper():
                tail.pop(0)
            excerpt = " ".join(tail[:WORDS]).strip()
            chapters.append(
                {
                    "number": number,
                    "title": title,
                    "page": index + 1,
                    "excerpt": excerpt,
                    "provenance": {
                        "source": SOURCE,
                        "locator": f"Capitolul {number}, p. {index + 1}",
                        "confidence": "verbatim",
                    },
                }
            )
            break
        else:
            missing.append(f"chapter {number} ({needle})")

    if missing:
        print("not found: " + ", ".join(missing), file=sys.stderr)
        return 1

    document = {
        "$schema": "../schema/design.schema.json",
        "id": "design-reforma",
        "title": "Ce propune reforma, dincolo de cifre",
        "publisher": "Cristian Nichifor",
        "published": False,
        "provenance": {
            "source": SOURCE,
            "locator": "capitolele 7-11 și 13-15",
            "confidence": "verbatim",
            "note": (
                "Text citat din propunere, nu calculat. Simulatorul poate arăta ce costă sau "
                "pe cine atinge o decizie de arhitectură, dar nu poate stabili dacă e bună."
            ),
        },
        "chapters": chapters,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(chapters)} chapters -> {OUT.relative_to(ROOT.parent.parent)}")
    for chapter in chapters:
        print(f"  ch{chapter['number']:>2} p{chapter['page']:>3}  {chapter['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

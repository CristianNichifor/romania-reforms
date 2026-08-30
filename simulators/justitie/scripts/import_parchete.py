"""The prosecution service: the half of the reform this simulator had never modelled.

Section 7.3 of the paper reorganises the parchete in parallel with the courts — 42 county
prosecution offices merging the judecatorie and tribunal levels, 15 appellate offices, and the
Public Ministry above them. Everything here has been about courts. This reads the other side.

The CSM report prints the staffing table by level (p. 93), and it is internally consistent:
683 + 264 + 719 + 1.386 = 3.052 posts, and the vacancies sum to 765 the same way.

**Two of the report's own totals do not reconcile, and both are carried as found.** The table
says 3.052 posts and 765 vacant, which leaves 2.287 filled; the prose on the same page says
2.293. The six-post difference is the reserve-fund posts of art. 147, which the two counts
treat differently. Separately, the auxiliary paragraph gives 1.435 posts, 1.353 filled and 137
vacant — and 1.353 + 137 is 1.490, not 1.435. Neither is corrected here. A source that
disagrees with itself is a fact about the source, and quietly picking the number that adds up
would hide it.

What the paper's merger touches is the bottom two levels: 1.386 + 719 = 2.105 prosecutor posts
in offices attached to judecatorii and tribunale, against 42 county offices. The appellate
level it leaves at 15, which is what already exists.

Usage:
    uv run --with pypdf python scripts/import_parchete.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "csm-starea-justitiei-2025.pdf"
OUT = ROOT / "data" / "parchete-2025.json"

MONTHS = 12

LEVELS = [
    ("piccj", r"PÎCCJ \(inclusiv DNA, DIICOT şi Secţia parchetelor militare\)"),
    ("curte-de-apel", r"Parchetele de pe lângă curţile de apel \(inclusiv PCMA\)"),
    ("tribunal", r"Parchetele de pe lângă tribunale \(inclusiv PTMT şi PTMF\)"),
    ("judecatorie", r"Parchetele de pe lângă judecătorii"),
]

# The prosecution grades pay a shade under the judicial ones at every level.
GRADE_OF_LEVEL = {
    "piccj": "Procuror cu grad de PICCJ",
    "curte-de-apel": "Procuror cu grad de curte de apel",
    "tribunal": "Procuror cu grad de tribunal",
    "judecatorie": "Procuror cu grad de judecătorie",
}


def main() -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")
    text = re.sub(
        r"\s+", " ", " ".join((p.extract_text() or "") for p in PdfReader(str(SOURCE)).pages)
    )

    # Scope every lookup to the December table, and to that one specifically.
    #
    # Two traps sit here. The level names also head chapters II.1.4 and II.2.4 hundreds of pages
    # earlier, so a document-wide search matched those and the rows summed to 3.060 against the
    # table's 3.052. And the chapter prints the same table twice — once for January and once for
    # 31 December — so anchoring on the header alone lands on January's 3.071 posts, which are
    # a different year's staffing wearing the same shape. The December sentence is the anchor.
    december = text.find("La data de 31 decembrie 2025, la nivelul parchetelor")
    if december < 0:
        print("the December staffing sentence is gone; refusing to guess", file=sys.stderr)
        return 1
    anchor = text.find("Categoria Posturi de procuror prevăzute în schemă", december)
    if anchor < 0:
        print("the prosecution staffing table's header changed", file=sys.stderr)
        return 1
    table = text[anchor : anchor + 4000]

    levels = []
    for key, label in LEVELS:
        # Posts then vacancies, each as total / execution / art. 147 / management. The
        # extraction splits some cells, so only the two totals are taken by position and the
        # rest is left alone.
        match = re.search(label + r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s", table)
        if not match:
            print(f"the prosecution table no longer has a row for {key}", file=sys.stderr)
            return 1
        posts, vacant = int(match.group(1)), int(match.group(5))
        levels.append(
            {
                "level": key,
                "posts": posts,
                "vacant": vacant,
                "filled": posts - vacant,
            }
        )

    posts_total = sum(row["posts"] for row in levels)
    vacant_total = sum(row["vacant"] for row in levels)
    stated = re.search(r"erau ocupate (\d+) posturi .{0,200}?şi vacante (\d+) de posturi", text)
    if not stated:
        print("the prose totals changed; refusing to guess", file=sys.stderr)
        return 1
    stated_filled, stated_vacant = int(stated.group(1)), int(stated.group(2))
    if posts_total != 3052 or vacant_total != stated_vacant:
        print(f"table sums to {posts_total} posts / {vacant_total} vacant, "
              f"prose says 3052 / {stated_vacant}", file=sys.stderr)
        return 1

    auxiliary = re.search(
        r"erau prevăzute în total ([\d.]+) de posturi \(grefier, grefier arhivar și specialist "
        r"IT\), din care ([\d.]+) de posturi erau ocupate, iar (\d+) de posturi vacante",
        text,
    )
    if not auxiliary:
        print("the auxiliary paragraph changed", file=sys.stderr)
        return 1
    aux = {
        "posts": int(auxiliary.group(1).replace(".", "")),
        "filled": int(auxiliary.group(2).replace(".", "")),
        "vacant": int(auxiliary.group(3)),
    }

    central = []
    for label in ("PÎCCJ \\(inclusiv Secția parchetelor militare \\)", "DIICOT", "DNA"):
        found = re.search(label + r"\s+(\d+)\s+(\d+)\s+(\d+)", text)
        if found:
            central.append(
                {
                    "office": label.replace("\\", "").replace("(inclusiv Secția parchetelor militare )", "").strip(),
                    "posts": int(found.group(1)),
                    "filled": int(found.group(2)),
                    "vacant": int(found.group(3)),
                }
            )

    grades = json.loads((ROOT / "data" / "indemnizatii-2022.json").read_text(encoding="utf-8"))
    pay = {}
    for key, needle in GRADE_OF_LEVEL.items():
        match = next((g for g in grades["grades"] if g["name"].startswith(needle)), None)
        if match is None:
            print(f"no pay grade for {key} ({needle})", file=sys.stderr)
            return 1
        pay[key] = match["monthlyLei"]

    wage_bill = 0.0
    for row in levels:
        row["monthlyLei"] = pay[row["level"]]
        row["annualLei"] = round(row["filled"] * pay[row["level"]] * MONTHS)
        wage_bill += row["annualLei"]

    # What the merger touches: the two levels the paper folds into 42 county offices.
    merged = [row for row in levels if row["level"] in ("tribunal", "judecatorie")]
    merged_posts = sum(row["posts"] for row in merged)
    merged_filled = sum(row["filled"] for row in merged)
    merged_bill = sum(row["annualLei"] for row in merged)

    print(f"{'nivel':<16}{'posturi':>9}{'ocupate':>9}{'vacante':>9}{'lei/lună':>10}{'cost anual':>16}")
    for row in levels:
        print(f"{row['level']:<16}{row['posts']:>9}{row['filled']:>9}{row['vacant']:>9}"
              f"{row['monthlyLei']:>10,.0f}{row['annualLei']:>16,.0f}")
    print(f"{'TOTAL':<16}{posts_total:>9}{posts_total - vacant_total:>9}{vacant_total:>9}"
          f"{'':>10}{wage_bill:>16,.0f}")
    print(f"\nproza spune {stated_filled} ocupate; tabelul dă {posts_total - vacant_total} "
          f"(diferență {stated_filled - (posts_total - vacant_total)}, posturi art. 147)")
    print(f"auxiliari la parchete: {aux['posts']} prevăzute, {aux['filled']} ocupate, "
          f"{aux['vacant']} vacante  ({aux['filled'] + aux['vacant'] - aux['posts']:+d} față de total)")
    print(f"\nce comasează 7.3: {merged_posts} posturi la judecătorii+tribunale "
          f"({merged_filled} ocupate, {merged_bill / 1e6:,.0f} mil. lei/an) -> 42 parchete județene")

    document = {
        "$schema": "../schema/parchete.schema.json",
        "id": "parchete-2025",
        "title": "Parchetele: posturi la 31 decembrie 2025 și costul lor de bază",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": "2025",
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Capitolul IV.1, p. 93-94",
            "confidence": "verbatim",
            "note": (
                "Posturile sunt citate din raport. Costul este calculat aici, înmulțind "
                "posturile ocupate cu indemnizația de bază a gradului, din Legea 153/2017."
            ),
        },
        "levels": levels,
        "totals": {
            "posts": posts_total,
            "filled": posts_total - vacant_total,
            "vacant": vacant_total,
            "statedFilled": stated_filled,
            "annualLei": round(wage_bill),
        },
        "auxiliary": aux,
        "centralClerks": central,
        "merger": {
            "posts": merged_posts,
            "filled": merged_filled,
            "annualLei": merged_bill,
            "proposedOffices": 42,
            "provenance": {
                "source": "reforma-sistem-judiciar-romania",
                "locator": "Capitolul 7.3",
                "confidence": "verbatim",
            },
        },
        "limitations": [
            {
                "id": "raportul-nu-se-potriveste-cu-el-insusi",
                "text": (
                    "Tabelul dă 3.052 de posturi și 765 vacante, deci 2.287 ocupate; proza de pe "
                    "aceeași pagină spune 2.293. Diferența de șase posturi vine din cele "
                    "acordate în temeiul art. 147, numărate altfel în cele două locuri. La "
                    "auxiliari, 1.353 ocupate plus 137 vacante fac 1.490, nu 1.435 câte spune "
                    "aceeași frază. Ambele sunt păstrate așa cum sunt: o sursă care nu se "
                    "potrivește cu ea însăși e un fapt despre sursă."
                ),
                "severity": "material",
                "affects": ["cost", "parchete"],
            },
            {
                "id": "piccj-cuprinde-dna-si-diicot",
                "text": (
                    "Linia PÎCCJ include DNA, DIICOT și Secția parchetelor militare, care nu "
                    "sunt parchete de rând și nu intră în comasarea propusă. Cele 683 de "
                    "posturi nu se pot citi ca personalul unui parchet general."
                ),
                "severity": "material",
                "affects": ["cost", "parchete"],
            },
            {
                "id": "doar-indemnizatia-de-baza-la-procurori",
                "text": (
                    "Ca și la judecători, este indemnizația de bază la vârful grilei, în lei "
                    "2022, fără sporuri. Costul real e peste, iar anul grilei nu e anul "
                    "posturilor."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "volumul-parchetelor-e-in-alta-parte",
                "text": (
                    "Fișierul de față ia doar posturile și costul lor. Volumul de activitate și "
                    "încărcătura pe procuror — pe care raportul le dă pe anexe întregi — sunt "
                    "citite și redistribuite pe cele 42 de parchete propuse în "
                    "„parchete-comasare”, nu aici. Cele două nu trebuie citite ca un întreg: "
                    "aici sunt posturi din schemă, acolo procurori care ocupă efectiv un post."
                ),
                "severity": "note",
                "affects": ["parchete"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

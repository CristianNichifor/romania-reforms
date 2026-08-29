"""Put every court on the map, by joining its printed name to the SIRUTA registry.

The CSM report gives caseloads and nothing else. Its own `fara-geografie` limitation says so:
no locations, no population served, so the access cost of closing a courthouse — the distance
a citizen then travels — cannot be read from it. That limitation is why this exists, and it
only lifts halfway. This recovers *where each court is*. What each court **serves** — the
arondare — is set by law, not by this report, and is still missing.

So a location here is `derived`, never `verbatim`. The report did not say Judecatoria Aiud is
in Aiud; the name did, and this file states the reasoning so a reader can reject it.

**The registry comes from the administrative simulator.** `simulators/administrativ` already
carries all 3,186 UATs with their names, counties and administrative rank, and a second copy
would be a second thing to drift. It is read as a file rather than imported as a package: one
consumer is not evidence of a shared abstraction, and if a third simulator needs SIRUTA this
moves to `packages/` then.

Three rules do the work:

1. **A court is named after its seat.** Strip the court-type prefix and what remains is a
   place: `Judecatoria AIUD` is in Aiud.
2. **A county-named court sits in the county seat.** `Tribunalul DOLJ` is in Craiova. This is
   the one genuine assumption, and it is how the court system is actually organised.
3. **Where a name is ambiguous, the court is in the town.** Nineteen names exist in several
   counties at once — there are four Calarasi and five Costesti — and in every one exactly
   one candidate is a municipiu or an oras and the rest are communes. Where that is not true
   the script fails rather than guessing.

   This disambiguates; it does not claim every court is in a town. Five judecatorii sit in
   communes — Cornetu, Gurahont, Liesti, Podu Turcului and Raducaneni — and their names are
   unambiguous, so they never reach this rule. They are also precisely what a consolidation
   reform is about, so seating them correctly matters more than most.

Usage:
    uv run python scripts/locate_instante.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REGISTRY = (
    HERE.parent / "administrativ" / "web" / "public" / "data" / "attributes.json"
)
MANIFEST = HERE.parent / "administrativ" / "web" / "public" / "data" / "manifest.json"
COURTS = HERE / "data" / "instante-2023.json"
OUT = HERE / "data" / "instante-localizate-2023.json"

# Rank 3 is an oras and anything lower is a municipiu; 4 is a commune.
ADMIN_RANK_ORAS = 3

# Prefixes, longest first: "Tribunalul Militar Teritorial" has to be tried before "Tribunalul".
COURT_PREFIXES = (
    "JUDECATORIA ",
    "CURTEA DE APEL ",
    "TRIBUNALUL PENTRU MINORI SI FAMILIE ",
    "TRIBUNALUL MILITAR TERITORIAL ",
    "TRIBUNALUL COMERCIAL ",
    "TRIBUNALUL MILITAR ",
    "TRIBUNALUL ",
)

# Where the printed name and the registry disagree about the same place.
#
# Mostly the definite article: the court is "Judecatoria ODORHEIUL SECUIESC", the commune is
# "Odorheiu Secuiesc". Romanian place names carry the article in some registers and not in
# others, and neither spelling is wrong.
#
# `VTLCEA` is different and worth keeping visible: page 142 of the report — the annex this
# data comes from — prints `Tribunalul VŢLCEA`, with a T-cedilla where an A-circumflex
# belongs, while pages 42, 53 and 125 of the same document print it correctly. The import
# transcribed the page faithfully, which is why the name in `instante-2023.json` is garbled
# and marked `verbatim`. The fix belongs here rather than there: the printed form stays as
# printed, and this records what it was read as.
ALIASES = {
    "VTLCEA": "VALCEA",
    "ODORHEIUL SECUIESC": "ODORHEIU SECUIESC",
    "SANNICOLAUL MARE": "SANNICOLAU MARE",
    "SIMLEUL SILVANIEI": "SIMLEU SILVANIEI",
    "GURA HONT": "GURAHONT",
    "SECTORUL 1 BUCURESTI": "SECTORUL 1",
    "SECTORUL 2 BUCURESTI": "SECTORUL 2",
    "SECTORUL 3 BUCURESTI": "SECTORUL 3",
    "SECTORUL 4 BUCURESTI": "SECTORUL 4",
    "SECTORUL 5 BUCURESTI": "SECTORUL 5",
    "SECTORUL 6 BUCURESTI": "SECTORUL 6",
}

# Bucharest is six sectors and no single seat, so a city-wide court is placed on the city
# rather than on an arbitrary one of them.
BUCHAREST = "B"


def fold(text: str) -> str:
    """Upper-case, unaccented, punctuation-free — the form both sides are compared in.

    The two sources disagree about diacritics in every way available: the registry writes
    `CĂLĂRAȘI` with comma-below, the report writes `CĂLĂRAŞI` with cedilla, and the annex
    sometimes writes neither. Folding all of it away is the only comparison that holds.
    """
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("ş", "s").replace("ţ", "t").replace("Ş", "S").replace("Ţ", "T")
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split())


def strip_status(name: str) -> str:
    for prefix in ("MUNICIPIUL ", "ORASUL ", "ORAS ", "COMUNA "):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def main() -> int:
    for path in (REGISTRY, MANIFEST, COURTS):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document = json.loads(COURTS.read_text(encoding="utf-8"))

    names = registry["name"]
    counties = registry["county"]
    ranks = registry["adminRank"]
    siruta = registry["siruta"]

    by_place: dict[str, list[int]] = {}
    for index, name in enumerate(names):
        by_place.setdefault(strip_status(fold(name)), []).append(index)

    county_code_of = {fold(full): code for code, full in manifest.get("countyNames", {}).items()}
    # A county's seat: its capital. Bucharest's six sectors are all flagged as capitals, so it
    # is excluded here and handled as a city.
    seat_of_county: dict[str, int] = {}
    for index, code in enumerate(counties):
        if code != BUCHAREST and registry["isCapital"][index]:
            seat_of_county.setdefault(code, index)

    located: list[dict] = []
    failed: list[str] = []

    for court in document["courts"]:
        if court["tier"] == "iccj":
            # One court, in Bucharest, and not a candidate for consolidation.
            located.append({**court, "county": BUCHAREST, "siruta": None, "placedBy": "city"})
            continue

        place = fold(court["name"])
        for prefix in COURT_PREFIXES:
            if place.startswith(prefix):
                place = place[len(prefix) :]
                break
        place = ALIASES.get(place, place)

        if place == "BUCURESTI":
            located.append({**court, "county": BUCHAREST, "siruta": None, "placedBy": "city"})
            continue

        candidates = by_place.get(place, [])
        if len(candidates) > 1:
            towns = [i for i in candidates if ranks[i] <= ADMIN_RANK_ORAS]
            if len(towns) != 1:
                failed.append(
                    f"{court['name']}: {len(towns)} towns among "
                    f"{[names[i] for i in candidates]}"
                )
                continue
            candidates = towns

        if len(candidates) == 1:
            index = candidates[0]
            located.append(
                {**court, "county": counties[index], "siruta": siruta[index], "placedBy": "name"}
            )
            continue

        code = county_code_of.get(place)
        if code == BUCHAREST:
            located.append({**court, "county": BUCHAREST, "siruta": None, "placedBy": "city"})
            continue
        if code is not None and code in seat_of_county:
            index = seat_of_county[code]
            located.append(
                {
                    **court,
                    "county": code,
                    "siruta": siruta[index],
                    "placedBy": "county-seat",
                }
            )
            continue

        failed.append(f"{court['name']}: no place called {place!r}")

    print(f"courts: {len(document['courts'])}")
    for how in ("name", "county-seat", "city"):
        print(f"  placed by {how:<12} {sum(1 for c in located if c['placedBy'] == how):>4}")
    print(f"  unplaced             {len(failed):>4}")

    if failed:
        print("\nunplaced:", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nEvery court has to land somewhere or the map argues from a subset while "
            "looking complete. Add an alias rather than dropping the court.",
            file=sys.stderr,
        )
        return 1

    # The check that earns the file's keep. The importer guards its own reading with the
    # report's row numbering; this guards the join by proving nothing was lost or invented:
    # the same courts, the same tiers, the same national caseload as went in.
    before = sorted((c["id"], c["tier"], c["volume"]) for c in document["courts"])
    after = sorted((c["id"], c["tier"], c["volume"]) for c in located)
    if before != after:
        print("FAIL: the join changed the courts themselves", file=sys.stderr)
        return 1

    out = {
        "$schema": "../schema/courts-located.schema.json",
        "id": f"{document['id']}-localizate",
        "title": f"{document['title']} — cu localizare",
        "publisher": document["publisher"],
        "period": document["period"],
        "provenance": {
            "source": document["id"],
            "confidence": "derived",
            "locator": "nume instanță → registrul SIRUTA (simulators/administrativ)",
            "note": (
                "Raportul nu conține localizarea instanțelor. Fiecare instanță a fost "
                "așezată după numele ei: instanța poartă numele localității de sediu, o "
                "instanță numită după un județ stă în reședința lui, iar o instanță stă "
                "într-un municipiu sau oraș, niciodată într-o comună."
            ),
        },
        "nationalAverages": document["nationalAverages"],
        "courts": located,
        # The blocking limitation stays blocking. Knowing where a court *is* says nothing
        # about what it serves, and the access cost of closing one is a question about
        # catchment, not position.
        "limitations": document["limitations"],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(HERE.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

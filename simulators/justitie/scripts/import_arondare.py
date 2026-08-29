"""Which localities belong to which judecătorie — the arondare.

This is the dataset the court map has been missing since it was built. The CSM report says how
much work each court does and nothing about who it serves, and its own `fara-geografie`
limitation says the access cost of closing a courthouse cannot be evaluated without it. The
arondare is not in that report because it is not a statistic: it is set by Government Decision
1217/2023, under art. 42(2) of Legea 304/2022, as a list of localities per court.

With it, "183 courts close" stops being a count and becomes a distance: for every commune in
the country, how much further to the nearest surviving courthouse.

The annex is a flat list, so the structure has to be reconstructed from ordering:

    JUDEŢUL ALBA                  <- county, until the next county header
    1. Judecătoria Alba Iulia     <- court, until the next court header
    cu sediul în municipiul Alba Iulia
    MUNICIPIU                     <- category, ignored except to skip the header line
    1. Alba Iulia                 <- a locality of the court above
    COMUNE
    1. Berghin
    ...

A numbered line is a court when it says so and a locality otherwise, which is the only
ambiguity in the format. Localities are resolved against the SIRUTA registry *within the
current county*, because names repeat across the country and almost never inside one.

**The check that matters is completeness.** Every one of the 3,186 UATs must land in exactly
one judecătorie: the arondare partitions the country, so a missing commune means a parse hole
and a duplicated one means a mis-attributed court. A partial arondare would still draw a map,
and the map would understate what a closure costs.

Usage:
    uv run python scripts/import_arondare.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "hg-1217-2023-arondare"
SOURCE_FILE = ROOT / f"sources/{SOURCE}.pdf"
URL = "https://sgg.gov.ro/1/wp-content/uploads/2023/11/HGANEXA-13.pdf"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"
OUT = ROOT / "data/arondare-2023.json"

REGISTRY = ROOT.parent / "administrativ" / "web" / "public" / "data" / "attributes.json"
MANIFEST = ROOT.parent / "administrativ" / "web" / "public" / "data" / "manifest.json"

COUNTY_HEADER = re.compile(r"^JUDE[ŢT]UL\s+(.+)$", re.I)
BUCHAREST_HEADER = re.compile(r"^MUNICIPIUL\s+BUCURE[ŞS]TI$", re.I)
COURT_HEADER = re.compile(r"^\d+\.\s+Judec[ăa]toria\s+(.+?)\s*$")
NUMBERED = re.compile(r"^(\d+)\.\s+(.+?)\s*$")
CATEGORY = re.compile(r"^(MUNICIPI\w*|ORA[ŞS]\w*|COMUNE|SECTOARE)\s*$", re.I)
SEAT_LINE = re.compile(r"^cu sediu(?:l|rile)?\s+[îi]n\s+(?:municipiul|ora[şs]ul|comuna)?\s*(.+?)\s*$", re.I)

BUCHAREST = "B"

# A locality line can carry a note about a court that is not sitting.
#
# Judecatoria Insuratei exists in law and is suspended: the annex lists its communes twice,
# once under Braila and Faurei as "X - pana la data reluarii activitatii Judecatoriei
# Insuratei", and once under Insuratei itself as "X - in prezent in circumscriptia
# Judecatoriei Braila". The first is where the commune actually goes today; the second is a
# forward reference. Taking both would assign eleven communes twice.
#
# This is also why the CSM report counts 175 judecatorii while the decision defines 176.
CURRENT_HOLDER = re.compile(r"\s+-\s+p[âaă]n[ăa] la data relu[ăa]rii", re.I)
FORWARD_REFERENCE = re.compile(r"\s+-\s+[îi]n prezent [îi]n circumscrip[țţt]ia", re.I)

# Where the decision and the SIRUTA registry spell the same commune differently. Four are the
# a-circumflex orthography and one vowel that shifted; `Petreu` is not a spelling at all — the
# decision names a commune that the registry calls Abramut, and Abramut is the only Bihor
# commune otherwise unaccounted for, so the completeness check is what proves the pairing
# rather than any claim made here.
# Communes the decision does not mention at all. Both were created after it was adopted in
# November 2023, so the arondare simply predates them — a gap in the source rather than in the
# parse. Listed by name so that a *new* hole still fails the completeness check.
CREATED_AFTER_THE_DECISION = {"CAPU CÂMPULUI", "GOLOGANU"}

ALIASES = {
    ("AB", "RIMETEA"): "RAMETEA",
    ("BH", "PETREU"): "ABRAMUT",
    ("BZ", "NAIENI"): "NAENI",
    ("CJ", "RISCA"): "RASCA",
    ("OT", "GIUVARESTI"): "GIUVARASTI",
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("ş", "s").replace("ţ", "t").replace("Ş", "S").replace("Ţ", "T")
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split())


def strip_status(name: str) -> str:
    for prefix in ("MUNICIPIUL ", "ORASUL ", "ORAS ", "COMUNA "):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def download() -> Path:
    if SOURCE_FILE.exists():
        return SOURCE_FILE
    import urllib.request

    print(f"downloading {URL} ...")
    request = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        data = response.read()
    SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_bytes(data)
    return SOURCE_FILE


def main() -> int:
    for path in (REGISTRY, MANIFEST):
        if not path.exists():
            raise SystemExit(f"Missing {path}; export the administrative payload first")

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    code_of_county = {fold(name): code for code, name in manifest.get("countyNames", {}).items()}

    # Locality lookup, per county, so a name that repeats nationally resolves inside its own.
    in_county: dict[tuple[str, str], list[str]] = {}
    for siruta, name, county in zip(
        registry["siruta"], registry["name"], registry["county"], strict=True
    ):
        in_county.setdefault((county, strip_status(fold(name))), []).append(siruta)

    reader = PdfReader(str(download()))
    lines: list[str] = []
    for page in reader.pages:
        lines += [" ".join(x.split()) for x in (page.extract_text() or "").split("\n") if x.strip()]

    county: str | None = None
    court: str | None = None
    courts: dict[str, dict] = {}
    assigned: dict[str, str] = {}
    problems: list[str] = []

    for line in lines:
        if BUCHAREST_HEADER.match(line):
            county = BUCHAREST
            continue
        header = COUNTY_HEADER.match(line)
        if header:
            code = code_of_county.get(fold(header.group(1)))
            if code is None:
                problems.append(f"unknown county header: {line!r}")
            county = code
            continue
        found = COURT_HEADER.match(line)
        if found:
            court = f"Judecătoria {found.group(1)}"
            courts[court] = {
                "name": court,
                "county": county,
                "seatSiruta": None,
                "localities": [],
                "suspended": False,
            }
            continue
        seat = SEAT_LINE.match(line)
        if seat:
            # Key the court to a place, not to its name. The decision writes "Judecatoria
            # Gurahont" and the CSM report "Judecatoria GURA HONT"; eleven of the 176 differ
            # that way. A SIRUTA code is the same in both languages of spelling.
            if court is not None and county is not None:
                where = ALIASES.get(
                    (county, strip_status(fold(seat.group(1)))),
                    strip_status(fold(seat.group(1))),
                )
                found_seat = in_county.get((county, where), [])
                if len(found_seat) == 1:
                    courts[court]["seatSiruta"] = found_seat[0]
            continue
        if CATEGORY.match(line):
            continue
        item = NUMBERED.match(line)
        if not item or court is None or county is None:
            continue

        text = item.group(2)
        # A commune listed under a suspended court, with a note saying where it sits today,
        # is already counted under the court that holds it.
        if FORWARD_REFERENCE.search(text):
            courts[court]["suspended"] = True
            continue
        text = CURRENT_HOLDER.split(text)[0].strip()

        place = strip_status(fold(text))
        place = ALIASES.get((county, place), place)
        matches = in_county.get((county, place), [])
        if len(matches) != 1:
            problems.append(
                f"{court}: {text!r} in {county} matched {len(matches)} UATs"
            )
            continue
        siruta = matches[0]
        if siruta in assigned:
            problems.append(f"{text!r} is in both {assigned[siruta]} and {court}")
            continue
        assigned[siruta] = court
        courts[court]["localities"].append(siruta)

    # The six sector courts carry no locality list: the decision names them and says only "cu
    # sediile in municipiul Bucuresti", because each one's circumscription is the sector it is
    # named after. Filled after the parse, not before — done first, the court headers in the
    # Bucharest section overwrote these entries and left all six empty while the assignment
    # count still looked right.
    for sector in range(1, 7):
        name = f"Judecătoria Sectorului {sector}"
        if name not in courts:
            problems.append(f"{name} is not in the decision")
            continue
        for siruta, uat, code in zip(
            registry["siruta"], registry["name"], registry["county"], strict=True
        ):
            if code == BUCHAREST and fold(uat) == f"SECTORUL {sector}":
                courts[name]["localities"].append(siruta)
                courts[name]["seatSiruta"] = siruta
                assigned[siruta] = name

    seatless = [c["name"] for c in courts.values() if not c["seatSiruta"] and not c["suspended"]]
    if seatless:
        problems.append(f"{len(seatless)} courts have no seat: {seatless[:6]}")

    print(f"courts: {len(courts)}   localities assigned: {len(assigned):,}")

    # Completeness. The arondare partitions the country, so anything short of every UAT is a
    # parse hole, and a hole makes every distance the map computes an underestimate.
    name_of = dict(zip(registry["siruta"], registry["name"], strict=True))
    county_of = dict(zip(registry["siruta"], registry["county"], strict=True))
    missing = [
        s
        for s in registry["siruta"]
        if s not in assigned and name_of[s] not in CREATED_AFTER_THE_DECISION
    ]
    if missing:
        problems.append(f"{len(missing)} UATs belong to no court")
        for siruta in missing[:15]:
            problems.append(f"  unassigned: {name_of[siruta]} ({county_of[siruta]})")
    absent = sorted(name_of[s] for s in registry["siruta"] if s not in assigned)

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for line in problems[:30]:
            print(f"  {line}", file=sys.stderr)
        return 1

    document = {
        "$schema": "../schema/arondare.schema.json",
        "id": "arondare-2023",
        "title": "Localitățile din circumscripția fiecărei judecătorii",
        "publisher": "Guvernul României",
        "period": "2023",
        "provenance": {
            "source": SOURCE,
            "locator": "HG nr. 1217/2023, anexă, în temeiul art. 42 alin. (2) din Legea nr. 304/2022",
            "confidence": "verbatim",
            "note": (
                "Lista este citită din anexa hotărârii; codurile SIRUTA sunt adăugate prin "
                "potrivirea numelui în interiorul județului, deci sunt derivate."
            ),
        },
        "courts": [courts[name] for name in courts],
        "limitations": [
            {
                "id": "comune-mai-noi-decat-hotararea",
                "text": (
                    "Hotărârea este din noiembrie 2023 și nu menționează "
                    + " și ".join(absent)
                    + ", comune înființate după adoptarea ei. Nu au, deocamdată, o "
                    "judecătorie arondată în acest document."
                ),
                "severity": "material",
                "affects": ["arondare"],
            },
            {
                "id": "judecatoria-insuratei-suspendata",
                "text": (
                    "Judecătoria Însurăţei există în hotărâre, dar nu funcționează: cele "
                    "unsprezece comune ale ei sunt arondate în prezent Judecătoriilor "
                    "Brăila și Făurei, până la reluarea activității. De aceea hotărârea "
                    "definește 176 de judecătorii, iar raportul CSM raportează 175."
                ),
                "severity": "material",
                "affects": ["arondare"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

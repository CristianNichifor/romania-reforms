"""How many people each court actually serves.

Every CSM edition in this repository carries a blocking limitation called `fara-geografie`:
"the document contains neither the location of the courts nor the population they serve". Half
of it stopped being true when `locate_instante.py` put all 241 courts on the map. The other half
was still true this morning, and it is the half that matters — a consolidation argument is about
how many people are moved further from a courthouse, and nothing in this repository said how many
people a courthouse has.

The pieces were all here and had never been joined:

    HG 1217/2023           which communes belong to which judecătorie   (arondare-2023)
      + the SIRUTA registry  how many people live in each commune       (administrativ)
      = the population each court serves

`build_incarcatura.py` does this join internally, as an intermediate step towards routing volume
to the 42 proposed courts, and throws the intermediate away. Published on its own it answers a
different and more basic question, and it makes a second one answerable: cases per thousand
residents, per court, which no source states. A court with twice the caseload of its neighbour
may be twice the size or may be twice as litigious, and until the denominator exists there is no
way to tell which.

Not every court has the same kind of answer, and flattening them would be wrong in several
directions at once. Every row therefore carries `bazaPopulatiei`, saying where its number came
from, so a consumer can sum the right subset instead of inferring it from the court's name:

  * `comune-arondate` — 175 judecătorii, summed over the communes the decision gives them.
  * `judet` — 42 county tribunals. A tribunal is the county's court, which is a reading of the
    court structure rather than a lookup; the decision arondates only the judecătorii.
  * `judet-partajat` — 4 specialised tribunals. Cluj, Argeș, Mureș and the Brașov minors-and-
    family court do serve their counties, alongside the ordinary tribunal, split by subject
    matter. Their population is the county's and must not be added to a national total, or Cluj
    is counted twice.
  * `jurisdictie-personala` — 4 military tribunals, null. Their jurisdiction is over service
    members rather than over a territory. Tribunalul Militar Iaşi is not the court of the 760.774
    people in Iaşi county, and writing that number down would be a claim nobody made.
  * `circumscriptie-nepublicata` — 15 curți de apel, null. Which counties each serves is not
    published anywhere this repository can read — see the blocking limitation in
    `curti-apel-regiuni.json` — and taking the seat's county would understate each by about
    three times.

The check that matters is that the two territorial tiers agree. Every commune belongs to exactly
one judecătorie and every judecătorie to one county, so summing the 175 and summing the 42 must
give the same number, and that number must be the country. Both come to 19.048.834 against a
national 19.053.815 — 99,97%, with the residue named rather than absorbed: two communes founded
after the decision was adopted.

Usage:
    uv run python scripts/build_populatie_arondata.py
"""

from __future__ import annotations

import array
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT.parent / "administrativ" / "web" / "public" / "data"
OUT = ROOT / "data" / "populatie-arondata.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_incarcatura import ALIASES, DORMANT, fold, load  # noqa: E402


def population_by_siruta() -> tuple[dict[str, int], dict[str, str]]:
    """Population per commune, read from the payload the web app reads.

    Not through `pipeline.reference_model`, which is the obvious route and pulls in geopandas to
    get at a column of integers. The exported payload has the same numbers in a form both this
    script and the browser can read, and reading the same bytes as the map is the stronger
    guarantee anyway: a Python answer and a TypeScript answer that disagree about how many people
    a court serves would be a very quiet bug.

    Layout, from `pipeline/export.py` and mirrored in `web/src/model/load.ts`: `attributes.bin`
    opens with `uatCount` unsigned 32-bit populations, in the index order of the `siruta` array
    in `attributes.json`.
    """
    manifest = json.loads((PAYLOAD / "manifest.json").read_text(encoding="utf-8"))
    attributes = json.loads((PAYLOAD / "attributes.json").read_text(encoding="utf-8"))
    count = manifest["uatCount"]

    raw = array.array("I")
    raw.frombytes((PAYLOAD / "attributes.bin").read_bytes()[: count * 4])
    if sys.byteorder != "little":
        raw.byteswap()
    if len(raw) != count or len(attributes["siruta"]) != count:
        raise SystemExit(
            f"payload disagrees with itself: {len(raw)} populations, "
            f"{len(attributes['siruta'])} sirutas, manifest says {count}"
        )

    return (
        dict(zip(attributes["siruta"], (int(value) for value in raw), strict=True)),
        dict(zip(attributes["siruta"], attributes["name"], strict=True)),
    )


def judecatorie_key(name: str) -> str:
    """The join key between HG 1217/2023 and the CSM register.

    Shared with `build_incarcatura.py` down to the alias table, because the two vocabularies
    disagree systematically — the decision uses the genitive for the Bucharest sectors and drops
    the enclitic article the register keeps — and a second, slightly different normaliser would
    marry a different set of courts without saying so.
    """
    key = fold(re.sub(r"^Judec[ăa]toria\s+", "", name))
    return ALIASES.get(key, key)


def build() -> dict:
    population, commune_name = population_by_siruta()
    located = load("instante-localizate-2025")["courts"]
    legal = load("arondare-2023")["courts"]

    by_key = {judecatorie_key(court["name"]): court for court in located if court["tier"] == "judecatorie"}

    courts = []
    unmatched: list[str] = []
    dormant: list[str] = []
    missing_localities: list[str] = []
    assigned: set[str] = set()

    for court in legal:
        key = judecatorie_key(court["name"])
        if key in DORMANT:
            dormant.append(court["name"])
            continue
        register = by_key.get(key)
        if register is None:
            unmatched.append(court["name"])
            continue

        known = [siruta for siruta in court["localities"] if siruta in population]
        missing = len(court["localities"]) - len(known)
        if missing:
            missing_localities.append(f"{court['name']}: {missing}")
        assigned.update(known)
        served = sum(population[siruta] for siruta in known)
        volume = register.get("volume") or 0

        courts.append(
            {
                "nume": register["name"],
                "grad": "judecatorie",
                "judet": register.get("county"),
                "populatie": served,
                "bazaPopulatiei": "comune-arondate",
                "localitati": len(known),
                "localitatiFaraPopulatie": missing,
                "volumCsm": volume,
                # The figure the denominator was missing for. Not a litigation rate — CSM's
                # volume carries the stock inherited from previous years as well as the year's
                # filings — but comparable between courts, which is what it is for.
                "dosarePerMieDeLocuitori": (
                    round(volume / served * 1000, 1) if served else None
                ),
            }
        )

    # A tribunal is a county court, so its population is its county's. Summed from the
    # judecătorii rather than from the registry directly: that way the two tiers cannot disagree
    # about the same county, and a commune missing from the decision is missing from both.
    by_county: dict[str, int] = {}
    for court in courts:
        if court["judet"]:
            by_county[court["judet"]] = by_county.get(court["judet"], 0) + court["populatie"]

    # Not every court the register calls a tribunal is a county court, and treating them alike
    # produces a table that is wrong in two different ways at once.
    #
    # A military tribunal's jurisdiction is over persons — service members — and not over a
    # territory. Tribunalul Militar Iaşi is not the court of 760.774 people in Iaşi county, and
    # writing that number down would be a claim nobody made.
    #
    # A specialised tribunal does serve its county, alongside the ordinary tribunal, split by
    # subject matter. Its population is the county's, but the two must not both be added into a
    # national total or Cluj is counted twice. `bazaPopulatiei` says which of the three cases
    # each row is, so a consumer can sum the right subset instead of guessing from the name.
    for court in located:
        if court["tier"] != "tribunal":
            continue
        name = fold(court["name"])
        volume = court.get("volume") or 0
        if "MILITAR" in name:
            served, basis = None, "jurisdictie-personala"
        elif any(word in name for word in ("SPECIALIZAT", "COMERCIAL", "MINORI")):
            served, basis = by_county.get(court["county"], 0), "judet-partajat"
        else:
            served, basis = by_county.get(court["county"], 0), "judet"
        courts.append(
            {
                "nume": court["name"],
                "grad": "tribunal",
                "judet": court["county"],
                "populatie": served,
                "bazaPopulatiei": basis,
                "localitati": 0,
                "localitatiFaraPopulatie": 0,
                "volumCsm": volume,
                "dosarePerMieDeLocuitori": (
                    round(volume / served * 1000, 1) if served else None
                ),
            }
        )

    # Appeal courts and the Înalta Curte carry the question rather than a number.
    for court in located:
        if court["tier"] not in {"curte-de-apel", "curte de apel", "iccj"}:
            continue
        courts.append(
            {
                "nume": court["name"],
                "grad": court["tier"],
                "judet": court.get("county"),
                "populatie": None,
                "bazaPopulatiei": (
                    "national" if court["tier"] == "iccj" else "circumscriptie-nepublicata"
                ),
                "localitati": 0,
                "localitatiFaraPopulatie": 0,
                "volumCsm": court.get("volume") or 0,
                "dosarePerMieDeLocuitori": None,
            }
        )

    courts.sort(key=lambda row: (row["grad"], -(row["populatie"] or 0)))

    national = sum(population.values())
    covered = sum(population[siruta] for siruta in assigned)
    # Named, not counted. Two communes were founded after the decision was adopted and belong to
    # no judecătorie in it; that is a fact about the decision, and a bare count would read as
    # rounding.
    unassigned = sorted(commune_name[siruta] for siruta in set(population) - assigned)

    return {
        "summary": {
            "judecatorii": sum(1 for row in courts if row["grad"] == "judecatorie"),
            "tribunale": sum(1 for row in courts if row["grad"] == "tribunal"),
            "populatieNationala": national,
            "populatieArondata": covered,
            "cotaArondata": round(covered / national, 4) if national else None,
            "comuneNearondate": len(unassigned),
            "judecatoriiSuspendate": dormant,
            "judecatoriiNepotrivite": unmatched,
        },
        "comuneNearondate": unassigned,
        "localitatiFaraPopulatie": missing_localities,
        "instante": courts,
    }


LIMITATIONS = [
    {
        "id": "curtile-de-apel-nu-au-populatie",
        "text": (
            "Curțile de apel primesc `populatie: null`. Ce județe ține fiecare nu se publică în "
            "nicio sursă pe care acest depozit o poate citi — vezi limitarea din "
            "`curti-apel-regiuni.json` — iar a le da populația județului în care stă sediul ar "
            "subevalua fiecare curte de vreo trei ori. Un null care se vede este mai bun decât o "
            "cifră care nu se poate contrazice."
        ),
        "severity": "blocking",
        "affects": ["instante"],
    },
    {
        "id": "tribunalul-e-judetul-prin-lectura-nu-prin-lista",
        "text": (
            "Populația unui tribunal este a județului său, fiindcă tribunalul este instanța "
            "județului. Este o lectură a structurii instanțelor, nu o listă citită dintr-un "
            "document: hotărârea de arondare acoperă doar judecătoriile."
        ),
        "severity": "material",
        "affects": ["instante"],
    },
    {
        "id": "populatia-e-din-registru-nu-din-recensamant",
        "text": (
            "Populația pe comună vine din registrul folosit de simulatorul administrativ, cu "
            "aceleași proprietăți acolo ca și aici. Nu este populația rezidentă la o dată anume "
            "și nu se compară cu un recensământ; se compară între instanțe, ceea ce este exact "
            "ce se cere de la ea."
        ),
        "severity": "note",
        "affects": ["instante", "summary"],
    },
    {
        "id": "dosare-pe-mie-nu-e-rata-de-litigare",
        "text": (
            "`dosarePerMieDeLocuitori` împarte volumul de activitate CSM la populația arondată. "
            "Volumul cuprinde stocul rămas din anii anteriori, nu doar cauzele intrate în an, "
            "deci raportul nu este o rată de litigare. Este comparabil între instanțe, fiindcă "
            "numărătorul este definit la fel pentru toate."
        ),
        "severity": "material",
        "affects": ["instante"],
    },
]


def main() -> int:
    body = build()
    document = {
        "$schema": "../schema/populatie-arondata.schema.json",
        "id": "populatie-arondata",
        "title": "Populația pe care o servește fiecare instanță",
        "publisher": "Cristian Nichifor",
        "period": "2023",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": (
                "HG 1217/2023 (arondare-2023) pentru comunele fiecărei judecătorii, registrul "
                "SIRUTA din simulatorul administrativ pentru populația fiecărei comune"
            ),
            "confidence": "derived",
            "note": (
                "Jumătatea care lipsea din limitarea `fara-geografie`: rapoartele CSM nu spun "
                "câți oameni servește o instanță, iar fără numitor nu se poate spune dacă o "
                "instanță e mare sau doar procesivă."
            ),
        },
        **body,
        "limitations": LIMITATIONS,
    }

    OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = body["summary"]
    print(
        f"{summary['judecatorii']} judecătorii + {summary['tribunale']} tribunale -> {OUT.name}"
    )
    print(
        f"  {summary['populatieArondata']:,} of {summary['populatieNationala']:,} people"
        f" ({summary['cotaArondata']:.2%})".replace(",", ".")
    )
    if summary["comuneNearondate"]:
        print(f"  {summary['comuneNearondate']} communes belong to no judecătorie")
    if summary["judecatoriiNepotrivite"]:
        print(f"  unmatched: {', '.join(summary['judecatoriiNepotrivite'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

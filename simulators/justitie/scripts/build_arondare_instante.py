"""Which communes each court serves, addressed the way the browser can use them.

The statistics page needs to answer "what would this proposed court have to judge", and the
proposed courts are a function of sliders the reader moves. So the routing has to happen in the
browser, on every drag, which means the browser needs the same chain the Python side already
walks:

    court -> the communes it serves -> the consolidated unit each belongs to -> its new seat

Only the first link is missing there, and the obvious way to supply it is wrong. `arondare-2023`
names courts the way HG 1217/2023 does; `portal-instante` names them the way the portal's enum
does; and the two disagree systematically — the decision takes the genitive for the Bucharest
sectors and drops the enclitic article the register keeps. `build_incarcatura.py` and
`build_populatie_arondata.py` already share one normaliser and one alias table for exactly that,
and writing a second one in TypeScript would be a second set of near-misses that nothing
compares against. **So the join is done once, here, and published resolved.**

Communes are written as indices into the administrative model's UAT array rather than as SIRUTA
codes. That is the same choice the administrative app makes when it encodes pinned seats into a
link, for the same reason: the index is the SIRUTA sort order, it is stable across builds, and
it saves the browser a lookup table of 3.186 strings. `uatCount` is recorded beside them so a
payload that has moved underneath this file fails loudly instead of silently addressing the
wrong communes.

Two tiers, because only two can be routed:

  * **Judecătorii** carry the communes the decision gives them.
  * **Tribunale** carry every commune in their county, since a tribunal is the county's court.
  * Appeal courts are absent. Which counties each holds is not published anywhere readable — the
    blocking limitation in `curti-apel-regiuni.json` — so their caseload cannot be routed, and
    an empty list would read as "serves nobody" rather than "not known".

Usage:
    uv run python scripts/build_arondare_instante.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT.parent / "administrativ" / "web" / "public" / "data"
OUT = ROOT / "data" / "arondare-instante.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_incarcatura import DORMANT, load  # noqa: E402
from build_intrate import key as portal_key  # noqa: E402
from build_populatie_arondata import judecatorie_key, population_by_siruta  # noqa: E402


def build() -> dict:
    manifest = json.loads((PAYLOAD / "manifest.json").read_text(encoding="utf-8"))
    attributes = json.loads((PAYLOAD / "attributes.json").read_text(encoding="utf-8"))
    index_of = {siruta: index for index, siruta in enumerate(attributes["siruta"])}
    county_of_uat = attributes["county"]
    population, _ = population_by_siruta()

    portal = load("portal-instante")["instante"]
    located = load("instante-localizate-2025")["courts"]
    legal = load("arondare-2023")["courts"]

    # The portal enum is the key everything downstream joins on, so each court is resolved to it
    # here rather than left as a printed name.
    portal_by_key = {portal_key(court["institutie"]): court for court in portal}
    register_by_judecatorie = {
        judecatorie_key(court["name"]): court for court in located if court["tier"] == "judecatorie"
    }

    courts = []
    unmatched: list[str] = []
    dormant: list[str] = []
    assigned: set[int] = set()

    for court in legal:
        name_key = judecatorie_key(court["name"])
        if name_key in DORMANT:
            dormant.append(court["name"])
            continue
        register = register_by_judecatorie.get(name_key)
        if register is None:
            unmatched.append(f"{court['name']} (nu e în registru)")
            continue
        entry = portal_by_key.get(portal_key(register["name"]))
        if entry is None:
            unmatched.append(f"{court['name']} (nu e pe portal)")
            continue

        uats = sorted(
            index_of[siruta]
            for siruta in court["localities"]
            if siruta in index_of and siruta in population
        )
        assigned.update(uats)
        courts.append(
            {
                "institutie": entry["institutie"],
                "grad": "judecatorie",
                "judet": entry["judet"],
                "uat": uats,
            }
        )

    # A tribunal is the county's court, so it carries the county. Built from the same commune
    # list the judecătorii were built from rather than from the registry directly, so the two
    # tiers cannot disagree about which communes exist.
    by_county: dict[str, list[int]] = {}
    for court in courts:
        if court["judet"]:
            by_county.setdefault(court["judet"], []).extend(court["uat"])

    for entry in portal:
        if entry["level"] != "tribunal" or not entry["judet"]:
            continue
        # Military tribunals judge people rather than places; routing their caseload over a
        # county would move work that never came from it.
        if "MILITAR" in entry["institutie"].upper():
            continue
        uats = sorted(by_county.get(entry["judet"], []))
        if not uats:
            unmatched.append(f"{entry['institutie']} (județ fără judecătorii)")
            continue
        courts.append(
            {
                "institutie": entry["institutie"],
                "grad": "tribunal",
                "judet": entry["judet"],
                "uat": uats,
            }
        )

    covered = {county_of_uat[index] for index in assigned}
    return {
        "summary": {
            "uatCount": manifest["uatCount"],
            "instante": len(courts),
            "judecatorii": sum(1 for court in courts if court["grad"] == "judecatorie"),
            "tribunale": sum(1 for court in courts if court["grad"] == "tribunal"),
            "comuneArondate": len(assigned),
            "judeteAcoperite": len(covered),
            "judecatoriiSuspendate": dormant,
            "nepotrivite": unmatched,
        },
        "instante": courts,
    }


LIMITATIONS = [
    {
        "id": "comunele-sunt-indici-nu-coduri",
        "text": (
            "Comunele se scriu ca indici în tabloul de UAT-uri al modelului administrativ, nu ca "
            "coduri SIRUTA — aceeași alegere pe care o face aplicația administrativă când pune "
            "un sediu fixat într-un link, și din același motiv: indicele este ordinea de sortare "
            "a SIRUTA și este stabil între build-uri. `summary.uatCount` stă alături, ca un "
            "payload care s-a mutat sub acest fișier să pice zgomotos, nu să adreseze tăcut alte "
            "comune."
        ),
        "severity": "note",
        "affects": ["instante"],
    },
    {
        "id": "curtile-de-apel-lipsesc",
        "text": (
            "Curțile de apel nu sunt aici. Ce județe ține fiecare nu se publică în nicio sursă "
            "citibilă — vezi limitarea din `curti-apel-regiuni.json` — deci volumul lor nu se "
            "poate direcționa. Lipsesc în loc să primească o listă goală, fiindcă o listă goală "
            "s-ar citi „nu servesc pe nimeni”, nu „nu se știe”."
        ),
        "severity": "blocking",
        "affects": ["instante"],
    },
    {
        "id": "tribunalul-ia-judetul-prin-lectura",
        "text": (
            "Un tribunal primește toate comunele județului său, fiindcă tribunalul este instanța "
            "județului. Hotărârea de arondare acoperă numai judecătoriile, deci aceasta este o "
            "lectură a structurii instanțelor, nu o listă citită."
        ),
        "severity": "material",
        "affects": ["instante"],
    },
]


def main() -> int:
    body = build()
    document = {
        "$schema": "../schema/arondare-instante.schema.json",
        "id": "arondare-instante",
        "title": "Comunele fiecărei instanțe, adresate ca indici de UAT",
        "publisher": "Cristian Nichifor",
        "period": "2023",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": (
                "HG 1217/2023 (arondare-2023), rezolvat la enumerarea portalului prin registrul "
                "CSM (instante-localizate-2025) și indexat în tabloul de UAT-uri administrativ"
            ),
            "confidence": "derived",
            "note": (
                "Publicat rezolvat ca browserul să nu aibă nevoie de un al doilea normalizator "
                "de nume: cele două vocabulare se întâlnesc o singură dată, în Python."
            ),
        },
        **body,
        "limitations": LIMITATIONS,
    }
    OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = body["summary"]
    print(
        f"{summary['judecatorii']} judecătorii + {summary['tribunale']} tribunale, "
        f"{summary['comuneArondate']} comune -> {OUT.name} ({OUT.stat().st_size / 1000:.0f} kB)"
    )
    if summary["nepotrivite"]:
        print(f"  unmatched: {', '.join(summary['nepotrivite'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

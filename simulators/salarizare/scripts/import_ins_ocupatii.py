"""Import what the public sector is actually paid, by occupation group, from INS.

    uv run python scripts/import_ins_ocupatii.py

Writes data/fiscal/ins-ocupatii.json.

Everything this project knows about Romanian pay so far comes from two places: the law,
which says what a coefficient is, and the budget execution, which says what was spent in
total. Neither says what a person in a given job is actually paid. The Danish side has had
that since the beginning — LONSOFF publishes earnings per occupation — and the Romanian
side has been a legal grid standing in for a fact.

INS matrix FOM121A closes part of that gap. It is the October earnings survey, and it
carries, in one cube: the number of full-time employees paid for the whole month, their
**salariul brut de bază**, and their gross income — split by ownership (so the public
sector can be isolated), by CAEN activity, and by ISCO major occupation group.

The base salary is the part that matters. It is the same quantity the grid holds, so for
the first time the law's numbers can be checked against a measurement rather than against
another law.

Three limits, none of them small:

  * **Ten ISCO major groups, not 1 049 positions.** This answers "what does a public-sector
    professional in education earn", never "what does an auditor earn". It cannot be used
    to weight the grid by position, and this importer does not pretend otherwise.
  * **No CAEN section O.** The survey covers sections A–S and omits O, public administration
    and defence. Education (P) and health (Q) are in; ministries, police and the army are
    not. Most of the public sector by headcount is covered; most of the argument about
    supplements is not.
  * **Full-time employees paid for the whole month, in October.** Part-timers, new starters
    and anyone on leave without pay are outside it, which biases the average upward.

The transport is worth recording because it is not the obvious one: the data POST goes to
`/tempo-ins/pivot` with a colon-separated `encQuery`, not to `/tempo-ins/matrix/{code}`
with a JSON array. Five plausible payload shapes against the latter all return 400. The
contract was read off github.com/mark-veres/tempo.py.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/fiscal/ins-ocupatii.json"

BASE = "http://statistici.insse.ro:8077/tempo-ins/"
MATRIX = "FOM121A"
UA = "public-pay-simulator/1.0 (+https://github.com/CristianNichifor/public-pay-simulator)"

# Dimension order is the order INS returns in dimensionsMap, and encQuery must follow it.
# Options are resolved by label rather than by the numeric nomItemId, so a renumbering on
# their side surfaces as a loud KeyError instead of silently selecting the wrong cell.
WANT = {
    0: ["Numarul salariatilor", "Salariul  brut de baza"],
    1: ["Proprietate publica"],
    2: ["P  INVATAMANT", "Q  SANATATE"],
    3: None,  # every ISCO major group, including the total
    4: ["Total "],
    5: None,  # every year the matrix carries
    6: ["Numar persoane", "Lei "],
}

# The ISCO major groups, shortened. The printed labels run to 120 characters because they
# spell out the whole group; a chart needs something a reader can hold.
SHORT = {
    "Total": "Toate ocupațiile",
    "Membri ai corpului legislativ": "Conducători",
    "Specialisti in diverse domenii": "Specialiști",
    "Tehnicieni si alti specialisti": "Tehnicieni",
    "Functionari administrativi": "Funcționari administrativi",
    "Lucratori in domeniul serviciilor": "Lucrători în servicii",
    "Lucratori calificati in agricultura": "Lucrători calificați, agricultură",
    "Muncitori calificati": "Muncitori calificați",
    "Operatori la instalatii": "Operatori de instalații",
    "Ocupatii elementare": "Ocupații elementare",
}

ACTIVITY = {"P  INVATAMANT": "invatamant", "Q  SANATATE": "sanatate"}


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        return json.loads(response.read().decode())


def short_label(label: str) -> str:
    for prefix, name in SHORT.items():
        if label.startswith(prefix):
            return name
    return label[:48]


def main() -> None:
    print(f"reading {MATRIX} metadata from INS ...")
    meta = get(f"{BASE}matrix/{MATRIX}")
    dimensions = meta["dimensionsMap"]
    details = meta["details"]

    selected: list[list[dict]] = []
    for index, dimension in enumerate(dimensions):
        options = dimension["options"]
        wanted = WANT.get(index)
        if wanted is None:
            chosen = options
        else:
            chosen = []
            for prefix in wanted:
                hit = [o for o in options if o["label"].startswith(prefix)]
                if not hit:
                    raise SystemExit(
                        f"dimension {index} ({dimension['label']}) has no option starting "
                        f"with {prefix!r} — INS relabelled it, so the selection is unsafe"
                    )
                chosen.extend(hit)
        selected.append(chosen)
        print(f"  dim{index} {dimension['label'][:44]:46} {len(chosen):>3} of {len(options)}")

    # The data POST is /pivot, and encQuery is dimensions joined by ':' with the option
    # ids inside each joined by ','. Posting a JSON array to /matrix/{code} returns 400.
    enc = ":".join(",".join(str(o["nomItemId"]) for o in dim) for dim in selected)
    body = json.dumps({
        "encQuery": enc,
        "language": "ro",
        "matCode": MATRIX,
        "matMaxDim": details.get("matMaxDim"),
        "matRegJ": details.get("matRegJ"),
        "matUMSpec": details.get("matUMSpec"),
    }).encode()
    request = urllib.request.Request(
        f"{BASE}pivot", data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    print("\nfetching the cube ...")
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        text = response.read().decode()

    rows = list(csv.reader(io.StringIO(text)))
    header, body_rows = rows[0], [r for r in rows[1:] if len(r) == len(rows[0])]
    print(f"  {len(body_rows)} cells over {len(header)} columns")

    # measure -> activity -> occupation -> year -> value
    cube: dict[str, dict] = {}
    for row in body_rows:
        measure, _ownership, activity, occupation, _sex, year, unit, value = (c.strip() for c in row)
        if not value or value in {":", "c", "-"}:
            continue
        key = "count" if measure.startswith("Numarul") else "base"
        # Guard the pairing: a count must arrive in persons and a salary in lei. If INS
        # ever reorders the measure and unit dimensions this stops the import rather than
        # writing headcounts into a salary series.
        if (key == "count") != unit.startswith("Numar persoane"):
            raise SystemExit(f"measure {measure!r} arrived with unit {unit!r} — cube misread")
        activity_key = next((v for k, v in ACTIVITY.items() if activity.startswith(k)), None)
        if activity_key is None:
            continue
        cube.setdefault(key, {}).setdefault(activity_key, {}).setdefault(
            short_label(occupation), {}
        )[year.replace("Anul ", "")] = float(value)

    series: list[dict] = []
    for key, unit, label in (("count", "COUNT", "salariați"), ("base", "CP_MNAC", "salariu de bază")):
        for activity, occupations in sorted(cube.get(key, {}).items()):
            for occupation, by_year in sorted(occupations.items()):
                observations = [
                    {"period": year, "value": round(value, 2)}
                    for year, value in sorted(by_year.items())
                ]
                if not observations:
                    continue
                series.append({
                    "id": f"ins-{key}-{activity}-{occupation.lower().replace(' ', '-').replace(',', '')[:40]}",
                    "label": f"{occupation} — {activity}, {label}",
                    "geo": "RO",
                    "unit": unit,
                    "dims": {
                        "kind": "occupationGroup",
                        "measure": key,
                        "activity": activity,
                        "occupation": occupation,
                        "ownership": "public",
                    },
                    "observations": observations,
                    "provenance": {
                        "source": "ins-tempo-fom121a",
                        "locator": (
                            f"INS Tempo {MATRIX}, proprietate publica, "
                            f"{'P INVATAMANT' if activity == 'invatamant' else 'Q SANATATE'}, "
                            f"{occupation}, {label}"
                        ),
                        "confidence": "verbatim",
                    },
                })

    latest = max(
        (o["period"] for s in series for o in s["observations"]), default="necunoscut"
    )
    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "ins-ocupatii",
        "title": "Salariați și salariul brut de bază în sectorul public, pe grupe majore de ocupații",
        "publisher": "Institutul Național de Statistică",
        "methodology": (
            "Ancheta din luna octombrie (Tempo FOM121A): salariați cu program complet de "
            "lucru, plătiți întreaga lună, proprietate publică, pe activități CAEN și pe "
            "grupe majore de ocupații ISCO-08."
        ),
        "retrieved": latest,
        "query": {"endpoint": f"{BASE}pivot", "matrix": MATRIX, "ownership": "Proprietate publica"},
        "provenance": {
            "source": "ins-tempo-fom121a",
            "locator": f"INS Tempo, matricea {MATRIX}",
            "confidence": "verbatim",
        },
        "series": series,
        "limitations": [
            {
                "id": "grupe-majore-nu-functii",
                "text": (
                    "Zece grupe majore ISCO, nu 1049 de funcții. Cifrele răspund la „cât ia "
                    "un specialist din învățământ”, niciodată la „cât ia un auditor”. Nu pot "
                    "fi folosite ca să repartizeze posturile pe funcțiile din grilă: nimic "
                    "publicat nu face legătura aceea, iar o repartiție inventată ar arăta la "
                    "fel de convingător ca una reală."
                ),
                "affects": ["headcount", "structure"],
                "severity": "blocking",
            },
            {
                "id": "fara-administratie-publica",
                "text": (
                    "Ancheta acoperă secțiunile CAEN A–S și omite secțiunea O, "
                    "administrație publică și apărare. Învățământul și sănătatea sunt "
                    "înăuntru; ministerele, poliția și armata nu. Adică exact familiile în "
                    "jurul cărora se poartă discuția despre sporuri lipsesc de aici."
                ),
                "affects": ["headcount", "gross"],
                "severity": "material",
            },
            {
                "id": "doar-cine-a-lucrat-toata-luna",
                "text": (
                    "Numai salariații cu program complet care au fost plătiți întreaga lună "
                    "octombrie. Cei cu normă parțială, cei intrați în cursul lunii și cei "
                    "aflați în concediu fără plată sunt în afara anchetei, ceea ce împinge "
                    "media în sus față de statul de plată real."
                ),
                "affects": ["gross"],
                "severity": "material",
            },
            {
                "id": "baza-nu-venitul",
                "text": (
                    "Seriile de aici sunt salariul brut de bază, adică exact mărimea pe care "
                    "o dă și grila — de aceea se pot compara. Venitul total, cu sporuri, e o "
                    "altă coloană a aceleiași anchete și nu e importată aici, ca să nu fie "
                    "confundată cu baza."
                ),
                "affects": ["gross"],
                "severity": "note",
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n  {latest}, proprietate publică:")
    for activity in ("invatamant", "sanatate"):
        counts = cube.get("count", {}).get(activity, {})
        salaries = cube.get("base", {}).get(activity, {})
        total = counts.get("Toate ocupațiile", {}).get(latest)
        print(f"\n  {activity}  ({total:,.0f} salariați)".replace(",", " ") if total else f"\n  {activity}")
        for occupation in sorted(counts, key=lambda o: -counts[o].get(latest, 0)):
            n = counts[occupation].get(latest)
            pay = salaries.get(occupation, {}).get(latest)
            if n and pay:
                print(f"     {occupation[:34]:36} {n:>9,.0f}   {pay:>8,.0f} lei".replace(",", " "))

    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(series)} series")


if __name__ == "__main__":
    main()

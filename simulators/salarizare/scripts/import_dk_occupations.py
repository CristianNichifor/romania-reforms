"""Import Danish public-sector earnings by occupation, with quartiles.

    uv run python scripts/import_dk_occupations.py

Writes data/fiscal/dk-occupations.json.

The IDA tables that anchor the Danish regime cover engineers and academics. They say
nothing about doctors, nurses, school teachers or police — the occupations a Romanian
reader most wants to compare, and the ones the alignment crosswalk had to leave with an
empty Danish side.

Danmarks Statistik's LONSOFF closes that gap: earnings for 67 public-sector occupation
groups, and — the part that makes a real comparison possible — a lower quartile, a median
and an upper quartile for each. Denmark does not publish a grid for these jobs because
there is no grid to publish; pay is negotiated. The quartiles are the closest thing to a
range the Danish system has, and they describe what people are actually paid rather than
what a table permits.

That asymmetry is the point rather than a flaw in the data, and it is recorded as such:
the Romanian range is what the law sets, the Danish range is what people earn.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/fiscal/dk-occupations.json"
DST = "https://api.statbank.dk/v1/data"

YEAR = "2024"
# Danish standard week is 37 hours; the source is hourly, the comparison is monthly.
HOURS_PER_MONTH = 37 * 52 / 12

# The occupations worth putting beside the Romanian grid, and nothing else: a table of
# all 67 would bury the ones that answer the question.
OCCUPATIONS = {
    "TOT": "Toți angajații publici",
    "130": "Medici (rezidenți și specialiști tineri)",
    "138": "Medici primari / consultanți seniori",
    "157": "Medici stomatologi",
    "155": "Asistenți medicali",
    "124": "Moașe",
    "117": "Fizioterapeuți",
    "149": "Asistenți de îngrijire socială și sănătate",
    "132": "Învățători și profesori de gimnaziu",
    "119": "Profesori de liceu",
    "143": "Educatori",
    "133": "Absolvenți de master (administrație)",
    "127": "Personal de birou",
    "135": "Manageri din sectorul public",
    "140": "Polițiști",
}

QUARTILES = {"NEDRE": "q1", "MEDIAN": "median", "OVRE": "q3"}

# What Danish public pay is actually made of. Romania caps supplements at a share of base
# and then exempts a long list; Denmark does not legislate a ceiling at all, so the only
# way to ask whether Romania's supplement layer is unusually large is to measure what
# Denmark's actually comes to.
# These seven partition the total exactly — at 2024 they sum to 368,75 against a
# published 368,74 — which is how we know nothing is missing and nothing is counted twice.
COMPONENTS = {
    "FORINKL": "total",
    "BASIS": "basic",
    "GENE": "conditions",
    "OVERB": "overtime",
    "UREGEL": "irregular",
    "GODE": "fringe",
    "PENS": "pension",
    "SYGDOM": "sickness",
}

# Holiday pay is NOT one of them. Danmarks Statistik prints it with a leading ".." because
# it is a sub-item *inside* basic earnings, not a component beside it — a Dane on holiday
# keeps drawing salary, exactly as a Romanian does. Treating it as a peer and subtracting
# it would remove twelve percent of Danish basic pay that is already counted once, and the
# error is not cosmetic: it inverts which country leans more on its base salary. It is
# imported so the page can say what holiday pay is worth, and marked so nothing sums it.
SUB_ITEMS = {"FERIE": "holiday"}


def fetch_csv(measures: list[str]) -> list[dict]:
    body = json.dumps({
        "table": "LONSOFF", "format": "CSV", "lang": "en", "delimiter": "Semicolon",
        "variables": [
            {"code": "OFFPERSGRP", "values": list(OCCUPATIONS)},
            {"code": "GRP", "values": ["GRPTOT"]},
            {"code": "SEKTOR", "values": ["1032"]},
            {"code": "AFLOEN", "values": ["TIFA"]},
            {"code": "LØNMÅL", "values": measures},
            {"code": "KØN", "values": ["MOK"]},
            {"code": "Tid", "values": [YEAR]},
        ],
    }).encode()
    request = urllib.request.Request(DST, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")), delimiter=";"))


def quartile_of(label: str) -> str:
    if label.lower().startswith("lower"):
        return "q1"
    if label.lower().startswith("median"):
        return "median"
    return "q3"


def main() -> None:
    print("fetching LONSOFF from Danmarks Statistik ...")
    rows = fetch_csv(list(QUARTILES))

    # Keyed by the printed English label, since the CSV returns text rather than codes.
    by_label: dict[str, dict[str, float]] = {}
    for row in rows:
        label = row["OFFPERSGRP"].strip()
        by_label.setdefault(label, {})[quartile_of(row["LØNMÅL"])] = (
            float(row["INDHOLD"]) * HOURS_PER_MONTH
        )

    # Match the printed labels back onto the codes we asked for, so the output keeps the
    # stable identifier rather than a string that changes with the API's language setting.
    codes = list(OCCUPATIONS)
    labels = list(by_label)
    if len(labels) != len(codes):
        print(f"  warning: asked for {len(codes)} groups, received {len(labels)}")

    series = []
    for label, values in sorted(by_label.items(), key=lambda kv: -kv[1].get("median", 0)):
        slug = (
            label.lower()
            .replace(",", "").replace("(", "").replace(")", "").replace("/", " ")
            .replace("  ", " ").strip().replace(" ", "-")[:48]
        )
        for quartile, amount in values.items():
            series.append({
                "id": f"dk-occ-{slug}-{quartile}",
                "label": f"{label} — {quartile}",
                "geo": "DK",
                "unit": "CP_MNAC",
                "dims": {"kind": "occupation", "occupation": label, "quartile": quartile},
                "observations": [{"period": YEAR, "value": round(amount, 2)}],
                "provenance": {
                    "source": "dst-lonsoff",
                    "locator": f"Danmarks Statistik LONSOFF, {label}, general government, {YEAR}",
                    "confidence": "verbatim",
                },
            })
        print(f"  {label[:44]:46} {values.get('q1',0):8,.0f} {values.get('median',0):8,.0f} {values.get('q3',0):8,.0f}".replace(",", " "))

    print("\nfetching the composition of Danish public pay ...")
    comp_rows = fetch_csv(list(COMPONENTS) + list(SUB_ITEMS))
    label_to_key = {
        "EARNINGS IN DKK PER HOUR WORKED": "total",
        "Basic earnings in DKK per hour worked": "basic",
        "Nuisance bonus in DKK per hour worked": "conditions",
        "Overtime payment in DKK per hour worked": "overtime",
        "Irregular payments in DKK per hour worked": "irregular",
        "Fringe benefits in DKK per hour worked": "fringe",
        "Pension including ATP in DKK per hour worked": "pension",
        "Sickness with pay, etc. in DKK per hour worked": "sickness",
        "..Holiday payments in DKK per hour worked": "holiday",
    }
    composition: dict[str, dict[str, float]] = {}
    for row in comp_rows:
        key = label_to_key.get(row["LØNMÅL"].strip())
        if not key:
            continue
        try:
            value = float(row["INDHOLD"])
        except ValueError:
            continue  # Danmarks Statistik prints '..' where a cell is suppressed.
        composition.setdefault(row["OFFPERSGRP"].strip(), {})[key] = value

    partition = [c for c in COMPONENTS.values() if c != "total"]

    for occupation, parts in composition.items():
        total = parts.get("total", 0)
        if not total:
            continue

        # The proof that the seven components are the whole of earnings, checked per
        # occupation rather than assumed from the one group it was verified on by hand.
        residual = total - sum(parts.get(c, 0) for c in partition)
        if abs(residual) / total > 0.005:
            raise SystemExit(
                f"{occupation}: components miss {residual:.2f} of {total:.2f} DKK — the "
                "partition is no longer complete, so shares would be wrong"
            )

        for component, value in parts.items():
            if component == "total":
                continue
            # Holiday rides along as a memo line: readable, never summable.
            kind = "composition" if component in partition else "composition-subitem"
            note = (
                " (sub-poziție, deja inclusă în salariul de bază)"
                if kind == "composition-subitem"
                else ""
            )
            series.append({
                "id": f"dk-comp-{occupation.lower().replace(' ', '-')[:40]}-{component}",
                "label": f"{occupation} — {component}{note}",
                "geo": "DK",
                "unit": "PC_TOT",
                "dims": {"kind": kind, "occupation": occupation, "component": component},
                "observations": [{"period": YEAR, "value": round(value / total, 5)}],
                "provenance": {
                    "source": "dst-lonsoff",
                    "locator": f"Danmarks Statistik LONSOFF, {occupation}, {component} ÷ total, {YEAR}",
                    "confidence": "derived",
                },
            })
        share = lambda k: parts.get(k, 0) / total * 100  # noqa: E731
        print(f"  {occupation[:40]:42} bază {share('basic'):5.1f}%  condiții {share('conditions'):4.1f}%"
              f"  ore supl. {share('overtime'):4.1f}%  neregulate {share('irregular'):4.1f}%"
              f"  pensie {share('pension'):5.1f}%  boală {share('sickness'):4.1f}%")

    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "dk-occupations",
        "title": "Câștiguri în sectorul public danez, pe grupe ocupaționale",
        "publisher": "Danmarks Statistik",
        "methodology": "LONSOFF, câștiguri pe oră lucrată, administrație publică",
        "retrieved": YEAR,
        "query": {"endpoint": DST, "table": "LONSOFF", "sector": "1032", "year": YEAR,
                  "hoursPerMonth": round(HOURS_PER_MONTH, 2)},
        "provenance": {
            "source": "dst-lonsoff",
            "locator": "Danmarks Statistik, tabelul LONSOFF",
            "confidence": "verbatim",
        },
        "series": series,
        "limitations": [
            {
                "id": "castig-nu-grila",
                "text": "Danemarca nu publică o grilă pentru aceste ocupații fiindcă nu există una: salariul se negociază local peste un minim din contractul colectiv. Cifrele de aici sunt ce câștigă oamenii, nu ce permite un tabel. Intervalul românesc pus alături este exact invers — ce stabilește legea, înainte de sporuri. Diferența nu e o eroare de date, e chiar deosebirea dintre cele două sisteme.",
                "affects": ["gross", "structure"],
                "severity": "material",
            },
            {
                "id": "cuartile-nu-extreme",
                "text": "Intervalul danez merge de la cuartila inferioară la cea superioară: jumătatea din mijloc a oamenilor din acea ocupație. Un sfert câștigă mai puțin decât capătul de jos și un sfert mai mult decât cel de sus. Nu e minimul și maximul posibil.",
                "affects": ["gross"],
                "severity": "note",
            },
            {
                "id": "compozitie-vs-plafon",
                "text": "Compoziția daneză este ce s-a plătit efectiv. Partea românească pusă alături vine tot din execuția bugetară — clasificația economică, la nivel de paragraf — deci și ea e un fapt, nu un plafon. Ce rămâne necomparabil e altceva: execuția arată regimul actual, în timp ce plafonul de 20% aparține proiectului de lege, care nu s-a aplicat încă niciun an.",
                "affects": ["structure"],
                "severity": "note",
            },
            {
                "id": "pensia-si-boala-ies-din-comparatie",
                "text": "Din câștigul danez se scot pensia plătită de angajator (13,5%) și zilele de boală plătite (5,7%) înainte de comparație, fiindcă partea românească exclude contribuțiile angajatorului și plătește concediul medical din alt titlu bugetar. Concediul de odihnă, în schimb, nu se scade din nicio parte: Danemarca îl tipărește separat, dar ca sub-poziție a salariului de bază, exact cum în România salariul curge mai departe în concediu.",
                "affects": ["gross", "structure"],
                "severity": "material",
            },
            {
                "id": "include-sporuri",
                "text": "Câștigul pe oră lucrată include sporuri, plăți neregulate și compensații pentru condiții, dar nu pensia. Salariul de bază românesc pus alături nu include sporuri, care în proiect pot adăuga până la 20% peste — plus sporurile exceptate de la plafon.",
                "affects": ["gross"],
                "severity": "material",
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(series)} series across {len(by_label)} occupations")


if __name__ == "__main__":
    main()

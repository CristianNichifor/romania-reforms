"""What the prosecution merger does to the work, office by office.

`parchete-2025` carried a blocking limitation from the day it was written: *"Raportul dă și
volumul de activitate și încărcătura pe procuror, pe capitole întregi. Aici sunt luate doar
posturile și costul lor; redistribuirea muncii între cele 42 de parchete propuse nu e
calculată."* This is that calculation.

Section 7.3 merges the two bottom prosecution levels into 42 county offices, exactly as chapter
7 merges the courts. The CSM report publishes what each office actually handles — Anexa 2 gives
all 176 offices attached to judecatorii, a second annex the 42 attached to tribunals — so the
merger can be run on real volumes rather than asserted ones.

**The merger evens the work out, and by more than anything else in this repository.** Today the
busiest judecatorie-level office carries 14,4 times the caseload per prosecutor of the quietest
— 4.483 against 312. Pooled into county offices that ratio falls to 3,2. It is not an artefact
of the two extremes either: the robust p90/p10 spread falls from 2,85 to 2,22.

This is the strongest thing found here *in favour* of the paper, and it is an argument the paper
never actually makes. Its case for consolidation was built on efficiency grades that turn out
not to support it (`eficienta-csm`) and on a court count that overstates itself
(`danemarca-comparatie`). The workload argument it left on the table is the one that holds.

**What consolidation does not do is dissolve the concentration.** Pooling six sector offices
with a tribunal office makes Bucharest a single office holding 18,1% of the national caseload.
And the heaviest load per prosecutor after the merger is not Bucharest but Ilfov, at 1.866 —
a reminder that pooling redistributes cases, not prosecutors.

Three things are carried rather than fixed:

Volumes from the two levels are summed, and they are not the same kind of case — a tribunal-level
file is heavier than a judecatorie-level one. The merger the paper proposes implies exactly this
addition, so the addition is what is computed, but a merged load of N is not comparable to a
judecatorie load of N.

The counts are of cases to be resolved, not of work done, and the report's own resolution rates
differ sharply between the levels. Adding them measures the size of the in-tray.

And offices are merged by county, because that is what 7.3 says. The court half of this
simulator routes across county lines by distance and finds 48 units better served elsewhere;
prosecution cannot be routed the same way, because which communes an office covers is not
published — the same wall `curti-apel-regiuni` hit.

Usage:
    uv run --with pypdf python scripts/build_parchete_comasare.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources" / "csm-starea-justitiei-2025.pdf"
ATTRIBUTES = ROOT / "app" / "public" / "data" / "admin-attributes.json"
MANIFEST = ROOT / "app" / "public" / "data" / "admin-manifest.json"
OUT = ROOT / "data" / "parchete-comasare.json"

# Both annexes print "N. NAME" then their columns. Names carry digits (the Bucharest sectors)
# and lower case (the specialised minors office), so the class has to admit both.
NAME = r"[A-ZĂÂÎŞŢȘȚ][A-ZĂÂÎŞŢȘȚa-zăâîșț0-9 \-\.]*?"
JUDECATORIE_PAGES = (168, 171)
TRIBUNAL_PAGES = (172, 174)

# One typo in the source, corrected by name rather than by fuzzy matching. Anexa 2 prints
# "TÂRNŞVENI" where every other register — including the court annex of the same report — has
# Târnăveni. A fuzzy matcher would fix this and quietly fix other things too; an explicit entry
# fixes exactly one thing and can be argued with.
ALIASES = {"TARNSVENI": "TARNAVENI"}

# The report's own national averages, used as fatal checks on the extraction: if the rows this
# script reads do not reproduce the totals the report prints beside them, the rows are wrong.
JUDECATORIE_MEAN_PER_PROSECUTOR = 1542.67
TRIBUNAL_TOTAL_VOLUME = 88603


def fold(text: str) -> str:
    """Diacritic-blind, punctuation-blind key. The two annexes and the court register spell the
    same towns three different ways, and Târnăveni appears in one of them as TÂRNŞVENI."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def number(text: str) -> float:
    """The judecatorie annex writes 1832,00 and the tribunal annex writes 285.38, in adjacent
    columns of the same document."""
    text = text.strip()
    if "," in text:
        return float(text.replace(".", "").replace(",", "."))
    return float(text)


def annexes() -> tuple[list[dict], list[dict]]:
    from pypdf import PdfReader  # noqa: PLC0415

    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")
    pages = [p.extract_text() or "" for p in PdfReader(str(SOURCE)).pages]

    def flat(first: int, last: int) -> str:
        return re.sub(r"\s+", " ", " ".join(pages[first - 1 : last]))

    lower = flat(*JUDECATORIE_PAGES)
    start = lower.find("Activitatea parchetelor de pe lângă judecătorii")
    if start < 0:
        raise SystemExit("Anexa 2 (parchete de pe lângă judecătorii) is not where it was")
    lower = lower[start:]
    rows = re.findall(
        rf"(\d{{1,3}})\.\s+({NAME})\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+(\d+)(?=\s|$)", lower
    )
    judecatorie = [
        {
            "office": name.strip(),
            "volume": int(volume),
            "perProsecutor": number(per_prosecutor),
            "perSchema": number(per_schema),
            "prosecutors": int(posts),
        }
        for _, name, volume, per_prosecutor, per_schema, posts in rows
    ]
    if [int(r[0]) for r in rows] != list(range(1, len(rows) + 1)):
        raise SystemExit("Anexa 2's numbering has holes; rows were dropped")

    upper = flat(*TRIBUNAL_PAGES)
    start = upper.find("Activitatea parchetelor de pe lângă tribunale")
    if start < 0:
        raise SystemExit("the tribunal-level annex is not where it was")
    # The appellate annex follows immediately and matches the same row shape.
    end = upper.find("Activitatea parchetelor de pe lângă curţi", start)
    if end < 0:
        raise SystemExit("cannot find where the tribunal annex ends; refusing to run past it")
    upper = upper[start:end]
    rows = re.findall(
        rf"(\d{{1,3}})\.\s+({NAME})\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)(?=\s|$)", upper
    )
    tribunal = []
    for _, name, volume, per_prosecutor, per_schema, _up in rows:
        per = number(per_prosecutor)
        if per <= 0:
            raise SystemExit(f"{name}: caseload per prosecutor is {per}")
        # The tribunal annex prints no headcount, but volume / load is one by construction.
        prosecutors = int(round(int(volume) / per))
        tribunal.append(
            {
                "office": name.strip(),
                "volume": int(volume),
                "perProsecutor": per,
                "perSchema": number(per_schema),
                "prosecutors": prosecutors,
            }
        )
    if [int(r[0]) for r in rows] != list(range(1, len(rows) + 1)):
        raise SystemExit("the tribunal annex's numbering has holes")

    if len(judecatorie) != 176:
        raise SystemExit(f"expected 176 judecatorie-level offices, read {len(judecatorie)}")
    total = sum(r["volume"] for r in judecatorie)
    posts = sum(r["prosecutors"] for r in judecatorie)
    mean = round(total / posts, 2)
    if mean != JUDECATORIE_MEAN_PER_PROSECUTOR:
        raise SystemExit(
            f"rows give {mean} cases per prosecutor, the report prints "
            f"{JUDECATORIE_MEAN_PER_PROSECUTOR}"
        )
    upper_total = sum(r["volume"] for r in tribunal)
    if upper_total != TRIBUNAL_TOTAL_VOLUME:
        raise SystemExit(
            f"tribunal rows sum to {upper_total}, the report's prose says {TRIBUNAL_TOTAL_VOLUME}"
        )
    return judecatorie, tribunal


def county_lookup() -> tuple[dict[str, str], dict[str, str]]:
    """Two registers, tried in that order: the court one first because it is this simulator's
    own, the UAT one for the towns the court annex does not have."""
    courts = json.loads(
        (ROOT / "data" / "instante-localizate-2025.json").read_text(encoding="utf-8")
    )["courts"]
    by_court = {
        fold(re.sub(r"^Judec[ăa]toria\s+", "", c["name"])): c["county"]
        for c in courts
        if c["tier"] == "judecatorie"
    }
    if not ATTRIBUTES.exists():
        raise SystemExit(f"Missing {ATTRIBUTES}; run the app's copy-data step first")
    attributes = json.loads(ATTRIBUTES.read_text(encoding="utf-8"))
    by_uat: dict[str, str] = {}
    for name, county in zip(attributes["name"], attributes["county"], strict=True):
        # "MUNICIPIUL TÂRNĂVENI" -> "TARNAVENI"
        bare = fold(re.sub(r"^(MUNICIPIUL|ORAȘ|ORAS|COMUNA)\s+", "", name))
        by_uat.setdefault(bare, county)
    return by_court, by_uat


def main() -> int:
    judecatorie, tribunal = annexes()
    by_court, by_uat = county_lookup()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    county_names: dict[str, str] = manifest["countyNames"]
    code_of_name = {fold(name): code for code, name in county_names.items()}

    # ---- every lower-level office to a county ----------------------------------------------------
    unresolved: list[str] = []
    resolved_by: dict[str, str] = {}
    for office in judecatorie:
        folded = ALIASES.get(fold(office["office"]), fold(office["office"]))
        if folded in by_court:
            office["county"] = by_court[folded]
            resolved_by[office["office"]] = "instanță"
        elif folded in by_uat:
            office["county"] = by_uat[folded]
            resolved_by[office["office"]] = "UAT"
        else:
            unresolved.append(office["office"])
    if unresolved:
        raise SystemExit(f"no county for these prosecution offices: {unresolved}")

    # The specialised minors office sits inside a county like any other and the merger absorbs
    # it; nothing in 7.3 keeps a separate specialised prosecution office.
    specialised = []
    for office in tribunal:
        folded = fold(office["office"])
        if folded in code_of_name:
            office["county"] = code_of_name[folded]
        else:
            # "BRAȘOV MINORI familie BRAŞOV" — the county name is in there, the label is not.
            match = next((c for name, c in code_of_name.items() if name in folded), None)
            if match is None:
                raise SystemExit(f"cannot place tribunal-level office {office['office']!r}")
            office["county"] = match
            specialised.append(office["office"])

    counties = sorted({o["county"] for o in judecatorie} | {o["county"] for o in tribunal})
    if len(counties) != 42:
        raise SystemExit(f"the merger produced {len(counties)} counties, not 42")

    merged = []
    for code in counties:
        lower = [o for o in judecatorie if o["county"] == code]
        upper = [o for o in tribunal if o["county"] == code]
        volume = sum(o["volume"] for o in lower) + sum(o["volume"] for o in upper)
        prosecutors = sum(o["prosecutors"] for o in lower) + sum(o["prosecutors"] for o in upper)
        if prosecutors <= 0:
            raise SystemExit(f"{code}: merged office with no prosecutors")
        merged.append(
            {
                "county": code,
                "name": county_names.get(code, code),
                "officesBefore": len(lower) + len(upper),
                "volume": volume,
                "prosecutors": prosecutors,
                "perProsecutor": round(volume / prosecutors, 1),
                "lowerVolume": sum(o["volume"] for o in lower),
                "upperVolume": sum(o["volume"] for o in upper),
            }
        )

    def spread(values: list[float]) -> dict:
        values = sorted(values)
        return {
            "min": round(values[0], 1),
            "max": round(values[-1], 1),
            "median": round(statistics.median(values), 1),
            "maxOverMin": round(values[-1] / values[0], 2),
            # Robust to the single-prosecutor oddities the report carries.
            "p90OverP10": round(
                statistics.quantiles(values, n=10)[8] / statistics.quantiles(values, n=10)[0], 2
            ),
        }

    # Însurăței is printed with zeros across the row — no cases, no prosecutors, no load. It is
    # an office that exists in law and is not running, which is also why the court annex of the
    # same report has no judecătorie to match it. It stays in the register as the report has it,
    # but a dormant office is not an observation about how work is spread, so it is kept out of
    # the spread rather than allowed to divide by zero.
    dormant = [o["office"] for o in judecatorie if o["prosecutors"] == 0]
    active = [o for o in judecatorie if o["prosecutors"] > 0]
    before = spread([o["perProsecutor"] for o in active])
    after = spread([o["perProsecutor"] for o in merged])
    busiest = max(merged, key=lambda o: o["volume"])
    heaviest = max(merged, key=lambda o: o["perProsecutor"])

    summary = {
        "officesBefore": len(judecatorie) + len(tribunal),
        "officesAfter": len(merged),
        "totalVolume": sum(o["volume"] for o in merged),
        "totalProsecutors": sum(o["prosecutors"] for o in merged),
        "nationalPerProsecutor": round(
            sum(o["volume"] for o in merged) / sum(o["prosecutors"] for o in merged), 1
        ),
        "spreadBefore": before,
        "spreadAfter": after,
        "maxOverMinFalls": round(before["maxOverMin"] - after["maxOverMin"], 2),
        "busiestCounty": busiest["county"],
        "busiestVolume": busiest["volume"],
        "busiestShareOfTotal": round(busiest["volume"] / sum(o["volume"] for o in merged), 3),
        "heaviestCounty": heaviest["county"],
        "heaviestPerProsecutor": heaviest["perProsecutor"],
        "dormantOffices": sorted(dormant),
        "activeOfficesBefore": len(active) + len(tribunal),
        "resolvedByUat": sorted(k for k, v in resolved_by.items() if v == "UAT"),
        "specialisedAbsorbed": specialised,
    }

    print(f"{summary['officesBefore']} parchete -> {summary['officesAfter']} județene   "
          f"{summary['totalVolume']:,} dosare   {summary['totalProsecutors']:,} procurori   "
          f"media {summary['nationalPerProsecutor']:,.1f}/procuror\n")
    print(f"{'':22}{'min':>9}{'mediana':>10}{'max':>10}{'max/min':>10}{'p90/p10':>10}")
    print(f"{'azi (judecătorii)':22}{before['min']:>9,.0f}{before['median']:>10,.0f}"
          f"{before['max']:>10,.0f}{before['maxOverMin']:>10.2f}{before['p90OverP10']:>10.2f}")
    print(f"{'după comasare':22}{after['min']:>9,.0f}{after['median']:>10,.0f}"
          f"{after['max']:>10,.0f}{after['maxOverMin']:>10.2f}{after['p90OverP10']:>10.2f}")
    print(f"\ncel mai mare volum: {busiest['name']} cu {busiest['volume']:,} dosare "
          f"({summary['busiestShareOfTotal'] * 100:.1f}% din total)")
    print(f"cea mai mare încărcătură: {heaviest['name']} cu {heaviest['perProsecutor']:,.0f}/procuror")
    if summary["resolvedByUat"]:
        print(f"\nrezolvate din registrul UAT (fără instanță pereche): {summary['resolvedByUat']}")
    if specialised:
        print(f"parchet specializat absorbit: {specialised}")

    document = {
        "$schema": "../schema/parchete-comasare.schema.json",
        "id": "parchete-comasare",
        "title": "Munca parchetelor, redistribuită pe cele 42 de parchete județene propuse",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": "2025",
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Anexa nr. 2 și anexa activității parchetelor de pe lângă tribunale, p. 168-173",
            "confidence": "derived",
            "note": (
                "Volumele și încărcăturile pe fiecare parchet sunt citate din anexe. "
                "Repartizarea pe județe și însumarea pe cele 42 de parchete propuse sunt "
                "calculate aici, după comasarea din capitolul 7.3."
            ),
        },
        "summary": summary,
        "merged": merged,
        # The offices themselves, so the distance-routed variant can read them rather than
        # extract the annexes a second time. Two extractions of one table drift apart.
        "offices": [
            {
                "office": o["office"],
                "level": "judecatorie",
                "county": o["county"],
                "volume": o["volume"],
                "prosecutors": o["prosecutors"],
            }
            for o in judecatorie
        ]
        + [
            {
                "office": o["office"],
                "level": "tribunal",
                "county": o["county"],
                "volume": o["volume"],
                "prosecutors": o["prosecutors"],
            }
            for o in tribunal
        ],
        "limitations": [
            {
                "id": "doua-feluri-de-dosare-adunate",
                "text": (
                    "Volumele celor două niveluri sunt adunate, deși un dosar de la tribunal nu "
                    "e cât unul de la judecătorie. Comasarea propusă de lucrare exact această "
                    "adunare o presupune, deci ea e ce se calculează — dar o încărcătură "
                    "comasată de N nu se compară cu una de judecătorie de N."
                ),
                "severity": "material",
                "affects": ["merged", "summary"],
            },
            {
                "id": "dosare-de-solutionat-nu-munca-facuta",
                "text": (
                    "Se numără dosarele de soluționat, nu munca dusă la capăt. Raportul dă rate "
                    "de soluționare foarte diferite între niveluri — 31,27% la tribunale față "
                    "de mult mai mult la judecătorii — deci suma măsoară mărimea teancului de "
                    "intrare, nu efortul."
                ),
                "severity": "material",
                "affects": ["merged"],
            },
            {
                "id": "comasare-pe-judet-nu-pe-distanta",
                "text": (
                    "Parchetele sunt comasate aici pe județ, fiindcă asta spune 7.3. Fișierul "
                    "acesta a susținut o vreme că nici nu s-ar putea altfel, pentru că nu se "
                    "publică ce comune acoperă un parchet — ceea ce era greșit: un parchet de pe "
                    "lângă o judecătorie lucrează în circumscripția acelei judecătorii, deci "
                    "teritoriul lui e publicat, ca al instanței, în HG 1217/2023. Arondarea după "
                    "distanță se calculează în „parchete-arondare”; ce rămâne aici e varianta pe "
                    "județ, cea a lucrării."
                ),
                "severity": "note",
                "affects": ["merged"],
            },
            {
                "id": "posturile-de-la-tribunale-sunt-deduse",
                "text": (
                    "Anexa parchetelor de pe lângă tribunale nu tipărește numărul de procurori, "
                    "așa că e dedus împărțind volumul la încărcătura pe procuror, care e "
                    "definiția lui. Acolo unde raportul dă cifre ciudate — Galați apare cu o "
                    "încărcătură egală cu volumul, deci un singur procuror — deducția le "
                    "moștenește. Sunt păstrate așa cum sunt."
                ),
                "severity": "material",
                "affects": ["merged"],
            },
            {
                "id": "un-parchet-fara-instanta",
                "text": (
                    "Raportul numără 176 de parchete pe lângă judecătorii, dar anexa instanțelor "
                    "are 175 de judecătorii. Diferența e Însurăței, care apare cu zero pe toată "
                    "linia — zero dosare, zero procurori — adică un parchet care există în lege "
                    "și nu funcționează. Rămâne în tabel așa cum îl dă raportul, dar e scos din "
                    "statistica de împrăștiere, fiindcă un parchet care nu lucrează nu spune "
                    "nimic despre cum e împărțită munca. Județul lui e luat din registrul UAT, "
                    "nefiind o judecătorie pereche de unde."
                ),
                "severity": "note",
                "affects": ["merged"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

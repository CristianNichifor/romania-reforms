"""The prosecution service as three tiers instead of four, with the top one on regions.

`parchete-comasare` merged the two bottom levels into 42 county offices, which is what section
7.3 proposes. It left the level above untouched at 15, because that is what the paper leaves it
at. But this repository already argues, in `curti-apel-regiuni`, that 15 appellate courts on no
particular geography would be better as 8 on the development regions — and prosecution offices
are organised in the mirror of the courts. Leaving the courts regionalised and the prosecution
offices on the old map would break the mirror the whole system is built on.

So this is the other half of that variant: county prosecution offices sitting where the county
courts sit, regional prosecution offices sitting where the regional appellate courts would, and
the Public Ministry above them.

    today      176 + 42 + 15 + 1
    proposed    42 +  8 + 1

**There is much less here to fix than there was one tier down, and merging fixes less of it.**
The county merger cut the spread of cases per prosecutor from 14,4x to 3,2x. This tier starts
at 4,65x — already far more even — and merging takes it to 3,35x. Worth doing, but the case for
regionalising the appellate tier cannot be made on workload the way the county one can.

**The oddity of this tier is that load runs backwards, and merging does not touch it.**
Bucharest has the largest volume of any appellate prosecution office and the *lightest* load
per prosecutor in the country — 41 cases against Galați's 192 — because it holds by far the
most prosecutors. After the merger the same inversion survives: Sud-Est, which is Constanța
plus Galați, carries 138 cases per prosecutor while București-Ilfov carries 41.

That is the finding, and it is about staffing rather than geography. Merging changes where the
boundaries are; it does not move one prosecutor toward the work. Whether a merged office would
be staffed to its caseload is not something this file can say, because nothing in the report
says how a merged office would be staffed at all.

This is a variant, not the paper. Section 7.3 keeps 15 appellate prosecution offices, and
nothing in the document proposes regions for them.

Usage:
    uv run --with pypdf python scripts/build_parchete_regiuni.py
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
OUT = ROOT / "data" / "parchete-regiuni.json"

NAME = r"[A-ZĂÂÎŞŢȘȚ][A-ZĂÂÎŞŢȘȚa-zăâîșț0-9 \-\.]*?"
PAGES = (172, 175)

# The report prints its own total beside the table. If the rows this script reads do not
# reproduce it, the rows are wrong and the build stops.
APPELLATE_TOTAL_VOLUME = 14739
APPELLATE_OFFICES = 15


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def number(text: str) -> float:
    text = text.strip()
    if "," in text:
        return float(text.replace(".", "").replace(",", "."))
    return float(text)


def load(name: str) -> dict:
    path = ROOT / "data" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run the builder that makes it first")
    return json.loads(path.read_text(encoding="utf-8"))


def spread(values: list[float]) -> dict:
    values = sorted(v for v in values if v > 0)
    quantiles = statistics.quantiles(values, n=10) if len(values) >= 4 else None
    return {
        "min": round(values[0], 1),
        "max": round(values[-1], 1),
        "median": round(statistics.median(values), 1),
        "maxOverMin": round(values[-1] / values[0], 2),
        "p90OverP10": round(quantiles[8] / quantiles[0], 2) if quantiles else None,
    }


def appellate_offices() -> list[dict]:
    from pypdf import PdfReader  # noqa: PLC0415

    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")
    pages = [p.extract_text() or "" for p in PdfReader(str(SOURCE)).pages]
    text = re.sub(r"\s+", " ", " ".join(pages[PAGES[0] - 1 : PAGES[1]]))
    start = text.find("Activitatea parchetelor de pe lângă curţile de apel")
    if start < 0:
        raise SystemExit("the appellate prosecution annex is not where it was")
    # The PICCJ/DNA/DIICOT table follows and matches the same row shape.
    end = text.find("Activitatea parchetelor PICCJ", start)
    if end < 0:
        raise SystemExit("cannot find where the appellate annex ends; refusing to run past it")
    table = text[start:end]

    rows = re.findall(
        rf"(\d{{1,2}})\.\s+({NAME})\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)(?=\s|$)", table
    )
    offices = []
    for _, name, volume, per_prosecutor, per_schema, investigation in rows:
        per = number(per_prosecutor)
        if per <= 0:
            raise SystemExit(f"{name}: caseload per prosecutor is {per}")
        offices.append(
            {
                "office": name.strip(),
                "volume": int(volume),
                "perProsecutor": per,
                "perSchema": number(per_schema),
                # The report's second load column: the same cases over only those prosecutors
                # who actually worked criminal investigations, rather than everyone on the
                # establishment. It is the obvious way the inversion below could be an artefact
                # — a large office whose prosecutors do much besides case work would show a low
                # load without being under-worked — so it is carried and the check is run.
                "perProsecutorInvestigation": number(investigation),
                # The annex prints no headcount; volume over load is its definition.
                "prosecutors": int(round(int(volume) / per)),
            }
        )
    if len(offices) != APPELLATE_OFFICES:
        raise SystemExit(f"expected {APPELLATE_OFFICES} appellate offices, read {len(offices)}")
    if [int(r[0]) for r in rows] != list(range(1, APPELLATE_OFFICES + 1)):
        raise SystemExit("the appellate annex's numbering has holes")
    total = sum(o["volume"] for o in offices)
    if total != APPELLATE_TOTAL_VOLUME:
        raise SystemExit(f"rows sum to {total}, the report prints {APPELLATE_TOTAL_VOLUME}")
    return offices


def main() -> int:
    offices = appellate_offices()
    curti = load("curti-apel-regiuni")
    comasare = load("parchete-comasare")

    # Appellate court -> region, from the variant this mirrors: a region is its seat plus what
    # it absorbs, and the two together must name all fifteen courts exactly once.
    region_of_court: dict[str, str] = {}
    for region in curti["regions"]:
        for court in [region["seat"], *region["absorbs"]]:
            key = fold(re.sub(r"^Curtea de Apel\s+", "", court))
            if key in region_of_court:
                raise SystemExit(f"{court} is claimed by two regions")
            region_of_court[key] = region["region"]
    if len(region_of_court) != APPELLATE_OFFICES:
        raise SystemExit(
            f"the regions name {len(region_of_court)} appellate courts, not {APPELLATE_OFFICES}"
        )

    unplaced = []
    for office in offices:
        region = region_of_court.get(fold(office["office"]))
        if region is None:
            unplaced.append(office["office"])
        office["region"] = region
    if unplaced:
        raise SystemExit(f"no region for these appellate prosecution offices: {unplaced}")

    seat_of_region = {
        r["region"]: fold(re.sub(r"^Curtea de Apel\s+", "", r["seat"])) for r in curti["regions"]
    }
    regions = []
    for region in curti["regions"]:
        members = [o for o in offices if o["region"] == region["region"]]
        volume = sum(o["volume"] for o in members)
        prosecutors = sum(o["prosecutors"] for o in members)
        if prosecutors <= 0:
            raise SystemExit(f"{region['region']}: merged office with no prosecutors")
        seat = next(o for o in members if fold(o["office"]) == seat_of_region[region["region"]])
        regions.append(
            {
                "region": region["region"],
                "seat": seat["office"],
                "seatCounty": region["seatCounty"],
                "counties": region["counties"],
                "officesBefore": len(members),
                "absorbs": [o["office"] for o in members if o is not seat],
                "volume": volume,
                "prosecutors": prosecutors,
                "perProsecutor": round(volume / prosecutors, 1),
            }
        )

    before = spread([o["perProsecutor"] for o in offices])
    after = spread([r["perProsecutor"] for r in regions])
    heaviest_today = max(offices, key=lambda o: o["perProsecutor"])
    lightest_today = min(offices, key=lambda o: o["perProsecutor"])
    biggest_today = max(offices, key=lambda o: o["volume"])

    county = comasare["summary"]
    structure = {
        "todayLower": county["officesBefore"],
        "todayAppellate": len(offices),
        "proposedCounty": county["officesAfter"],
        "proposedRegional": len(regions),
        "todayTotal": county["officesBefore"] + len(offices) + 1,
        "proposedTotal": county["officesAfter"] + len(regions) + 1,
    }

    summary = {
        "officesBefore": len(offices),
        "officesAfter": len(regions),
        "absorbed": len(offices) - len(regions),
        "totalVolume": sum(r["volume"] for r in regions),
        "totalProsecutors": sum(r["prosecutors"] for r in regions),
        "nationalPerProsecutor": round(
            sum(r["volume"] for r in regions) / sum(r["prosecutors"] for r in regions), 1
        ),
        "spreadBefore": before,
        "spreadAfter": after,
        "heaviestToday": heaviest_today["office"],
        "heaviestTodayPerProsecutor": heaviest_today["perProsecutor"],
        "lightestToday": lightest_today["office"],
        "lightestTodayPerProsecutor": lightest_today["perProsecutor"],
        "biggestToday": biggest_today["office"],
        "biggestTodayVolume": biggest_today["volume"],
        "biggestTodayPerProsecutor": biggest_today["perProsecutor"],
        "loadRunsBackwards": biggest_today["perProsecutor"] < heaviest_today["perProsecutor"],
        # Does it survive being measured on prosecutors who actually investigate?
        "biggestTodayInvestigationLoad": biggest_today["perProsecutorInvestigation"],
        "heaviestTodayInvestigationLoad": heaviest_today["perProsecutorInvestigation"],
        "inversionSurvivesInvestigationMeasure": (
            biggest_today["perProsecutorInvestigation"]
            < heaviest_today["perProsecutorInvestigation"]
        ),
        "structure": structure,
    }

    print(f"{structure['todayLower']} + {structure['todayAppellate']} + 1 parchete azi  ->  "
          f"{structure['proposedCounty']} județene + {structure['proposedRegional']} regionale + 1\n")
    print(f"{'regiune':18}{'sedii':>7}{'dosare':>9}{'procurori':>11}{'pe procuror':>13}")
    for r in sorted(regions, key=lambda x: -x["volume"]):
        print(f"{r['region']:18}{r['officesBefore']:>7}{r['volume']:>9,}"
              f"{r['prosecutors']:>11}{r['perProsecutor']:>13,.1f}")
    print(f"\n{'':18}{'min':>9}{'mediana':>10}{'max':>9}{'max/min':>10}")
    print(f"{'azi, 15 parchete':18}{before['min']:>9,.0f}{before['median']:>10,.0f}"
          f"{before['max']:>9,.0f}{before['maxOverMin']:>10.2f}")
    print(f"{'după, 8 regionale':18}{after['min']:>9,.0f}{after['median']:>10,.0f}"
          f"{after['max']:>9,.0f}{after['maxOverMin']:>10.2f}")
    print(f"\nîncărcătura merge invers: {biggest_today['office']} are cel mai mare volum "
          f"({biggest_today['volume']:,}) și cea mai mică încărcătură "
          f"({biggest_today['perProsecutor']:,.0f}/procuror); {heaviest_today['office']} are "
          f"{heaviest_today['perProsecutor']:,.0f}")

    document = {
        "$schema": "../schema/parchete-regiuni.schema.json",
        "id": "parchete-regiuni",
        "title": "Parchetele pe trei niveluri: 42 județene, 8 regionale, unul național",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": "2025",
        "variantOfPaper": True,
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Anexa activității parchetelor de pe lângă curţile de apel, p. 172-174",
            "confidence": "derived",
            "note": (
                "Volumele celor 15 parchete de pe lângă curțile de apel sunt citate din anexă. "
                "Gruparea lor pe cele opt regiuni de dezvoltare urmează varianta de curți de "
                "apel din acest depozit și nu este propusă de lucrare."
            ),
        },
        "summary": summary,
        "regions": regions,
        "offices": offices,
        "limitations": [
            {
                "id": "regiunile-nu-sunt-in-lucrare",
                "text": (
                    "Lucrarea păstrează 15 parchete de pe lângă curțile de apel și nu propune "
                    "regiuni pentru ele. Gruparea de aici este o variantă a acestui depozit, "
                    "construită ca oglindă a variantei de curți de apel — parchetele sunt "
                    "organizate în oglinda instanțelor, iar a regionaliza instanțele fără "
                    "parchete ar rupe tocmai simetria pe care stă sistemul."
                ),
                "severity": "blocking",
                "affects": ["regions", "summary"],
            },
            {
                "id": "comasarea-nu-muta-procurori",
                "text": (
                    "Comasarea schimbă unde sunt granițele, nu unde sunt oamenii. Nimic din "
                    "raport nu spune cum s-ar încadra un parchet regional, deci încărcătura de "
                    "după e volumul comasat împărțit la procurorii care există azi în acele "
                    "sedii. Dacă schema s-ar rescrie odată cu harta, cifrele ar arăta altfel."
                ),
                "severity": "material",
                "affects": ["regions"],
            },
            {
                "id": "posturile-sunt-deduse-si-aici",
                "text": (
                    "Anexa nu tipărește numărul de procurori, ci încărcătura pe procuror, așa "
                    "că numărul e dedus împărțind volumul la ea — chiar definiția indicatorului. "
                    "Rotunjirea la procuror întreg introduce o eroare mică în încărcăturile "
                    "regionale."
                ),
                "severity": "material",
                "affects": ["regions", "offices"],
            },
            {
                "id": "distanta-creste-pentru-justitiabili",
                "text": (
                    "Aceleași distanțe care apar la varianta de curți de apel se aplică și "
                    "aici: comasarea a 15 sedii în 8 duce media pe județ până la sediul de "
                    "regiune de la 56 la 124 de km, iar 24 de județe merg mai departe decât azi. "
                    "Pentru parchete contează mai puțin decât pentru instanțe — cetățeanul se "
                    "duce rar la parchetul de apel — dar nu contează deloc."
                ),
                "severity": "material",
                "affects": ["regions"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

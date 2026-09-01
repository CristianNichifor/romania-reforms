"""What the prosecution establishment would look like if it followed the caseload.

`parchete-regiuni` ended on a finding it could not act on: the load runs backwards. The
appellate office with the most cases carries the lightest load per prosecutor in the country,
and merging offices does not change that, because merging moves boundaries and not people. It
said the thing wanting repair was the establishment rather than the map, and then stopped.

This is that repair, as arithmetic. For each proposed office — 42 county, 8 regional — it asks
what headcount would give every prosecutor in the tier the same number of cases, and compares
that with the headcount there now. The difference is the misalignment, in people.

**Most of the gap could be closed without moving anybody.** That is the finding worth having.
The prosecution service is carrying 765 vacant posts, and the number of prosecutors who would
have to arrive somewhere to level the two tiers is smaller than that. Recruiting into the
offices that are short, rather than transferring out of the ones that are long, would do most
of the work — which matters, because the two policies are not remotely equivalent for the
people in them.

**The inversion is not an artefact of Bucharest doing other work.** The obvious objection to
the finding is that a big office looks lightly loaded because many of its prosecutors do things
other than investigate. The report publishes a second load column counting only prosecutors who
actually worked criminal investigations, and on that measure Bucharest is at 73 against
Galați's 306 — the gap widens rather than closes.

**This is a measure of misalignment, not a personnel plan.** A prosecutor is not a unit of
capacity that can be posted where the arithmetic wants them, and nothing here accounts for the
minimum size below which an office cannot function, for specialisation, or for the fact that a
transfer is a house and a school and a family. The number says how far the establishment is
from the work. It does not say anyone should be moved.

Usage:
    uv run python scripts/build_parchete_incadrare.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "parchete-incadrare.json"


def load(name: str) -> dict:
    path = ROOT / "data" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run the builder that makes it first")
    return json.loads(path.read_text(encoding="utf-8"))


def level(name: str, offices: list[dict]) -> dict:
    """One tier, equalised.

    The target is the tier's own mean caseload, not a national one: a county office and a
    regional office do different work at different grades, and pooling them would produce a
    number that describes neither.
    """
    total_volume = sum(o["volume"] for o in offices)
    total_staff = sum(o["prosecutors"] for o in offices)
    if total_staff <= 0 or total_volume <= 0:
        raise SystemExit(f"{name}: nothing to equalise")
    target = total_volume / total_staff

    rows = []
    for office in offices:
        # Never below one: an office with cases needs somebody in it, and a rounding rule that
        # can empty an office is describing something other than a prosecution service.
        equalised = max(1, round(office["volume"] / target))
        rows.append(
            {
                "name": office["name"],
                "volume": office["volume"],
                "prosecutors": office["prosecutors"],
                "equalised": equalised,
                "delta": equalised - office["prosecutors"],
                "perProsecutor": round(office["volume"] / office["prosecutors"], 1),
            }
        )

    short = [r for r in rows if r["delta"] > 0]
    long = [r for r in rows if r["delta"] < 0]
    arrivals = sum(r["delta"] for r in short)
    departures = -sum(r["delta"] for r in long)
    rows.sort(key=lambda r: r["delta"])

    return {
        "level": name,
        "offices": len(rows),
        "totalVolume": total_volume,
        "totalProsecutors": total_staff,
        "targetPerProsecutor": round(target, 1),
        "officesShort": len(short),
        "officesLong": len(long),
        "arrivals": arrivals,
        "departures": departures,
        # Rounding to whole people means the two sides need not match exactly.
        "netRoundingDrift": arrivals - departures,
        "shareOfCorpsMoving": round(arrivals / total_staff, 3),
        "spreadToday": round(
            max(r["perProsecutor"] for r in rows) / min(r["perProsecutor"] for r in rows), 2
        ),
        "medianTodayPerProsecutor": round(statistics.median(r["perProsecutor"] for r in rows), 1),
        "mostShort": rows[-1]["name"],
        "mostShortBy": rows[-1]["delta"],
        "mostLong": rows[0]["name"],
        "mostLongBy": -rows[0]["delta"],
        "rows": rows,
    }


def main() -> int:
    comasare = load("parchete-comasare")
    regiuni = load("parchete-regiuni")
    parchete = load("parchete-2025")

    county = level(
        "județene",
        [
            {"name": o["name"], "volume": o["volume"], "prosecutors": o["prosecutors"]}
            for o in comasare["merged"]
        ],
    )
    regional = level(
        "regionale",
        [
            {"name": r["region"], "volume": r["volume"], "prosecutors": r["prosecutors"]}
            for r in regiuni["regions"]
        ],
    )

    # The alternative to moving anyone: the service is already short of this many people.
    vacant = parchete["totals"]["vacant"]
    arrivals = county["arrivals"] + regional["arrivals"]
    summary = {
        "arrivals": arrivals,
        "departures": county["departures"] + regional["departures"],
        "vacantPosts": vacant,
        "vacanciesCoverArrivals": vacant >= arrivals,
        "arrivalsAsShareOfVacancies": round(arrivals / vacant, 3),
        "totalProsecutors": county["totalProsecutors"] + regional["totalProsecutors"],
        "shareOfCorpsMoving": round(
            arrivals / (county["totalProsecutors"] + regional["totalProsecutors"]), 3
        ),
        "inversionSurvivesInvestigationMeasure": regiuni["summary"][
            "inversionSurvivesInvestigationMeasure"
        ],
        "investigationLoadBiggest": regiuni["summary"]["biggestTodayInvestigationLoad"],
        "investigationLoadHeaviest": regiuni["summary"]["heaviestTodayInvestigationLoad"],
    }

    for tier in (county, regional):
        print(f"{tier['level'].upper()}  {tier['offices']} parchete, "
              f"{tier['totalProsecutors']:,} procurori, țintă "
              f"{tier['targetPerProsecutor']:,.0f} dosare/procuror")
        print(f"  {tier['officesShort']} sub schemă (ar primi {tier['arrivals']}), "
              f"{tier['officesLong']} peste (ar ceda {tier['departures']})")
        print(f"  cel mai scurt: {tier['mostShort']} +{tier['mostShortBy']};  "
              f"cel mai lung: {tier['mostLong']} -{tier['mostLongBy']}")
        print(f"  împrăștiere azi {tier['spreadToday']}x, mediana "
              f"{tier['medianTodayPerProsecutor']:,.0f}\n")

    print(f"în total ar trebui să ajungă {arrivals} de procurori acolo unde sunt dosarele, "
          f"{summary['shareOfCorpsMoving'] * 100:.0f}% din corp")
    print(f"posturi vacante azi: {vacant} — "
          f"{'acoperă' if summary['vacanciesCoverArrivals'] else 'NU acoperă'} nevoia "
          f"({summary['arrivalsAsShareOfVacancies'] * 100:.0f}% din ele)")
    print(f"inversiunea pe procurorii de urmărire penală: "
          f"{summary['investigationLoadBiggest']} vs {summary['investigationLoadHeaviest']} — "
          f"{'rezistă' if summary['inversionSurvivesInvestigationMeasure'] else 'dispare'}")

    document = {
        "$schema": "../schema/parchete-incadrare.schema.json",
        "id": "parchete-incadrare",
        "title": "Cât de departe e schema parchetelor de munca lor",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "variantOfPaper": True,
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Volumele pe parchet din anexe, prin parchete-comasare și parchete-regiuni",
            "confidence": "derived",
            "note": (
                "Volumele și procurorii vin din raportul CSM. Egalizarea încărcăturii pe fiecare "
                "nivel și diferența față de schema de azi sunt calculate aici. Nu este o "
                "propunere de mișcare de personal."
            ),
        },
        "summary": summary,
        "levels": [county, regional],
        "limitations": [
            {
                "id": "nu-e-un-plan-de-personal",
                "text": (
                    "Cifra spune cât de departe e schema de muncă, nu că cineva ar trebui mutat. "
                    "Un procuror nu e o unitate de capacitate care se pune unde cere aritmetica: "
                    "un transfer e o casă, o școală și o familie. Nimic de aici nu ține cont de "
                    "mărimea minimă sub care un parchet nu poate funcționa, de specializare sau "
                    "de faptul că oamenii nu se redistribuie ca dosarele."
                ),
                "severity": "blocking",
                "affects": ["levels", "summary"],
            },
            {
                "id": "dosarele-nu-sunt-egale",
                "text": (
                    "Egalizarea presupune că un dosar e un dosar. Nu e: la parchetele "
                    "județene se adună dosare de la judecătorii și de la tribunale, iar la cele "
                    "regionale sunt cauze de apel. O schemă construită pe numărul de dosare ar "
                    "sub-încadra parchetele cu cauze grele și ar supra-încadra pe cele cu multe "
                    "cauze mărunte."
                ),
                "severity": "material",
                "affects": ["levels"],
            },
            {
                "id": "vacantele-nu-sunt-pe-parchet",
                "text": (
                    "Cele 765 de posturi vacante sunt raportate pe nivel, nu pe parchet, deci nu "
                    "se poate spune că sunt vacante exact acolo unde lipsesc oameni. "
                    "Comparația arată doar că nevoia de reechilibrare e mai mică decât golul "
                    "existent — nu că golul e în locurile potrivite."
                ),
                "severity": "material",
                "affects": ["summary"],
            },
            {
                "id": "procurorii-sunt-dedusi",
                "text": (
                    "La nivelul regional și la cel de tribunal, numărul de procurori e dedus din "
                    "volum împărțit la încărcătura pe procuror, fiindcă anexele nu tipăresc "
                    "efectivul. Rotunjirea la om întreg face ca sosirile și plecările să nu se "
                    "potrivească exact; diferența e raportată ca atare."
                ),
                "severity": "material",
                "affects": ["levels"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

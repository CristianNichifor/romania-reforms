"""Where the prosecution offices would sit if distance decided, like the courts.

`parchete-comasare` merged the offices by county and declared, as blocking, that they could not
be routed by road distance the way the courts are, because no document publishes which communes
each prosecution office covers.

That was wrong, and the mistake was in reading rather than in data. A parchet *de pe lângă
Judecătoria X* acts in the circumscription of Judecătoria X — that is what "de pe lângă" means,
and it is why the CSM report lists exactly one office per court. The prosecution circumscription
is published: it is the court's, in HG 1217/2023. Nothing had to be found; something had to be
noticed.

So prosecution can follow the courts exactly, and this routes it the same way `incarcatura-noua`
routes the bench:

    office volume (CSM, per parchet)
      -> the communes of the court it attaches to (HG 1217/2023)
        -> each commune's consolidated unit (the administrative model)
          -> the nearest of 42 seats by road (arondare-noua)

**The point of doing it is that it keeps the prosecutor in the same town as the court.** Chapter
7 argues for consolidation on logistics: prosecutors, police and judges working in one place.
Merging prosecution by county while the courts route by distance would have broken exactly that
for the units that cross a county line — a citizen whose case is heard in the next county while
the prosecution file sits in their own. Routed together, the two maps agree by construction.

**It moves real work, and it costs something.** 39 of the 42 seats receive a different caseload
than the county merge gives them, and 160.327 cases — 9,5% of the national total — change seat.
Bucharest alone gains 78.000, because the units around it are nearer its courts than their own
county seats.

The cost is that workload comes out slightly less even, not more: cases per prosecutor spread
3,76x across the distance-routed seats against 3,18x across the county-merged ones. That is the
honest trade. Routing prosecution with the courts is not a workload optimisation and does not
pretend to be one — it buys the thing chapter 7 actually argues for, which is the prosecutor,
the judge and the police sitting in the same town as the case. Merging prosecution by county
while the courts route by distance would have broken exactly that, for the 48 units whose court
is in another county.

Usage:
    uv run python scripts/build_parchete_arondare.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "parchete-arondare.json"

sys.path.insert(0, str(ADMINISTRATIV))

# Ten offices the prosecution annex and the government decision spell differently, derived by
# taking the two name sets and pairing what was left over rather than guessed at. Keyed by the
# annex's spelling and applied at lookup: the first version built the index with them and
# matched nothing, because it was translating the side that did not need translating.
ALIASES = {
    "GURA HONT": "GURAHONT",
    "ODORHEIUL SECUIESC": "ODORHEIU SECUIESC",
    "SIMLEUL SILVANIEI": "SIMLEU SILVANIEI",
    "TARNSVENI": "TARNAVENI",
    **{f"SECTORUL {n} BUCURESTI": f"SECTORULUI {n}" for n in range(1, 7)},
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def load(name: str) -> dict:
    path = ROOT / "data" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run the builder that makes it first")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    from pipeline.reference_model import Params, load_data, run  # noqa: PLC0415

    comasare = load("parchete-comasare")
    legal = load("arondare-2023")["courts"]
    arondare = load("arondare-noua")

    data = load_data()
    result, _ = run(data, Params())
    unit_of = {m: seat for seat, members in result.members.items() for m in members}
    court_of_unit = {u["siruta"]: u["courtSiruta"] for u in arondare["units"] if u["courtSiruta"]}
    seat_name = {u["courtSiruta"]: u["courtName"] for u in arondare["units"] if u["courtSiruta"]}
    seat_county = {u["courtSiruta"]: u["courtCounty"] for u in arondare["units"] if u["courtSiruta"]}
    seats = sorted(set(court_of_unit.values()))
    if len(seats) != 42:
        raise SystemExit(f"arondare-noua routes to {len(seats)} seats, not 42")

    # The prosecution office's territory is its court's. Keyed from the decision's side, because
    # that is where the localities are.
    localities_of = {}
    for court in legal:
        key = fold(re.sub(r"^Judec[ăa]toria\s+", "", court["name"]))
        localities_of[key] = [
            s for s in court["localities"] if s in data.population
        ]

    lower = [o for o in comasare["offices"] if o["level"] == "judecatorie"]
    upper = [o for o in comasare["offices"] if o["level"] == "tribunal"]

    received = {seat: 0.0 for seat in seats}
    received_staff = {seat: 0.0 for seat in seats}
    unreachable_volume = 0.0
    invariant = 0.0
    split = 0.0
    unmatched: list[str] = []
    dormant: list[str] = []

    for office in lower:
        key = fold(office["office"])
        key = ALIASES.get(key, key)
        places = localities_of.get(key)
        if places is None:
            unmatched.append(f"{office['office']} (cheie {key})")
            continue
        if office["volume"] == 0 or office["prosecutors"] == 0:
            dormant.append(office["office"])
            continue
        if not places:
            unmatched.append(office["office"])
            continue
        weights = {s: data.population[s] for s in places}
        total = sum(weights.values())
        if total <= 0:
            unmatched.append(office["office"])
            continue

        destinations = {court_of_unit.get(unit_of.get(s)) for s in places}
        destinations.discard(None)
        if not destinations:
            unmatched.append(office["office"])
            continue
        if len(destinations) == 1:
            invariant += office["volume"]
        else:
            split += office["volume"]

        for siruta in places:
            fraction = weights[siruta] / total
            seat = court_of_unit.get(unit_of.get(siruta))
            if seat is None:
                unreachable_volume += office["volume"] * fraction
                continue
            received[seat] += office["volume"] * fraction
            received_staff[seat] += office["prosecutors"] * fraction

    if unmatched:
        raise SystemExit(f"could not route the volume of: {unmatched}")

    # County-level offices sit at the county seat, as the tribunals they attach to do.
    seat_of_county = {seat_county[s]: s for s in seats}
    for office in upper:
        seat = seat_of_county.get(office["county"])
        if seat is None:
            raise SystemExit(f"no seat for county {office['county']}")
        received[seat] += office["volume"]
        received_staff[seat] += office["prosecutors"]

    routed = invariant + split
    upper_total = sum(o["volume"] for o in upper)
    # What arrived, plus what could not be reached, must equal what set out. `received` already
    # excludes the unreachable share, so it adds here rather than subtracting.
    landed = sum(received.values()) + unreachable_volume
    if abs(landed - routed - upper_total) > 1:
        raise SystemExit(
            f"volume was lost in routing: {routed + upper_total:,.0f} set out, {landed:,.0f} landed"
        )

    offices = []
    for seat in sorted(received, key=lambda s: -received[s]):
        staff = received_staff[seat]
        offices.append(
            {
                "siruta": seat,
                "name": seat_name[seat],
                "county": seat_county[seat],
                "volume": round(received[seat]),
                "prosecutors": round(staff, 1),
                "perProsecutor": round(received[seat] / staff, 1) if staff else None,
            }
        )

    # What routing by distance changes against merging by county.
    by_county = {o["county"]: o for o in comasare["merged"]}
    moved = 0.0
    differing = []
    for office in offices:
        county = by_county.get(office["county"])
        if county is None:
            continue
        delta = office["volume"] - county["volume"]
        if abs(delta) > 0.5:
            differing.append({"county": office["county"], "name": county["name"], "delta": round(delta)})
        moved += max(0.0, delta)
    differing.sort(key=lambda d: -abs(d["delta"]))

    loads = [o["perProsecutor"] for o in offices if o["perProsecutor"]]
    summary = {
        "seats": len(offices),
        "totalVolume": sum(o["volume"] for o in offices),
        "totalProsecutors": round(sum(o["prosecutors"] for o in offices), 1),
        "invariantVolume": round(invariant),
        "invariantShare": round(invariant / routed, 3),
        "unreachableVolume": round(unreachable_volume),
        "dormantOffices": sorted(dormant),
        "countiesDiffering": len(differing),
        "volumeChangingSeat": round(moved),
        "shareChangingSeat": round(moved / sum(o["volume"] for o in offices), 3),
        "biggestShift": differing[0] if differing else None,
        "spread": {
            "min": round(min(loads), 1),
            "max": round(max(loads), 1),
            "median": round(statistics.median(loads), 1),
            "maxOverMin": round(max(loads) / min(loads), 2),
        },
        "countySpreadMaxOverMin": comasare["summary"]["spreadAfter"]["maxOverMin"],
    }

    print(f"{summary['seats']} sedii, {summary['totalVolume']:,} dosare, "
          f"{summary['totalProsecutors']:,.0f} procurori")
    print(f"{summary['invariantShare'] * 100:.1f}% din volumul de nivel 1 merge întreg la un sediu")
    print(f"{summary['countiesDiffering']} sedii primesc altceva decât la comasarea pe județ; "
          f"{summary['volumeChangingSeat']:,} dosare ({summary['shareChangingSeat'] * 100:.1f}%) "
          f"schimbă sediul")
    if summary["biggestShift"]:
        b = summary["biggestShift"]
        print(f"cea mai mare mutare: {b['name']} {b['delta']:+,}")
    print(f"încărcătura: {summary['spread']['min']:,.0f}-{summary['spread']['max']:,.0f} "
          f"({summary['spread']['maxOverMin']}x; pe județ {summary['countySpreadMaxOverMin']}x)")

    document = {
        "$schema": "../schema/parchete-arondare.schema.json",
        "id": "parchete-arondare",
        "title": "Parchetele arondate după distanță, împreună cu instanțele",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": "2025",
        "variantOfPaper": True,
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Volumele pe parchet din anexe, rutate prin HG 1217/2023 și arondare-noua",
            "confidence": "derived",
            "note": (
                "Volumele sunt citate din raport. Teritoriul fiecărui parchet este cel al "
                "instanței pe lângă care funcționează, din HG 1217/2023; împărțirea pe comune "
                "după populație și arondarea la cel mai apropiat sediu sunt calculate aici."
            ),
        },
        "summary": summary,
        "offices": offices,
        "differences": differing,
        "limitations": [
            {
                "id": "circumscriptia-parchetului-e-a-instantei",
                "text": (
                    "Nicio hotărâre nu publică direct ce comune ține un parchet. Se ia "
                    "circumscripția instanței pe lângă care funcționează, fiindcă asta înseamnă "
                    "„de pe lângă” și fiindcă raportul CSM listează exact un parchet pentru "
                    "fiecare instanță. E o deducție, nu o citire: dacă vreun parchet ar avea "
                    "altă competență teritorială decât instanța lui, cifra lui de aici ar fi "
                    "greșită."
                ),
                "severity": "material",
                "affects": ["offices", "summary"],
            },
            {
                "id": "dosarele-se-impart-dupa-populatie",
                "text": (
                    "Ca la instanțe: dosarele unui parchet se împart pe comunele lui după "
                    "populație, fiindcă nu se publică de unde vine fiecare dosar. Cât de mult "
                    "contează se citește în „invariantShare”, partea din volum care merge "
                    "întreagă la un singur sediu și nu depinde deloc de împărțire."
                ),
                "severity": "material",
                "affects": ["offices"],
            },
            {
                "id": "procurorii-merg-cu-dosarele",
                "text": (
                    "Procurorii unui parchet sunt împărțiți pe aceleași ponderi ca dosarele lui. "
                    "E singura repartiție consecventă cu felul în care s-a împărțit volumul, dar "
                    "rezultă efective fracționare, iar un parchet nu se împarte în zecimi de om."
                ),
                "severity": "material",
                "affects": ["offices"],
            },
            {
                "id": "acelasi-oras-nu-inseamna-aceeasi-cladire",
                "text": (
                    "Argumentul pentru a aronda parchetele odată cu instanțele e logistic: "
                    "procurorul, judecătorul și poliția în același oraș. Faptul că ies în "
                    "aceleași 42 de orașe nu spune nimic despre clădiri, despre spațiu sau "
                    "despre costul mutării."
                ),
                "severity": "note",
                "affects": ["offices"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

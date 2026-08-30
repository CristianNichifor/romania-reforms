"""What each of the 42 proposed courts would actually have to judge.

The map half of this simulator says where every consolidated unit would go. The cost half says
how many judges the country needs in total. Nothing joined them: no file said what caseload any
individual proposed court would carry, which is the question a president of a court would ask
first and the one that decides whether a merged court is staffable.

The prosecution side of this got answered in `parchete-comasare`, because the CSM prints
prosecution volume per office. Courts are harder — volume is published per court, and the
proposed courts do not exist yet — so the work has to be routed:

    court volume (CSM, per judecatorie)
      -> split across the communes that court serves (HG 1217/2023 says which)
        -> each commune belongs to a consolidated unit (the administrative model)
          -> each unit answers to one of 42 seats (arondare-noua, by road distance)

**The splitting step is an assumption, and this file measures how much rests on it.** A
court's cases are divided among its communes in proportion to population, because how many
cases a commune generates is not published. That would be a soft foundation for the whole
answer — except that most of it does not depend on the split at all. Where every commune of an
existing judecatorie ends up at the same proposed court, that court inherits the whole volume
whatever the weighting, and the number only moves for the courts whose territory is divided.
The share of national volume that is assignment-invariant is computed and reported, so a reader
can see how much of the result is arithmetic and how much is modelling.

**The merger tightens the middle and leaves the tail, and the two have to be read together.**
Across the 175 courts that exist, the 90th percentile carries 9,7 times the caseload of the
10th. Across the 42 proposed courts that falls to 3,8 — a proportionally larger evening-out
than the prosecution merger managed. But the outright ratio between largest and smallest only
falls from 53,7 to 29,9, because pooling Bucharest's six sector courts and its tribunal creates
one court holding 676.660 cases, 19,5% of the country and 458 judges at the national average.
Consolidation makes ordinary courts alike; it does not make Bucharest ordinary.

**The inequality that remains is inherited, not created.** Cases per thousand residents vary
across the proposed courts by a factor of 1,7 between the 10th and 90th percentiles — much
less than volume does. Court size therefore mostly tracks how many people a court serves rather
than how litigious they are, which means the spread left after the merger is the county map's,
not the merger's.

Usage:
    uv run python scripts/build_incarcatura.py
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
OUT = ROOT / "data" / "incarcatura-noua.json"

sys.path.insert(0, str(ADMINISTRATIV))


# HG 1217/2023 and the CSM register spell ten courts differently, systematically: the decision
# uses the genitive for the Bucharest sectors and drops the enclitic article that the register
# keeps. Listed rather than fuzzy-matched, and every other mismatch is fatal — the first version
# of this file treated an unmatched court as dormant and silently dropped 14% of the national
# caseload, including all six Bucharest sectors.
ALIASES = {
    "GURAHONT": "GURA HONT",
    "ODORHEIU SECUIESC": "ODORHEIUL SECUIESC",
    "SIMLEU SILVANIEI": "SIMLEUL SILVANIEI",
    "SANNICOLAU MARE": "SANNICOLAUL MARE",
    **{f"SECTORULUI {n}": f"SECTORUL {n} BUCURESTI" for n in range(1, 7)},
}

# Judecătoria Însurăței is in the decision and absent from the register: it does not sit. This is
# the only court allowed to have no volume, and naming it here is what keeps "absent" from
# meaning "unmatched".
DORMANT = {"INSURATEI"}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.upper().replace("Ş", "S").replace("Ţ", "T").replace("-", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", text)).strip()


def load(name: str) -> dict:
    path = ROOT / "data" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run the importer that builds it first")
    return json.loads(path.read_text(encoding="utf-8"))


def spread(values: list[float]) -> dict:
    values = sorted(v for v in values if v > 0)
    quantiles = statistics.quantiles(values, n=10)
    return {
        "min": round(values[0], 1),
        "max": round(values[-1], 1),
        "median": round(statistics.median(values), 1),
        "maxOverMin": round(values[-1] / values[0], 2),
        "p90OverP10": round(quantiles[8] / quantiles[0], 2),
    }


def main() -> int:
    from pipeline.reference_model import Params, load_data, run  # noqa: PLC0415

    located = load("instante-localizate-2025")["courts"]
    legal = load("arondare-2023")["courts"]
    arondare = load("arondare-noua")

    data = load_data()
    result, _ = run(data, Params())

    # ---- commune -> consolidated unit -> proposed court ---------------------------------------
    unit_of: dict[str, str] = {}
    for seat, members in result.members.items():
        for member in members:
            unit_of[member] = seat
    court_of_unit = {u["siruta"]: u["courtSiruta"] for u in arondare["units"] if u["courtSiruta"]}
    seat_name = {u["courtSiruta"]: u["courtName"] for u in arondare["units"] if u["courtSiruta"]}
    seat_county = {u["courtSiruta"]: u["courtCounty"] for u in arondare["units"] if u["courtSiruta"]}
    if len(set(court_of_unit.values())) != 42:
        raise SystemExit(f"arondare-noua routes to {len(set(court_of_unit.values()))} seats, not 42")

    def court_of_commune(siruta: str) -> str | None:
        unit = unit_of.get(siruta)
        return court_of_unit.get(unit) if unit else None

    # ---- today's volume, per judecatorie, spread over the communes it serves -------------------
    volume_of_court = {
        fold(re.sub(r"^Judec[ăa]toria\s+", "", c["name"])): c["volume"]
        for c in located
        if c["tier"] == "judecatorie"
    }
    tribunal_volume: dict[str, int] = {}
    for court in located:
        if court["tier"] == "tribunal":
            tribunal_volume[court["county"]] = tribunal_volume.get(court["county"], 0) + court["volume"]

    received: dict[str, float] = {seat: 0.0 for seat in court_of_unit.values()}
    # Sulina's consolidated unit has no road to any court — the Delta is reached by water. Its
    # share of the volume is counted and reported rather than dropped or forced onto a seat: a
    # court it cannot drive to is not an assignment, it is a rounding error with a name.
    unreachable_volume = 0.0
    unreachable_communes: set[str] = set()
    invariant_volume = 0.0
    split_volume = 0.0
    unmatched_courts: list[str] = []
    homeless_localities = 0
    dormant: list[str] = []

    for court in legal:
        key = fold(re.sub(r"^Judec[ăa]toria\s+", "", court["name"]))
        key = ALIASES.get(key, key)
        if key in DORMANT:
            dormant.append(court["name"])
            continue
        volume = volume_of_court.get(key)
        if volume is None:
            unmatched_courts.append(f"{court['name']} (cheie {key})")
            continue
        localities = [s for s in court["localities"] if s in data.population]
        if not localities:
            unmatched_courts.append(court["name"])
            continue
        homeless_localities += len(court["localities"]) - len(localities)

        weights = {s: data.population[s] for s in localities}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            unmatched_courts.append(court["name"])
            continue

        destinations = {court_of_commune(s) for s in localities}
        destinations.discard(None)
        if not destinations:
            unmatched_courts.append(court["name"])
            continue
        # The measurement that tells a reader how much of this rests on the population split.
        if len(destinations) == 1:
            invariant_volume += volume
        else:
            split_volume += volume

        for siruta in localities:
            share = volume * weights[siruta] / total_weight
            seat = court_of_commune(siruta)
            if seat is None:
                unreachable_volume += share
                unreachable_communes.add(siruta)
                continue
            received[seat] += share

    if unmatched_courts:
        raise SystemExit(f"could not route the volume of: {unmatched_courts}")

    routed = invariant_volume + split_volume
    national_level_one = sum(volume_of_court.values())
    if abs(sum(received.values()) + unreachable_volume - routed) > 1:
        raise SystemExit(
            f"volume was lost in routing: {routed:,.0f} in, "
            f"{sum(received.values()) + unreachable_volume:,.0f} accounted for"
        )

    # ---- the proposed courts -------------------------------------------------------------------
    population_of_seat: dict[str, float] = {seat: 0.0 for seat in court_of_unit.values()}
    units_of_seat: dict[str, int] = {seat: 0 for seat in court_of_unit.values()}
    for unit in arondare["units"]:
        seat = unit.get("courtSiruta")
        if seat:
            population_of_seat[seat] += unit["population"]
            units_of_seat[seat] += 1

    # The judecatorie average, because the proposed court is the level-1 court. Read by tier
    # rather than by position: the report's order is not a contract.
    by_tier = load("instante-localizate-2025")["nationalAverages"]["byTier"]
    entry = next((t for t in by_tier if t["tier"] == "judecatorie"), None)
    if entry is None or not entry.get("perJudge"):
        raise SystemExit("no judecatorie caseload per judge in nationalAverages")
    per_judge = entry["perJudge"]

    courts = []
    for seat in sorted(received, key=lambda s: -received[s]):
        county = seat_county[seat]
        lower = received[seat]
        upper = tribunal_volume.get(county, 0)
        courts.append(
            {
                "siruta": seat,
                "name": seat_name[seat],
                "county": county,
                "units": units_of_seat[seat],
                "population": round(population_of_seat[seat]),
                "lowerVolume": round(lower),
                "upperVolume": upper,
                "volume": round(lower + upper),
                "judgesAtNationalLoad": round((lower + upper) / per_judge, 1),
                "casesPerThousandPeople": (
                    round((lower + upper) / population_of_seat[seat] * 1000, 1)
                    if population_of_seat[seat]
                    else None
                ),
            }
        )

    today = spread([c["volume"] for c in located if c["tier"] == "judecatorie"])
    after = spread([c["volume"] for c in courts])
    per_capita = spread([c["casesPerThousandPeople"] for c in courts if c["casesPerThousandPeople"]])

    busiest, quietest = courts[0], courts[-1]
    summary = {
        "courtsBefore": sum(1 for c in located if c["tier"] == "judecatorie"),
        "courtsAfter": len(courts),
        "routedVolume": round(routed),
        "nationalLevelOneVolume": national_level_one,
        "invariantVolume": round(invariant_volume),
        "invariantShare": round(invariant_volume / routed, 3),
        "splitVolume": round(split_volume),
        "tribunalVolume": sum(tribunal_volume.values()),
        "totalVolume": sum(c["volume"] for c in courts),
        "loadPerJudge": per_judge,
        "judgesNeeded": round(sum(c["judgesAtNationalLoad"] for c in courts), 1),
        "spreadToday": today,
        "spreadAfter": after,
        "spreadPerCapita": per_capita,
        "busiest": busiest["name"],
        "busiestVolume": busiest["volume"],
        "busiestShareOfTotal": round(busiest["volume"] / sum(c["volume"] for c in courts), 3),
        "busiestJudges": busiest["judgesAtNationalLoad"],
        "quietest": quietest["name"],
        "quietestVolume": quietest["volume"],
        "unreachableVolume": round(unreachable_volume),
        "unreachableCommunes": len(unreachable_communes),
        "dormantCourts": dormant,
        "localitiesNotInModel": homeless_localities,
    }

    print(f"{summary['courtsBefore']} judecătorii -> {summary['courtsAfter']} instanțe de nivel 1")
    print(f"volum rutat {summary['routedVolume']:,} din {national_level_one:,} dosare de nivel 1")
    print(f"  din care {summary['invariantShare'] * 100:.1f}% merge întreg la o singură instanță "
          f"(nu depinde de împărțirea pe populație)")
    print(f"+ {summary['tribunalVolume']:,} dosare de la tribunale = {summary['totalVolume']:,}\n")
    print(f"{'':16}{'min':>10}{'mediana':>11}{'max':>12}{'max/min':>10}{'p90/p10':>10}")
    for label, s in (("azi", today), ("după", after), ("la mia de loc.", per_capita)):
        print(f"{label:16}{s['min']:>10,.0f}{s['median']:>11,.0f}{s['max']:>12,.0f}"
              f"{s['maxOverMin']:>10.2f}{s['p90OverP10']:>10.2f}")
    print(f"\ncea mai încărcată: {busiest['name']} {busiest['volume']:,} dosare "
          f"({busiest['judgesAtNationalLoad']:.0f} judecători la media națională)")
    print(f"cea mai liniștită: {quietest['name']} {quietest['volume']:,} dosare")
    if dormant:
        print(f"instanțe din hotărâre fără activitate în registru: {dormant}")

    document = {
        "$schema": "../schema/incarcatura.schema.json",
        "id": "incarcatura-noua",
        "title": "Cât ar avea de judecat fiecare dintre cele 42 de instanțe propuse",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "csm-starea-justitiei-2025",
            "locator": "Anexa 1 (volumul pe instanță), rutat prin HG 1217/2023 și arondare-noua",
            "confidence": "derived",
            "note": (
                "Volumul fiecărei judecătorii este citat din raportul CSM. Împărțirea lui pe "
                "comune după populație, mutarea comunelor în unitățile consolidate și "
                "însumarea pe cele 42 de sedii sunt calculate aici."
            ),
        },
        "summary": summary,
        "courts": courts,
        "limitations": [
            {
                "id": "dosarele-se-impart-dupa-populatie",
                "text": (
                    "Dosarele unei judecătorii sunt împărțite pe comunele ei proporțional cu "
                    "populația, fiindcă nu se publică câte dosare vine din fiecare comună. O "
                    "comună urbană produce mai multe procese pe cap de locuitor decât una "
                    "rurală, deci împărțirea e aproximativă. Cât de mult contează se poate "
                    "citi: „invariantShare” spune ce parte din volum merge întreagă la o "
                    "singură instanță și deci nu depinde deloc de această împărțire."
                ),
                "severity": "material",
                "affects": ["courts", "summary"],
            },
            {
                "id": "delta-nu-are-drum",
                "text": (
                    "Unitatea consolidată a Sulinei — cinci comune, circa 7.200 de locuitori — "
                    "nu are drum până la niciun sediu de instanță, fiindcă în Deltă se ajunge pe "
                    "apă. Partea ei de volum e numărată separat, nu împărțită altor instanțe: o "
                    "instanță la care nu se poate ajunge cu mașina nu e o arondare."
                ),
                "severity": "note",
                "affects": ["courts", "summary"],
            },
            {
                "id": "arondarea-legala-e-din-2023",
                "text": (
                    "Ce comune ține fiecare judecătorie vine din HG 1217/2023, iar volumul din "
                    "raportul pe 2025. Între cele două date arondarea nu s-a schimbat, dar sunt "
                    "ani diferiți, iar comunele înființate după hotărâre nu au judecătorie în ea."
                ),
                "severity": "material",
                "affects": ["courts"],
            },
            {
                "id": "doua-niveluri-adunate-si-aici",
                "text": (
                    "Ca la parchete, volumul judecătoriilor și cel al tribunalelor sunt adunate, "
                    "deși un dosar de tribunal nu e cât unul de judecătorie. Comasarea propusă "
                    "asta presupune; cele două componente sunt păstrate separat în fișier ca să "
                    "poată fi citite și pe rând."
                ),
                "severity": "material",
                "affects": ["courts"],
            },
            {
                "id": "judecatorii-la-media-nationala",
                "text": (
                    "Numărul de judecători de care ar avea nevoie fiecare instanță e volumul "
                    "împărțit la încărcătura medie națională. E o măsură a mărimii, nu un stat "
                    "de funcții: o instanță mare se specializează pe complete și nu scalează "
                    "liniar, iar o instanță mică are un minim sub care nu poate funcționa."
                ),
                "severity": "material",
                "affects": ["courts"],
            },
            {
                "id": "depinde-de-parametrii-reformei-administrative",
                "text": (
                    "Unitățile consolidate sunt cele produse de simulatorul administrativ la "
                    "parametrii impliciți, iar arondarea lor e cea din „arondare-noua”. Cu alte "
                    "praguri ies alte unități, altă arondare și altă încărcătură."
                ),
                "severity": "material",
                "affects": ["courts"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

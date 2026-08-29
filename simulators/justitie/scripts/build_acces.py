"""What consolidation costs in travel: every commune, to its court, before and after.

This is the question the CSM report cannot answer and the reform paper asserts. Closing 183
first-level courts is a saving expressed in courts; to the person who has to attend one it is
a distance. With the arondare — which commune belongs to which judecătorie — and the road
graph the administrative simulator already builds, the distance is computable rather than
arguable.

**Today** is read from the law: HG 1217/2023 says which court serves a commune, and the road
distance is from that commune's seat to that court's seat.

**Under the proposal** each county keeps one level-1 court, seated where its tribunal already
sits, so every commune in the county travels to that one instead.

Both are road distances inside a county, which is the right scope: the arondare never crosses
a county line, and neither does the proposal.

Two things this deliberately does not do. It does not judge whether the extra distance is
worth the saving — that is the reader's call, and the point of showing it. And it does not
model who actually travels: a commune's population is not its litigants, so figures are
weighted by residents as the only proxy the data supports, and the limitation says so.

Usage:
    uv run python scripts/build_acces.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "acces-2025.json"

# The road graph belongs to the administrative simulator, which builds it from OSM and already
# exposes county-scoped shortest paths. Importing it is a real coupling and the second time
# this simulator has needed something from over there — the SIRUTA registry was the first.
# When there is a third, these move to packages/; two consumers is where that starts being
# arguable rather than premature.
sys.path.insert(0, str(ADMINISTRATIV))

BUCHAREST = "B"


def main() -> int:
    from pipeline.reference_model import _county_road_distances, load_data  # noqa: PLC0415

    arondare_file = ROOT / "data" / "arondare-2023.json"
    courts_file = ROOT / "data" / "instante-localizate-2025.json"
    for path in (arondare_file, courts_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    arondare = json.loads(arondare_file.read_text(encoding="utf-8"))
    located = json.loads(courts_file.read_text(encoding="utf-8"))["courts"]
    data = load_data()

    # The county's tribunal, which is where the proposal seats its one court. Specialised and
    # military tribunals are excluded: they sit in the same town but are not the county's
    # general first-level court.
    tribunal_seat: dict[str, str] = {}
    for court in located:
        if court["tier"] != "tribunal" or not court["siruta"]:
            continue
        name = court["name"]
        if any(word in name for word in ("Specializat", "Comercial", "Militar", "minori")):
            continue
        tribunal_seat.setdefault(court["county"], court["siruta"])

    rows: list[dict] = []
    unreachable: list[str] = []

    for court in arondare["courts"]:
        seat = court["seatSiruta"]
        county = court["county"]
        if not court["localities"] or not seat:
            continue
        today = _county_road_distances(data, county, [seat])
        target = tribunal_seat.get(county)
        tomorrow = _county_road_distances(data, county, [target]) if target else {}

        for siruta in court["localities"]:
            now = today.get(siruta, math.inf)
            then = tomorrow.get(siruta, math.inf)
            # Bucharest is one city: its sector courts and its tribunal are all in it, and a
            # road distance between sectors is not what anyone means by access here.
            if county == BUCHAREST:
                now = then = 0.0
            if not math.isfinite(now) or not math.isfinite(then):
                unreachable.append(f"{data.name[siruta]} ({county})")
                continue
            rows.append(
                {
                    "siruta": siruta,
                    "county": county,
                    "population": data.population[siruta],
                    "courtToday": court["name"],
                    "metresToday": round(now),
                    "metresProposed": round(then),
                }
            )

    if unreachable:
        print(f"{len(unreachable)} communes have no road route to a court:", file=sys.stderr)
        for line in unreachable[:10]:
            print(f"  {line}", file=sys.stderr)

    people = sum(r["population"] for r in rows)

    def weighted_median(key: str) -> float:
        ordered = sorted(rows, key=lambda r: r[key])
        half = people / 2
        running = 0
        for row in ordered:
            running += row["population"]
            if running >= half:
                return row[key]
        return 0.0

    def beyond(key: str, metres: int) -> int:
        return sum(r["population"] for r in rows if r[key] > metres)

    summary = {
        "communes": len(rows),
        "people": people,
        "medianTodayM": weighted_median("metresToday"),
        "medianProposedM": weighted_median("metresProposed"),
        "meanTodayM": round(sum(r["metresToday"] * r["population"] for r in rows) / people),
        "meanProposedM": round(sum(r["metresProposed"] * r["population"] for r in rows) / people),
        "beyond": {
            str(km): {
                "todayPeople": beyond("metresToday", km * 1000),
                "proposedPeople": beyond("metresProposed", km * 1000),
            }
            for km in (25, 50, 75, 100)
        },
        "unchanged": sum(1 for r in rows if r["metresProposed"] <= r["metresToday"]),
    }

    print(f"communes: {summary['communes']:,}   people: {people:,}")
    print(f"  median travel  {summary['medianTodayM'] / 1000:>6.1f} km -> "
          f"{summary['medianProposedM'] / 1000:.1f} km")
    print(f"  mean travel    {summary['meanTodayM'] / 1000:>6.1f} km -> "
          f"{summary['meanProposedM'] / 1000:.1f} km")
    for km, counts in summary["beyond"].items():
        print(f"  beyond {km:>3} km: {counts['todayPeople']:>10,} -> {counts['proposedPeople']:,}")
    print(f"  no worse off: {summary['unchanged']:,} communes")

    document = {
        "$schema": "../schema/acces.schema.json",
        "id": "acces-2025",
        "title": "Distanța până la instanță, azi și după comasare",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "hg-1217-2023-arondare",
            "locator": "arondarea din HG 1217/2023, distanțe rutiere din rețeaua OSM",
            "confidence": "derived",
            "note": (
                "Distanțele sunt calculate pe rețeaua de drumuri dintre reședința comunei și "
                "sediul instanței, în interiorul județului. Arondarea de azi este cea legală; "
                "cea propusă așază fiecare județ pe tribunalul lui."
            ),
        },
        "summary": summary,
        "communes": rows,
        "limitations": [
            {
                "id": "populatia-nu-e-numarul-de-justitiabili",
                "text": (
                    "Cifrele sunt ponderate cu populația comunei, pentru că numărul de "
                    "oameni care chiar ajung într-un proces nu există în datele publice pe "
                    "comune. O comună cu mulți locuitori și puține dosare cântărește aici mai "
                    "mult decât ar trebui."
                ),
                "severity": "material",
                "affects": ["access"],
            },
            {
                "id": "distanta-nu-e-timp",
                "text": (
                    "Se măsoară kilometri pe drum, nu timp de călătorie și nici transport "
                    "public. Într-o zonă de munte 40 de kilometri pot însemna mai mult decât "
                    "80 în câmpie."
                ),
                "severity": "material",
                "affects": ["access"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

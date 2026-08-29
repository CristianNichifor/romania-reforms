"""What consolidation costs in travel, and where the county line itself is the cost.

Closing 183 first-level courts is a saving expressed in courts; to the person attending one it
is a distance. With the arondare — which commune belongs to which judecătorie — and the road
graph the administrative simulator builds, the distance is computable rather than arguable.

Three numbers per commune, all on the **national** road graph:

  **azi** — to the court the law assigns it, under HG 1217/2023.
  **pe județ** — to the one court its county would keep.
  **cea mai apropiată** — to the nearest of the 42, wherever it is.

The third exists because the county line is a legal fact, not a geographic one. A commune in
northern Tulcea can be nearer to Brăila or Galați than to Tulcea, and a model that routes
everyone to their own county seat charges them for a boundary rather than for a journey. The
gap between the second and third numbers is what the county rule costs on its own, separately
from what consolidation costs.

Routing is national throughout, including for today's assignment: a commune's court is in its
own county, but the road to it need not stay there, and a county-scoped route would overstate
today's distance and flatter the comparison.

**Workload follows access.** If communes are reassigned to their nearest court, the caseload
goes with them. A court's dossiers are attributed to its communes in proportion to population
— the only split the public data supports — and then re-totalled per receiving court. The
proportionality is an assumption and the limitations say so.

Usage:
    uv run --project ../administrativ python scripts/build_acces.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "acces-2025.json"

# The road graph belongs to the administrative simulator, which builds it from OSM. This is
# the second thing this simulator needs from over there, after the SIRUTA registry; a third
# would settle the argument for moving both into packages/.
sys.path.insert(0, str(ADMINISTRATIV))

BUCHAREST = "B"


def main() -> int:
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    from scipy.sparse import coo_matrix  # noqa: PLC0415
    from scipy.sparse.csgraph import dijkstra  # noqa: PLC0415

    from pipeline.reference_model import load_data  # noqa: PLC0415

    arondare_file = ROOT / "data" / "arondare-2023.json"
    courts_file = ROOT / "data" / "instante-localizate-2025.json"
    edges_file = ADMINISTRATIV / "data" / "processed" / "road_distance.parquet"
    for path in (arondare_file, courts_file, edges_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    arondare = json.loads(arondare_file.read_text(encoding="utf-8"))
    located = json.loads(courts_file.read_text(encoding="utf-8"))["courts"]
    data = load_data()

    order = sorted(data.population)
    index_of = {siruta: i for i, siruta in enumerate(order)}
    size = len(order)

    # One undirected graph over every UAT seat in the country. County lines are not edges.
    edges = pd.read_parquet(edges_file)
    a = np.array([index_of[str(x)] for x in edges["a_siruta"]])
    b = np.array([index_of[str(x)] for x in edges["b_siruta"]])
    weight = edges["road_m"].to_numpy(dtype=float)
    keep = np.isfinite(weight)
    a, b, weight = a[keep], b[keep], weight[keep]
    graph = coo_matrix(
        (np.concatenate([weight, weight]), (np.concatenate([a, b]), np.concatenate([b, a]))),
        shape=(size, size),
    ).tocsr()

    # Today's courts, and the one court each county would keep. The proposal seats it where
    # the county's tribunal already sits; specialised and military tribunals share the town
    # but are not the county's general first-level court.
    court_of: dict[str, str] = {}
    seat_of_court: dict[str, str] = {}
    for court in arondare["courts"]:
        if not court["seatSiruta"]:
            continue
        seat_of_court[court["name"]] = court["seatSiruta"]
        for siruta in court["localities"]:
            court_of[siruta] = court["name"]

    county_court: dict[str, str] = {}
    for court in located:
        if court["tier"] != "tribunal" or not court["siruta"]:
            continue
        if any(w in court["name"] for w in ("Specializat", "Comercial", "Militar", "minori")):
            continue
        county_court.setdefault(court["county"], court["siruta"])

    # Bucharest's tribunal is seated on the city rather than on a sector, so it carries no
    # SIRUTA and never entered the court set — which left its six sectors being routed to
    # other counties' courts as though the capital had none. Seated on its lowest-numbered
    # sector: the choice is arbitrary and the distance is nil either way, because every
    # sector court and the tribunal are inside the same city.
    if BUCHAREST not in county_court:
        sectors = sorted(s for s in data.population if data.county[s] == BUCHAREST)
        if sectors:
            county_court[BUCHAREST] = sectors[0]

    def distances_from(seats: list[str]) -> np.ndarray:
        """Rows are seats, columns are UATs, in metres."""
        return dijkstra(graph, directed=False, indices=[index_of[s] for s in seats])

    today_seats = sorted(set(seat_of_court.values()))
    today_rows = {seat: i for i, seat in enumerate(today_seats)}
    today_matrix = distances_from(today_seats)

    proposed_seats = sorted(set(county_court.values()))
    proposed_rows = {seat: i for i, seat in enumerate(proposed_seats)}
    proposed_matrix = distances_from(proposed_seats)
    nearest_row = proposed_matrix.argmin(axis=0)
    nearest_metres = proposed_matrix.min(axis=0)

    # Attribute each court's dossiers to its communes by population, so that reassigning a
    # commune moves a share of the work with it.
    #
    # Keyed by the seat's SIRUTA, not by name: the decision writes "Judecatoria Gurahont" and
    # the CSM report "JUDECATORIA GURA HONT", and eleven of the 176 differ that way. Keyed by
    # name, every one of those courts contributes zero and the whole redistribution silently
    # collapses — which is exactly what it did.
    #
    # Judecatorii only. A tribunal's caseload is not attributable to communes the same way:
    # it serves the county as an appellate and specialised court rather than through an
    # arondare, so splitting it by population would invent a geography it does not have.
    volume_of_seat: dict[str, int] = {}
    for court in located:
        if court["tier"] == "judecatorie" and court["siruta"]:
            volume_of_seat[court["siruta"]] = volume_of_seat.get(court["siruta"], 0) + court["volume"]
    people_in_court: dict[str, int] = {}
    for siruta, name in court_of.items():
        people_in_court[name] = people_in_court.get(name, 0) + data.population[siruta]

    rows: list[dict] = []
    unreachable: list[str] = []
    for siruta, name in sorted(court_of.items()):
        column = index_of[siruta]
        county = data.county[siruta]
        seat = seat_of_court[name]

        today = today_matrix[today_rows[seat], column]
        by_county = (
            proposed_matrix[proposed_rows[county_court[county]], column]
            if county in county_court
            else math.inf
        )
        nearest = nearest_metres[column]
        nearest_seat = proposed_seats[nearest_row[column]]

        # Bucharest is one city: its sectors, their courts and the tribunal are all inside it,
        # and a road distance between them is not what access means here.
        if county == BUCHAREST:
            today = by_county = nearest = 0.0
            nearest_seat = county_court.get(BUCHAREST, seat)

        # No road at all. Eight of the eleven are the Danube Delta, where there is none —
        # Sulina, Crisan, Chilia Veche and their neighbours are reached by water whatever any
        # reform says. Kept in the file with null distances rather than dropped: eleven
        # communes vanishing from an access study would be the study answering a question
        # about 3.173 communes while appearing to answer one about 3.184.
        by_road = all(math.isfinite(x) for x in (today, by_county, nearest))
        if not by_road:
            unreachable.append(f"{data.name[siruta]} ({county})")

        # A court's caseload, split across its communes by population.
        share = data.population[siruta] / max(people_in_court.get(name, 0), 1)
        court_volume = volume_of_seat.get(seat, 0)
        rows.append(
            {
                "siruta": siruta,
                "county": county,
                "population": data.population[siruta],
                "courtToday": name,
                "cases": round(court_volume * share, 1),
                "metresToday": round(today) if by_road else None,
                "metresByCounty": round(by_county) if by_road else None,
                "metresNearest": round(nearest) if by_road else None,
                "nearestCounty": data.county[nearest_seat] if by_road else county,
                "byRoad": by_road,
            }
        )

    if unreachable:
        print(f"{len(unreachable)} communes have no road route:", file=sys.stderr)
        for line in unreachable[:10]:
            print(f"  {line}", file=sys.stderr)

    on_road = [r for r in rows if r["byRoad"]]
    people = sum(r["population"] for r in on_road)

    def weighted_median(key: str) -> float:
        ordered = sorted(on_road, key=lambda r: r[key])
        half, running = people / 2, 0
        for row in ordered:
            running += row["population"]
            if running >= half:
                return row[key]
        return 0.0

    def beyond(key: str, metres: int) -> int:
        return sum(r["population"] for r in on_road if r[key] > metres)

    keys = ("metresToday", "metresByCounty", "metresNearest")
    summary = {
        "communes": len(rows),
        "people": people,
        "median": {k: weighted_median(k) for k in keys},
        "mean": {k: round(sum(r[k] * r["population"] for r in on_road) / people) for k in keys},
        "beyond": {
            str(km): {k: beyond(k, km * 1000) for k in keys} for km in (25, 50, 75, 100)
        },
        "crossCounty": sum(1 for r in on_road if r["nearestCounty"] != r["county"]),
        "crossCountyPeople": sum(
            r["population"] for r in on_road if r["nearestCounty"] != r["county"]
        ),
        "communesWithoutRoad": sum(1 for r in rows if not r["byRoad"]),
    }

    # ---- assignment under a load ceiling -------------------------------------------------
    #
    # Nearest-court routing minimises travel and makes the load *less* even: communes flow to
    # whichever court is easiest to reach, and those are already the busiest. Balancing needs
    # the other half of the statement — get people as close as possible *subject to* no court
    # taking more than its share.
    #
    # Solved greedily by regret, deterministically, rather than by a solver. Each commune is
    # priced by what its second-nearest court would cost it over its nearest; the ones with
    # most to lose choose first, and a full court is skipped. Ties break on SIRUTA so the
    # answer is the same on every machine. This is not the optimum — an exact transportation
    # LP would beat it — but it is explainable line by line, which is worth more here than the
    # last per cent, and every run reports how far the result sits from unconstrained travel.
    # Bucharest is pinned, and the reason is a finding rather than a convenience. Its six
    # sectors carry 373.213 dossiers between them — 5,7 times the average court — and they
    # cannot be sent anywhere: a sector of the capital does not attend court in another
    # county. So no ceiling below 5,7x is reachable for Bucharest by moving communes, and the
    # only lever the proposal does not pull is giving the city more than one court.
    #
    # Left in the pool, its caseload spilled across the country and dragged mean travel to
    # 47,7 km, which is a statement about the algorithm rather than about Romania.
    bucharest_seat = county_court.get(BUCHAREST)

    def assign_with_ceiling(multiplier: float) -> tuple[dict[str, str], float]:
        movable = [r for r in on_road if r["county"] != BUCHAREST]
        total_cases = sum(r["cases"] for r in movable)
        seats = [s for s in proposed_seats if s != bucharest_seat]
        ceiling = multiplier * total_cases / max(len(seats), 1)
        load = dict.fromkeys(proposed_seats, 0.0)

        chosen_fixed = {}
        for row in on_road:
            if row["county"] == BUCHAREST and bucharest_seat:
                chosen_fixed[row["siruta"]] = bucharest_seat
                load[bucharest_seat] += row["cases"]

        priced = []
        for row in movable:
            column = index_of[row["siruta"]]
            options = sorted(
                (
                    (proposed_matrix[i, seat_index], seat)
                    for i, seat in enumerate(proposed_seats)
                    if seat != bucharest_seat
                    for seat_index in [column]
                ),
                key=lambda pair: (pair[0], pair[1]),
            )
            regret = options[1][0] - options[0][0] if len(options) > 1 else 0.0
            priced.append((-regret, row["siruta"], row, options))
        priced.sort(key=lambda item: (item[0], item[1]))

        chosen: dict[str, str] = dict(chosen_fixed)
        loads: dict[str, float] = dict(load)
        cost = 0.0
        for _, siruta, row, options in priced:
            # The ceiling is soft at the margin, and it has to be. Where every court is
            # already full the commune still has to go somewhere, and it goes to its nearest:
            # falling through to the last option instead sent it to the farthest court in the
            # country, which drove mean travel to 50 km and made a tighter ceiling produce a
            # worse spread than a looser one — the shape that gave the bug away.
            pick = next(
                ((m, seat) for m, seat in options if loads[seat] + row["cases"] <= ceiling),
                options[0],
            )
            metres, seat = pick
            chosen[siruta] = seat
            loads[seat] += row["cases"]
            cost += metres * row["population"]
        load.update(loads)
        return chosen, cost

    scenarios = {}
    for multiplier in (1.2, 1.5, 2.0):
        chosen, cost = assign_with_ceiling(multiplier)
        cases_of = {r["siruta"]: r["cases"] for r in on_road}
        loads: dict[str, float] = {}
        for siruta, seat in chosen.items():
            loads[seat] = loads.get(seat, 0.0) + cases_of[siruta]
        moved = sum(
            1
            for r in on_road
            if chosen[r["siruta"]] != proposed_seats[nearest_row[index_of[r["siruta"]]]]
        )
        scenarios[f"{multiplier:g}"] = {
            "ceilingMultiplier": multiplier,
            "spread": round(max(loads.values()) / max(min(loads.values()), 1), 1),
            "meanMetres": round(cost / people),
            "communesNotAtNearest": moved,
        }

    # Workload per receiving court, under each rule.
    def workload(key: str) -> dict[str, float]:
        totals: dict[str, float] = {}
        for row in rows:
            county = row["county"] if key == "metresByCounty" else row["nearestCounty"]
            totals[county] = totals.get(county, 0) + row["cases"]
        return totals

    by_county_load = workload("metresByCounty")
    by_access_load = workload("metresNearest")
    # A county whose court draws nothing is not a rounding artefact: it means every commune in
    # it is nearer to a neighbour's court, which is a statement about that county rather than
    # about the arithmetic. Reported rather than divided by.
    empty = sorted(c for c in by_county_load if by_access_load.get(c, 0) == 0)
    summary["balanced"] = scenarios
    summary["workload"] = {
        "byCounty": {
            "min": round(min(by_county_load.values())),
            "max": round(max(by_county_load.values())),
        },
        "byAccess": {
            "min": round(min(by_access_load.values())),
            "max": round(max(by_access_load.values())),
            "countiesDrawingNothing": empty,
        },
    }

    print(f"communes {summary['communes']:,} ({summary['communesWithoutRoad']} without a road)"
          f"   people on the road network {people:,}")
    for label, key in (("azi", "metresToday"), ("pe judet", "metresByCounty"), ("cea mai apropiata", "metresNearest")):
        print(f"  {label:<18} median {summary['median'][key] / 1000:>5.1f} km   "
              f"mean {summary['mean'][key] / 1000:>5.1f} km   "
              f"peste 50 km {summary['beyond']['50'][key]:>9,}")
    print(f"  communes nearer to another county's court: {summary['crossCounty']:,} "
          f"({summary['crossCountyPeople']:,} people)")
    load = summary["workload"]
    ratio = lambda d: f"{d['max'] / d['min']:.1f}x" if d["min"] else "infinit"  # noqa: E731
    print(f"  workload spread  pe judet {ratio(load['byCounty'])}   dupa acces {ratio(load['byAccess'])}")
    for name, sc in scenarios.items():
        print(f"  ceiling {name}x mean:  spread {sc['spread']:>5.1f}x   "
              f"mean travel {sc['meanMetres'] / 1000:>5.1f} km   "
              f"{sc['communesNotAtNearest']:>4} communes not at their nearest")
    if load["byAccess"]["countiesDrawingNothing"]:
        print(f"  counties whose court draws nothing: {load['byAccess']['countiesDrawingNothing']}")

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
                "Distanțele sunt calculate pe rețeaua națională de drumuri, între reședința "
                "comunei și sediul instanței. Traseul nu se oprește la granița județului, "
                "pentru că nici drumul nu se oprește."
            ),
        },
        "summary": summary,
        "communes": rows,
        "limitations": [
            {
                "id": "populatia-nu-e-numarul-de-justitiabili",
                "text": (
                    "Cifrele sunt ponderate cu populația comunei, pentru că numărul de oameni "
                    "care chiar ajung într-un proces nu există în datele publice pe comune. O "
                    "comună cu mulți locuitori și puține dosare cântărește aici mai mult decât "
                    "ar trebui. Din același motiv, dosarele unei instanțe sunt împărțite pe "
                    "comunele ei proporțional cu populația."
                ),
                "severity": "material",
                "affects": ["access", "workload"],
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
            {
                "id": "delta-nu-are-drum",
                "text": (
                    "Unsprezece comune nu au drum până la nicio instanță; opt dintre ele sunt "
                    "în Deltă — Sulina, Crișan, Chilia Veche, Pardina și vecinele lor — unde "
                    "accesul e pe apă, indiferent de orice reformă. Rămân în fișier, fără "
                    "distanță, și sunt scoase din medii; a le șterge ar face ca studiul să "
                    "răspundă despre 3.173 de comune arătând că răspunde despre 3.184."
                ),
                "severity": "material",
                "affects": ["access"],
            },
            {
                "id": "arondarea-peste-judet-nu-e-legala-azi",
                "text": (
                    "Varianta „cea mai apropiată instanță” ignoră granițele de județ. Astăzi "
                    "arondarea este stabilită prin lege pe județ, așa că această variantă "
                    "arată ce ar costa mai puțin, nu ce se poate face fără a schimba legea."
                ),
                "severity": "material",
                "affects": ["access", "workload"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Which court each consolidated UAT would answer to, chosen by road distance alone.

The access figures already route nationally, but they route *communes* — the 3.186 units that
exist today. If the administrative reform happens first, those communes are gone: they are
members of about 250 consolidated UATs, and it is the consolidated unit that needs a court.

Two things follow, and neither is visible at commune level.

**A unit must not be split.** Assigning communes one by one to their nearest court can send
two halves of the same new UAT to two different courts, which is not an arondare anyone could
administer. This file assigns the whole unit by the distance from its seat, and counts how
many units commune-level routing would have torn in half — that count is the argument for
doing it this way rather than a preference.

**County lines are not the right boundary.** Resedintele de judet are not evenly spaced, so a
unit near a county border is often closer to the neighbouring county's court than to its own.
The proposal keeps one court per county for coverage, but nothing requires a citizen to drive
past a nearer courthouse to reach the one inside their county. Assignment here is national:
the nearest of the 42 seats wins, whatever county it sits in.

What this is not: a legal arondare. Which localities answer to which court is fixed by
Government decision, and cross-county assignment is not something the current framework does.
This is what the map would look like if distance decided it.

Usage:
    uv run python scripts/build_arondare_noua.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "arondare-noua.json"

sys.path.insert(0, str(ADMINISTRATIV))

BUCHAREST = "B"


def main() -> int:
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    from scipy.sparse import coo_matrix  # noqa: PLC0415
    from scipy.sparse.csgraph import dijkstra  # noqa: PLC0415

    from pipeline.reference_model import Params, load_data, run  # noqa: PLC0415

    courts_file = ROOT / "data" / "instante-localizate-2025.json"
    edges_file = ADMINISTRATIV / "data" / "processed" / "road_distance.parquet"
    for path in (courts_file, edges_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    located = json.loads(courts_file.read_text(encoding="utf-8"))["courts"]
    data = load_data()

    order = sorted(data.population)
    index_of = {siruta: i for i, siruta in enumerate(order)}
    size = len(order)

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

    # The 42 seats: one per county, where the county's general tribunal already sits.
    county_court: dict[str, str] = {}
    for court in located:
        if court["tier"] != "tribunal" or not court["siruta"]:
            continue
        if any(w in court["name"] for w in ("Specializat", "Comercial", "Militar", "minori")):
            continue
        county_court.setdefault(court["county"], court["siruta"])
    if BUCHAREST not in county_court:
        sectors = sorted(s for s in data.population if data.county[s] == BUCHAREST)
        if sectors:
            county_court[BUCHAREST] = sectors[0]

    seats = sorted(set(county_court.values()))
    county_of_seat = {seat: county for county, seat in county_court.items()}
    matrix = dijkstra(graph, directed=False, indices=[index_of[s] for s in seats])

    # The consolidated map, at the administrative simulator's own defaults. Reading it from the
    # reference model rather than from a stored export keeps the two simulators from drifting:
    # if the merge rules change, this file changes with them on the next run.
    result, _ = run(data, Params())

    units = []
    split_by_commune = 0
    for seat, members in sorted(result.members.items()):
        population = sum(data.population[m] for m in members)
        county = data.county[seat]
        column = index_of[seat]
        metres = matrix[:, column]

        reachable = bool(np.isfinite(metres).any())
        nearest_i = int(np.argmin(metres)) if reachable else None
        nearest_seat = seats[nearest_i] if reachable else None
        nearest_m = float(metres[nearest_i]) if reachable else float("inf")

        own_seat = county_court.get(county)
        own_m = float(metres[seats.index(own_seat)]) if own_seat in seats else None

        # Would commune-by-commune routing have torn this unit apart?
        chosen = {
            seats[int(np.argmin(matrix[:, index_of[m]]))]
            for m in members
            if np.isfinite(matrix[:, index_of[m]]).any()
        }
        if len(chosen) > 1:
            split_by_commune += 1

        units.append(
            {
                "siruta": seat,
                "name": data.name[seat],
                "county": county,
                "members": len(members),
                "population": population,
                "courtSiruta": nearest_seat,
                "courtName": data.name[nearest_seat] if nearest_seat else None,
                "courtCounty": county_of_seat[nearest_seat] if nearest_seat else None,
                "metres": round(nearest_m) if reachable else None,
                "ownCountyMetres": (
                    None if own_m is None or not np.isfinite(own_m) else round(own_m)
                ),
                "crossesCounty": (
                    bool(county_of_seat[nearest_seat] != county) if nearest_seat else False
                ),
                "wouldSplitByCommune": len(chosen) > 1,
            }
        )

    routed = [u for u in units if u["metres"] is not None]
    crossing = [u for u in routed if u["crossesCounty"]]
    # Only meaningful where the unit's own county court is also reachable.
    comparable = [u for u in crossing if u["ownCountyMetres"] is not None]
    # Person-metres saved, reduced to metres per person who crosses. A national total in
    # person-kilometres is a number nobody can picture; "how much shorter is your drive" is.
    saved = sum((u["ownCountyMetres"] - u["metres"]) * u["population"] for u in comparable)
    crossing_people = sum(u["population"] for u in comparable)
    saved_each = saved / crossing_people if crossing_people else 0.0
    people = sum(u["population"] for u in routed)
    mean_nearest = sum(u["metres"] * u["population"] for u in routed) / people
    mean_own = (
        sum(
            u["ownCountyMetres"] * u["population"]
            for u in routed
            if u["ownCountyMetres"] is not None
        )
        / sum(u["population"] for u in routed if u["ownCountyMetres"] is not None)
    )

    print(f"unități consolidate: {len(units)}   rutate: {len(routed)}")
    print(f"trec granița de județ: {len(crossing)}  "
          f"({sum(u['population'] for u in crossing):,} locuitori)")
    print(f"s-ar rupe în două dacă am aronda comună cu comună: {split_by_commune}")
    print(f"\ndrum mediu ponderat: {mean_own / 1000:.1f} km pe județ  ->  "
          f"{mean_nearest / 1000:.1f} km la cea mai apropiată")
    print(f"pentru ei, drumul e mai scurt cu {saved_each / 1000:.0f} km în medie\n")
    biggest = sorted(comparable, key=lambda u: u["ownCountyMetres"] - u["metres"], reverse=True)
    print(f"{'unitate':<26}{'jud':>5}{'instanța':>18}{'jud':>5}{'la':>8}{'în jud.':>10}")
    for u in biggest[:12]:
        print(f"{u['name'][:24]:<26}{u['county']:>5}{u['courtName'][:16]:>18}"
              f"{u['courtCounty']:>5}{u['metres'] / 1000:>7.0f}k{u['ownCountyMetres'] / 1000:>9.0f}k")

    document = {
        "$schema": "../schema/arondare-noua.schema.json",
        "id": "arondare-noua",
        "title": "Arondarea unităților consolidate la instanțe, după distanță",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": (
                "Unitățile consolidate din simulatorul administrativ, la parametrii impliciți, "
                "arondate la cele 42 de sedii de tribunal pe graful rutier național"
            ),
            "confidence": "derived",
        },
        "courtSeats": len(seats),
        "summary": {
            "units": len(units),
            "routed": len(routed),
            "crossingCounty": len(crossing),
            "peopleCrossingCounty": sum(u["population"] for u in crossing),
            "wouldSplitByCommune": split_by_commune,
            "meanMetresOwnCounty": round(mean_own),
            "meanMetresNearest": round(mean_nearest),
            "metresSavedEachCrossing": round(saved_each),
        },
        "units": units,
        "limitations": [
            {
                "id": "arondarea-peste-judet-nu-e-legala",
                "text": (
                    "Arondarea — ce localități răspund de care instanță — se stabilește prin "
                    "hotărâre de Guvern, iar cadrul de azi nu arondează peste granița de județ. "
                    "Harta de aici arată cum ar arăta dacă ar decide distanța, nu cum este."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "depinde-de-parametrii-reformei-administrative",
                "text": (
                    "Unitățile consolidate sunt cele produse de simulatorul administrativ la "
                    "parametrii impliciți. Cu alte praguri ies alte unități, deci și altă "
                    "arondare. Cifrele de aici descriu o configurație, nu singura posibilă."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "distanta-se-masoara-din-sediu",
                "text": (
                    "Distanța este de la sediul unității consolidate la sediul instanței. "
                    "Locuitorii din comunele de margine ale unei unități mari au de mers mai "
                    "mult decât arată cifra, iar unitățile consolidate sunt, prin construcție, "
                    "mai mari decât comunele de azi."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "cele-42-raman-o-alegere-de-acoperire",
                "text": (
                    "Cele 42 de sedii sunt fixate de regula de acoperire — un tribunal de județ "
                    "plus Bucureștiul —, nu de distanță. Dacă sediile s-ar alege tot după "
                    "distanță, harta ar arăta din nou altfel."
                ),
                "severity": "note",
                "affects": ["acces"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

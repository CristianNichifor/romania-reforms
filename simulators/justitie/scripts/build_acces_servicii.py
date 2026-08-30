"""Court or hospital: which county service is actually further away.

Chapter 7 argues consolidation on logistics — put the county's services in one town. The
simulator can now put a number on what that means for a citizen, because the arondare and the
hospital coordinates finally sit on the same road graph and the same corrected court seats.

The comparison is deliberately asymmetric, and the asymmetry is the point. A consolidated UAT
gets one court, chosen by distance from among 42. It does not get "one hospital" — it uses
whichever is nearest, and there are 300 of them. So the question is not whether the reform
moves courts closer than hospitals; it is whether a country that already accepts driving *this
far* for emergency care would find the court's distance unusual.

**Every hospital distance here is an upper bound, and that is not a hedge.** The ministry's map
omits 52 hospitals in six counties. A hospital nobody plotted can only make the true distance
shorter, never longer, so wherever this file says a court is nearer than a hospital, the real
gap is at most that and possibly smaller. The claim is safe in exactly one direction and the
file only makes claims in that direction.

Usage:
    uv run python scripts/build_acces_servicii.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "acces-servicii.json"

sys.path.insert(0, str(ADMINISTRATIV))

BUCHAREST = "B"


def main() -> int:
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    from scipy.sparse import coo_matrix  # noqa: PLC0415
    from scipy.sparse.csgraph import dijkstra  # noqa: PLC0415

    from pipeline.reference_model import Params, load_data, run  # noqa: PLC0415

    spitale_file = ROOT / "data" / "spitale-2026.json"
    politie_file = ROOT / "data" / "politie-osm.json"
    courts_file = ROOT / "data" / "court-distance.json"
    edges_file = ADMINISTRATIV / "data" / "processed" / "road_distance.parquet"
    for path in (spitale_file, politie_file, courts_file, edges_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    spitale = json.loads(spitale_file.read_text(encoding="utf-8"))
    politie = json.loads(politie_file.read_text(encoding="utf-8"))
    courts = json.loads(courts_file.read_text(encoding="utf-8"))
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

    # One multi-source pass from every UAT that holds a hospital gives the nearest-hospital
    # distance for the whole country at once.
    hospital_seats = sorted(
        {h["siruta"] for h in spitale["hospitals"] if h["siruta"] and h["siruta"] in index_of}
    )
    if len(hospital_seats) < 50:
        print(f"only {len(hospital_seats)} hospital towns; the join broke", file=sys.stderr)
        return 1
    to_hospital = dijkstra(
        graph, directed=False, indices=[index_of[s] for s in hospital_seats], min_only=True
    )

    police_seats = sorted(
        {s["siruta"] for s in politie["stations"] if s["siruta"] and s["siruta"] in index_of}
    )
    to_police = dijkstra(
        graph, directed=False, indices=[index_of[s] for s in police_seats], min_only=True
    )

    court_seats = [c["siruta"] for c in courts["courts"]]
    county_of_seat = {c["siruta"]: c["county"] for c in courts["courts"]}
    court_matrix = dijkstra(graph, directed=False, indices=[index_of[s] for s in court_seats])
    to_court = court_matrix.min(axis=0)

    missing_counties = set(spitale["summary"]["countiesMissing"])
    result, _ = run(data, Params())

    units = []
    for seat, members in sorted(result.members.items()):
        column = index_of[seat]
        court_m = float(to_court[column])
        hospital_m = float(to_hospital[column])
        police_m = float(to_police[column])
        if not all(np.isfinite(x) for x in (court_m, hospital_m, police_m)):
            continue
        units.append(
            {
                "siruta": seat,
                "name": data.name[seat],
                "county": data.county[seat],
                "population": sum(data.population[m] for m in members),
                "courtMetres": round(court_m),
                "hospitalMetresAtMost": round(hospital_m),
                "policeMetresAtMost": round(police_m),
                # True only where the map is complete enough for the comparison to mean
                # anything; a unit near an unplotted hospital would read as further from care
                # than it is.
                "comparable": data.county[seat] not in missing_counties,
            }
        )

    comparable = [u for u in units if u["comparable"]]
    people = sum(u["population"] for u in comparable) or 1
    mean_court = sum(u["courtMetres"] * u["population"] for u in comparable) / people
    mean_hospital = sum(u["hospitalMetresAtMost"] * u["population"] for u in comparable) / people
    further_to_court = [u for u in comparable if u["courtMetres"] > u["hospitalMetresAtMost"]]
    people_further = sum(u["population"] for u in further_to_court)

    # The population-weighted mean is dominated by seats that already hold a hospital, so the
    # medians ship beside it. They are the honest shape of a distribution where most units sit
    # at zero for one service and forty kilometres for the other.
    def median(values: list[int]) -> int:
        ordered = sorted(values)
        middle = len(ordered) // 2
        if not ordered:
            return 0
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) // 2

    # Police cover all 42 counties, so unlike hospitals they need no county exclusion; the
    # median is taken over every routed unit rather than the comparable subset.
    median_police = median([u["policeMetresAtMost"] for u in units])
    seat_has_police = sum(1 for u in units if u["policeMetresAtMost"] == 0)
    median_court = median([u["courtMetres"] for u in comparable])
    median_hospital = median([u["hospitalMetresAtMost"] for u in comparable])
    # The same seats measured against both networks: this is the comparison that cannot be an
    # artefact of where consolidated seats are chosen, because it is one set of seats.
    seat_has_hospital = sum(1 for u in comparable if u["hospitalMetresAtMost"] == 0)
    seat_has_court = sum(1 for u in comparable if u["courtMetres"] == 0)

    print(f"unități comparabile: {len(comparable)} din {len(units)}  "
          f"({people:,} locuitori)".replace(",", "."))
    print(f"drum mediu la instanță: {mean_court / 1000:.1f} km")
    print(f"drum mediu la spital:   cel mult {mean_hospital / 1000:.1f} km")
    print(f"mediana: {median_court / 1000:.1f} km la instanță, "
          f"{median_hospital / 1000:.1f} km la spital")
    print(f"sedii care sunt deja oraș cu spital: {seat_has_hospital} din {len(comparable)}; "
          f"oraș cu instanță: {seat_has_court}")
    print(f"sedii cu secție de poliție: {seat_has_police} din {len(units)}   "
          f"mediana la poliție: cel mult {median_police / 1000:.1f} km")
    print(f"unități mai departe de instanță decât de spital: {len(further_to_court)} "
          f"({100 * people_further / people:.0f}% din locuitori)")

    document = {
        "$schema": "../schema/acces-servicii.schema.json",
        "id": "acces-servicii",
        "title": "Cât de departe e instanța, față de cât de departe e spitalul",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": (
                "Unitățile consolidate rutate pe graful național către cele 42 de sedii de "
                "instanță și către cele mai apropiate spitale localizate"
            ),
            "confidence": "derived",
        },
        "summary": {
            "units": len(units),
            "comparableUnits": len(comparable),
            "comparablePeople": people,
            "meanMetresToCourt": round(mean_court),
            "meanMetresToHospitalAtMost": round(mean_hospital),
            "medianMetresToCourt": median_court,
            "medianMetresToHospitalAtMost": median_hospital,
            "seatsThatAreHospitalTowns": seat_has_hospital,
            "seatsThatAreCourtTowns": seat_has_court,
            "medianMetresToPoliceAtMost": median_police,
            "seatsThatArePoliceTowns": seat_has_police,
            "policeTowns": len(police_seats),
            "unitsFurtherFromCourt": len(further_to_court),
            "peopleFurtherFromCourt": people_further,
            "hospitalTowns": len(hospital_seats),
        },
        "units": units,
        "limitations": [
            {
                "id": "distanta-la-spital-e-o-limita-de-sus",
                "text": (
                    "Harta ministerului nu are 52 de spitale din șase județe. Un spital "
                    "nemarcat nu poate decât să scurteze drumul real, niciodată să-l "
                    "lungească, deci distanțele la spital de aici sunt limite de sus. Acolo "
                    "unde instanța iese mai aproape decât spitalul, diferența adevărată e cel "
                    "mult atât, poate mai mică."
                ),
                "severity": "material",
                "affects": ["acces", "colocare"],
            },
            {
                "id": "judetele-fara-spitale-marcate-sunt-excluse",
                "text": (
                    "Unitățile din cele șase județe fără spitale pe hartă sunt păstrate în "
                    "fișier, dar scoase din comparație: pentru ele cifra ar spune că oamenii "
                    "sunt departe de îngrijire, când de fapt spitalul lor nu e marcat."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "media-e-trasa-in-jos-de-sedii",
                "text": (
                    "Media ponderată la spital e mică pentru că 62% dintre sediile unităților "
                    "consolidate sunt deja orașe cu spital, deci contează cu zero. De aceea "
                    "sunt publicate și medianele, și de aceea comparația care contează e "
                    "aceeași mulțime de sedii măsurată față de ambele rețele: 133 din 214 au "
                    "spital în oraș, 36 au instanță."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "politia-e-din-osm",
                "text": (
                    "Punctele de poliție vin din OpenStreetMap, fiindcă niciun registru public "
                    "nu le publică. Acoperirea e națională, dar colaborativă și neverificabilă, "
                    "deci distanțele la poliție sunt tot limite de sus."
                ),
                "severity": "material",
                "affects": ["acces", "colocare"],
            },
            {
                "id": "o-instanta-nu-e-o-urgenta",
                "text": (
                    "Comparația nu spune că un proces și o urgență medicală se măsoară la fel. "
                    "Spitalul e reperul disponibil pentru cât drum acceptă deja țara la un "
                    "serviciu județean, nu un etalon de echivalență."
                ),
                "severity": "note",
                "affects": ["colocare"],
            },
            {
                "id": "distanta-din-sediu-nu-din-casa",
                "text": (
                    "Se măsoară din sediul unității consolidate, nu de la casa omului. "
                    "Unitățile consolidate sunt mari, deci cei de la margine au de mers mai "
                    "mult decât arată ambele cifre."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

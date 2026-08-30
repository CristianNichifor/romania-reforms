"""The same country under several consolidation scenarios, costed each way.

Everything so far describes one map. That is a point, and the argument is a curve: consolidation
is defended as an administrative saving, and what it costs is a journey. Neither number means
much alone, and neither means much at a single setting.

The expensive step — the national travel-time matrix — does not depend on the scenario, so
running four of them is cheap. What changes per scenario is which centres exist, and therefore
every route, every bus and every journey above them.

**The question this exists to answer.** If the administrative saving is flat across scenarios
while the transport cost is not, then the aggressive consolidation is buying almost nothing and
paying for it in travel. If both move together, the trade is real and a reader has to weigh it.
Either way it is the reader's judgement, and the point of computing it is that the judgement can
be made with numbers instead of impressions.

Output:
    data/scenarios.json

Usage:
    uv run python -m scripts.sweep_scenarios
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "scenarios.json"

sys.path.insert(0, str(ADMINISTRATIV))

from scripts.costs import WEEKDAYS_PER_YEAR, annual_cost, load_prices  # noqa: E402
from scripts.county_times import county_times  # noqa: E402
from scripts.fleet import resources_for_route  # noqa: E402
from scripts.network import routes_for_hub  # noqa: E402
from scripts.tiers import DAY_PROFILE, classify, service_for  # noqa: E402
from scripts.zones import zone_of, zones_from_counties  # noqa: E402

LAYOVER_MIN: Final[float] = 10.0
SPARE_RATIO: Final[float] = 0.15
PULSE_DWELL_MIN: Final[float] = 5.0
SEATS: Final[dict[str, int]] = {"basic": 20, "feeder": 40, "trunk": 50}

# Four settings of administrativ's own parameters. Not a sweep of everything — a handful of
# scenarios a reader might actually argue for, from the hardest consolidation to the loosest.
SCENARIOS: Final[list[dict]] = [
    {"id": "implicit", "label": "Parametrii impliciți", "params": {}},
    {"id": "prag-inalt", "label": "Prag de absorbție mai mare", "params": {"x": 15_000}},
    {
        "id": "raze-mici",
        "label": "Raze mai mici",
        "params": {"r_national_m": 10_000, "r_cap_m": 7_500, "r_town_m": 7_500},
    },
    {"id": "fara-tinta", "label": "Fără țintă de populație", "params": {"p_target": 0}},
    # Not a setting of administrativ's model — a map imposed directly. Its parameters never
    # produce very few regions, so the four above are variations on the same shape and the
    # trade-off cannot show itself. One centre per county is the shape the judicial reform
    # proposes, and it is the honest extreme against which "consolidation costs travel" is
    # either true or is not.
    {"id": "un-centru-pe-judet", "label": "Un centru pe județ", "params": None},
]


def cost_one(
    region_of,
    data,
    county,
    population,
    neighbours,
    edge_s,
    edge_m,
    zones,
    capitals,
    prices,
    dwell,
    factor,
):
    """Route, cost and time one scenario end to end. Returns the numbers a reader compares."""
    members: dict[str, set[str]] = collections.defaultdict(set)
    for uat, centre in region_of.items():
        members[centre].add(uat)
    hub_ids = set(members)
    in_county: dict[str, set[str]] = collections.defaultdict(set)
    for uat, code in county.items():
        in_county[code].add(uat)

    routes: list[tuple[str, list[str], list[str], float, float]] = []

    def collect(hub, group, zone, tier):
        for r in routes_for_hub(hub, group, zone, neighbours, edge_s, population):
            metres = 0.0
            ok = True
            for a, b in zip(r.stops, r.stops[1:], strict=False):
                step = edge_m.get((a, b))
                if step is None:
                    ok = False
                    break
                metres += step
            if ok:
                routes.append((tier, r.stops, r.serves, r.one_way_min, metres / 1000))

    for centre, group in members.items():
        collect(centre, group, zones[zone_of(county[centre])], "T3")
    for capital, code in capitals.items():
        centres = {h for h in hub_ids if county[h] == code} | {capital}
        if len(centres) > 1:
            collect(capital, centres, in_county[code], "T2")

    hours = 0.0
    km_by_class: dict[str, float] = collections.defaultdict(float)
    peak_by_class: dict[str, int] = collections.defaultdict(int)
    for tier, stops, serves, one_way, km in routes:
        if tier == "T2":
            name = "trunk"
        else:
            largest = max((int(population[s]) for s in serves), default=0)
            name = classify(largest, is_hub=False)
        service = service_for(name)
        res = resources_for_route(
            round_trip_min=2 * one_way / factor + len(stops) * dwell,
            layover_min=LAYOVER_MIN,
            departures=service.departures,
            period_hours=DAY_PROFILE,
            km_round_trip=2 * km,
        )
        hours += res.bus_hours
        km_by_class[name] += res.bus_km
        peak_by_class[name] += res.peak_vehicles

    fleet = {n: math.ceil(p * (1 + SPARE_RATIO)) for n, p in peak_by_class.items()}
    cost = annual_cost(hours, dict(km_by_class), fleet, prices)

    # Journey to the county seat, pulsed and not, weighted by the people who make it.
    trunk_by_centre = {
        c: ow / factor for tier, _s, serves, ow, _k in routes if tier == "T2" for c in serves
    }
    headway = sum(DAY_PROFILE.values()) * 60.0 / sum(service_for("trunk").departures.values())
    journeys: list[tuple[float, float, int]] = []
    # Kept per UAT as well as aggregated: the map needs to be able to show the difference,
    # not only report it. Rounded to whole minutes because that is all a colour band uses.
    per_uat: dict[str, tuple[int, int]] = {}
    for centre, group in members.items():
        reach = county_times(county, neighbours, edge_s, county[centre], [centre])
        trunk = trunk_by_centre.get(centre, 0.0 if centre in capitals else None)
        if trunk is None:
            continue
        for uat in group:
            feeder = (
                0.0 if uat == centre else (reach[uat] / 60.0 / factor if uat in reach else None)
            )
            if feeder is None:
                continue
            free = 0.0 if (uat == centre and trunk == 0.0) else 1.0
            journeys.append(
                (
                    feeder + free * headway / 2 + trunk,
                    feeder + free * PULSE_DWELL_MIN + trunk,
                    int(population[uat]),
                )
            )
            per_uat[uat] = (
                round(feeder + free * headway / 2 + trunk),
                round(feeder + free * PULSE_DWELL_MIN + trunk),
            )

    people = sum(p for _u, _p, p in journeys)

    def weighted_median(index: int) -> float:
        ordered = sorted(journeys, key=lambda j: j[index])
        half, running = people / 2, 0
        for row in ordered:
            running += row[2]
            if running >= half:
                return round(row[index], 1)
        return 0.0

    total_km = sum(km_by_class.values())
    return {
        "hubs": len(hub_ids),
        "routes": len(routes),
        "fleet": sum(fleet.values()),
        "meanSeats": round(sum(SEATS[c] * n for c, n in fleet.items()) / sum(fleet.values()), 1),
        "busHoursWeekday": round(hours),
        "busKmWeekday": round(total_km),
        "operatingRon": round(cost.operating_ron),
        "capitalRon": round(cost.capital_ron),
        "totalRon": round(cost.total_ron),
        "ronPerBusKm": round(cost.operating_ron / (total_km * WEEKDAYS_PER_YEAR), 2),
        "peopleWithJourney": people,
        "medianUncoordinatedMin": weighted_median(0),
        "medianPulsedMin": weighted_median(1),
        "journeyByUat": per_uat,
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd
    import pandas as pd
    from pipeline.county_capitals import COUNTY_CAPITAL_SIRUTA
    from pipeline.reference_model import Params, load_data, run

    processed = ADMINISTRATIV / "data" / "processed"
    times_file = ROOT / "data" / "road_time.parquet"
    if not times_file.exists():
        raise SystemExit(f"Missing {times_file}. Run: uv run python -m scripts.build_road_time")

    prices = load_prices()
    items = json.loads((ROOT / "data/cost-inputs.json").read_text(encoding="utf-8"))["items"]
    dwell, factor = items["dwellMinPerStop"]["value"], items["serviceSpeedFactor"]["value"]

    times = pd.read_parquet(times_file)
    distances = pd.read_parquet(processed / "road_distance.parquet")
    adjacency = pd.read_parquet(processed / "adjacency.parquet")
    uats = gpd.read_file(processed / "uat_geometry.gpkg", layer="uat")
    county = dict(zip(uats.siruta, uats.county_code, strict=True))
    population = dict(zip(uats.siruta, uats.population, strict=True))

    edge_s: dict[tuple[str, str], float] = {}
    for a, b, s in zip(times.a_siruta, times.b_siruta, times.road_s, strict=True):
        if np.isfinite(s):
            edge_s[(a, b)] = edge_s[(b, a)] = s
    edge_m: dict[tuple[str, str], float] = {}
    for a, b, m in zip(distances.a_siruta, distances.b_siruta, distances.road_m, strict=True):
        if np.isfinite(m):
            edge_m[(a, b)] = edge_m[(b, a)] = m
    neighbours: dict[str, list[str]] = collections.defaultdict(list)
    for a, b, ok in zip(adjacency.a_siruta, adjacency.b_siruta, adjacency.traversable, strict=True):
        if ok:
            neighbours[a].append(b)
            neighbours[b].append(a)
    zones = zones_from_counties(county)
    capitals = {s: c for s, c in COUNTY_CAPITAL_SIRUTA.items()}

    data = load_data()
    rows = []
    for scenario in SCENARIOS:
        print(f"  {scenario['label']}...", flush=True)
        if scenario["params"] is None:
            # Every UAT to its county capital. Bucharest keeps its own sector as a centre,
            # because it has no capital in the table and its sectors are centres already.
            capital_of = {c: s for s, c in capitals.items()}
            region_of = {u: capital_of.get(county[u], u) for u in county if county[u] in capital_of}
            info = {"savings_admin_ron": float("nan"), "savings_operating_ron": float("nan")}
        else:
            result, info = run(data, Params(**scenario["params"]))
            region_of = result.region_of
        row = cost_one(
            region_of,
            data,
            county,
            population,
            neighbours,
            edge_s,
            edge_m,
            zones,
            capitals,
            prices,
            dwell,
            factor,
        )
        row |= {
            "id": scenario["id"],
            "label": scenario["label"],
            "params": scenario["params"],
            "administrativeSavingRon": (
                None
                if info["savings_admin_ron"] != info["savings_admin_ron"]
                else round(info["savings_admin_ron"])
            ),
            "operatingSavingRon": (
                None
                if info["savings_operating_ron"] != info["savings_operating_ron"]
                else round(info["savings_operating_ron"])
            ),
        }
        rows.append(row)

    base = rows[0]
    document = {
        "$schema": "../schema/scenarios.schema.json",
        "id": "scenarios",
        "title": "Aceeași țară, sub mai multe scenarii de comasare",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "administrativ-plus-retea",
            "locator": (
                "modelul administrativ rulat la parametrii din fiecare scenariu, apoi trasee, "
                "flotă și cost pe aceeași rețea rutieră"
            ),
            "confidence": "derived",
            "note": (
                "Matricea de timpi de parcurs nu depinde de scenariu, deci scenariile diferă "
                "doar prin ce centre există. Tot ce se schimbă mai sus decurge din asta."
            ),
        },
        "scenarios": rows,
        "limitations": [
            {
                "id": "patru-puncte-nu-o-curba",
                "text": (
                    "Sunt patru setări, alese pentru că cineva le-ar putea susține, nu o "
                    "explorare a spațiului de parametri. Între ele curba nu este cunoscută."
                ),
                "severity": "material",
                "affects": ["cost", "access"],
            },
            {
                "id": "economiile-nu-sunt-ale-noastre",
                "text": (
                    "Economiile administrative sunt calculate de simulatorul administrativ, "
                    "cu limitările lui, iar costurile de transport moștenesc modelul de viteze "
                    "neverificat de aici."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"\n{'scenariu':28}{'centre':>8}{'flotă':>8}{'cost/an':>12}{'mediană':>10}{'econ.adm':>12}"
    )
    for r in rows:
        print(
            f"{r['label']:28}{r['hubs']:>8}{r['fleet']:>8}"
            f"{r['totalRon'] / 1e9:>10.2f}md{r['medianPulsedMin']:>9.0f}m"
            + (
                f"{r['administrativeSavingRon'] / 1e9:>10.2f}md"
                if r["administrativeSavingRon"]
                else f"{'—':>12}"
            )
        )
    print(f"\nagainst {base['label']}:")
    for r in rows[1:]:
        print(
            f"  {r['label']:26} centres {r['hubs'] / base['hubs'] - 1:+6.0%}   "
            f"transport {r['totalRon'] / base['totalRon'] - 1:+6.0%}   "
            f"journey {r['medianPulsedMin'] / base['medianPulsedMin'] - 1:+6.0%}   "
            + (
                f"saving {r['administrativeSavingRon'] / base['administrativeSavingRon'] - 1:+6.0%}"
                if r["administrativeSavingRon"]
                else "saving      —"
            )
        )
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

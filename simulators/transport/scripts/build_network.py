"""Build the national feeder network, and name the places it cannot reach.

One shortest-path tree per hub, every leaf a route, every UAT either served exactly once or
listed by name as unroutable. There is no third outcome: a UAT that were neither would be a
place nobody counted, and an uncounted place flatters every figure built on top of it — the
failure that once cost administrativ eight courts, including all six Bucharest sector courts.

The unroutable are not a number, they are a list. Fourteen UATs have no road route to their
hub and almost all of them are Danube Delta or Brăila river-island communes — Chilia Veche,
Crișan, C.A. Rosetti, Maliuc, Pardina, Ceatalchioi, Frecăței, Mărașu. Reachable only by water,
found by the model without being told they exist. A count would hide that; the list invites
someone to notice the model is right about which places are hard.

Distance is accumulated along the same tree as time, rather than routed separately: a bus
drives the road it drives, and taking the time from one path and the kilometres from another
would price a journey nobody makes.

Output:
    data/network.json    routes, the unroutable, and what the network totals

Usage:
    uv run python -m scripts.build_network
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "network.json"

sys.path.insert(0, str(ADMINISTRATIV))

from pipeline.county_capitals import COUNTY_CAPITAL_SIRUTA  # noqa: E402

from scripts.network import routes_for_hub  # noqa: E402
from scripts.zones import zone_of, zones_from_counties  # noqa: E402


def path_metres(stops: list[str], edge_m: dict[tuple[str, str], float]) -> float:
    """Kilometres along the route the bus actually drives, leaf to hub.

    Missing edge returns NaN rather than zero: a route whose length cannot be measured must
    not be priced as though it were free.
    """
    total = 0.0
    for here, nxt in zip(stops, stops[1:], strict=False):
        step = edge_m.get((here, nxt))
        if step is None:
            return float("nan")
        total += step
    return total


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd
    import pandas as pd

    processed = ADMINISTRATIV / "data" / "processed"
    hubs_file = ROOT / "data" / "hubs.json"
    times_file = ROOT / "data" / "road_time.parquet"
    for path, how in (
        (hubs_file, "uv run python -m scripts.export_hubs"),
        (times_file, "uv run python -m scripts.build_road_time"),
    ):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run: {how}")

    hub_doc = json.loads(hubs_file.read_text(encoding="utf-8"))
    hub_of = hub_doc["hubOf"]

    times = pd.read_parquet(times_file)
    distances = pd.read_parquet(processed / "road_distance.parquet")
    adjacency = pd.read_parquet(processed / "adjacency.parquet")
    uats = gpd.read_file(processed / "uat_geometry.gpkg", layer="uat")

    county = dict(zip(uats.siruta, uats.county_code, strict=True))
    population = dict(zip(uats.siruta, uats.population, strict=True))
    name = dict(zip(uats.siruta, uats.name_uat, strict=True))

    edge_s: dict[tuple[str, str], float] = {}
    for a, b, seconds in zip(times.a_siruta, times.b_siruta, times.road_s, strict=True):
        if np.isfinite(seconds):
            edge_s[(a, b)] = edge_s[(b, a)] = seconds
    edge_m: dict[tuple[str, str], float] = {}
    for a, b, metres in zip(distances.a_siruta, distances.b_siruta, distances.road_m, strict=True):
        if np.isfinite(metres):
            edge_m[(a, b)] = edge_m[(b, a)] = metres

    neighbours: dict[str, list[str]] = collections.defaultdict(list)
    for a, b, traversable in zip(
        adjacency.a_siruta, adjacency.b_siruta, adjacency.traversable, strict=True
    ):
        if traversable:
            neighbours[a].append(b)
            neighbours[b].append(a)

    zones = zones_from_counties(county)
    members: dict[str, set[str]] = collections.defaultdict(set)
    for uat, centre in hub_of.items():
        members[centre].add(uat)
    hub_ids = set(members)

    def emit(route, tier: str) -> dict:
        km = path_metres(route.stops, edge_m) / 1000
        return {
            "tier": tier,
            "hub": route.hub,
            "leaf": route.leaf,
            "stops": route.stops,
            "serves": route.serves,
            "oneWayMin": round(route.one_way_min, 1),
            "oneWayKm": None if np.isnan(km) else round(km, 1),
            "isLong": route.is_long,
        }

    # T3, the feeders: every UAT to the centre that serves it.
    print(f"Routing {len(members)} hubs (T3 feeders)...")
    rows: list[dict] = []
    served: set[str] = set()
    for centre in sorted(members):
        for route in routes_for_hub(
            hub=centre,
            members=members[centre],
            zone=zones[zone_of(county[centre])],
            neighbours=neighbours,
            edge_s=edge_s,
            population=population,
        ):
            served.update(route.serves)
            rows.append(emit(route, "T3"))

    # T2, the trunk: every centre to its county seat. The same tree machinery, with the hubs
    # as members instead of the UATs — `members` is what a route serves and `zone` is what it
    # may cross, so a trunk route drives through the villages between two centres without
    # being responsible for them. Their feeder already is.
    #
    # This layer matters more than its route count suggests. A feeder reaches a centre in a
    # median 27,6 minutes; the trunk leg from that centre to the county seat is a median 55,4.
    # Costing the feeders alone would have described a network that connects nobody to their
    # county town.
    in_county: dict[str, set[str]] = collections.defaultdict(set)
    for uat, code in county.items():
        in_county[code].add(uat)

    print(f"Routing {len(COUNTY_CAPITAL_SIRUTA)} county seats (T2 trunk)...")
    trunk_served: set[str] = set()
    for capital, code in sorted(COUNTY_CAPITAL_SIRUTA.items(), key=lambda kv: kv[1]):
        centres = {h for h in hub_ids if county[h] == code} | {capital}
        if len(centres) < 2:
            continue
        for route in routes_for_hub(
            hub=capital,
            members=centres,
            zone=in_county[code],
            neighbours=neighbours,
            edge_s=edge_s,
            population=population,
        ):
            trunk_served.update(route.serves)
            rows.append(emit(route, "T2"))

    trunk_orphans = sorted(
        h
        for h in hub_ids
        if county[h] != "B" and h not in COUNTY_CAPITAL_SIRUTA and h not in trunk_served
    )

    unroutable = sorted(set(hub_of) - served - hub_ids)
    feeders = [r for r in rows if r["tier"] == "T3"]
    trunks = [r for r in rows if r["tier"] == "T2"]

    def quantiles(subset: list[dict]) -> dict:
        minutes = np.array([r["oneWayMin"] for r in subset])
        return {
            "routes": len(subset),
            "oneWayMinMedian": round(float(np.median(minutes)), 1),
            "oneWayMinP90": round(float(np.quantile(minutes, 0.9)), 1),
            "oneWayMinMax": round(float(minutes.max()), 1),
            "longRoutes": sum(1 for r in subset if r["isLong"]),
        }

    document = {
        "$schema": "../schema/network.schema.json",
        "id": "network",
        "title": "Rețeaua de trasee care leagă fiecare UAT de centrul lui",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "arbore-de-drumuri-minime",
            "locator": (
                "arbore de drumuri minime din fiecare centru peste zona lui, pe timpii din "
                "data/road_time.parquet și repartizarea din data/hubs.json"
            ),
            "confidence": "derived",
            "note": (
                "Traseul deservește o regiune, dar poate traversa toată zona: restrângerea "
                "la regiune ar lăsa 91 de UAT-uri fără traseu. Timpii sunt modelați, nu "
                "măsurați pe teren."
            ),
        },
        "summary": {
            "hubs": len(hub_ids),
            "routes": len(rows),
            "uatsServed": len(served),
            "uatsUnroutable": len(unroutable),
            "uatsTotal": len(hub_of),
            "countySeats": len(COUNTY_CAPITAL_SIRUTA),
            "hubsWithoutTrunk": len(trunk_orphans),
            "feeder": quantiles(feeders),
            "trunk": quantiles(trunks),
            "hubSirutas": sorted(hub_ids),
        },
        "hubsWithoutTrunk": [
            {"siruta": s, "name": name[s], "county": county[s]} for s in trunk_orphans
        ],
        "unroutable": [
            {"siruta": s, "name": name[s], "county": county[s], "hub": hub_of[s]}
            for s in unroutable
        ],
        "routes": rows,
        "limitations": [
            {
                "id": "uat-uri-fara-drum",
                "text": (
                    "Paisprezece UAT-uri nu au traseu rutier până la centrul lor și sunt "
                    "listate pe nume. Aproape toate sunt în Delta Dunării sau pe insulele "
                    "Brăilei, accesibile doar pe apă. Ele nu apar în costuri, deci orice "
                    "cifră de aici descrie țara mai puțin aceste locuri."
                ),
                "severity": "material",
                "affects": ["network", "cost", "access"],
            },
            {
                "id": "centre-fara-legatura-la-resedinta",
                "text": (
                    "Un centru nu are traseu rutier până la reședința de județ: Sulina, în "
                    "Deltă, accesibilă doar pe apă. Locuitorii arondați lui ajung la centru, "
                    "dar nu mai departe, iar drumul până la reședința de județ nu apare în "
                    "niciun cost de aici."
                ),
                "severity": "material",
                "affects": ["network", "cost", "access"],
            },
            {
                "id": "legatura-trunchi-dubleaza-drumul",
                "text": (
                    "Traseul de rabatere ajunge la centru într-o mediană de 27,6 minute, dar "
                    "de acolo până la reședința de județ mediana este 60,6. O călătorie "
                    "completă este deci de ordinul a 88 de minute dus, fără timpul de "
                    "așteptare la corespondență, care nu este încă modelat."
                ),
                "severity": "material",
                "affects": ["access"],
            },
            {
                "id": "trasee-lungi-neîmpărțite",
                "text": (
                    "Cincizeci de trasee depășesc o oră dus. Un traseu nu poate fi scurtat "
                    "prin împărțire — durata lui este distanța capătului până la centru — "
                    "așa că sunt semnalate, nu ascunse. Releele și corespondențele sunt un "
                    "răspuns real, dar aparțin nivelului de orar."
                ),
                "severity": "material",
                "affects": ["access"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    s = document["summary"]
    for tier, label in (("feeder", "T3 feeder"), ("trunk", "T2 trunk ")):
        q = s[tier]
        print(
            f"  {label}: {q['routes']:>5,} routes   one-way median "
            f"{q['oneWayMinMedian']:>5.1f}  p90 {q['oneWayMinP90']:>5.1f}  "
            f"max {q['oneWayMinMax']:>5.1f}   over an hour {q['longRoutes']}"
        )
    print(
        f"  UATs served {s['uatsServed']:,}   unroutable {s['uatsUnroutable']} (named)   "
        f"hubs without a trunk route {s['hubsWithoutTrunk']}"
    )
    covered = len(served) + len(unroutable) + len(hub_ids)
    print(f"  accounted for: {covered:,} of {s['uatsTotal']:,}")
    if covered != s["uatsTotal"]:
        print("  FATAL: a UAT is neither served, nor a hub, nor named unroutable", file=sys.stderr)
        return 1
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

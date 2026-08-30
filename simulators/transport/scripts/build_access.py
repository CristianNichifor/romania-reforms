"""How long it takes to reach your county seat, and what coordination is worth.

A journey is a feeder to the centre, a wait, and a trunk to the county seat. The first two
layers built the rides; this adds the wait, which is the part a timetable controls and the
part a passenger notices most.

**Two scenarios, same buses.** Uncoordinated, a passenger arriving at a centre waits on
average half the trunk headway. Pulsed — feeders timed to meet the trunk, which is how Danish
and Swiss regional networks work — the wait is the few minutes the trunk stands at the
interchange. No extra vehicle, no extra kilometre: the difference is entirely in when the
departures are written.

That is the number the design document promised and could not yet produce.

Output:
    data/access.json    per UAT: feeder, wait, trunk, total, both scenarios

Usage:
    uv run python -m scripts.build_access
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "access.json"

sys.path.insert(0, str(ADMINISTRATIV))

from scripts.county_times import county_times  # noqa: E402
from scripts.tiers import DAY_PROFILE, service_for  # noqa: E402

# Minutes a trunk bus stands at the interchange for its feeders to arrive. Under a pulse this
# is the whole wait; the passenger steps off one bus and onto another.
PULSE_DWELL_MIN: Final[float] = 5.0


def wait_uncoordinated(headway_min: float) -> float:
    """Average wait for a passenger arriving at random against a given headway.

    Half the headway is the textbook result for uniform arrivals, and it is the right model
    here precisely because the timetables are *not* coordinated: nothing tells the feeder
    passenger when the trunk leaves.
    """
    return headway_min / 2.0


def trunk_headway_min() -> float:
    """Minutes between trunk departures, from the service standard rather than assumed."""
    trunk = service_for("trunk")
    departures = sum(trunk.departures.values())
    hours = sum(DAY_PROFILE.values())
    return hours * 60.0 / departures


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd
    import pandas as pd
    from pipeline.county_capitals import COUNTY_CAPITAL_SIRUTA

    processed = ADMINISTRATIV / "data" / "processed"
    for path, how in (
        (ROOT / "data/network.json", "scripts.build_network"),
        (ROOT / "data/road_time.parquet", "scripts.build_road_time"),
    ):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run: uv run python -m {how}")

    network = json.loads((ROOT / "data/network.json").read_text(encoding="utf-8"))
    hub_of = json.loads((ROOT / "data/hubs.json").read_text(encoding="utf-8"))["hubOf"]
    inputs = json.loads((ROOT / "data/cost-inputs.json").read_text(encoding="utf-8"))["items"]
    service_factor = inputs["serviceSpeedFactor"]["value"]

    times = pd.read_parquet(ROOT / "data/road_time.parquet")
    adjacency = pd.read_parquet(processed / "adjacency.parquet")
    uats = gpd.read_file(processed / "uat_geometry.gpkg", layer="uat")
    county = dict(zip(uats.siruta, uats.county_code, strict=True))
    population = dict(zip(uats.siruta, uats.population, strict=True))
    name = dict(zip(uats.siruta, uats.name_uat, strict=True))

    edge_s: dict[tuple[str, str], float] = {}
    for a, b, seconds in zip(times.a_siruta, times.b_siruta, times.road_s, strict=True):
        if np.isfinite(seconds):
            edge_s[(a, b)] = edge_s[(b, a)] = seconds
    neighbours: dict[str, list[str]] = collections.defaultdict(list)
    for a, b, ok in zip(adjacency.a_siruta, adjacency.b_siruta, adjacency.traversable, strict=True):
        if ok:
            neighbours[a].append(b)
            neighbours[b].append(a)

    # Trunk leg per centre, from the routes already built.
    trunk_min: dict[str, float] = {}
    for route in network["routes"]:
        if route["tier"] != "T2":
            continue
        for centre in route["serves"]:
            trunk_min[centre] = route["oneWayMin"] / service_factor

    members: dict[str, set[str]] = collections.defaultdict(set)
    for uat, centre in hub_of.items():
        members[centre].add(uat)

    headway = trunk_headway_min()
    waits = {"uncoordinated": wait_uncoordinated(headway), "pulsed": PULSE_DWELL_MIN}

    rows: list[dict] = []
    for centre, group in members.items():
        reach = county_times(county, neighbours, edge_s, county[centre], [centre])
        trunk = trunk_min.get(centre, 0.0 if centre in COUNTY_CAPITAL_SIRUTA else None)
        for uat in group:
            if uat == centre:
                feeder = 0.0
            elif uat in reach:
                feeder = reach[uat] / 60.0 / service_factor
            else:
                continue
            if trunk is None:
                continue
            wait = 0.0 if uat == centre and trunk == 0.0 else None
            rows.append(
                {
                    "siruta": uat,
                    "name": name[uat],
                    "county": county[uat],
                    "population": int(population[uat]),
                    "feederMin": round(feeder, 1),
                    "trunkMin": round(trunk, 1),
                    "uncoordinatedMin": round(
                        feeder + (0.0 if wait == 0.0 else waits["uncoordinated"]) + trunk, 1
                    ),
                    "pulsedMin": round(
                        feeder + (0.0 if wait == 0.0 else waits["pulsed"]) + trunk, 1
                    ),
                }
            )

    people = sum(r["population"] for r in rows)

    def share_within(field: str, minutes: int) -> float:
        return round(sum(r["population"] for r in rows if r[field] <= minutes) / people * 100, 1)

    def weighted_median(field: str) -> float:
        ordered = sorted(rows, key=lambda r: r[field])
        half, running = people / 2, 0
        for row in ordered:
            running += row["population"]
            if running >= half:
                return row[field]
        return 0.0

    summary = {
        "uats": len(rows),
        "people": people,
        "trunkHeadwayMin": round(headway, 1),
        "waitUncoordinatedMin": round(waits["uncoordinated"], 1),
        "waitPulsedMin": round(waits["pulsed"], 1),
        "medianUncoordinatedMin": weighted_median("uncoordinatedMin"),
        "medianPulsedMin": weighted_median("pulsedMin"),
        "within": {
            str(m): {
                "uncoordinatedPct": share_within("uncoordinatedMin", m),
                "pulsedPct": share_within("pulsedMin", m),
            }
            for m in (60, 90, 120)
        },
    }

    document = {
        "$schema": "../schema/access.schema.json",
        "id": "access",
        "title": "Cât durează până la reședința de județ, cu și fără corespondență",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "retea-plus-orar",
            "locator": (
                "traseele din data/network.json, timpii din data/road_time.parquet, "
                "standardul de serviciu din scripts/tiers.py"
            ),
            "confidence": "derived",
            "note": (
                "Călătoria este rabatere plus așteptare plus trunchi. Așteptarea "
                "necoordonată este jumătate din intervalul de succedare, rezultatul clasic "
                "pentru sosiri uniforme; cea cu corespondență este staționarea trunchiului. "
                "Aceleași autobuze în ambele cazuri."
            ),
        },
        "summary": summary,
        "uats": sorted(rows, key=lambda r: r["siruta"]),
        "limitations": [
            {
                "id": "asteptarea-nu-e-masurata",
                "text": (
                    "Așteptarea este modelată, nu observată: jumătate din interval fără "
                    "corespondență, cinci minute cu. Un orar real coordonează unele "
                    "legături și pe altele nu."
                ),
                "severity": "material",
                "affects": ["access"],
            },
            {
                "id": "doar-dus",
                "text": (
                    "Se măsoară drumul până la reședința de județ, nu și întoarcerea. "
                    "Întoarcerea depinde de ora la care pleacă ultima cursă, care nu este "
                    "modelată aici."
                ),
                "severity": "material",
                "affects": ["access"],
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    s = summary
    print(f"{s['uats']:,} UATs, {s['people']:,} people")
    print(
        f"trunk headway {s['trunkHeadwayMin']:.0f} min -> uncoordinated wait "
        f"{s['waitUncoordinatedMin']:.0f} min, pulsed {s['waitPulsedMin']:.0f}"
    )
    print("\nmedian journey to the county seat:")
    print(f"  uncoordinated {s['medianUncoordinatedMin']:>6.1f} min")
    print(f"  pulsed        {s['medianPulsedMin']:>6.1f} min")
    print("\nshare of population within:")
    for m, v in s["within"].items():
        print(
            f"  {m:>3} min   uncoordinated {v['uncoordinatedPct']:>5.1f}%   "
            f"pulsed {v['pulsedPct']:>5.1f}%"
        )
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "access.json"

sys.path.insert(0, str(ADMINISTRATIV))

from scripts.county_times import county_times  # noqa: E402
from scripts.rail_costs import REFERENCE_TRAINS_PER_WEEKDAY  # noqa: E402
from scripts.rail_speeds import class_commercial_kmh  # noqa: E402
from scripts.tiers import DAY_PROFILE, service_for  # noqa: E402

# Minutes a trunk bus stands at the interchange for its feeders to arrive. Under a pulse this
# is the whole wait; the passenger steps off one bus and onto another.
PULSE_DWELL_MIN: Final[float] = 5.0

# --- the rail alternative -------------------------------------------------------------------
#
# A UAT is offered a train only when it has a station **within walking distance**. That is not
# timidity, it is the one honest reading of the data available: `station_km` from the rail build
# is a straight line, and turning a straight line into a bus leg would be precisely the
# geometry-as-road-time error the rail speed model was written to avoid. A walk over a short
# straight line with a detour factor is defensible; a bus over a long one is not.
#
# The consequence is the finding rather than a limitation of it: most Romanian communes do not
# get a train, because the track does not pass close enough, and the model says so instead of
# inventing a shuttle to the halt.
WALK_KMH: Final[float] = 4.5

# Straight line to street distance for a short walk. Streets are not crow-flies.
WALK_DETOUR: Final[float] = 1.3

# Beyond this a station does not serve a settlement on foot. Kept in step with
# build_railnet.STATION_WALK_KM; repeated rather than imported so this module needs no geo stack.
STATION_WALK_KM: Final[float] = 2.0


def rail_displacement(routes: list[dict], mode: dict[str, str]) -> dict:
    """How much bus service rail could actually release — which is far less than it looks.

    The tempting arithmetic is "247 communes are faster by train, so withdraw their buses".
    That is wrong, and wrong structurally rather than by a margin. A feeder serves every UAT
    down its branch, so a route can only be withdrawn if **every** commune on it is better off
    by train. One village with a station on a branch of eight releases nothing at all.

    Counted here rather than asserted, because the bound it produces is the useful number: it
    turns "we do not know what rail does to cost" into "rail can displace at most this much",
    and that is a claim a reader can argue with.

    A route counted here is still only a *candidate*. Withdrawing it would leave those communes
    with a train and nothing else, and a service running once every forty-eight minutes with no
    fallback is not the predictable network this model is built around.
    """
    fully = partly = untouched = 0
    fully_km = total_km = 0.0
    for route in routes:
        known = [s for s in route["serves"] if s in mode]
        if not known:
            continue
        by_rail = sum(1 for s in known if mode[s] == "rail")
        km = route.get("oneWayKm") or 0.0
        total_km += km
        if by_rail == len(known):
            fully += 1
            fully_km += km
        elif by_rail:
            partly += 1
        else:
            untouched += 1
    return {
        "routesFullyRailServed": fully,
        "routesPartlyRailServed": partly,
        "routesUntouched": untouched,
        "displaceableKmShare": round(fully_km / total_km, 4) if total_km else 0.0,
    }


def load_rail_access(path: Path | None = None) -> dict[str, dict]:
    """Per-UAT rail access from the rail build, or empty if it has not been run.

    Empty rather than fatal on purpose: setting the rail layer aside must yield exactly the
    bus-only simulator, which is the property the design document asked for and the only way to
    tell what rail actually changes.
    """
    source = path or (ROOT / "data" / "rail_access.parquet")
    if not source.exists():
        return {}
    import pandas as pd

    frame = pd.read_parquet(source)
    return {
        str(row.siruta): {
            "station_km": row.station_km,
            "seat_station_km": row.seat_station_km,
            "rail_km": row.rail_km,
        }
        for row in frame.itertuples()
    }


def rail_journey_min(entry: dict, rail_kmh: float, wait: float) -> float | None:
    """Walk, train, walk. None when the train is not a real option for this UAT.

    Both ends must be walkable. A commune whose station is five kilometres off is not served by
    the railway that passes it, and neither is one whose county seat's station is — the second
    condition removes the whole county at a stroke, which is the correct and slightly brutal
    answer for the five county seats whose station sits outside the town.
    """
    if not entry:
        return None
    station_km, seat_km, rail_km = (
        entry.get("station_km"),
        entry.get("seat_station_km"),
        entry.get("rail_km"),
    )
    # `is None` is not enough. A None written into a float column comes back from parquet as
    # NaN, and every comparison against NaN is False — so an unreachable UAT sailed through
    # both the None check and the distance check and produced a NaN journey time, which then
    # won a min() against a real number. Same trap as the untagged OSM way in build_railnet.
    values = (station_km, seat_km, rail_km)
    if any(v is None or not math.isfinite(v) for v in values):
        return None
    if station_km > STATION_WALK_KM or seat_km > STATION_WALK_KM:
        return None
    return walk_min(station_km) + wait + rail_km / rail_kmh * 60 + walk_min(seat_km)


def walk_min(straight_km: float) -> float:
    """Minutes on foot to cover a straight-line gap, allowing for streets."""
    return straight_km * WALK_DETOUR / WALK_KMH * 60


def train_headway_min(trains_per_weekday: int, service_hours: float) -> float:
    """Minutes between trains, from a daily count over the operating day.

    Trains are rarer than buses, so the uncoordinated wait is the larger part of what rail
    costs a passenger — and correspondingly the pulse is worth more on rail than on the road.
    """
    if trains_per_weekday <= 0 or service_hours <= 0:
        raise ValueError("trains per weekday and service hours must both be positive")
    return service_hours * 60 / trains_per_weekday


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
    rail = load_rail_access()
    # A regional train runs far less often than a feeder bus, so the uncoordinated wait is the
    # larger part of what rail costs a passenger — and the pulse is worth correspondingly more
    # on rail than on the road. Same reference service the rail cost model prices.
    rail_kmh = class_commercial_kmh("as_is")
    rail_headway = train_headway_min(REFERENCE_TRAINS_PER_WEEKDAY, sum(DAY_PROFILE.values()))
    rail_waits = {
        "uncoordinated": wait_uncoordinated(rail_headway),
        "pulsed": PULSE_DWELL_MIN,
    }

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
            bus_unco = feeder + (0.0 if wait == 0.0 else waits["uncoordinated"]) + trunk
            bus_pulsed = feeder + (0.0 if wait == 0.0 else waits["pulsed"]) + trunk

            # The train is offered as an alternative to the whole bus journey, not as a leg
            # bolted onto it: a passenger who can walk to a station does not ride the feeder to
            # the centre first. Whichever is faster wins, which is the mode choice falling out
            # of the comparison rather than being asserted.
            entry = rail.get(uat, {})
            rail_unco = rail_journey_min(entry, rail_kmh, rail_waits["uncoordinated"])
            rail_pulsed = rail_journey_min(entry, rail_kmh, rail_waits["pulsed"])

            best_unco = min(x for x in (bus_unco, rail_unco) if x is not None)
            best_pulsed = min(x for x in (bus_pulsed, rail_pulsed) if x is not None)
            rows.append(
                {
                    "siruta": uat,
                    "name": name[uat],
                    "county": county[uat],
                    "population": int(population[uat]),
                    "feederMin": round(feeder, 1),
                    "trunkMin": round(trunk, 1),
                    "uncoordinatedMin": round(bus_unco, 1),
                    "pulsedMin": round(bus_pulsed, 1),
                    "railUncoordinatedMin": None if rail_unco is None else round(rail_unco, 1),
                    "railPulsedMin": None if rail_pulsed is None else round(rail_pulsed, 1),
                    "bestUncoordinatedMin": round(best_unco, 1),
                    "bestPulsedMin": round(best_pulsed, 1),
                    "mode": "rail"
                    if rail_pulsed is not None and rail_pulsed < bus_pulsed
                    else "bus",
                }
            )

    people = sum(r["population"] for r in rows)
    # Computed before the summary because the limitation quotes it. A limitation carrying a
    # number that is not the number the model produced is how this file published two false
    # statements about itself earlier in its life.
    displacement = rail_displacement(network["routes"], {r["siruta"]: r["mode"] for r in rows})

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
        # Rail reported separately from the bus figures above rather than folded into them.
        # Folding would hide the shape of the result, which is the result: rail reaches few
        # places and transforms the ones it reaches. A single blended median would show a
        # four-minute improvement and say nothing about either half of that.
        "rail": {
            "headwayMin": round(rail_headway, 1),
            "waitUncoordinatedMin": round(rail_waits["uncoordinated"], 1),
            "commercialKmh": round(rail_kmh, 1),
            "uatsWithOption": sum(1 for r in rows if r["railPulsedMin"] is not None),
            "uatsFasterByRail": sum(1 for r in rows if r["mode"] == "rail"),
            "peopleFasterByRail": sum(r["population"] for r in rows if r["mode"] == "rail"),
            "medianBestUncoordinatedMin": weighted_median("bestUncoordinatedMin"),
            "medianBestPulsedMin": weighted_median("bestPulsedMin"),
            **displacement,
            "withinBest": {
                str(m): {
                    "uncoordinatedPct": share_within("bestUncoordinatedMin", m),
                    "pulsedPct": share_within("bestPulsedMin", m),
                }
                for m in (60, 90, 120)
            },
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
                "id": "trenul-doar-pe-jos",
                "text": (
                    "Trenul este oferit unui UAT numai dacă are stație la mai puțin de 2 km, la "
                    "ambele capete ale călătoriei. Motivul este că distanța până la stație se "
                    "cunoaște doar în linie dreaptă, iar transformarea unei linii drepte lungi "
                    "într-un traseu cu autobuzul ar fi exact eroarea pe care modelul feroviar a "
                    "fost scris să o evite. Consecința este că o comună cu gara la 5 km apare "
                    "aici ca neservită de calea ferată care trece prin ea. Un serviciu de "
                    "rabatere până la haltă ar schimba rezultatul și nu poate fi evaluat fără "
                    "timpi rutieri până la stații."
                ),
                "severity": "material",
                "affects": ["access"],
            },
            {
                "id": "trenul-nu-schimba-costul",
                "text": (
                    "Costul din data/cost.json rămâne calculat pe toate traseele de autobuz, iar "
                    "serviciul feroviar suplimentar nu este adăugat nicăieri. Cât de mult ar "
                    "putea schimba asta este însă mărginit și măsurat, nu necunoscut: un traseu "
                    "de rabatere servește toate comunele de pe ramura lui, deci poate fi retras "
                    "doar dacă TOATE merg mai repede cu trenul. Numai "
                    f"{displacement['routesFullyRailServed']} din "
                    f"{len(network['routes'])} de trasee îndeplinesc condiția, adică "
                    f"{displacement['displaceableKmShare']:.1%} din kilometri. Restul rețelei "
                    "rutiere rămâne necesară oricum. Și acele trasee sunt doar candidate: "
                    "retragerea lor ar lăsa comunele respective cu un tren la 48 de minute și "
                    "nimic altceva, ceea ce nu este rețeaua previzibilă pe care o modelează "
                    "acest simulator."
                ),
                "severity": "material",
                "affects": ["access", "cost"],
            },
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
    r = s["rail"]
    print(
        f"\nrail at {r['commercialKmh']:.0f} km/h, {r['headwayMin']:.0f} min headway:\n"
        f"  {r['uatsWithOption']:,} UATs can walk to a station at both ends\n"
        f"  {r['uatsFasterByRail']:,} of them are faster by train "
        f"({r['peopleFasterByRail']:,} people)\n"
        f"  median with rail  {r['medianBestPulsedMin']:>6.1f} min pulsed "
        f"(bus only {s['medianPulsedMin']:.1f})"
    )
    print(
        f"  bus the train could release: {r['routesFullyRailServed']} routes of "
        f"{r['routesFullyRailServed'] + r['routesPartlyRailServed'] + r['routesUntouched']}, "
        f"{r['displaceableKmShare']:.1%} of km — the rest of the road network is needed anyway"
    )
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

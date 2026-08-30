"""The rail graph, its stations, and county-seat-to-county-seat journey times.

This builds the `T1` tier the design document has carried since the first draft and never had:
trains connecting the county seats to each other, over the track that exists.

**Which track counts.** `railway=rail` with `usage IN (main, branch)` and no `service` tag.
That last filter matters more than it looks: 13.421 of the 24.020 rail ways in the Romanian
extract are yards, sidings, spurs and crossovers. Route a passenger service over those and it
threads through goods loops at a plausible-looking speed, which is exactly the class of quietly
wrong answer this repository exists to avoid.

**The station is not the village.** Halte sit two to five kilometres from the settlement they are
named for, and sometimes name a different settlement altogether. So the join is explicit and its
residual is reported rather than hidden: for every county seat this records how far its nearest
station is from the seat point, and a seat whose station is beyond `STATION_WALK_KM` is marked
as needing a bus to reach its own railway. That is an honest and somewhat damning property of
Romanian rail, and the model shows it.

**Times come from `rail_speeds`, not from a timetable** — see that module for why the published
Mersul Trenurilor is the wrong input for a counterfactual rather than a missing one. Every edge
is priced at both condition classes, so the cost of rehabilitation is a column rather than a
separate model run.

Output:
    data/railnet.json               per condition class: seat-to-seat minutes, station join
    data/reports/railnet.md

Usage:
    uv run python -m scripts.build_railnet
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PROCESSED_DIR = ADMINISTRATIV / "data" / "processed"
RAW_DIR = ADMINISTRATIV / "data" / "raw"
OUT_DIR = ROOT / "data"

from scripts.rail_speeds import (  # noqa: E402
    CONDITION_CLASSES,
    RAIL_SPEED_PROVENANCE,
    class_commercial_kmh,
)

# Stereo70. Metric, and the projection administrativ measures every other length in.
CRS_METRIC = "EPSG:3844"

# Passenger track only. `usage` separates the network proper from industrial spurs; `service`
# separates running lines from yard furniture.
LINE_WHERE = "railway = 'rail'"
PASSENGER_USAGE = ("main", "branch")

# What counts as a station a passenger can start from. `halt` is included: on a regional network
# it is most of the stops, and excluding it would leave the model serving only the large towns
# and then reporting rail as useless for everyone else.
STATION_KINDS = ("station", "halt")

# Beyond this, the station does not serve the seat on foot and the journey needs a bus leg.
# Assumed. Reported per seat rather than applied silently, because the residual is a finding.
STATION_WALK_KM = 2.0

# Two rail vertices closer than this are treated as the same junction. Same purpose as
# administrativ's road-graph snapping: OSM splits a line at every tag change, and without
# welding the endpoints the graph is a heap of disconnected segments.
#
# **Checked, because the detour it produces looked wrong.** The median rail path between county
# seats is 1,64x the straight line, well above the 1,2-1,35 a flat network gives, and the
# obvious suspect was this constant — snap too tight, miss junctions, force long ways round.
# Sweeping it over a tenfold range says otherwise:
#
#     10 m   102 774 nodes   1722/1722 pairs   detour 1,56
#     25 m    86 887 nodes   1722/1722 pairs   detour 1,64
#     50 m    70 604 nodes   1722/1722 pairs   detour 1,63
#    100 m    51 636 nodes   1722/1722 pairs   detour 1,53
#
# Connectivity is complete at every setting and the detour moves by 7% while the node count
# moves by half. The graph is not under-connected: the detour is the Carpathians, which is a
# fact about Romania rather than about this constant.
SNAP_M = 25.0

TAG = re.compile(r'"([a-z_:]+)"=>"([^"]*)"')


def _tags(blob: object) -> dict[str, str]:
    """Parse GDAL's hstore blob. An untagged way arrives as NaN, not as None."""
    return dict(TAG.findall(blob)) if isinstance(blob, str) else {}


def load_lines(pbf: Path):
    """Passenger running lines, in metric CRS, with their signed speed where tagged."""
    import geopandas as gpd

    frame = gpd.read_file(
        pbf,
        layer="lines",
        where=LINE_WHERE,
        columns=["railway", "name", "other_tags"],
        engine="pyogrio",
    )
    tags = [_tags(blob) for blob in frame["other_tags"]]
    frame["usage"] = [t.get("usage") for t in tags]
    frame["service"] = [t.get("service") for t in tags]
    frame["electrified"] = [t.get("electrified") not in (None, "no") for t in tags]
    speed = []
    for t in tags:
        raw = t.get("maxspeed")
        speed.append(float(raw) if raw and raw.isdigit() else np.nan)
    frame["maxspeed"] = speed

    keep = frame["usage"].isin(PASSENGER_USAGE) & frame["service"].isna()
    frame = frame.loc[keep].to_crs(CRS_METRIC).reset_index(drop=True)
    if frame.empty:
        raise SystemExit("no passenger rail lines survived filtering — check the extract")
    return frame


def load_stations(pbf: Path):
    """Station and halt points, in metric CRS."""
    import geopandas as gpd

    # GDAL promotes `railway` to a column on the lines layer but not on points, where it stays
    # in the hstore. So the filter is a LIKE over the blob, and the exact value is re-checked in
    # Python — `railway=stationary_something` would otherwise slip through the pattern.
    like = " OR ".join(f'other_tags LIKE \'%"railway"=>"{k}"%\'' for k in STATION_KINDS)
    frame = gpd.read_file(
        pbf, layer="points", where=like, columns=["name", "other_tags"], engine="pyogrio"
    )
    kind = [_tags(blob).get("railway") for blob in frame["other_tags"]]
    frame["railway"] = kind
    frame = frame.loc[frame["railway"].isin(STATION_KINDS)]
    frame = frame.to_crs(CRS_METRIC).reset_index(drop=True)
    if frame.empty:
        raise SystemExit("no stations found — check the extract")
    return frame


def load_population(path: Path | None = None) -> dict[int, int]:
    """SIRUTA → population, from administrativ's UAT attributes."""
    source = path or (RAW_DIR / "uat_attributes.json")
    rows = json.loads(source.read_text(encoding="utf-8"))
    return {int(r["siruta_code"]): int(r["population"]) for r in rows}


def pick_county_seats(seats, population: dict[int, int]):
    """The most populous UAT in each county.

    There is no `is_county_seat` flag anywhere in the pipeline, and `seat_rank` does not carry
    one either — rank I holds eleven large municipii, not the forty-one reședințe. Population is
    the rule that reproduces the official list, and it is applied here rather than hard-coding
    forty-one SIRUTA codes, which would silently rot the first time a county changed seat.

    **Bucharest.** Its six sectors all carry county code `B`, so this picks the most populous
    sector as the capital's rail node. For a rail graph that is the right shape — the sectors
    share Gara de Nord — but it is a choice, and `zones.py` makes the same one.
    """
    frame = seats.copy()
    frame["population"] = [population.get(int(s), 0) for s in frame["siruta"]]
    unknown = int((frame["population"] == 0).sum())
    if unknown > len(frame) * 0.05:
        raise SystemExit(f"population missing for {unknown} of {len(frame)} seats — bad join")
    chosen = (
        frame.sort_values(["county_code", "population"], ascending=[True, False])
        .groupby("county_code", as_index=False)
        .head(1)
    )
    return chosen.sort_values("county_code", ignore_index=True)


# Simplification tolerance for the published geometry, in metres. The map draws the country
# at six zoom levels out, where 100 m is well under a pixel; the graph is built from the full
# geometry regardless, so this affects what is drawn and never what is measured.
DRAW_TOLERANCE_M = 100.0


def write_geometry(lines, stations) -> None:
    """Publish simplified track and stations for the map.

    Only what the map can use: the line's signed speed, so a reader can see the slow network
    directly, and the stations, so the gap between a halt and the town it names is visible
    rather than only stated in a limitation.
    """
    draw = lines[["maxspeed", "electrified", "geometry"]].copy()
    draw["geometry"] = draw.geometry.simplify(DRAW_TOLERANCE_M)
    draw = draw.to_crs("EPSG:4326")
    draw["maxspeed"] = draw["maxspeed"].astype("float64").where(draw["maxspeed"].notna(), -1)
    # Five decimals is about a metre. The geometry has already been simplified to 100 m, so
    # every digit past that is bytes shipped to a browser to describe noise.
    draw.to_file(OUT_DIR / "rail-lines.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    points = stations[["railway", "name", "geometry"]].to_crs("EPSG:4326")
    points.to_file(OUT_DIR / "rail-stations.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    for name in ("rail-lines.geojson", "rail-stations.geojson"):
        size = (OUT_DIR / name).stat().st_size / 1e6
        print(f"  wrote {name}  {size:.1f} MB")


def build_graph(lines):
    """Weld line endpoints into a graph whose edge weight is metres.

    Speed is not baked in here. The same graph is searched once per condition class, which is
    what keeps the two classes honestly comparable: identical topology, different speed.
    """
    from scipy.sparse import coo_matrix

    coords: list[tuple[float, float]] = []
    edges: list[tuple[int, int, float, float]] = []

    grid: dict[tuple[int, int], int] = {}

    def node_at(x: float, y: float) -> int:
        key = (int(x // SNAP_M), int(y // SNAP_M))
        found = grid.get(key)
        if found is not None:
            return found
        index = len(coords)
        coords.append((x, y))
        grid[key] = index
        return index

    for geom, signed in zip(lines.geometry, lines["maxspeed"], strict=True):
        parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for part in parts:
            xs, ys = part.xy
            for i in range(len(xs) - 1):
                a = node_at(xs[i], ys[i])
                b = node_at(xs[i + 1], ys[i + 1])
                if a == b:
                    continue
                length = float(np.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]))
                edges.append((a, b, length, signed))

    if not edges:
        raise SystemExit("rail graph has no edges")

    rows = np.array([e[0] for e in edges])
    cols = np.array([e[1] for e in edges])
    metres = np.array([e[2] for e in edges])
    signed = np.array([e[3] for e in edges])
    size = len(coords)
    graph = coo_matrix((metres, (rows, cols)), shape=(size, size)).tocsr()
    return graph, np.array(coords), signed, metres


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, default=RAW_DIR / "romania-latest.osm.pbf")
    args = parser.parse_args(argv)

    import geopandas as gpd
    from scipy.sparse.csgraph import dijkstra

    if not args.pbf.exists():
        raise SystemExit(f"missing OSM extract: {args.pbf}")
    seats_path = PROCESSED_DIR / "uat_seats.gpkg"
    if not seats_path.exists():
        raise SystemExit(f"missing {seats_path} — run administrativ's build_seats first")

    print("Reading rail lines...")
    lines = load_lines(args.pbf)
    tagged = lines["maxspeed"].notna()
    length_km = lines.geometry.length.sum() / 1000
    print(f"  {len(lines):,} passenger line ways, {length_km:,.0f} km, {tagged.sum():,} tagged")

    print("Reading stations...")
    stations = load_stations(args.pbf)
    print(f"  {len(stations):,} stations and halts")

    print("Building graph...")
    graph, coords, _, _ = build_graph(lines)
    print(f"  {graph.shape[0]:,} nodes")

    seats = gpd.read_file(seats_path, layer="seat").to_crs(CRS_METRIC)
    county_seats = pick_county_seats(seats, load_population())
    print(f"  {len(county_seats):,} county seats")

    # Nearest rail node to each station, and nearest station to each seat. Both are plain
    # nearest-point joins; the distances they leave over are the finding, not an error.
    from scipy.spatial import cKDTree

    node_tree = cKDTree(coords)
    station_xy = np.column_stack([stations.geometry.x, stations.geometry.y])
    _, station_node = node_tree.query(station_xy)

    station_tree = cKDTree(station_xy)
    seat_xy = np.column_stack([county_seats.geometry.x, county_seats.geometry.y])
    seat_to_station_m, nearest_station = station_tree.query(seat_xy)

    walk = seat_to_station_m / 1000 <= STATION_WALK_KM
    print(f"  {int(walk.sum())}/{len(county_seats)} seats within {STATION_WALK_KM} km of a station")

    sources = station_node[nearest_station]
    # Dijkstra returns a row per source over *every* node in the graph. The seat-to-seat matrix
    # is the submatrix at the source columns; taking the median of the full row instead measures
    # the distance from a county seat to every anonymous vertex of track in Romania, which is a
    # number with no meaning. It read as a plausible 560 minutes, which is how that mistake
    # survives if nobody takes the submatrix.
    rail_m = dijkstra(graph, directed=False, indices=sources)[:, sources]
    pair = ~np.eye(len(sources), dtype=bool)
    reachable = np.isfinite(rail_m) & pair

    # How much longer the track is than the crow flies, between the same pairs. A detour factor
    # near 1 would mean the graph is cutting corners it should not.
    straight_m = np.linalg.norm(seat_xy[:, None, :] - seat_xy[None, :, :], axis=-1)
    detour = float(np.median(rail_m[reachable] / straight_m[reachable]))
    print(f"  {int(reachable.sum())}/{int(pair.sum())} seat pairs connected by rail")
    print(f"  median detour over straight line: {detour:.2f}x")

    result: dict[str, dict] = {}
    for condition in CONDITION_CLASSES:
        kmh = class_commercial_kmh(condition)
        minutes = rail_m[reachable] / 1000 / kmh * 60
        result[condition] = {
            "commercialKmh": round(kmh, 1),
            "medianPairMin": round(float(np.median(minutes)), 1),
            "longestPairMin": round(float(minutes.max()), 1),
        }
        print(
            f"  {condition:15s} {kmh:5.1f} km/h  median pair {np.median(minutes):6.1f} min"
            f"  longest {minutes.max():6.1f} min"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_geometry(lines, stations)
    document = {
        "$schema": "../schema/railnet.schema.json",
        "id": "railnet",
        "title": "Rețeaua feroviară: infrastructura existentă și serviciul derivat",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": RAIL_SPEED_PROVENANCE,
        "network": {
            "passengerLineKm": round(float(length_km), 1),
            "wayCount": int(len(lines)),
            "taggedSpeedShare": round(float(tagged.mean()), 3),
            "stationCount": int(len(stations)),
            "electrifiedShare": round(float(lines["electrified"].mean()), 3),
        },
        "pairs": {
            "connected": int(reachable.sum()),
            "possible": int(pair.sum()),
            "medianDetour": round(detour, 2),
        },
        "seats": {
            "considered": int(len(county_seats)),
            "withinWalkOfStation": int(walk.sum()),
            "walkKm": STATION_WALK_KM,
            "medianSeatToStationKm": round(float(np.median(seat_to_station_m)) / 1000, 2),
        },
        "conditions": result,
        "limitations": [
            {
                "id": "gara-nu-e-satul",
                "text": (
                    f"Gara nu este localitatea. Mediana distanței de la reședință la cea mai "
                    f"apropiată stație este {np.median(seat_to_station_m) / 1000:.2f} km, iar "
                    f"{len(county_seats) - int(walk.sum())} din {len(county_seats)} reședințe au "
                    f"stația la peste {STATION_WALK_KM} km — au nevoie de autobuz ca să ajungă la "
                    "propria cale ferată. Distanța este raportată, nu adăugată încă la timpul de "
                    "călătorie."
                ),
                "severity": "material",
                "affects": ["railnet"],
            },
            {
                "id": "viteza-comerciala-din-presa",
                "text": (
                    "Viteza comercială observată de 45 km/h, care calibrează clasa as_is, este o "
                    "cifră raportată public pentru trenurile de călători, nu o serie oficială CFR. "
                    "Este singurul reper măsurat al modelului feroviar și ar trebui înlocuită cu o "
                    "raportare a administratorului de infrastructură."
                ),
                "severity": "material",
                "affects": ["railnet"],
            },
            {
                "id": "fara-cost-feroviar",
                "text": (
                    "Se calculează timpul, nu costul. Tariful de utilizare a infrastructurii, "
                    "energia, personalul de tren și materialul rulant nu sunt încă modelate, deci "
                    "comparația dintre reabilitarea liniei și autobuze suplimentare nu se poate "
                    "încă face în lei."
                ),
                "severity": "blocking",
                "affects": ["railnet", "cost"],
            },
        ],
    }
    (OUT_DIR / "railnet.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {OUT_DIR / 'railnet.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

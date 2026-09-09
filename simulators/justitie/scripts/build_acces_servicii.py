"""Court or health provider: which county service is actually further away.

Chapter 7 argues consolidation on logistics — put the county's services in one town. The
simulator can now put a number on what that means for a citizen, because the arondare and the
shared health service-access views sit beside the same corrected court seats.

The comparison is deliberately asymmetric, and the asymmetry is the point. A consolidated UAT
gets one court, chosen by distance from among 42. It does not get "one health provider" — it
uses whichever eligible provider UAT is nearest. So the question is not whether the reform
moves courts closer than health care; it is whether a country that already accepts driving
*this far* for a county-scale service would find the court's distance unusual.

The UAT-routed health distance is still an upper bound. The shared UAT view excludes county-only
providers rather than pretending they have a UAT; a provider nobody can place can only make the
true UAT-level distance shorter, never longer. The point-level health distance is different:
it uses only providers with accepted coordinates and is explicitly straight-line, not road time.

Usage:
    uv run python scripts/build_acces_servicii.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "acces-servicii.json"

sys.path.insert(0, str(ADMINISTRATIV))

BUCHAREST = "B"
BUCHAREST_MUNICIPALITY_SIRUTA = "179132"
HEALTH_POINT_ACCESS_VIEW_ID = "health-point-access-2024-2026"
HEALTH_POINT_ACCESS_DISTANCE_METHOD = "straight-line"
EARTH_RADIUS_METRES = 6_371_008.8
WEB_MERCATOR_RADIUS_METRES = 6_378_137.0
WEB_MERCATOR_MAX_LATITUDE = 85.05112878


def finite_float(value, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise SystemExit(f"{field} must be finite")
    return number


def project_wgs84(lon: float, lat: float) -> tuple[float, float]:
    clipped_lat = max(min(lat, WEB_MERCATOR_MAX_LATITUDE), -WEB_MERCATOR_MAX_LATITUDE)
    return (
        WEB_MERCATOR_RADIUS_METRES * math.radians(lon),
        WEB_MERCATOR_RADIUS_METRES
        * math.log(math.tan(math.pi / 4 + math.radians(clipped_lat) / 2)),
    )


def unproject_wgs84(x: float, y: float) -> tuple[float, float]:
    return (
        math.degrees(x / WEB_MERCATOR_RADIUS_METRES),
        math.degrees(2 * math.atan(math.exp(y / WEB_MERCATOR_RADIUS_METRES)) - math.pi / 2),
    )


def ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    points = [
        project_wgs84(
            finite_float(point[0], "geometry.longitude"),
            finite_float(point[1], "geometry.latitude"),
        )
        for point in ring
    ]
    if len(points) < 3:
        raise SystemExit("UAT geometry ring has fewer than three points")
    if points[0] != points[-1]:
        points.append(points[0])

    double_area = 0.0
    cx_acc = 0.0
    cy_acc = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        cross = x0 * y1 - x1 * y0
        double_area += cross
        cx_acc += (x0 + x1) * cross
        cy_acc += (y0 + y1) * cross

    if abs(double_area) < 1e-6:
        xs = [point[0] for point in points[:-1]]
        ys = [point[1] for point in points[:-1]]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return abs(double_area / 2), cx_acc / (3 * double_area), cy_acc / (3 * double_area)


def polygon_centroid(polygon: list[list[list[float]]]) -> tuple[float, float, float]:
    if not polygon:
        raise SystemExit("UAT polygon has no rings")
    outer_area, outer_x, outer_y = ring_centroid(polygon[0])
    total_area = outer_area
    x_acc = outer_x * outer_area
    y_acc = outer_y * outer_area
    for hole in polygon[1:]:
        hole_area, hole_x, hole_y = ring_centroid(hole)
        total_area -= hole_area
        x_acc -= hole_x * hole_area
        y_acc -= hole_y * hole_area
    if total_area <= 0:
        return outer_area, outer_x, outer_y
    return total_area, x_acc / total_area, y_acc / total_area


def geometry_centroid(geometry: dict) -> dict[str, float]:
    kind = geometry["type"]
    polygons = (
        geometry["coordinates"]
        if kind == "MultiPolygon"
        else [geometry["coordinates"]]
        if kind == "Polygon"
        else None
    )
    if polygons is None:
        raise SystemExit(f"unsupported UAT geometry type {kind}")

    total_area = 0.0
    x_acc = 0.0
    y_acc = 0.0
    for polygon in polygons:
        area, x, y = polygon_centroid(polygon)
        total_area += area
        x_acc += x * area
        y_acc += y * area
    if total_area <= 0:
        raise SystemExit("UAT geometry has zero area")
    lon, lat = unproject_wgs84(x_acc / total_area, y_acc / total_area)
    return {"latitude": lat, "longitude": lon}


def read_uat_locations() -> dict[str, dict[str, float]]:
    geometry_file = ADMINISTRATIV / "web" / "public" / "data" / "uats.geojson"
    attributes_file = ADMINISTRATIV / "web" / "public" / "data" / "attributes.json"
    for path in (geometry_file, attributes_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    geometry = json.loads(geometry_file.read_text(encoding="utf-8"))
    attributes = json.loads(attributes_file.read_text(encoding="utf-8"))
    sirutas = [str(siruta) for siruta in attributes["siruta"]]
    features = geometry["features"]
    if len(features) != len(sirutas):
        raise SystemExit("administrativ geometry and attributes have different row counts")

    locations: dict[str, dict[str, float]] = {}
    duplicates: list[str] = []
    for siruta, feature in zip(sirutas, features, strict=True):
        if siruta in locations:
            duplicates.append(siruta)
        locations[siruta] = geometry_centroid(feature["geometry"])
    if duplicates:
        listed = ", ".join(sorted(set(duplicates))[:10])
        raise SystemExit(f"administrativ geometry has duplicate SIRUTA rows: {listed}")
    return locations


def read_health_points(point_access: dict) -> list[dict]:
    if point_access["id"] != HEALTH_POINT_ACCESS_VIEW_ID:
        raise SystemExit(f"expected {HEALTH_POINT_ACCESS_VIEW_ID}, got {point_access['id']}")
    points: list[dict] = []
    duplicate_ids: list[str] = []
    seen: set[str] = set()
    for point in point_access["points"]:
        provider_id = str(point["providerId"])
        if provider_id in seen:
            duplicate_ids.append(provider_id)
        seen.add(provider_id)
        lat = finite_float(point["latitude"], f"{provider_id}.latitude")
        lon = finite_float(point["longitude"], f"{provider_id}.longitude")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise SystemExit(f"health point {provider_id} has coordinates outside WGS84 bounds")
        out = dict(point)
        out["latitude"] = lat
        out["longitude"] = lon
        points.append(out)
    if duplicate_ids:
        listed = ", ".join(sorted(set(duplicate_ids))[:10])
        raise SystemExit(f"point health-access view has duplicate provider rows: {listed}")
    if len(points) != int(point_access["summary"]["pointAccessProviders"]):
        raise SystemExit("point health-access provider count does not match its summary")
    if not points:
        raise SystemExit("point health-access view has no provider points")
    return points


def straight_line_metres(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    hav = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_METRES * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def nearest_health_point(location: dict[str, float], points: list[dict]) -> tuple[dict, int]:
    best = points[0]
    best_metres = math.inf
    for point in points:
        metres = straight_line_metres(
            location["latitude"],
            location["longitude"],
            point["latitude"],
            point["longitude"],
        )
        if metres < best_metres:
            best = point
            best_metres = metres
    return best, int(round(best_metres))


def graph_from_web_payload(np, coo_matrix, expected_order=None):
    manifest_file = ADMINISTRATIV / "web" / "public" / "data" / "manifest.json"
    attributes_file = ADMINISTRATIV / "web" / "public" / "data" / "attributes.json"
    adjacency_file = ADMINISTRATIV / "web" / "public" / "data" / "adjacency.bin"
    for path in (manifest_file, attributes_file, adjacency_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    attributes = json.loads(attributes_file.read_text(encoding="utf-8"))
    order = [str(siruta) for siruta in attributes["siruta"]]
    if expected_order is not None and order != expected_order:
        raise SystemExit("administrativ web payload order differs from the reference model order")
    index_of = {siruta: i for i, siruta in enumerate(order)}
    county_by_siruta = dict(zip(order, attributes["county"], strict=True))
    size = len(order)

    edge_count = manifest["edgeCount"]
    raw = adjacency_file.read_bytes()
    edge_a = np.frombuffer(raw, dtype=np.uint16, count=edge_count, offset=0)
    edge_b = np.frombuffer(raw, dtype=np.uint16, count=edge_count, offset=edge_count * 2)
    edge_road = np.frombuffer(raw, dtype=np.float32, count=edge_count, offset=edge_count * 4)
    traversable = np.frombuffer(raw, dtype=np.uint8, count=edge_count, offset=edge_count * 12)
    keep = traversable == 1
    a, b, weight = edge_a[keep], edge_b[keep], edge_road[keep]
    graph = coo_matrix(
        (np.concatenate([weight, weight]), (np.concatenate([a, b]), np.concatenate([b, a]))),
        shape=(size, size),
    ).tocsr()
    return graph, index_of, order, county_by_siruta


def graph_from_parquet(path, index_of, size, np, coo_matrix):
    import pandas as pd  # noqa: PLC0415

    edges = pd.read_parquet(path)
    a = np.array([index_of[str(x)] for x in edges["a_siruta"]])
    b = np.array([index_of[str(x)] for x in edges["b_siruta"]])
    weight = edges["road_m"].to_numpy(dtype=float)
    keep = np.isfinite(weight)
    a, b, weight = a[keep], b[keep], weight[keep]
    return coo_matrix(
        (np.concatenate([weight, weight]), (np.concatenate([a, b]), np.concatenate([b, a]))),
        shape=(size, size),
    ).tocsr()


def main() -> int:
    import numpy as np  # noqa: PLC0415
    from scipy.sparse import coo_matrix  # noqa: PLC0415
    from scipy.sparse.csgraph import dijkstra  # noqa: PLC0415

    health_access_file = (
        REPO_ROOT
        / "packages"
        / "health_access"
        / "data"
        / "health-service-access-uat-2024-2026.json"
    )
    health_point_access_file = (
        REPO_ROOT / "packages" / "health_access" / "data" / "health-point-access-2024-2026.json"
    )
    politie_file = ROOT / "data" / "politie-osm.json"
    located_file = ROOT / "data" / "instante-localizate-2025.json"
    courts_file = ROOT / "data" / "court-distance.json"
    edges_file = ADMINISTRATIV / "data" / "processed" / "road_distance.parquet"
    for path in (
        health_access_file,
        health_point_access_file,
        politie_file,
        located_file,
        courts_file,
    ):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    health_access = json.loads(health_access_file.read_text(encoding="utf-8"))
    health_point_access = json.loads(health_point_access_file.read_text(encoding="utf-8"))
    health_points = read_health_points(health_point_access)
    uat_locations = read_uat_locations()
    politie = json.loads(politie_file.read_text(encoding="utf-8"))
    located = json.loads(located_file.read_text(encoding="utf-8"))["courts"]
    courts = json.loads(courts_file.read_text(encoding="utf-8"))

    try:
        from pipeline.reference_model import Params, load_data, run  # noqa: PLC0415

        data = load_data()
        order = sorted(data.population)
        index_of = {siruta: i for i, siruta in enumerate(order)}
        county_by_siruta = {siruta: data.county[siruta] for siruta in order}
        size = len(order)
        graph = (
            graph_from_parquet(edges_file, index_of, size, np, coo_matrix)
            if edges_file.exists()
            else graph_from_web_payload(np, coo_matrix, order)[0]
        )
        base_units = None
    except (ModuleNotFoundError, SystemExit) as error:
        if not OUT.exists():
            raise
        print(f"{error}. Reusing committed consolidated service rows.", file=sys.stderr)
        graph, index_of, order, county_by_siruta = graph_from_web_payload(np, coo_matrix)
        previous = json.loads(OUT.read_text(encoding="utf-8"))
        base_units = previous["units"]
        police_towns = previous["summary"]["policeTowns"]
        today_courts = previous["summary"]["todayCourts"]

    # One multi-source pass from every UAT that holds an eligible health provider gives the
    # nearest-health-service distance for the whole country at once.
    health_units = health_access["units"]
    health_by_siruta = {unit["siruta"]: unit for unit in health_units}
    health_route_seats: set[str] = set()
    missing_health_sirutas = []
    for unit in health_units:
        if not unit["hasLocalProvider"]:
            continue
        if unit["siruta"] in index_of:
            health_route_seats.add(unit["siruta"])
            continue
        if unit["siruta"] == BUCHAREST_MUNICIPALITY_SIRUTA:
            health_route_seats.update(
                siruta for siruta, county in county_by_siruta.items() if county == BUCHAREST
            )
            continue
        missing_health_sirutas.append(unit["siruta"])
    if missing_health_sirutas:
        print(
            "shared health access UATs do not all exist in the road graph: "
            + ", ".join(missing_health_sirutas[:10]),
            file=sys.stderr,
        )
        return 1
    health_route_seats = set(sorted(health_route_seats))
    health_provider_towns = health_access["summary"]["uatsWithLocalProvider"]
    if len(health_route_seats) < 100:
        print(
            f"only {len(health_route_seats)} health provider towns; the join broke",
            file=sys.stderr,
        )
        return 1
    to_health = dijkstra(
        graph,
        directed=False,
        indices=[index_of[s] for s in sorted(health_route_seats)],
        min_only=True,
    )

    units = []
    if base_units is None:
        police_seats = sorted(
            {s["siruta"] for s in politie["stations"] if s["siruta"] and s["siruta"] in index_of}
        )
        police_towns = len(police_seats)
        to_police = dijkstra(
            graph,
            directed=False,
            indices=[index_of[s] for s in police_seats],
            min_only=True,
        )

        # Today's first-level network: the 175 judecatorii that actually exist. Without it,
        # "38 km to a court" is a number with nothing to be compared against.
        today_seats = sorted(
            {c["siruta"] for c in located if c["tier"] == "judecatorie" and c["siruta"]}
        )
        today_courts = len(today_seats)
        if len(today_seats) < 100:
            print(
                f"only {len(today_seats)} judecatorii located; the baseline would lie",
                file=sys.stderr,
            )
            return 1
        to_today = dijkstra(
            graph,
            directed=False,
            indices=[index_of[s] for s in today_seats],
            min_only=True,
        )

        court_seats = [c["siruta"] for c in courts["courts"]]
        court_matrix = dijkstra(graph, directed=False, indices=[index_of[s] for s in court_seats])
        to_court = court_matrix.min(axis=0)

        result, _ = run(data, Params())
        for seat, members in sorted(result.members.items()):
            column = index_of[seat]
            court_m = float(to_court[column])
            health_m = float(to_health[column])
            police_m = float(to_police[column])
            today_m = float(to_today[column])
            if not all(np.isfinite(x) for x in (court_m, health_m, police_m, today_m)):
                continue
            local_health = health_by_siruta.get(seat)
            if local_health is None and county_by_siruta.get(seat) == BUCHAREST:
                local_health = health_by_siruta.get(BUCHAREST_MUNICIPALITY_SIRUTA, {})
            if local_health is None:
                local_health = {}
            location = uat_locations.get(seat)
            if location is None:
                print(f"missing UAT centroid for consolidated seat {seat}", file=sys.stderr)
                return 1
            point, point_m = nearest_health_point(location, health_points)
            units.append(
                {
                    "siruta": seat,
                    "name": data.name[seat],
                    "county": data.county[seat],
                    "population": sum(data.population[m] for m in members),
                    "courtMetres": round(court_m),
                    "hospitalMetresAtMost": round(health_m),
                    "localHealthProviderCount": local_health.get("localProviderCount", 0),
                    "nearestHealthPointProviderId": point["providerId"],
                    "nearestHealthPointDistanceMetres": point_m,
                    "policeMetresAtMost": round(police_m),
                    "todayCourtMetres": round(today_m),
                    "comparable": True,
                }
            )
    else:
        for unit in base_units:
            seat = unit["siruta"]
            if seat not in index_of:
                continue
            health_m = float(to_health[index_of[seat]])
            if not np.isfinite(health_m):
                continue
            local_health = health_by_siruta.get(seat)
            if local_health is None and county_by_siruta.get(seat) == BUCHAREST:
                local_health = health_by_siruta.get(BUCHAREST_MUNICIPALITY_SIRUTA, {})
            if local_health is None:
                local_health = {}
            location = uat_locations.get(seat)
            if location is None:
                print(f"missing UAT centroid for consolidated seat {seat}", file=sys.stderr)
                return 1
            point, point_m = nearest_health_point(location, health_points)
            units.append(
                {
                    "siruta": seat,
                    "name": unit["name"],
                    "county": unit["county"],
                    "population": unit["population"],
                    "courtMetres": unit["courtMetres"],
                    "hospitalMetresAtMost": round(health_m),
                    "localHealthProviderCount": local_health.get("localProviderCount", 0),
                    "nearestHealthPointProviderId": point["providerId"],
                    "nearestHealthPointDistanceMetres": point_m,
                    "policeMetresAtMost": unit["policeMetresAtMost"],
                    "todayCourtMetres": unit["todayCourtMetres"],
                    "comparable": True,
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
    median_today = median([u["todayCourtMetres"] for u in units])
    seat_has_today_court = sum(1 for u in units if u["todayCourtMetres"] == 0)
    median_proposed_all = median([u["courtMetres"] for u in units])
    all_people = sum(u["population"] for u in units) or 1
    mean_today = sum(u["todayCourtMetres"] * u["population"] for u in units) / all_people
    mean_proposed_all = sum(u["courtMetres"] * u["population"] for u in units) / all_people
    further_than_today = [u for u in units if u["courtMetres"] > u["todayCourtMetres"]]
    # The sharpest number: a court in your own town today, and a drive tomorrow.
    lose_local = [u for u in units if u["todayCourtMetres"] == 0 and u["courtMetres"] > 0]
    bands = {}
    for km in (25, 50, 75):
        limit = km * 1000
        now = [u for u in units if u["todayCourtMetres"] > limit]
        after = [u for u in units if u["courtMetres"] > limit]
        bands[str(km)] = {
            "todayUnits": len(now),
            "todayPeople": sum(u["population"] for u in now),
            "proposedUnits": len(after),
            "proposedPeople": sum(u["population"] for u in after),
        }
    seat_has_police = sum(1 for u in units if u["policeMetresAtMost"] == 0)
    median_court = median([u["courtMetres"] for u in comparable])
    median_hospital = median([u["hospitalMetresAtMost"] for u in comparable])
    rows_with_point_distance = [
        u for u in units if u.get("nearestHealthPointDistanceMetres") is not None
    ]
    point_distances = [u["nearestHealthPointDistanceMetres"] for u in rows_with_point_distance]
    median_health_point = median(point_distances)
    weighted_median_health_point = 0
    if rows_with_point_distance:
        weighted = sorted(
            (u["nearestHealthPointDistanceMetres"], u["population"])
            for u in rows_with_point_distance
            if u["population"] > 0
        )
        total_weight = sum(weight for _, weight in weighted)
        running = 0
        for metres, weight in weighted:
            running += weight
            if running >= total_weight / 2:
                weighted_median_health_point = metres
                break
    # The same seats measured against both networks: this is the comparison that cannot be an
    # artefact of where consolidated seats are chosen, because it is one set of seats.
    seat_has_hospital = sum(1 for u in comparable if u["localHealthProviderCount"] > 0)
    seat_has_court = sum(1 for u in comparable if u["courtMetres"] == 0)

    print(
        f"unități comparabile: {len(comparable)} din {len(units)}  ({people:,} locuitori)".replace(
            ",", "."
        )
    )
    print(f"drum mediu la instanță: {mean_court / 1000:.1f} km")
    print(f"drum mediu la sănătate: cel mult {mean_hospital / 1000:.1f} km")
    print(
        f"mediana: {median_court / 1000:.1f} km la instanță, "
        f"{median_hospital / 1000:.1f} km la sănătate"
    )
    print(
        f"sedii care sunt deja oraș cu furnizor de sănătate: {seat_has_hospital} "
        f"din {len(comparable)}; oraș cu instanță: {seat_has_court}"
    )
    print(
        f"sedii cu secție de poliție: {seat_has_police} din {len(units)}   "
        f"mediana la poliție: cel mult {median_police / 1000:.1f} km"
    )
    # A ratio is the wrong shape here: the median today is zero, so there is nothing to divide
    # by, and writing the guard as a ternary around the whole print swallowed the line entirely.
    print(
        f"azi, {today_courts} judecătorii: {seat_has_today_court} din {len(units)} sedii "
        f"au deja una în oraș, mediana {median_today / 1000:.1f} km"
    )
    print(f"după reformă, 42: {seat_has_court} sedii, mediana {median_proposed_all / 1000:.1f} km")
    print(
        f"media ponderată: {mean_today / 1000:.1f} km azi -> {mean_proposed_all / 1000:.1f} km după"
    )
    print(
        f"pierd instanța din oraș: {len(lose_local)} unități "
        f"({100 * sum(u['population'] for u in lose_local) / all_people:.0f}% din locuitori)"
    )
    for km, band in bands.items():
        print(
            f"  peste {km:>2} km: azi {band['todayUnits']:>3} unități / "
            f"{100 * band['todayPeople'] / all_people:4.1f}%   după "
            f"{band['proposedUnits']:>3} / {100 * band['proposedPeople'] / all_people:4.1f}%"
        )
    print(
        f"unități mai departe de instanță decât de sănătate: {len(further_to_court)} "
        f"({100 * people_further / people:.0f}% din locuitori)"
    )
    print(
        f"punct sănătate cel mai apropiat: mediana {median_health_point / 1000:.1f} km "
        f"({HEALTH_POINT_ACCESS_DISTANCE_METHOD})"
    )

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
                "instanță și către cele mai apropiate UAT-uri cu furnizori de sănătate "
                "serviceAccessEligible din pachetul health_access; cel mai apropiat punct de "
                "sănătate este calculat separat din health-point-access-2024-2026, în linie "
                "dreaptă de la centroidul UAT la coordonata furnizorului acceptat"
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
            "policeTowns": police_towns,
            "todayCourts": today_courts,
            "medianMetresToTodayCourt": median_today,
            "medianMetresToProposedCourt": median_proposed_all,
            "seatsThatAreTodayCourtTowns": seat_has_today_court,
            "allPeople": all_people,
            "meanMetresToTodayCourt": round(mean_today),
            "meanMetresToProposedCourt": round(mean_proposed_all),
            "unitsFurtherThanToday": len(further_than_today),
            "peopleFurtherThanToday": sum(u["population"] for u in further_than_today),
            "unitsLosingTheirLocalCourt": len(lose_local),
            "peopleLosingTheirLocalCourt": sum(u["population"] for u in lose_local),
            "beyond": bands,
            "unitsFurtherFromCourt": len(further_to_court),
            "peopleFurtherFromCourt": people_further,
            "hospitalTowns": health_provider_towns,
            "healthAccessView": health_access["id"],
            "healthProviderTowns": health_provider_towns,
            "healthAccessEligibleProviders": health_access["summary"]["eligibleProviders"],
            "healthAccessBlockedProviders": health_access["summary"]["blockedProviders"],
            "healthAccessNamedExclusions": health_access["summary"]["namedExclusions"],
            "healthPointAccessView": health_point_access["id"],
            "healthPointAccessProviders": health_point_access["summary"]["pointAccessProviders"],
            "healthPointAccessBlockedProviders": health_point_access["summary"][
                "pointAccessBlockedProviders"
            ],
            "healthPointAccessNamedExclusions": health_point_access["summary"]["namedExclusions"],
            "healthPointAccessRowsWithDistance": len(rows_with_point_distance),
            "healthPointAccessDistanceMethod": HEALTH_POINT_ACCESS_DISTANCE_METHOD,
            "healthPointAccessMedianNearestMetres": median_health_point,
            "healthPointAccessPopulationWeightedMedianNearestMetres": weighted_median_health_point,
        },
        "units": units,
        "limitations": [
            {
                "id": "distanta-la-spital-e-o-limita-de-sus",
                "text": (
                    "Accesul la sănătate vine din vederea shared health_access, care numără "
                    "doar furnizorii serviceAccessEligible. Cei fără localizare UAT sunt "
                    "excluși nominal; dacă unul ar fi mai aproape, distanța reală ar scădea, "
                    "nu ar crește."
                ),
                "severity": "material",
                "affects": ["acces", "colocare"],
            },
            {
                "id": "furnizorii-fara-uat-sunt-exclusi",
                "text": (
                    f"{health_access['summary']['blockedProviders']} furnizori din registrul "
                    "ANMCS au doar localizare la nivel de județ. Sunt păstrați ca excluderi "
                    "în pachetul shared și nu intră în nicio distanță locală."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "media-e-trasa-in-jos-de-sedii",
                "text": (
                    "Media ponderată la sănătate e trasă în jos de sediile care au deja un "
                    "furnizor localizat, deci contează cu zero. De aceea sunt publicate și "
                    "medianele, și de aceea comparația care contează e aceeași mulțime de "
                    f"sedii măsurată față de ambele rețele: {seat_has_hospital} din "
                    f"{len(comparable)} au furnizor de sănătate în UAT, {seat_has_court} au "
                    "instanță."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
            {
                "id": "sanatatea-vine-din-pachetul-shared",
                "text": (
                    "Comparația de acces nu mai folosește harta locală a spitalelor din "
                    "simulatorul justiției. Citește vederea UAT-level din packages/health_access "
                    "și raportează aceleași numere de furnizori eligibili și excluderi ca "
                    "pachetul shared."
                ),
                "severity": "note",
                "affects": ["acces", "colocare"],
            },
            {
                "id": "sanatatea-punctuala-in-linie-dreapta",
                "text": (
                    "Distanța la cel mai apropiat furnizor punctual citește "
                    "health-point-access-2024-2026 și folosește doar furnizorii cu coordonate "
                    f"acceptate: {health_point_access['summary']['pointAccessProviders']} rânduri. "
                    "Metoda este în linie dreaptă de la centroidul UAT-ului consolidat la "
                    "coordonata furnizorului, deci nu este distanță rutieră sau timp de acces. "
                    f"{health_point_access['summary']['pointAccessBlockedProviders']} furnizori "
                    "fără punct acceptat rămân excluși nominal din calcul."
                ),
                "severity": "material",
                "affects": ["acces", "colocare"],
            },
            {
                "id": "azi-inseamna-cea-mai-apropiata-nu-cea-arondata",
                "text": (
                    "Pentru reperul de azi se ia cea mai apropiată judecătorie pe drum, nu cea "
                    "de care UAT-ul este arondat legal. Arondarea de azi trimite uneori mai "
                    "departe decât cea mai apropiată instanță, așa că drumul real de azi este "
                    "cel puțin cât arată aici — comparația cu reforma e deci conservatoare, nu "
                    "generoasă."
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

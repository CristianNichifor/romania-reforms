"""Appellate courts on the eight development regions — a variant, not the paper.

The paper proposes "~15 curti de apel regionale", which is the number that already exists: the
word is regionale but the structure is unchanged. This models the alternative the author chose
after seeing that — one appellate court per development region, eight instead of fifteen.

**It is labelled a variant everywhere, because it is not what the paper says.** The simulator's
job is to test the document; when it models something else, it has to say so or it becomes a
second unlabelled proposal wearing the first one's authority.

The regions are derived, not typed. `regions.geojson` carries boundary *lines* with the region
on each side, so polygonising them yields eight areas, and a county falls in whichever contains
its representative point. That reproduces the composition of Legea 315/2004 exactly — 5, 7, 6,
4, 6, 6, 6, 2 counties — without anyone entering it by hand.

Naming them takes one more step: the polygons carry no names, so each boundary line is sampled
every two kilometres and probed 400 m to either side, and the region a probe lands in gets that
side's name. Majority wins. The check that matters is that the eight names come out distinct —
a mislabelling would show up as two regions sharing one.

**What this cannot do is attribute appeals correctly.** No document in the repository maps a
county to its appellate circuit, so a court's caseload is credited to the region its seat sits
in. Where a circuit reaches across a region boundary — and some do — the volume is in the wrong
column. The counts of courts and the travel figures are sound; the caseload split is a
best-effort attribution and is marked as one.

Usage:
    uv run python scripts/build_curti_apel.py
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "curti-apel-regiuni.json"

sys.path.insert(0, str(ADMINISTRATIV))

REGION_LINES = ADMINISTRATIV / "web" / "public" / "data" / "regions.geojson"
GEOMETRY = ADMINISTRATIV / "data" / "processed" / "uat_geometry.gpkg"
SAMPLE_M, PROBE_M = 2000, 400


def derive_regions() -> tuple[dict[str, str], dict[str, list[str]]]:
    """County code -> region name, and its inverse, both from the boundary geometry."""
    import geopandas as gpd  # noqa: PLC0415
    from shapely.geometry import Point  # noqa: PLC0415
    from shapely.ops import polygonize, unary_union  # noqa: PLC0415

    lines = gpd.read_file(REGION_LINES).to_crs("EPSG:3844")
    areas = list(polygonize(unary_union(lines.geometry)))
    if len(areas) != 8:
        raise SystemExit(f"the region lines polygonise into {len(areas)} areas, not 8")
    regions = gpd.GeoDataFrame(geometry=areas, crs="EPSG:3844")

    votes: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for _, row in lines.iterrows():
        geom = row.geometry
        parts = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
        for part in parts:
            distance = SAMPLE_M
            while distance < part.length:
                here = part.interpolate(distance)
                before = part.interpolate(max(distance - 30, 0))
                after = part.interpolate(min(distance + 30, part.length))
                dx, dy = after.x - before.x, after.y - before.y
                norm = (dx * dx + dy * dy) ** 0.5
                if norm:
                    for side, (ox, oy) in (
                        ("leftregion", (-dy / norm * PROBE_M, dx / norm * PROBE_M)),
                        ("rightregion", (dy / norm * PROBE_M, -dx / norm * PROBE_M)),
                    ):
                        name = row[side]
                        # Outside the national border there is no region; those probes vote
                        # for nothing and, left in, they outvoted Nord-Vest.
                        if not name or name != name:
                            continue
                        hit = regions[regions.contains(Point(here.x + ox, here.y + oy))]
                        if len(hit) == 1:
                            votes[hit.index[0]][name] += 1
                distance += SAMPLE_M

    named = {i: (votes[i].most_common(1) or [("?", 0)])[0][0] for i in range(len(areas))}
    if len(set(named.values())) != 8:
        raise SystemExit(f"region names are not distinct: {sorted(named.values())}")

    uats = gpd.read_file(GEOMETRY).to_crs("EPSG:3844")
    counties = uats.dissolve(by="county_code")[["geometry"]].reset_index()
    points = gpd.GeoDataFrame(
        counties[["county_code"]],
        geometry=counties.geometry.representative_point(),
        crs="EPSG:3844",
    )
    joined = gpd.sjoin(points, regions, how="left", predicate="within")
    region_of: dict[str, str] = {}
    for code, index in zip(joined["county_code"], joined["index_right"], strict=True):
        if index != index:
            raise SystemExit(f"county {code} falls outside every region")
        region_of[str(code)] = named[int(index)]
    if len(region_of) != 42:
        raise SystemExit(f"{len(region_of)} counties placed, expected 42")
    members: dict[str, list[str]] = collections.defaultdict(list)
    for code, name in region_of.items():
        members[name].append(code)
    return region_of, {k: sorted(v) for k, v in members.items()}


def main() -> int:
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    from scipy.sparse import coo_matrix  # noqa: PLC0415
    from scipy.sparse.csgraph import dijkstra  # noqa: PLC0415

    from pipeline.reference_model import load_data  # noqa: PLC0415

    located = json.loads(
        (ROOT / "data" / "instante-localizate-2025.json").read_text(encoding="utf-8")
    )["courts"]
    appellate = [c for c in located if c["tier"] == "curte-de-apel"]
    if len(appellate) < 14:
        print(f"only {len(appellate)} located appellate courts", file=sys.stderr)
        return 1

    region_of, members = derive_regions()
    data = load_data()

    # Bucharest-wide courts are seated on the city, not a sector, so they carry no SIRUTA —
    # the same trap the distance matrix hit. Seated on the lowest-numbered sector: arbitrary
    # between sectors, and the distance is nil either way because they share a city.
    sectors = sorted(s for s in data.population if data.county[s] == "B")
    for court in appellate:
        if not court["siruta"] and court["county"] == "B" and sectors:
            court["siruta"] = sectors[0]
    unplaced = [c["name"] for c in appellate if not c["siruta"]]
    if unplaced:
        print(f"appellate courts without a seat: {unplaced}", file=sys.stderr)
        return 1

    # Each existing appellate court belongs to the region its seat sits in.
    by_region: dict[str, list[dict]] = collections.defaultdict(list)
    for court in appellate:
        by_region[region_of[court["county"]]].append(court)
    empty = [r for r in members if not by_region.get(r)]
    if empty:
        print(f"regions with no appellate court to inherit: {empty}", file=sys.stderr)
        return 1

    # The seat rule, stated rather than chosen case by case: the busiest existing appellate
    # court in the region keeps the work. It is the one already staffed and housed for it.
    regions = []
    for name in sorted(members):
        courts = sorted(by_region[name], key=lambda c: -c["volume"])
        seat = courts[0]
        regions.append(
            {
                "region": name,
                "counties": members[name],
                "seat": seat["name"],
                "seatSiruta": seat["siruta"],
                "seatCounty": seat["county"],
                "absorbs": [c["name"] for c in courts[1:]],
                "courtsToday": len(courts),
                "volume": sum(c["volume"] for c in courts),
                "judges": round(sum(c.get("judges") or 0 for c in courts), 1),
            }
        )

    # Travel: from every county seat to its region's appellate seat, against the nearest
    # existing appellate seat — the closest thing to "today" that the data supports, since
    # circuit membership is not published here.
    order = sorted(data.population)
    index_of = {siruta: i for i, siruta in enumerate(order)}
    edges = pd.read_parquet(ADMINISTRATIV / "data" / "processed" / "road_distance.parquet")
    a = np.array([index_of[str(x)] for x in edges["a_siruta"]])
    b = np.array([index_of[str(x)] for x in edges["b_siruta"]])
    weight = edges["road_m"].to_numpy(dtype=float)
    keep = np.isfinite(weight)
    a, b, weight = a[keep], b[keep], weight[keep]
    graph = coo_matrix(
        (np.concatenate([weight, weight]), (np.concatenate([a, b]), np.concatenate([b, a]))),
        shape=(len(order), len(order)),
    ).tocsr()

    today_seats = sorted({c["siruta"] for c in appellate})
    to_today = dijkstra(
        graph, directed=False, indices=[index_of[s] for s in today_seats], min_only=True
    )
    seat_of_region = {r["region"]: r["seatSiruta"] for r in regions}
    variant_rows = dijkstra(
        graph, directed=False, indices=[index_of[seat_of_region[r["region"]]] for r in regions]
    )
    region_row = {r["region"]: i for i, r in enumerate(regions)}

    # One row per county, from its own capital.
    from pipeline.county_capitals import COUNTY_CAPITAL_SIRUTA as CAP  # noqa: PLC0415

    capital_of = {county: siruta for siruta, county in CAP.items()}
    counties = []
    for county, region in sorted(region_of.items()):
        capital = capital_of.get(county)
        if capital is None:  # Bucharest has no entry; it is its own appellate seat.
            continue
        column = index_of[str(capital)]
        variant = float(variant_rows[region_row[region]][column])
        today = float(to_today[column])
        if not np.isfinite(variant) or not np.isfinite(today):
            continue
        # The county tier routes across county lines because nothing requires a citizen to
        # drive past a nearer courthouse. The same question one tier up: is a county's own
        # regional seat the nearest of the eight, or is it sent past one?
        distances = variant_rows[:, column]
        nearest_i = int(np.argmin(distances))
        nearest_m = float(distances[nearest_i])
        nearest_region = regions[nearest_i]["region"]
        counties.append(
            {
                "county": county,
                "region": region,
                "metresToRegionSeat": round(variant),
                "metresToNearestToday": round(today),
                "nearestRegion": nearest_region,
                "metresToNearestRegionSeat": round(nearest_m),
                # From the rounded figures, not the raw ones, so a reader who subtracts the two
                # published distances gets the published detour rather than a metre less.
                "detourMetres": round(variant) - round(nearest_m),
                "nearerAnotherRegion": nearest_region != region,
            }
        )

    worse = [c for c in counties if c["metresToRegionSeat"] > c["metresToNearestToday"]]
    sent_past = sorted(
        (c for c in counties if c["nearerAnotherRegion"]), key=lambda c: -c["detourMetres"]
    )
    mean_variant = sum(c["metresToRegionSeat"] for c in counties) / len(counties)
    mean_today = sum(c["metresToNearestToday"] for c in counties) / len(counties)

    print(f"{'regiune':<18}{'jud':>4}{'azi':>5}{'sediu propus':>28}{'dosare':>10}")
    for r in regions:
        print(f"  {r['region']:<18}{len(r['counties']):>3}{r['courtsToday']:>5}"
              f"{r['seat'][:26]:>28}{r['volume']:>10,}")
    print(f"\n15 curți de apel -> {len(regions)}; "
          f"{sum(len(r['absorbs']) for r in regions)} absorbite")
    print(f"drum de la reședința de județ: {mean_today/1000:.0f} km la cea mai apropiată de azi"
          f" -> {mean_variant/1000:.0f} km la sediul regional")
    print(f"județe care ar avea de mers mai mult: {len(worse)} din {len(counties)}")
    print(f"județe trimise pe lângă un sediu regional mai apropiat: {len(sent_past)}")
    for c in sent_past[:6]:
        print(f"    {c['county']}  {c['region']} ({c['metresToRegionSeat']/1000:.0f} km) "
              f"-> {c['nearestRegion']} ({c['metresToNearestRegionSeat']/1000:.0f} km), "
              f"ocol {c['detourMetres']/1000:.0f} km")

    document = {
        "$schema": "../schema/curti-apel.schema.json",
        "id": "curti-apel-regiuni",
        "title": "Variantă: o curte de apel pe regiune de dezvoltare",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "variantOfPaper": True,
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": "Variantă la Capitolul 7, care propune ~15 curți de apel",
            "confidence": "assumed",
            "note": (
                "Lucrarea propune 15 curți de apel, adică exact câte există. Această variantă "
                "le reduce la 8, câte regiuni de dezvoltare are țara. Nu este propunerea "
                "lucrării și este marcată ca variantă peste tot."
            ),
        },
        "regions": regions,
        "counties": counties,
        "summary": {
            "today": len(appellate),
            "variant": len(regions),
            "absorbed": sum(len(r["absorbs"]) for r in regions),
            "meanMetresToNearestToday": round(mean_today),
            "meanMetresToRegionSeat": round(mean_variant),
            "countiesTravellingFurther": len(worse),
        "countiesNearerAnotherRegion": len(sent_past),
        "meanDetourMetres": (
            round(sum(c["detourMetres"] for c in sent_past) / len(sent_past)) if sent_past else 0
        ),
        "worstDetour": (
            {
                "county": sent_past[0]["county"],
                "region": sent_past[0]["region"],
                "nearestRegion": sent_past[0]["nearestRegion"],
                "detourMetres": sent_past[0]["detourMetres"],
            }
            if sent_past
            else None
        ),
            "countiesCompared": len(counties),
        },
        "limitations": [
            {
                "id": "regiunile-nu-sunt-cele-mai-apropiate-sedii",
                "text": (
                    "Douăsprezece județe din 41 sunt trimise pe lângă un sediu regional mai "
                    "apropiat: Călărași ar avea 136 km până la Constanța și are 265 până la "
                    "Pitești; Buzăul are Bucureștiul la 124 km și Constanța la 245. Ocolul mediu "
                    "e de 79 km. E aceeași obiecție pe care partea de instanțe o ridică față de "
                    "granițele de județ, un nivel mai sus — dar nu se rezolvă la fel. Regiunile "
                    "de dezvoltare sunt definite de Legea 315/2004, iar a aronda un județ la "
                    "sediul cel mai apropiat înseamnă a nu mai avea regiuni. Cifrele arată "
                    "prețul; alegerea între o geografie legală și un drum mai scurt nu se face "
                    "din date."
                ),
                "severity": "material",
                "affects": ["counties", "summary"],
            },
            {
                "id": "nu-e-propunerea-lucrarii",
                "text": (
                    "Lucrarea propune ~15 curți de apel — adică numărul actual. Reducerea la 8, "
                    "pe regiuni de dezvoltare, este o variantă aleasă de autor după ce a văzut "
                    "asta, nu ce scrie în document."
                ),
                "severity": "material",
                "affects": ["curti-de-apel"],
            },
            {
                "id": "circumscriptiile-nu-sunt-publicate-aici",
                "text": (
                    "Niciun document din depozit nu spune ce județe ține fiecare curte de apel. "
                    "Volumul unei curți este trecut la regiunea în care se află sediul ei; acolo "
                    "unde o circumscripție trece peste granița regiunii, dosarele sunt numărate "
                    "în coloana greșită. Numărul de instanțe și distanțele nu sunt afectate."
                ),
                "severity": "blocking",
                "affects": ["curti-de-apel"],
            },
            {
                "id": "sediul-e-ales-dupa-volum",
                "text": (
                    "Sediul fiecărei regiuni este curtea de apel existentă cu cele mai multe "
                    "dosare din acea regiune — cea deja construită și încadrată pentru asta. "
                    "Este o regulă, nu o alegere caz cu caz, dar rămâne o regulă aleasă aici."
                ),
                "severity": "material",
                "affects": ["curti-de-apel"],
            },
            {
                "id": "apelul-nu-e-fondul",
                "text": (
                    "Distanțele sunt de la reședința de județ, nu de la casa omului, și la apel "
                    "drumul îl face de regulă avocatul, nu justițiabilul. Kilometrii de aici "
                    "cântăresc altfel decât cei de la instanța de fond."
                ),
                "severity": "material",
                "affects": ["acces", "curti-de-apel"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

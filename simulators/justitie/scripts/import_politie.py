"""Police stations, from OpenStreetMap, because no register publishes them.

Chapter 7's logistics argument is about courts, prosecutors and police sharing a town. Hospitals
stood in for that until now, and the file said so, because four attempts at police data had
failed: sectiidepolitie.ro serves its map from routes that answer 302, cnas.ro is irrelevant,
data.gov.ro has no dataset of stations, code4romania has no repository touching them, and a
commercial directory offered 25 entries, all in Bucharest.

OpenStreetMap has 1.728, and it is not a fallback of last resort here — the road graph every
distance in this simulator is measured on comes from the same project. Using OSM for the
buildings and OSM for the roads is consistent; it was the omission that was inconsistent.

**Crowd-sourced completeness is uneven, and the two claims this file makes react to that
differently.** That every court seat has a police station is an existence claim: patchy mapping
can only make it harder to find one, never invent one, so 42 of 42 is safe against
under-coverage. Any distance computed from these points is the opposite — an unmapped station
can only shorten a real journey — so distances are upper bounds, exactly as the hospital
figures are.

What this cannot do is distinguish a county inspectorate from a village post. OSM's tagging
does not reliably carry rank: 1.602 of the 1.728 have no operator at all, and names run from
"Inspectoratul General al Poliției Române" to "Post de Poliție (fostă jandarmi)". So the file
counts presence, not capacity, and never says a seat is a policing centre — only that policing
exists there.

Usage:
    uv run python scripts/import_politie.py
"""

from __future__ import annotations

import collections
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
SOURCE = ROOT / "sources" / "osm-politie.json"
OUT = ROOT / "data" / "politie-osm.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"

QUERY = """[out:json][timeout:180];
area["ISO3166-1"="RO"][admin_level=2]->.ro;
(
  node["amenity"="police"](area.ro);
  way["amenity"="police"](area.ro);
  relation["amenity"="police"](area.ro);
);
out center tags;
"""

sys.path.insert(0, str(ADMINISTRATIV))
GEOMETRY = ADMINISTRATIV / "data" / "processed" / "uat_geometry.gpkg"


def download() -> list[dict]:
    if not SOURCE.exists():
        print("querying Overpass ...")
        request = urllib.request.Request(
            OVERPASS,
            data=urllib.parse.urlencode({"data": QUERY}).encode(),
            headers={"User-Agent": UA},
        )
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
            SOURCE.parent.mkdir(parents=True, exist_ok=True)
            SOURCE.write_bytes(response.read())
    return json.loads(SOURCE.read_text(encoding="utf-8"))["elements"]


def main() -> int:
    import geopandas as gpd  # noqa: PLC0415
    from shapely.geometry import Point  # noqa: PLC0415

    if not GEOMETRY.exists():
        raise SystemExit(f"Missing {GEOMETRY}; the administrative simulator holds the boundaries")

    stations = []
    for element in download():
        centre = element.get("center") or {}
        lat = element.get("lat", centre.get("lat"))
        lon = element.get("lon", centre.get("lon"))
        if lat is None or lon is None:
            continue
        tags = element.get("tags") or {}
        stations.append(
            {
                "name": tags.get("name") or "",
                "operator": tags.get("operator") or "",
                "osm": f"{element['type']}/{element['id']}",
                "lat": round(float(lat), 6),
                "lng": round(float(lon), 6),
            }
        )
    if len(stations) < 500:
        print(f"only {len(stations)} police features; the query or the area changed", file=sys.stderr)
        return 1

    uats = gpd.read_file(GEOMETRY)
    points = gpd.GeoDataFrame(
        stations, geometry=[Point(s["lng"], s["lat"]) for s in stations], crs="EPSG:4326"
    ).to_crs(uats.crs)
    joined = gpd.sjoin(
        points,
        uats[["siruta", "name_uat", "county_code", "geometry"]],
        how="left",
        predicate="within",
    )

    rows = []
    for record in joined.to_dict("records"):
        siruta = record.get("siruta")
        placed = siruta is not None and siruta == siruta
        rows.append(
            {
                "name": record["name"],
                "operator": record["operator"],
                "osm": record["osm"],
                "lat": record["lat"],
                "lng": record["lng"],
                "siruta": str(siruta) if placed else None,
                "uat": record["name_uat"] if placed else None,
                "county": record["county_code"] if placed else None,
            }
        )

    located = [r for r in rows if r["county"]]
    covered = sorted({r["county"] for r in located})
    all_counties = sorted(set(uats["county_code"]))
    towns = {r["siruta"] for r in located}

    courts = json.loads((ROOT / "data" / "court-distance.json").read_text(encoding="utf-8"))
    seat_of = {c["county"]: c["siruta"] for c in courts["courts"]}
    seats_with = [c for c, s in seat_of.items() if s in towns]
    per_county = collections.Counter(r["county"] for r in located)

    print(f"secții de poliție: {len(rows)}   localizate: {len(located)}")
    print(f"județe acoperite: {len(covered)} din {len(all_counties)}")
    print(f"UAT-uri cu cel puțin o secție: {len(towns)} din {len(uats)}")
    print(f"sedii de instanță cu secție: {len(seats_with)} din {len(seat_of)}")
    print(f"cele mai puține pe județ: {per_county.most_common()[-3:]}")

    document = {
        "$schema": "../schema/politie.schema.json",
        "id": "politie-osm",
        "title": "Secțiile de poliție, din OpenStreetMap",
        "publisher": "OpenStreetMap contributors",
        "period": "2026",
        "provenance": {
            "source": "openstreetmap",
            "locator": 'Overpass, amenity=police în aria României, noduri, căi și relații',
            "confidence": "derived",
            "note": (
                "Date colaborative, sub ODbL. Încadrarea în UAT este calculată aici, prin "
                "intersecție cu limitele administrative. Nu există registru public al "
                "sediilor de poliție din care să fie verificate."
            ),
        },
        "summary": {
            "stations": len(rows),
            "located": len(located),
            "countiesCovered": len(covered),
            "countiesTotal": len(all_counties),
            "uatsWithStation": len(towns),
            "uatsTotal": len(uats),
            "courtSeatsWithStation": len(seats_with),
            "courtSeats": len(seat_of),
            "unnamed": sum(1 for r in rows if not r["name"]),
        },
        "stations": rows,
        "limitations": [
            {
                "id": "osm-nu-e-registru",
                "text": (
                    "OpenStreetMap e o hartă colaborativă, nu un registru oficial. Nu există "
                    "niciun registru public al sediilor de poliție cu care să fie verificată, "
                    "așa că acoperirea nu poate fi confirmată — doar folosită. Am încercat "
                    "sectiidepolitie.ro, data.gov.ro, depozitele Code for Romania și un "
                    "director comercial; niciunul nu publică lista."
                ),
                "severity": "material",
                "affects": ["colocare"],
            },
            {
                "id": "prezenta-nu-e-rang",
                "text": (
                    "Etichetele nu spun consecvent ce fel de unitate este: 1.602 din 1.728 nu "
                    "au deloc operator, iar numele merg de la „Inspectoratul General al "
                    "Poliției Române” la „Post de Poliție”. Se numără prezența, nu capacitatea, "
                    "și nicăieri nu se spune că un sediu ar fi un centru de comandă."
                ),
                "severity": "material",
                "affects": ["colocare"],
            },
            {
                "id": "distantele-sunt-limite-de-sus",
                "text": (
                    "O secție nemarcată nu poate decât să scurteze un drum real, niciodată "
                    "să-l lungească, deci orice distanță calculată din aceste puncte este o "
                    "limită de sus. Faptul că fiecare sediu de instanță are o secție e însă "
                    "robust la acoperirea incompletă: lipsa unor puncte ar face mai greu, nu "
                    "mai ușor, să găsești una."
                ),
                "severity": "note",
                "affects": ["acces", "colocare"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

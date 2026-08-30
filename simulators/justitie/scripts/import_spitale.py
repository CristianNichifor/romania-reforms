"""Where the hospitals are, and whether the courts would sit with them.

Chapter 7 of the reform paper argues for consolidation partly on logistics: put the county's
court, its prosecutors and its police in one place instead of scattering them, and the county's
public services stop being spread across half a dozen towns. Hospitals are the one county-scale
service with a published national register, so they are the available test of whether the 42
proposed court seats are in fact where the county already concentrates its services.

The Ministry of Health's list looks like a table of names. It is not: the page also carries a
Leaflet map, and each marker is written into the HTML with coordinates. Those are what this
reads — 301 hospitals with latitude and longitude, which needs no name matching and no
geocoder.

Placement is point-in-polygon against the UAT boundaries, not nearest seat. That distinction
moved 26 of the 301: Suceava's county emergency hospital sits nearer the seat of Șcheia, the
commune next door, than to Suceava's own, so nearest-seat filed it under Șcheia and reported
that the county capital had no hospital.

**The register is incomplete, and that is the first thing to say about it.** Six counties do
not appear at all — Bistrița-Năsăud, Galați, Ilfov, Mureș, Neamț and Sălaj. Galați and Târgu
Mureș plainly have county hospitals; Târgu Mureș is one of the country's teaching centres. So
nothing national can be computed from this file, and the co-location figure is reported over
the 36 counties the register actually covers, labelled as such.

Within those 36: every single court seat has a hospital. What that supports is narrow — the
proposed seats are already service centres — and it says nothing about the six counties whose
data is missing.

Usage:
    uv run python scripts/import_spitale.py
"""

from __future__ import annotations

import collections
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
SOURCE = ROOT / "sources" / "ms-unitati-sanitare.html"
OUT = ROOT / "data" / "spitale-2026.json"
URL = "https://ms.ro/ro/unitati-sanitare/"
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"

sys.path.insert(0, str(ADMINISTRATIV))

GEOMETRY = ADMINISTRATIV / "data" / "processed" / "uat_geometry.gpkg"


def download() -> str:
    if not SOURCE.exists():
        print(f"downloading {URL} ...")
        request = urllib.request.Request(URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
            SOURCE.parent.mkdir(parents=True, exist_ok=True)
            SOURCE.write_bytes(response.read())
    return SOURCE.read_text(encoding="utf-8", errors="ignore")


def markers(page: str) -> list[dict]:
    """Name and coordinates per map marker, read out of the inline Leaflet setup."""
    found = []
    for lat, lng, body in re.findall(
        r"var lat_lng = \{lat:\s*([-\d.]+),\s*lng:\s*([-\d.]+)\s*\};(.*?)marker\.bin", page, re.S
    ):
        parts = re.findall(r'message\s*\+?=\s*message?\s*\+?\s*"(.*?)";', body, re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "\n", " ".join(parts)))
        lines = [x.strip() for x in text.split("\n") if x.strip() and "Mai multe" not in x]
        if lines:
            found.append({"name": lines[0], "lat": float(lat), "lng": float(lng)})
    return found


def main() -> int:
    import geopandas as gpd  # noqa: PLC0415
    from shapely.geometry import Point  # noqa: PLC0415

    if not GEOMETRY.exists():
        raise SystemExit(f"Missing {GEOMETRY}; the administrative simulator holds the boundaries")

    hospitals = markers(download())
    if len(hospitals) < 200:
        print(f"only {len(hospitals)} markers; the page's shape changed", file=sys.stderr)
        return 1

    uats = gpd.read_file(GEOMETRY)
    points = gpd.GeoDataFrame(
        hospitals,
        geometry=[Point(h["lng"], h["lat"]) for h in hospitals],
        crs="EPSG:4326",
    ).to_crs(uats.crs)
    joined = gpd.sjoin(
        points, uats[["siruta", "name_uat", "county_code", "geometry"]], how="left", predicate="within"
    )

    rows = []
    for record in joined.to_dict("records"):
        siruta = record.get("siruta")
        rows.append(
            {
                "name": record["name"],
                "lat": round(float(record["lat"]), 6),
                "lng": round(float(record["lng"]), 6),
                "siruta": None if siruta is None or siruta != siruta else str(siruta),
                "uat": None if siruta is None or siruta != siruta else record["name_uat"],
                "county": None if siruta is None or siruta != siruta else record["county_code"],
            }
        )

    located = [r for r in rows if r["county"]]
    covered = sorted({r["county"] for r in located})
    all_counties = sorted(set(uats["county_code"]))
    missing = [c for c in all_counties if c not in covered]

    courts = json.loads((ROOT / "data" / "court-distance.json").read_text(encoding="utf-8"))
    seat_of = {c["county"]: c["siruta"] for c in courts["courts"]}
    per_uat = collections.Counter(r["siruta"] for r in located)

    checkable = [c for c in seat_of if c in covered]
    seats_with = [c for c in checkable if per_uat.get(seat_of[c], 0) > 0]
    at_seats = sum(n for s, n in per_uat.items() if s in seat_of.values())

    print(f"spitale: {len(rows)}   localizate într-un UAT: {len(located)}")
    print(f"județe acoperite: {len(covered)} din {len(all_counties)}   lipsesc: {missing}")
    print(f"sedii de instanță cu spital: {len(seats_with)} din {len(checkable)} verificabile")
    print(f"spitale în orașul unui sediu de instanță: {at_seats} din {len(located)} "
          f"({100 * at_seats / len(located):.0f}%)")

    document = {
        "$schema": "../schema/spitale.schema.json",
        "id": "spitale-2026",
        "title": "Spitalele publicate de Ministerul Sănătății, așezate pe hartă",
        "publisher": "Ministerul Sănătății",
        "period": "2026",
        "provenance": {
            "source": "ms-unitati-sanitare",
            "locator": "https://ms.ro/ro/unitati-sanitare/, marcajele hărții",
            "confidence": "verbatim",
            "note": (
                "Numele și coordonatele sunt citite din marcajele hărții din pagină. "
                "Încadrarea în UAT este calculată aici, prin intersecție cu limitele "
                "administrative."
            ),
        },
        "summary": {
            "hospitals": len(rows),
            "located": len(located),
            "countiesCovered": len(covered),
            "countiesTotal": len(all_counties),
            "countiesMissing": missing,
            "courtSeatsCheckable": len(checkable),
            "courtSeatsWithHospital": len(seats_with),
            "hospitalsInCourtSeatTowns": at_seats,
        },
        "hospitals": rows,
        "limitations": [
            {
                "id": "registrul-e-incomplet",
                "text": (
                    "Șase județe lipsesc cu totul din listă — Bistrița-Năsăud, Galați, Ilfov, "
                    "Mureș, Neamț și Sălaj. Galațiul și Târgu Mureșul au evident spitale "
                    "județene, iar Târgu Mureșul e unul dintre centrele medicale universitare "
                    "ale țării. Nimic la nivel național nu se poate calcula din acest fișier; "
                    "cifrele de aici sunt pe cele 36 de județe pe care lista le acoperă."
                ),
                "severity": "blocking",
                "affects": ["acces", "colocare"],
            },
            {
                "id": "spitalele-nu-sunt-parchete",
                "text": (
                    "Capitolul 7 argumentează comasarea prin colocarea instanțelor cu parchetele "
                    "și cu poliția județeană. Spitalele nu sunt niciuna dintre ele; sunt doar "
                    "singurul serviciu de rang județean cu registru public localizabil. Ce "
                    "arată cifra este că sediile propuse sunt deja centre de servicii, nu că "
                    "instanțele și parchetele ar ajunge în aceeași clădire."
                ),
                "severity": "material",
                "affects": ["colocare"],
            },
            {
                "id": "un-marcaj-in-afara-oricarui-uat",
                "text": (
                    "Un marcaj cade în afara oricărei limite administrative și este păstrat în "
                    "fișier, dar exclus din numărători. Coordonata lui este probabil greșită la "
                    "sursă."
                ),
                "severity": "note",
                "affects": ["acces"],
            },
            {
                "id": "incadrarea-e-prin-poligon-nu-prin-nume",
                "text": (
                    "Spitalele sunt încadrate prin intersecție cu limitele UAT, nu după numele "
                    "din denumire. Diferența nu e teoretică: 26 din 301 cad în alt UAT decât cel "
                    "al celui mai apropiat sediu, iar spitalul județean din Suceava se află "
                    "fizic pe teritoriul comunei Șcheia."
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

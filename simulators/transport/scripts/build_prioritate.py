"""Which bypasses are worth building first, weighted by who actually drives there.

`build_ocoliri.py` prices the whole programme and `build_road_time.py` measures what it buys
in journey time. Neither knows how many vehicles use each crossing, so both treat a bypass
around a village on DN1 and one around a village on an empty DN as equally valuable. They are
not: the first serves twenty thousand vehicles a day and the second two thousand.

This joins the crossings to measured traffic and ranks them. The output is the only form in
which a €35 md programme is a usable answer — not "build all of it" but "these are worth it,
in this order, and here is where the curve flattens".

**How the join works, and what its 23% means.** Each crossing is matched to the nearest
section in Romania's Environmental Noise Directive return within 60 m. 636 of 2 781 crossings
match, covering 1 278 of 6 292 kilometres. The unmatched ones are not unknown: the directive
covers every road above three million vehicles a year, so a trunk or primary crossing absent
from it is *bounded below* 8 219 vehicles a day rather than unmeasured. That makes the ranked
subset the top of the distribution by construction — which is exactly the part a programme
would build first.

**Value of time is not applied here.** Converting hours into lei needs a value of travel time,
which is a policy parameter with a wide range and a heavy influence on the answer. This
reports lei per vehicle-hour saved and stops; a reader who wants a benefit-cost ratio supplies
their own value and divides. Choosing one here would bury the most contestable number in the
chain inside a single ratio.

Output:
    data/prioritate.json    crossings ranked by cost per vehicle-hour saved

Usage:
    uv run python -m scripts.build_prioritate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PBF = ADMINISTRATIV / "data" / "raw" / "romania-latest.osm.pbf"
TRAFFIC = ROOT / "data" / "reports" / "major-roads.gpkg"
OUT = ROOT / "data" / "prioritate.json"

CLASSES: Final[tuple[str, ...]] = ("trunk", "primary")
LOCALITY_KMH: Final[int] = 50
MIN_CROSSING_M: Final[float] = 500.0

# How close a crossing must be to a measured section to inherit its traffic. Wide enough for
# the two geometries to be independently generalised, narrow enough not to borrow the volume
# of a parallel road: END sections are their own linework, not OSM's.
MATCH_M: Final[float] = 60.0

# The directive's inclusion threshold: three million vehicles a year. A crossing that does not
# match is below this, not unknown — which is what lets the unmatched remainder be bounded
# rather than guessed.
END_THRESHOLD_AADT: Final[float] = 3_000_000 / 365
DAYS: Final[int] = 365

CRS: Final[str] = "EPSG:3844"


def regime_speeds() -> tuple[float, float]:
    """Effective km/h inside a locality and on the open road, for the classes bypassed.

    Taken from the same measured limits and the same efficiency term the journey model uses,
    rather than from the legal 50 and 90 — a bypass does not deliver the sign, it delivers
    what the road actually runs at. Averaged over trunk and primary weighted by their length,
    because a crossing may be either and the difference between them is small.
    """
    from scripts.speeds import EFFICIENCY, VEHICLES, load_limits

    limits = load_limits()["classes"]
    car = VEHICLES["car"]
    inside_total = open_total = weight = 0.0
    for name in CLASSES:
        entry = limits[name]
        km = entry["km"]
        efficiency = EFFICIENCY[name]
        inside_total += min(entry["locality_kmh"], car.cap(name)) * efficiency * km
        open_total += min(entry["open_road_kmh"], car.cap(name)) * efficiency * km
        weight += km
    return inside_total / weight, open_total / weight


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    for path, how in (
        (PBF, "administrativ fetch --with-roads"),
        (TRAFFIC, "build_trafic --refetch"),
    ):
        if not path.exists():
            print(f"Missing {path}. Run: {how}", file=sys.stderr)
            return 1

    import geopandas as gpd
    import numpy as np
    from shapely.ops import linemerge, unary_union

    from scripts.measure_limits import parse_maxspeed

    inputs = json.loads((ROOT / "data" / "ocoliri-inputs.json").read_text(encoding="utf-8"))[
        "items"
    ]
    lei_per_km = inputs["bypassLeiPerKm"]["value"]
    lengthening = inputs["bypassLengthFactor"]["value"]
    inside_kmh, open_kmh = regime_speeds()
    print(f"  regime speeds: {inside_kmh:.1f} km/h through town, {open_kmh:.1f} on the bypass")

    selector = ",".join(f"'{c}'" for c in CLASSES)
    roads = (
        gpd.read_file(
            PBF,
            layer="lines",
            columns=["highway", "other_tags"],
            where=f"highway IN ({selector})",
            engine="pyogrio",
        )
        .set_crs("EPSG:4326")
        .to_crs(CRS)
    )
    limits = np.array([parse_maxspeed(t) for t in roads["other_tags"]])
    merged = linemerge(unary_union(list(roads[limits == LOCALITY_KMH].geometry)))
    parts = merged.geoms if merged.geom_type == "MultiLineString" else [merged]
    parts = [p for p in parts if p.length >= MIN_CROSSING_M]
    crossings = gpd.GeoDataFrame({"m": [p.length for p in parts]}, geometry=list(parts), crs=CRS)
    print(f"  {len(crossings):,} crossings >= {MIN_CROSSING_M:.0f} m")

    end = gpd.read_file(TRAFFIC, layer="MajorRoadSource", engine="pyogrio").to_crs(CRS)
    end["aadt"] = end["annualTrafficFlow"] / DAYS
    joined = gpd.sjoin_nearest(
        crossings,
        end[["aadt", "roadNationalCode", "geometry"]],
        how="left",
        max_distance=MATCH_M,
        distance_col="d",
    )
    # A crossing can sit near two reported sections; take the busier, which is the road the
    # bypass would actually relieve.
    joined = joined.groupby(level=0).agg({"m": "first", "aadt": "max", "roadNationalCode": "first"})

    known = joined[joined["aadt"].notna()].copy()
    known["km"] = known["m"] / 1000
    known["buildKm"] = known["km"] * lengthening
    # Hours saved by one vehicle: the crawl through, less the longer run around.
    known["hoursPerVehicle"] = known["km"] / inside_kmh - known["buildKm"] / open_kmh
    known["vehicleHoursYear"] = known["hoursPerVehicle"] * known["aadt"] * DAYS
    known["costRon"] = known["buildKm"] * lei_per_km
    known = known[known["vehicleHoursYear"] > 0]
    known["ronPerVehicleHour"] = known["costRon"] / known["vehicleHoursYear"]
    known = known.sort_values("ronPerVehicleHour")

    cumulative_cost = known["costRon"].cumsum()
    cumulative_benefit = known["vehicleHoursYear"].cumsum()
    total_benefit = float(cumulative_benefit.iloc[-1])
    curve = []
    for share in (0.25, 0.50, 0.75, 0.90, 1.00):
        cut = int(np.searchsorted(cumulative_benefit.to_numpy(), share * total_benefit)) + 1
        cut = min(cut, len(known))
        curve.append(
            {
                "benefitShare": share,
                "crossings": cut,
                "km": round(float(known["buildKm"].iloc[:cut].sum()), 1),
                "costRon": round(float(cumulative_cost.iloc[cut - 1])),
                "vehicleHoursYear": round(float(cumulative_benefit.iloc[cut - 1])),
                "worstRonPerVehicleHour": round(float(known["ronPerVehicleHour"].iloc[cut - 1]), 1),
            }
        )
        print(
            f"  {share:>4.0%} of the benefit: {cut:>3} crossings, {curve[-1]['km']:>6,.0f} km, "
            f"{curve[-1]['costRon'] / 1e9:>5.1f} md lei, "
            f"up to {curve[-1]['worstRonPerVehicleHour']:>7,.0f} lei/vehicle-hour"
        )

    document = {
        "$schema": "../schema/prioritate.schema.json",
        "id": "prioritate",
        "title": "Ce centuri merită construite întâi, după traficul măsurat",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "ocoliri-plus-end-major-roads",
            "locator": (
                "traversările din data/ocoliri.json, legate spațial la cel mult 60 m de "
                "secțiunile raportate sub Directiva 2002/49/CE cu fluxul lor anual"
            ),
            "confidence": "derived",
            "note": (
                "Câștigul pe vehicul se calculează cu vitezele efective ale modelului, nu cu "
                "limitele legale: o centură nu livrează indicatorul, ci ce merge drumul."
            ),
        },
        "speeds": {"insideKmh": round(inside_kmh, 1), "openKmh": round(open_kmh, 1)},
        "join": {
            "crossings": int(len(crossings)),
            "matched": int(len(joined[joined["aadt"].notna()])),
            "matchDistanceM": MATCH_M,
            "endThresholdAadt": round(END_THRESHOLD_AADT),
            "matchedKm": round(float(known["km"].sum()), 1),
        },
        "ranked": {
            "crossings": int(len(known)),
            "costRon": round(float(known["costRon"].sum())),
            "vehicleHoursYear": round(total_benefit),
            "medianRonPerVehicleHour": round(float(known["ronPerVehicleHour"].median()), 1),
            "bestRonPerVehicleHour": round(float(known["ronPerVehicleHour"].min()), 1),
            "worstRonPerVehicleHour": round(float(known["ronPerVehicleHour"].max()), 1),
        },
        "curve": curve,
        # The unit is the thing most likely to be misread, so it travels with the numbers.
        "unit": {
            "what": "lei de investiție pentru fiecare oră-vehicul economisită ÎNTR-UN AN",
            "howToCompare": (
                "Se împarte la numărul de ani de exploatare luați în calcul ca să iasă lei pe "
                "oră, comparabil cu valoarea timpului de călătorie. La 30 de ani, o traversare "
                "de 1.000 de lei pe oră-vehicul-an costă circa 33 de lei pe oră câștigată."
            ),
            "note": (
                "Valoarea timpului nu se aplică aici deliberat — vezi limitarea "
                "nu-se-aplica-o-valoare-a-timpului."
            ),
        },
        "top": [
            {
                "road": row.roadNationalCode,
                "km": round(row.km, 2),
                "aadt": int(row.aadt),
                "costRon": round(row.costRon),
                "vehicleHoursYear": round(row.vehicleHoursYear),
                "ronPerVehicleHour": round(row.ronPerVehicleHour, 1),
            }
            for row in known.head(20).itertuples()
        ],
        "limitations": [
            {
                "id": "doar-traversarile-cu-trafic-masurat",
                "text": (
                    f"Se clasează doar cele {len(known):,} de traversări care s-au putut lega "
                    f"de o secțiune cu trafic măsurat, din {len(crossings):,}. Restul nu sunt "
                    "necunoscute: directiva acoperă tot ce trece de trei milioane de vehicule "
                    "pe an, deci o traversare care nu se potrivește este SUB "
                    f"{END_THRESHOLD_AADT:,.0f} de vehicule pe zi, nu nemăsurată. "
                    "Clasamentul este deci vârful "
                    "distribuției prin construcție — exact partea pe care un program ar "
                    "construi-o prima. Ce rămâne nesigur: raportarea sub directivă este a "
                    "CNAIR și a trei consilii județene, deci un drum județean aglomerat poate "
                    "lipsi din motive administrative, nu de trafic."
                ).replace(",", "."),
                "severity": "material",
                "affects": ["prioritate"],
            },
            {
                "id": "nu-se-aplica-o-valoare-a-timpului",
                "text": (
                    "Se raportează lei pe oră-vehicul economisită și atât. Transformarea orelor "
                    "în lei cere o valoare a timpului de călătorie, care este un parametru de "
                    "politică publică cu interval larg și influență mare; alegerea uneia aici "
                    "ar îngropa cel mai contestabil număr din lanț într-un singur raport. "
                    "Cititorul care vrea un raport beneficiu-cost își pune propria valoare și "
                    "împarte."
                ),
                "severity": "note",
                "affects": ["prioritate"],
            },
            {
                "id": "beneficiul-e-doar-timpul-soferilor",
                "text": (
                    "Orele economisite sunt ale vehiculelor care trec. Nu se numără siguranța "
                    "rutieră — principalul motiv pentru care se construiesc centuri —, nici "
                    "zgomotul și aerul scoase din sat, nici timpul câștigat de localnicii care "
                    "traversează strada. O centură judecată doar pe timpul de parcurs este "
                    "subevaluată, iar cu cât satul este mai mic cu atât mai mult."
                ),
                "severity": "material",
                "affects": ["prioritate"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    best, worst = (
        document["ranked"]["bestRonPerVehicleHour"],
        document["ranked"]["worstRonPerVehicleHour"],
    )
    print(
        f"\n  cost per vehicle-hour saved: best {best:,.0f}, median "
        f"{document['ranked']['medianRonPerVehicleHour']:,.0f}, worst {worst:,.0f} lei"
    )
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

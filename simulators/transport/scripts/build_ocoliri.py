"""How many bypasses Romania's national roads need, and what they would cost.

The speed model's central finding is that a DN is not slow because it is a worse road — it is
slow because a third of its length threads through villages at 50 km/h. `measure_limits.py`
states that as a share. This turns the share into a list of places: every stretch of trunk or
primary road that carries a signed 50, merged into contiguous runs, is one settlement the
national road goes *through* rather than around.

That list is the bypass programme. It is derived from the same tags the whole speed model
rests on, so it cannot disagree with the journey times elsewhere in this repository.

**A crossing is not automatically a bypass.** Six hundred metres of village on a DN is a
nuisance; four kilometres of town is a project. The minimum length is the lever, and it is
deliberately explicit: at 200 m the country needs 3 714 bypasses, at 1 km it needs 1 953, and
the honest answer to "how many" is "it depends where you draw the line, and here is the curve".

**What the count is not.** It is a floor, not a total. `maxspeed` covers 84% of trunk and 88%
of primary by length, so crossings on untagged stretches are invisible here. It also counts
what the road passes through today: a village that grew along a bypass built in 1975 shows as
no crossing at all, which is correct, and one whose 50 zone was never mapped shows as no
crossing, which is not.

Output:
    data/ocoliri.json    crossings and cost by county, at several length thresholds

Usage:
    uv run python -m scripts.build_ocoliri
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PBF = ADMINISTRATIV / "data" / "raw" / "romania-latest.osm.pbf"
OUT = ROOT / "data" / "ocoliri.json"
INPUTS = ROOT / "data" / "ocoliri-inputs.json"

# The national network. County roads are left out on purpose: a DJ through a village is a
# nuisance for that village, but the through-traffic case that justifies public money is the
# national road, and DJ bypasses are a county's decision rather than a national programme.
CLASSES: Final[tuple[str, ...]] = ("trunk", "primary")

# A signed 50 on a road otherwise limited to 90 is the marker of a built-up area. Non-numeric
# values are untagged, exactly as in measure_limits.py — the parser is imported from there so
# the two cannot drift.
LOCALITY_KMH: Final[int] = 50

# Thresholds to report. The middle one is the default; the others exist so the reader can see
# how sharply the answer depends on where the line is drawn.
THRESHOLDS_M: Final[tuple[int, ...]] = (200, 500, 1000, 2000)
DEFAULT_THRESHOLD_M: Final[int] = 500

CRS_STEREO70: Final[str] = "EPSG:3844"


def crossings(geometries, lengths_floor: float = 0.0):
    """Contiguous runs of in-locality road, one per settlement the road passes through.

    `linemerge` joins ways that share an endpoint, so a village mapped as nine separate ways
    becomes one crossing. Two villages a kilometre apart stay separate because the 90 km/h
    stretch between them is not in this set — which is the whole reason this works.
    """
    from shapely.ops import linemerge, unary_union

    merged = linemerge(unary_union(list(geometries)))
    parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    return [p for p in parts if p.length >= lengths_floor]


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    if not PBF.exists():
        print(f"Missing {PBF}. Run administrativ's fetch with --with-roads.", file=sys.stderr)
        return 1

    import geopandas as gpd

    from scripts.measure_limits import parse_maxspeed

    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))["items"]
    lei_per_km = inputs["bypassLeiPerKm"]["value"]
    lengthening = inputs["bypassLengthFactor"]["value"]

    selector = ",".join(f"'{c}'" for c in CLASSES)
    print(f"Reading {', '.join(CLASSES)} from {PBF.name}...")
    roads = gpd.read_file(
        PBF,
        layer="lines",
        columns=["highway", "other_tags"],
        where=f"highway IN ({selector})",
        engine="pyogrio",
    )
    if roads.crs is None:
        roads = roads.set_crs("EPSG:4326")
    roads = roads.to_crs(CRS_STEREO70)

    limits = np.array([parse_maxspeed(t) for t in roads["other_tags"]])
    total_km = float(roads.geometry.length.sum()) / 1000
    tagged_km = float(roads.geometry.length[np.isfinite(limits)].sum()) / 1000
    inside = roads[limits == LOCALITY_KMH]
    inside_km = float(inside.geometry.length.sum()) / 1000
    print(f"  {total_km:,.0f} km, {tagged_km / total_km:.0%} tagged, {inside_km:,.0f} km at 50")

    print("Merging into settlement crossings...")
    every = crossings(inside.geometry)
    lengths = np.array([p.length for p in every])

    by_threshold = {}
    for floor in THRESHOLDS_M:
        keep = lengths >= floor
        crossing_km = float(lengths[keep].sum()) / 1000
        build_km = crossing_km * lengthening
        by_threshold[str(floor)] = {
            "crossings": int(keep.sum()),
            "throughTownKm": round(crossing_km, 1),
            "bypassKm": round(build_km, 1),
            "medianCrossingM": round(float(np.median(lengths[keep])), 0) if keep.any() else 0,
            "costRon": round(build_km * lei_per_km),
        }
        print(
            f"  >= {floor:>4} m: {keep.sum():>5,} crossings  {crossing_km:>7,.0f} km through "
            f"town  {build_km:>7,.0f} km to build  {build_km * lei_per_km / 1e9:>6.1f} md lei"
        )

    default = by_threshold[str(DEFAULT_THRESHOLD_M)]
    document = {
        "$schema": "../schema/ocoliri.schema.json",
        "id": "ocoliri",
        "title": "Câte centuri ocolitoare cer drumurile naționale, și cât ar costa",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "openstreetmap-maxspeed-plus-contract-sighisoara",
            "locator": (
                "traversările de localitate deduse din limita de 50 km/h pe clasele trunk și "
                "primary din romania-latest.osm.pbf; prețul pe kilometru din contractul de "
                "execuție al Variantei de Ocolire Sighișoara, octombrie 2025"
            ),
            "confidence": "derived",
            "note": (
                "Traversările sunt măsurate din etichete, nu numărate dintr-o listă de "
                "proiecte. Prețul vine dintr-un singur contract recent, iar lungimea de "
                "construit este traversarea înmulțită cu un factor de ocolire presupus."
            ),
        },
        "classes": list(CLASSES),
        "network": {
            "totalKm": round(total_km, 1),
            "coverage": round(tagged_km / total_km, 4),
            "throughLocalityKm": round(inside_km, 1),
            "throughLocalityShare": round(inside_km / total_km, 4),
        },
        "defaultThresholdM": DEFAULT_THRESHOLD_M,
        "byThreshold": by_threshold,
        "headline": default,
        "limitations": [
            {
                "id": "numarul-e-un-prag-nu-o-descoperire",
                "text": (
                    f"Câte centuri sunt necesare depinde de unde se trage linia: la 200 de "
                    f"metri ies {by_threshold['200']['crossings']:,} de traversări, la un "
                    f"kilometru {by_threshold['1000']['crossings']:,}, la doi kilometri "
                    f"{by_threshold['2000']['crossings']:,}. Pragul implicit este de "
                    f"{DEFAULT_THRESHOLD_M} de metri și este o alegere, nu o măsurătoare. "
                    "Curba întreagă este publicată tocmai ca cifra să nu poată fi citată fără "
                    "pragul ei."
                ),
                "severity": "material",
                "affects": ["ocoliri"],
            },
            {
                "id": "traversarile-sunt-un-prag-de-jos",
                "text": (
                    f"Acoperirea cu maxspeed este de {tagged_km / total_km:.0%} din kilometri "
                    "pe aceste clase, deci traversările de pe porțiunile neetichetate nu se "
                    "văd aici. Numărul este un prag de jos, nu un total. În plus, se numără ce "
                    "traversează drumul ASTĂZI: o localitate ocolită deja nu apare, ceea ce "
                    "este corect, iar una a cărei zonă de 50 nu a fost cartografiată tot nu "
                    "apare, ceea ce nu este."
                ),
                "severity": "material",
                "affects": ["ocoliri"],
            },
            {
                "id": "un-singur-contract-de-referinta",
                "text": (
                    "Prețul pe kilometru vine dintr-un singur contract: Varianta de Ocolire "
                    "Sighișoara, 260 de milioane de lei fără TVA pentru 13,057 km, ordin de "
                    "începere octombrie 2025. Este cel mai potrivit reper găsit — recent, "
                    "drum de două benzi, teren de deal — dar este UNUL. Terenul nu este "
                    "diferențiat: în câmpie o centură ar fi mai ieftină, iar în munte "
                    "considerabil mai scumpă. Centurile metropolitane nu sunt folosite ca "
                    "reper pentru că sunt alt produs: Cluj iese la 27 de milioane de euro pe "
                    "kilometru cu 156 de poduri și tuneluri, Sibiu la 21."
                ),
                "severity": "material",
                "affects": ["ocoliri"],
            },
            {
                "id": "pretul-de-contract-nu-e-costul-total",
                "text": (
                    "Valoarea contractului de execuție nu include, de regulă, exproprierile, "
                    "mutarea utilităților, proiectarea anterioară și avizele. La proiectele "
                    "rutière românești acestea adaugă frecvent între 10 și 30 la sută. Cifra "
                    "de aici este deci un cost de execuție, iar bugetul real este mai mare."
                ),
                "severity": "material",
                "affects": ["ocoliri"],
            },
            {
                "id": "nu-e-inca-legat-de-timpii-de-parcurs",
                "text": (
                    "Modelul spune cât costă ocolirea, nu cât timp câștigă. Legătura există și "
                    "este calculabilă din același model — o localitate ocolită scoate acei "
                    "kilometri din regimul de 50 și îi trece în cel de 90 — dar nu este încă "
                    "făcută. Până atunci, cifra este un cost fără beneficiul lui alături, "
                    "adică exact jumătatea de care un decident nu are nevoie singură."
                ),
                "severity": "blocking",
                "affects": ["ocoliri"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"\nAt the {DEFAULT_THRESHOLD_M} m threshold: {default['crossings']:,} bypasses, "
        f"{default['bypassKm']:,.0f} km, {default['costRon'] / 1e9:.1f} md lei "
        f"({default['costRon'] / 1e9 / 4.97:.1f} md euro)"
    )
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

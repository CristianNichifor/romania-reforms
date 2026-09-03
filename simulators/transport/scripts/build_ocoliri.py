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
LIMITS_IN = ROOT / "data" / "road-limits.json"
LIMITS_OUT = ROOT / "data" / "road-limits-bypassed.json"
TIMES_BASE = ROOT / "data" / "road_time.parquet"
TIMES_BYPASSED = ROOT / "data" / "road_time_bypassed.parquet"
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

    # The benefit, if the counterfactual has been routed. Both files come from the same graph
    # and the same code with only the limits changed, which is what makes them comparable —
    # and it is why the benefit is measured here rather than estimated from the speed table.
    benefit = None
    if TIMES_BASE.exists() and TIMES_BYPASSED.exists():
        import pandas as pd

        merged = pd.read_parquet(TIMES_BASE).merge(
            pd.read_parquet(TIMES_BYPASSED), on=["a_siruta", "b_siruta"], suffixes=("_b", "_y")
        )
        good = np.isfinite(merged["road_min_b"]) & np.isfinite(merged["road_min_y"])
        good &= merged["road_min_b"] > 0
        before, after = merged.loc[good, "road_min_b"], merged.loc[good, "road_min_y"]
        benefit = {
            "pairs": int(good.sum()),
            "medianMinBefore": round(float(before.median()), 2),
            "medianMinAfter": round(float(after.median()), 2),
            "meanMinBefore": round(float(before.mean()), 2),
            "meanMinAfter": round(float(after.mean()), 2),
            "totalHoursSaved": round(float((before - after).sum()) / 60, 1),
            "timeRatio": round(float(after.sum() / before.sum()), 4),
            "pairsFaster": int((after < before).sum()),
            "pairsSlower": int((after > before).sum()),
        }
        print(
            f"  benefit: median {benefit['medianMinBefore']} -> "
            f"{benefit['medianMinAfter']} min ({benefit['timeRatio'] - 1:+.1%} on total), "
            f"{benefit['pairsFaster']:,} of {benefit['pairs']:,} pairs faster"
        )
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
        "benefit": benefit,
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
                "id": "castigul-e-pe-clasa-nu-pe-segment",
                "text": (
                    "Beneficiul este măsurat, nu estimat: aceeași rețea, același cod, singura "
                    "diferență fiind fișierul de limite. Dar câștigul se aplică pe CLASĂ, nu pe "
                    "segment. speeds.py calculează o singură viteză pentru tot ce e trunk și "
                    "una pentru tot ce e primary, pornind de la cota medie de localitate a "
                    "clasei; a ocoli 93% dintre traversări ridică acea medie peste tot deodată, "
                    "inclusiv pe porțiuni care nu ar fi ocolite niciodată, cum sunt cele din "
                    "interiorul orașelor mari. Pe totalul celor 9.235 de perechi estimarea este "
                    "rezonabilă; pentru o pereche anume este întinsă, în ambele sensuri. O "
                    "variantă pe segment ar cere reconstruirea grafului cu limite per muchie."
                ),
                "severity": "material",
                "affects": ["ocoliri"],
            },
            {
                "id": "beneficiul-e-doar-timp-de-drum",
                "text": (
                    "Ce se măsoară aici este timpul de parcurs între reședințe, adică exact "
                    "mărimea pe care o folosește restul acestui simulator. Ce NU se măsoară: "
                    "siguranța rutieră, zgomotul și poluarea scoase din sat, valoarea "
                    "terenului, și mai ales traficul care nu e autobuz. Justificarea "
                    "economică a unei centuri stă în tot traficul care o folosește, iar "
                    "volumele de trafic nu există în OpenStreetMap — recensământul de "
                    "circulație al CNAIR ar fi sursa. Deci beneficiul de aici este un prag de "
                    "jos, calculat pentru o singură categorie de utilizatori."
                ),
                "severity": "material",
                "affects": ["ocoliri"],
            },
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # The counterfactual limits: the same measurement, with the bypassed settlements taken out
    # of the in-locality share. Feeding this through speeds.py and build_road_time gives the
    # journey times of a country that built the programme — computed by the same code as the
    # baseline, which is the only way the two are comparable.
    #
    # The bypassed kilometres are split between trunk and primary in proportion to each
    # class's in-locality length, rather than measured per class. Merging crossings per class
    # would cut a village in half wherever the road changes classification mid-settlement and
    # drop both halves below the threshold; this approximation keeps the crossing whole and is
    # declared in the limitation below.
    limits = json.loads(LIMITS_IN.read_text(encoding="utf-8"))
    bypassed_share = default["throughTownKm"] / inside_km if inside_km else 0.0
    for name in CLASSES:
        entry = limits["classes"].get(name)
        if entry and entry.get("usable"):
            entry["locality_share"] = round(entry["locality_share"] * (1 - bypassed_share), 6)
    limits["provenance"]["note"] = (
        f"CONTRAFACTUAL: aceleași măsurători, cu {bypassed_share:.0%} din traversările de "
        f"localitate de pe trunk și primary scoase din cota de localitate — programul de "
        f"{default['crossings']:,} de centuri din data/ocoliri.json. Nu este o măsurătoare a "
        "României de azi și nu trebuie folosit ca atare."
    ).replace(",", ".")
    limits["limitations"] = list(limits.get("limitations", [])) + [
        {
            "id": "acest-fisier-e-contrafactual",
            "text": (
                "Fișierul descrie o rețea care nu există: cea de după construirea centurilor. "
                "Se folosește doar ca intrare pentru varianta ocolită a timpilor de parcurs. "
                "Baza reală este data/road-limits.json."
            ),
            "severity": "blocking",
            "affects": ["road-limits-bypassed"],
        }
    ]
    LIMITS_OUT.write_text(json.dumps(limits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  bypassed {bypassed_share:.0%} of in-locality km -> {LIMITS_OUT.name}")

    print(
        f"\nAt the {DEFAULT_THRESHOLD_M} m threshold: {default['crossings']:,} bypasses, "
        f"{default['bypassKm']:,.0f} km, {default['costRon'] / 1e9:.1f} md lei "
        f"({default['costRon'] / 1e9 / 4.97:.1f} md euro)"
    )
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

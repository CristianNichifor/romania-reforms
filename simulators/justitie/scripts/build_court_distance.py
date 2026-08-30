"""Road distance from every UAT to each of the 42 court seats, as a binary the browser can read.

The static arondare answers "which court, at the administrative simulator's default settings".
It cannot answer the question a reader actually has, which is what happens to the judicial map
when they move the administrative sliders — because the consolidated units change underneath it.

Recomputing the merge in the browser is cheap: the model is already a TypeScript port and its
payload is 1,6 MB. What the browser does not have is road distance, and Dijkstra over 3.186
nodes on every slider drag would be the wrong place to spend the time. So the distances are
precomputed here, once, for the only origins that matter: the 42 court seats. Assignment then
costs one pass over 42 numbers per unit.

Stored as unsigned 16-bit hundreds of metres, which tops out at 6.553 km. The matrix holds
every pair, so its largest entry is a corner-to-corner journey of about 947 km — the range is
comfortable but not for the reason it first appears, and the figure that bounds what a reader
ever sees is different: nobody is more than 128 km from their nearest court. 100 m of
resolution decides nothing in a comparison whose smallest interesting difference is a couple of
kilometres. 65535 means unreachable — the Delta, which no road serves.

Layout: 42 rows of 3.186 columns, row-major, column index being the UAT's position in SIRUTA
ascending order. That is the same index the administrative model's own binaries use, which is
what lets the browser join them without carrying a SIRUTA lookup.

Usage:
    uv run python scripts/build_court_distance.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
# Written to data/, not straight into the app's public/data: that directory is generated and
# gitignored, so a binary written there exists on the machine that built it and nowhere else.
# CI has no parquet and no road graph, and the parity test that reads it failed on the runner
# while passing locally.
OUT_BIN = ROOT / "data" / "court-distance.bin"
OUT_META = ROOT / "data" / "court-distance.json"

sys.path.insert(0, str(ADMINISTRATIV))

BUCHAREST = "B"
UNREACHABLE = 65535
SCALE_M = 100


def main() -> int:
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    from scipy.sparse import coo_matrix  # noqa: PLC0415
    from scipy.sparse.csgraph import dijkstra  # noqa: PLC0415

    from pipeline.reference_model import load_data  # noqa: PLC0415

    courts_file = ROOT / "data" / "instante-localizate-2025.json"
    edges_file = ADMINISTRATIV / "data" / "processed" / "road_distance.parquet"
    for path in (courts_file, edges_file):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    located = json.loads(courts_file.read_text(encoding="utf-8"))["courts"]
    data = load_data()

    order = sorted(data.population)
    index_of = {siruta: i for i, siruta in enumerate(order)}
    size = len(order)

    edges = pd.read_parquet(edges_file)
    a = np.array([index_of[str(x)] for x in edges["a_siruta"]])
    b = np.array([index_of[str(x)] for x in edges["b_siruta"]])
    weight = edges["road_m"].to_numpy(dtype=float)
    keep = np.isfinite(weight)
    a, b, weight = a[keep], b[keep], weight[keep]
    graph = coo_matrix(
        (np.concatenate([weight, weight]), (np.concatenate([a, b]), np.concatenate([b, a]))),
        shape=(size, size),
    ).tocsr()

    county_court: dict[str, str] = {}
    court_name: dict[str, str] = {}
    for court in located:
        if court["tier"] != "tribunal" or not court["siruta"]:
            continue
        if any(w in court["name"] for w in ("Specializat", "Comercial", "Militar", "minori")):
            continue
        if court["county"] in county_court:
            continue
        county_court[court["county"]] = court["siruta"]
        court_name[court["county"]] = court["name"]
    if BUCHAREST not in county_court:
        sectors = sorted(s for s in data.population if data.county[s] == BUCHAREST)
        if sectors:
            county_court[BUCHAREST] = sectors[0]
            court_name[BUCHAREST] = "Tribunalul București"

    # Sorted by county code so the row order is stable across builds and legible in the file.
    counties = sorted(county_court)
    seats = [county_court[c] for c in counties]
    matrix = dijkstra(graph, directed=False, indices=[index_of[s] for s in seats])

    hundreds = np.where(
        np.isfinite(matrix),
        np.minimum(np.rint(matrix / SCALE_M), UNREACHABLE - 1),
        UNREACHABLE,
    ).astype(np.uint16)

    reachable = int((hundreds != UNREACHABLE).all(axis=0).sum())
    longest = int(hundreds[hundreds != UNREACHABLE].max()) * SCALE_M
    # This is a full matrix, so its maximum is the farthest *pair* — Satu Mare to Tulcea and
    # the like, legitimately some 900 km by road. The bound that means anything is on the
    # nearest court, which is the only distance any reader is ever shown: nobody in Romania
    # lives 300 km from all 42 seats. Checking the matrix maximum against a nearest-court
    # threshold is how the first version of this file failed on correct data.
    nearest = np.where(matrix.min(axis=0) < np.inf, matrix.min(axis=0), 0)
    furthest_nearest = float(nearest.max())
    if furthest_nearest > 300_000:
        print(
            f"someone is {furthest_nearest / 1000:.0f} km from every court; "
            "that is the graph, not geography",
            file=sys.stderr,
        )
        return 1
    if longest > 1_500_000:
        print(f"a journey of {longest / 1000:.0f} km is longer than the country", file=sys.stderr)
        return 1

    OUT_BIN.parent.mkdir(parents=True, exist_ok=True)
    OUT_BIN.write_bytes(hundreds.tobytes())

    document = {
        "$schema": "../schema/court-distance.schema.json",
        "id": "court-distance",
        "title": "Distanța rutieră de la fiecare UAT la cele 42 de sedii de instanță",
        "publisher": "Cristian Nichifor",
        "period": "2025",
        "provenance": {
            "source": "reforma-sistem-judiciar-romania",
            "locator": (
                "Dijkstra pe graful rutier național al simulatorului administrativ, "
                "din fiecare sediu de tribunal județean"
            ),
            "confidence": "derived",
        },
        "file": "court-distance.bin",
        "dtype": "uint16",
        "scaleMetres": SCALE_M,
        "unreachable": UNREACHABLE,
        "rows": len(seats),
        "columns": size,
        "bytes": OUT_BIN.stat().st_size,
        "courts": [
            {"county": county, "siruta": county_court[county], "name": court_name.get(county, "")}
            for county in counties
        ],
        "limitations": [
            {
                "id": "rezolutie-de-100-m",
                "text": (
                    "Distanțele sunt rotunjite la 100 de metri, ca să încapă în jumătate din "
                    "spațiu. Diferența cea mai mică pe care o compară cineva aici este de "
                    "kilometri, deci rotunjirea nu schimbă nicio arondare."
                ),
                "severity": "note",
                "affects": ["acces"],
            },
            {
                "id": "sediu-la-sediu",
                "text": (
                    "Se măsoară de la sediul UAT-ului la sediul instanței, nu de la casa "
                    "omului. Pentru unitățile consolidate, care sunt mari, cei de la margine au "
                    "de mers mai mult decât arată cifra."
                ),
                "severity": "material",
                "affects": ["acces"],
            },
        ],
    }
    OUT_META.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{len(seats)} sedii × {size} UAT-uri = {OUT_BIN.stat().st_size / 1024:.0f} KB")
    print(f"UAT-uri accesibile din toate sediile: {reachable} din {size}")
    print(f"cel mai lung drum din matrice: {longest / 1000:.0f} km (colț la colț)")
    print(f"cel mai departe de orice instanță: {furthest_nearest / 1000:.0f} km")
    print(f"\nWrote {OUT_BIN.relative_to(ROOT.parent.parent)}")
    print(f"Wrote {OUT_META.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

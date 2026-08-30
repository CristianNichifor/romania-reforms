"""Ship the travel-time graph to the browser, so the map can follow a live scenario.

Until now the app carried five frozen consolidation scenarios, precomputed here. That was
always the wrong shape: `export_hubs.py` says in its first line that it *freezes one
administrative scenario*, and then the sweep quietly re-decided the same thing five more ways.
Administrativ owns consolidation. A reader who builds a map there should be able to bring it
here, exactly as `justitie` already lets them.

**The reason that was not done is gone.** It looked as though live journey times needed a
3.186 x 3.186 matrix in the browser. They do not. The road model is a graph of adjacent UATs —
9.281 edges — and Dijkstra over it in JavaScript is milliseconds. Better still, administrativ
already ships that graph: `admin-adjacency.bin` holds exactly these 9.281 edges, in this order.
So this file ships **only the times**, one float per edge, and the browser gets a routable
network for 37 KB by reusing a payload it has already downloaded.

**The alignment is the whole risk.** These times are positional: index `i` here means edge `i`
there. If the two ever diverge — a rebuilt adjacency, a changed sort — every commune in the
country would be painted with some other commune's journey and nothing would look wrong. So
the pairs are compared explicitly and a mismatch is fatal. This is the same failure that made
`uats.geojson` join zero of 3.186 rows and render a plausible grey map.

Output:
    data/road-time.bin      float32 per adjacency edge, seconds; NaN where impassable
    data/road-time.json     the manifest: count, checksum of the pair order, units

Usage:
    uv run python -m scripts.export_traveltime
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
PROCESSED = ADMINISTRATIV / "data" / "processed"
OUT_BIN = ROOT / "data" / "road-time.bin"
OUT_MANIFEST = ROOT / "data" / "road-time.json"


def pair_checksum(a: list[str], b: list[str]) -> str:
    """A hash of the edge order itself.

    Published so the browser can refuse to use these times against an adjacency it does not
    recognise, rather than silently pairing them with the wrong edges.
    """
    digest = hashlib.sha256()
    for x, y in zip(a, b, strict=True):
        digest.update(f"{x}|{y}\n".encode())
    return digest.hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import pandas as pd

    adjacency_path = PROCESSED / "adjacency.parquet"
    times_path = ROOT / "data" / "road_time.parquet"
    needed = (
        (adjacency_path, "administrativ build_adjacency"),
        (times_path, "scripts.build_road_time"),
    )
    for path, how in needed:
        if not path.exists():
            raise SystemExit(f"missing {path} — run {how} first")

    adjacency = pd.read_parquet(adjacency_path)
    times = pd.read_parquet(times_path)

    if len(adjacency) != len(times):
        raise SystemExit(
            f"edge counts differ: adjacency {len(adjacency):,}, times {len(times):,}. "
            "The times are positional; shipping them against a different graph would paint "
            "every commune with another commune's journey."
        )

    a_adj = adjacency["a_siruta"].astype(str).tolist()
    b_adj = adjacency["b_siruta"].astype(str).tolist()
    a_time = times["a_siruta"].astype(str).tolist()
    b_time = times["b_siruta"].astype(str).tolist()
    if a_adj != a_time or b_adj != b_time:
        bad = next(i for i in range(len(a_adj)) if a_adj[i] != a_time[i] or b_adj[i] != b_time[i])
        raise SystemExit(
            f"edge order diverged at index {bad}: adjacency has "
            f"({a_adj[bad]}, {b_adj[bad]}), times have ({a_time[bad]}, {b_time[bad]})"
        )

    seconds = times["road_s"].to_numpy(dtype=np.float32)
    OUT_BIN.write_bytes(seconds.tobytes())

    finite = np.isfinite(seconds)
    manifest = {
        "$schema": "../schema/road-time.schema.json",
        "id": "road-time",
        "title": "Timpii de parcurs pe muchiile grafului administrativ",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "road_time-peste-adjacency",
            "locator": (
                "data/road_time.parquet, aliniat pozițional la "
                "simulators/administrativ/data/processed/adjacency.parquet"
            ),
            "confidence": "derived",
            "note": (
                "Un float32 pe muchie, în secunde, în ORDINEA muchiilor din graful "
                "administrativ. Browserul rulează Dijkstra peste el, deci harta poate urmări "
                "orice scenariu de comasare, nu doar cele precalculate aici."
            ),
        },
        "edgeCount": int(len(seconds)),
        "pairChecksum": pair_checksum(a_adj, b_adj),
        "unit": "seconds",
        "dtype": "float32",
        "impassableEdges": int((~finite).sum()),
        "medianSeconds": round(float(np.median(seconds[finite])), 1),
        "limitations": [
            {
                "id": "timpii-sunt-pozitionali",
                "text": (
                    "Fișierul nu conține perechile de UAT-uri, ci doar timpii, în ordinea "
                    "muchiilor din graful administrativ. Este ieftin — 37 KB în loc de o "
                    "matrice — dar înseamnă că o reconstrucție a adiacenței fără "
                    "regenerarea acestui fișier ar asocia fiecărei muchii timpul altei muchii, "
                    "fără ca ceva să pară greșit. De aceea manifestul publică o sumă de "
                    "control a ordinii perechilor, iar consumatorul trebuie să o verifice."
                ),
                "severity": "material",
                "affects": ["road-time"],
            }
        ],
    }
    OUT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"  {len(seconds):,} edges, {OUT_BIN.stat().st_size / 1024:.0f} KB")
    print(f"  impassable {int((~finite).sum()):,}   median {manifest['medianSeconds']:.0f} s")
    print(f"  pair checksum {manifest['pairChecksum']}")
    print(f"Wrote {OUT_BIN} and {OUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

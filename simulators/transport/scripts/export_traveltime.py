"""Ship the travel-time graph to the browser, so the map can follow a live scenario.

Until now the app carried five frozen consolidation scenarios, precomputed here. That was
always the wrong shape: `export_hubs.py` says in its first line that it *freezes one
administrative scenario*, and then the sweep quietly re-decided the same thing five more ways.
Administrativ owns consolidation. A reader who builds a map there should be able to bring it
here, exactly as `justitie` already lets them.

**The reason that was not done is gone.** It looked as though live journey times needed a
3.186 x 3.186 matrix in the browser. They do not. The road model is a graph of adjacent UATs —
9.281 edges — and Dijkstra over it in JavaScript is milliseconds. So this ships the graph
itself: both endpoints and the time, 73 KB, and the browser can route the whole country.

**Self-describing on purpose.** The first draft shipped the times alone, positionally against
`adjacency.parquet`, at half the size. That was wrong: the browser never sees that file. It
sees `ModelData.neighbours`, a compressed-row graph built by other code in another order.
Times laid against the wrong graph give every commune some other commune's journey and look
entirely plausible — the failure that made `uats.geojson` join 0 of 3.186 rows and render a
convincing grey map. Carrying the endpoints costs 37 KB and removes the coupling: the consumer
builds its own graph and assumes nothing about anyone else's ordering.

What still has to be checked is the UAT order itself, because the endpoints are indices into
administrativ's `attributes.json`. The manifest publishes a checksum of the pair order for
that, and the exporter refuses to run if a siruta in the road graph is unknown there.

Output:
    data/road-time.bin      uint16 a[], uint16 b[], float32 seconds[], float32 metres[] —
                            indices into administrativ's UAT order; NaN where impassable
    data/road-time.json     the manifest: count, layout, checksum of the pair order

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

    # Emit the endpoints as well as the times, as indices into administrativ's UAT order.
    #
    # The first version of this file shipped times alone, positionally against
    # adjacency.parquet. That was 36 KB instead of 74 and it was wrong: the browser does not
    # see adjacency.parquet, it sees ModelData's compressed-row `neighbours`, which is a
    # different ordering built by different code. Times lined up against the wrong graph would
    # give every commune another commune's journey and look entirely plausible — the same
    # failure as the geojson join that matched 0 of 3.186 rows.
    #
    # Carrying the endpoints costs 37 KB and removes the coupling entirely: the consumer builds
    # its own graph and depends on nothing about how anyone else ordered theirs.
    attributes = json.loads(
        (ADMINISTRATIV / "web" / "public" / "data" / "attributes.json").read_text("utf-8")
    )
    index_of = {str(s): i for i, s in enumerate(attributes["siruta"])}
    missing = {s for s in (*a_time, *b_time) if s not in index_of}
    if missing:
        raise SystemExit(
            f"{len(missing)} siruta codes in the road graph are not in administrativ's "
            f"attribute order, e.g. {sorted(missing)[:3]} — the two are describing "
            "different countries"
        )

    # Metres as well as seconds. Journey times need only the clock, but costing needs
    # kilometres — fuel, tyres and maintenance are per kilometre, not per minute — and the
    # browser cannot recompute a fleet without them.
    distance_path = PROCESSED / "road_distance.parquet"
    if not distance_path.exists():
        raise SystemExit(f"missing {distance_path} — run administrativ build_road_distance")
    distances = pd.read_parquet(distance_path)
    if (
        distances["a_siruta"].astype(str).tolist() != a_time
        or distances["b_siruta"].astype(str).tolist() != b_time
    ):
        raise SystemExit("road_distance and road_time disagree on edge order")

    a_index = np.array([index_of[s] for s in a_time], dtype=np.uint16)
    b_index = np.array([index_of[s] for s in b_time], dtype=np.uint16)
    # NOT filtered by adjacency's `traversable` flag. That column marks whether a road crosses
    # the shared border (5.912 of 9.281); road_time measures seat-to-seat travel over the whole
    # network, which can be finite even where the border itself has no crossing. build_access
    # uses every finite time, so this must too — filtering here removed a third of the roads
    # and modelled a country nobody had built.
    seconds = times["road_s"].to_numpy(dtype=np.float32)
    metres = distances["road_m"].to_numpy(dtype=np.float32)
    OUT_BIN.write_bytes(
        a_index.tobytes() + b_index.tobytes() + seconds.tobytes() + metres.tobytes()
    )

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
        "layout": (
            "uint16 a[edgeCount], uint16 b[edgeCount], "
            "float32 seconds[edgeCount], float32 metres[edgeCount]"
        ),
        "impassableEdges": int((~finite).sum()),
        "medianSeconds": round(float(np.median(seconds[finite])), 1),
        "limitations": [
            {
                "id": "timpii-sunt-pozitionali",
                "text": (
                    "Capetele muchiilor sunt indici în ordinea UAT-urilor din "
                    "attributes.json al simulatorului administrativ, nu coduri SIRUTA. "
                    "Dacă acea ordine se schimbă fără regenerarea acestui fișier, fiecare "
                    "muchie ajunge între alte două comune, iar harta rezultată arată "
                    "perfect plauzibil. Suma de control din manifest există exact pentru "
                    "asta și trebuie verificată de consumator."
                ),
                "severity": "material",
                "affects": ["road-time"],
            }
        ],
    }
    OUT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"  {len(seconds):,} edges, {OUT_BIN.stat().st_size / 1024:.0f} KB "
        f"(a+b indices and seconds)"
    )
    print(f"  impassable {int((~finite).sum()):,}   median {manifest['medianSeconds']:.0f} s")
    print(f"  pair checksum {manifest['pairChecksum']}")
    print(f"Wrote {OUT_BIN} and {OUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

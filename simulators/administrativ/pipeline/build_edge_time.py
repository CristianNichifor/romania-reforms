"""Drive time for every adjacency edge, from the transport simulator.

The model measures in metres and the map says kilometres, which is the least legible rule it
has: "Hamcearca is 21.5 km from Topolog against a 50 km cap" asks a reader to hold a distance
in their head and judge it. Twenty-seven minutes does not.

The transport simulator already computed this — travel time over the same borders, from
measured speed limits by road class — and its payload is aligned to this project's adjacency
table. This re-keys it into the order `adjacency.bin` uses and writes it as one small array,
so the browser can read a time by edge index with no join at run time.

**Why re-key rather than read it directly.** Two orders are in play and they are not the same:
`road-time.bin` follows `adjacency.parquet`, while `export.py` writes `adjacency.bin` in its
own. Comparing the two positionally looks like a catastrophic data mismatch — 1.8% of
distances agreeing — when nothing is wrong at all. Keying on the unordered pair of endpoints
removes the trap, and doing it here means the browser never has to know it existed.

Output:
    web/public/data/edge-time.bin       uint16 seconds per edge, in adjacency.bin order
    data/processed/reports/edge_time.md

Usage:
    uv run python -m pipeline.build_edge_time
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from pipeline.build_geometry import Check, Report, write_report
from pipeline.paths import REPO_ROOT, REPORTS_DIR, WEB_DATA_DIR

# `REPO_ROOT` in pipeline.paths is the *simulator* root despite its name — it resolves to
# simulators/administrativ. The repository is two levels above it, and that is where the
# sibling simulators live.
TRANSPORT = REPO_ROOT.parent / "transport" / "data"

# Seconds, as uint16. The longest edge in the country is well under an hour by road, so 65,535
# seconds is eighteen hours of headroom — and it doubles as the impassable marker, which the
# transport file carries for 46 edges where no route exists.
IMPASSABLE = 65_535

# How far the transport file's own distances may sit from this project's before the pair is
# worth reporting. Both measure the same borders over the same network; where they disagree it
# is because the two were built from OSM extracts downloaded days apart.
DISTANCE_TOLERANCE_M = 25.0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    report = Report()

    meta_path = TRANSPORT / "road-time.json"
    bin_path = TRANSPORT / "road-time.bin"
    for path in (meta_path, bin_path):
        if not path.exists():
            raise SystemExit(f"Missing {path} — the transport simulator builds this")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    n = int(meta["edgeCount"])

    raw = np.fromfile(bin_path, dtype=np.uint8)
    their_a = np.frombuffer(raw, dtype=np.uint16, count=n, offset=0)
    their_b = np.frombuffer(raw, dtype=np.uint16, count=n, offset=2 * n)
    their_seconds = np.frombuffer(raw, dtype=np.float32, count=n, offset=4 * n)
    their_metres = np.frombuffer(raw, dtype=np.float32, count=n, offset=8 * n)

    adjacency_path = WEB_DATA_DIR / "adjacency.bin"
    if not adjacency_path.exists():
        raise SystemExit(f"Missing {adjacency_path}. Run: uv run python -m pipeline.export")
    ours = adjacency_path.read_bytes()
    our_a = np.frombuffer(ours, dtype=np.uint16, count=n, offset=0)
    our_b = np.frombuffer(ours, dtype=np.uint16, count=n, offset=2 * n)
    our_metres = np.frombuffer(ours, dtype=np.float32, count=n, offset=4 * n)

    by_pair = {
        (min(a, b), max(a, b)): (s, m)
        for a, b, s, m in zip(
            their_a.tolist(),
            their_b.tolist(),
            their_seconds.tolist(),
            their_metres.tolist(),
            strict=True,
        )
    }

    seconds = np.full(n, IMPASSABLE, dtype=np.uint16)
    missing = 0
    impassable = 0
    drift: list[float] = []

    for i, (a, b, m) in enumerate(
        zip(our_a.tolist(), our_b.tolist(), our_metres.tolist(), strict=True)
    ):
        found = by_pair.get((min(a, b), max(a, b)))
        if found is None:
            missing += 1
            continue
        s, tm = found
        if not np.isfinite(s) or s <= 0:
            impassable += 1
            continue
        seconds[i] = min(int(round(s)), IMPASSABLE - 1)
        if np.isfinite(m) and m > 0 and np.isfinite(tm) and tm > 0:
            drift.append(abs(tm - m))

    report.add(
        Check(
            "edges_matched",
            missing == 0,
            f"every one of {n:,} edges found a travel time"
            if missing == 0
            else f"{missing:,} of {n:,} edges had no counterpart in the transport payload",
            fatal=missing > 0,
        )
    )

    d = np.array(drift) if drift else np.zeros(1)
    close = float((d < DISTANCE_TOLERANCE_M).mean())
    report.add(
        Check(
            "distance_agreement",
            close > 0.95,
            f"{100 * close:.1f}% of edges agree on distance to within "
            f"{DISTANCE_TOLERANCE_M:.0f} m (max {d.max():,.0f} m) — the two payloads were built "
            "from OSM extracts downloaded days apart, and this is the size of that gap",
            fatal=close <= 0.90,
        )
    )

    usable = seconds[seconds != IMPASSABLE]
    kmh = (our_metres[seconds != IMPASSABLE] / 1000) / (usable / 3600)
    kmh = kmh[np.isfinite(kmh) & (kmh > 0)]
    report.add(
        Check(
            "implied_speed",
            5 < float(np.median(kmh)) < 120,
            f"implied speed: median {np.median(kmh):.1f} km/h, "
            f"p5 {np.percentile(kmh, 5):.1f}, p95 {np.percentile(kmh, 95):.1f} — county and "
            "communal roads, so a median near 50 is the expected shape",
            fatal=False,
        )
    )
    report.add(
        Check(
            "impassable",
            True,
            f"{impassable:,} edges have no drivable route and are marked impassable",
        )
    )

    out = WEB_DATA_DIR / "edge-time.bin"
    out.write_bytes(seconds.tobytes())
    report.add(
        Check(
            "payload",
            out.stat().st_size < 64_000,
            f"edge-time.bin is {out.stat().st_size / 1024:,.0f} KB",
        )
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_report(report, REPORTS_DIR / "edge_time.md", REPORTS_DIR / "edge_time.json")
    print(f"\nWrote {out} ({out.stat().st_size / 1024:,.0f} KB)")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())

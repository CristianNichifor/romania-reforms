"""Fill `sources/reference-drive-times-vl.csv` from a public routing service.

The reference file shipped unfilled on purpose, with an instruction not to estimate: a guessed
time makes `check_gate.py` pass while verifying nothing. This fills it from OSRM's public
demo server, which is what the file asks for — "a real recorded driving time between the two
commune seats and the service it came from".

**What this cross-check is worth, precisely.** OSRM and `speeds.py` both start from OpenStreetMap,
so this is not an independent measurement of Romanian roads and must never be described as one.
What differs is everything after the base data: OSRM applies its own car profile, its own speed
defaults where `maxspeed` is absent, its own turn and traffic-signal penalties, and its own
routing; `speeds.py` derives a per-class speed from the measured `maxspeed` distribution, the
locality share, and computed braking kinematics, then routes over administrativ's UAT graph.
Agreement means two unrelated implementations of "how fast is a Romanian road" over the same
tags land in the same place. Disagreement localises to a specific class or to the accumulation.

That is a weaker claim than the bus observations in `data/observed-journeys.json`, which are
recorded from published timetables and owe nothing to OSM. It is also the only check that can
reach the part those cannot: the road layer on its own, before dwell and the service factor.

Usage:
    uv run python -m scripts.fill_reference_drives          # writes the CSV
    uv run python -m scripts.fill_reference_drives --dry    # prints, writes nothing
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.request
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
REFERENCE = ROOT / "sources" / "reference-drive-times-vl.csv"
SEATS = ADMINISTRATIV / "data" / "processed" / "uat_seats.gpkg"

OSRM: Final[str] = "https://router.project-osrm.org/route/v1/driving"
SERVICE: Final[str] = "OSRM demo router.project-osrm.org profil car"
# The public demo asks for light use. Twelve requests, spaced.
PAUSE_S: Final[float] = 1.5


def seat_coordinates() -> dict[int, tuple[float, float]]:
    """Seat lon/lat by SIRUTA. The file is Stereo70; OSRM speaks WGS84."""
    import geopandas as gpd

    seats = gpd.read_file(SEATS).to_crs(4326)
    return {int(row.siruta): (row.geometry.x, row.geometry.y) for row in seats.itertuples()}


def drive_minutes(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    """One routed car journey, in minutes."""
    url = (
        f"{OSRM}/{origin[0]:.6f},{origin[1]:.6f};"
        f"{destination[0]:.6f},{destination[1]:.6f}?overview=false"
    )
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        payload = json.loads(response.read())
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RuntimeError(f"OSRM refused {url}: {payload.get('code')}")
    return payload["routes"][0]["duration"] / 60.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true", help="print without writing")
    args = parser.parse_args(argv)

    raw = REFERENCE.read_text(encoding="utf-8").splitlines()
    coordinates = seat_coordinates()
    today = time.strftime("%Y-%m-%d")

    out: list[str] = []
    filled = 0
    for line in raw:
        if line.startswith("#") or line.startswith("kind,") or not line.strip():
            out.append(line)
            continue
        row = next(csv.reader([line]))
        kind, from_siruta, to_siruta, from_name, to_name = row[:5]
        origin, destination = coordinates[int(from_siruta)], coordinates[int(to_siruta)]
        minutes = drive_minutes(origin, destination)
        filled += 1
        print(f"  {kind:8} {from_name:16} -> {to_name:14} {minutes:6.1f} min")
        # csv.writer rather than an f-string: the source and the place names are free text,
        # and a comma inside one of them silently shifts every field after it. The gate would
        # still have read the minutes correctly, which is exactly why it would go unnoticed.
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="").writerow(
            [kind, from_siruta, to_siruta, from_name, to_name, f"{minutes:.1f}", SERVICE, today]
        )
        out.append(buffer.getvalue())
        time.sleep(PAUSE_S)

    if args.dry:
        print(f"\n{filled} drives; nothing written (--dry)")
        return 0

    REFERENCE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nWrote {filled} recorded drives to {REFERENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

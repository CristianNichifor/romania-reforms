"""What the routed network costs in vehicles, hours and kilometres.

The resource vector, not lei. Converting it to money is `L2`, and keeping the two apart is
deliberate: a reader disputing the service standard argues with `tiers.py`, one disputing the
vehicle arithmetic argues with `fleet.py`, and one disputing the price of a driver-hour will
argue with `L2` — none of them has to accept the others to make their case.

**It reports against the upper bound on purpose.** `L1a` costed one shuttle per UAT, before
any routes existed. If the routed network is not materially cheaper than that, the route rule
is not merging and something is wrong — so the comparison is the evidence that this layer did
its job, and it is printed every run rather than checked once.

One bus serves a whole branch, so a route takes the service class of the **largest** UAT it
serves. Taking the smallest would run a 20-seat minibus past a town of 8 000.

Usage:
    uv run python -m scripts.cost_network
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"

from scripts.fleet import Resources, fleet_required, resources_for_route  # noqa: E402
from scripts.tiers import DAY_PROFILE, classify, service_for  # noqa: E402

LAYOVER_MIN: Final[float] = 10.0
SPARE_RATIO: Final[float] = 0.15

# What `L1a` costed before routes existed: every UAT its own shuttle to its hub. The ceiling
# this layer must come in under.
UPPER_BOUND: Final[dict[str, float]] = {
    "peak_vehicles": 3_914,
    "fleet": 4_502,
    "bus_hours": 19_564.0,
    "bus_km": 983_633.0,
}


def cost(routes: list[dict], population: dict[str, int]) -> tuple[Resources, int]:
    """Sum the network. Returns the totals and how many routes had no measured length."""
    total = Resources(0, 0.0, 0.0, 0.0)
    unmeasured = 0
    for route in routes:
        if route["oneWayKm"] is None:
            unmeasured += 1
            continue
        largest = max((int(population[s]) for s in route["serves"]), default=0)
        service = service_for(classify(largest, is_hub=False))
        total = total + resources_for_route(
            round_trip_min=2 * route["oneWayMin"],
            layover_min=LAYOVER_MIN,
            departures=service.departures,
            period_hours=DAY_PROFILE,
            km_round_trip=2 * route["oneWayKm"],
        )
    return total, unmeasured


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd

    network_file = ROOT / "data" / "network.json"
    if not network_file.exists():
        raise SystemExit(f"Missing {network_file}. Run: uv run python -m scripts.build_network")

    network = json.loads(network_file.read_text(encoding="utf-8"))
    uats = gpd.read_file(ADMINISTRATIV / "data/processed/uat_geometry.gpkg", layer="uat")
    population = dict(zip(uats.siruta, uats.population, strict=True))

    total, unmeasured = cost(network["routes"], population)
    fleet = fleet_required(total.peak_vehicles, SPARE_RATIO)

    print(
        f"Costed {len(network['routes']) - unmeasured:,} routes"
        f"{f' ({unmeasured} without a measured length)' if unmeasured else ''}\n"
    )
    print(f"{'':24}{'one shuttle per UAT':>20}{'routed network':>17}{'':>8}")
    for label, key, got in (
        ("peak vehicles", "peak_vehicles", total.peak_vehicles),
        (f"fleet incl. {SPARE_RATIO:.0%} spare", "fleet", fleet),
        ("bus-hours / weekday", "bus_hours", total.bus_hours),
        ("bus-km / weekday", "bus_km", total.bus_km),
    ):
        bound = UPPER_BOUND[key]
        print(f"{label:24}{bound:>20,.0f}{got:>17,.0f}{(got / bound - 1) * 100:>7.0f}%")

    print(
        f"\nannualised over 250 weekdays: {total.bus_hours * 250:,.0f} bus-hours, "
        f"{total.bus_km * 250 / 1e6:,.1f} M bus-km"
    )
    print(f"fleet per daily bus-hour: {fleet / total.bus_hours:.2f}")

    if total.peak_vehicles >= UPPER_BOUND["peak_vehicles"]:
        print(
            "\nFATAL: the routed network is no cheaper than one bus per UAT — "
            "the route rule is not merging",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

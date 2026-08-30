"""Turn the network's cost into a subsidy, and check the result against Danish practice.

Output:
    data/fares.json

Usage:
    uv run python -m scripts.build_fares
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.costs import WEEKDAYS_PER_YEAR
from scripts.fares import FARE_INPUTS, farebox, load_fare_prices, sensitivity

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fares.json"
COST = ROOT / "data" / "cost.json"
ACCESS = ROOT / "data" / "access.json"


def main() -> int:
    inputs = json.loads(FARE_INPUTS.read_text(encoding="utf-8"))
    cost = json.loads(COST.read_text(encoding="utf-8"))
    access = json.loads(ACCESS.read_text(encoding="utf-8"))["summary"]

    prices = load_fare_prices()
    bus_km = cost["perWeekday"]["busKm"] * WEEKDAYS_PER_YEAR
    operating = cost["annualRon"]["operating"]
    total = cost["annualRon"]["total"]

    central = farebox(bus_km, operating, prices)
    band = sensitivity(bus_km, operating, prices)
    movia = inputs["benchmarks"]["moviaFareboxRecovery"]["value"]
    people = access["people"]

    document = {
        "$schema": "../schema/fares.schema.json",
        "id": "fares",
        "title": "Din bilete și din buget: cât rămâne de acoperit public",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": inputs["provenance"],
        "assumptions": {
            "farePerPassengerKm": prices.fare_per_passenger_km,
            "loadFactor": prices.load_factor,
            "meanSeats": prices.mean_seats,
            "busKmPerYear": round(bus_km),
        },
        "central": {
            "passengerKm": round(central.passenger_km),
            "revenueRon": round(central.revenue_ron),
            "operatingRon": round(operating),
            "totalRon": round(total),
            "subsidyRon": round(central.subsidy_ron),
            "recovery": round(central.recovery, 3),
            "subsidyPerPersonYearRon": round(central.subsidy_ron / people, 2),
            "passengerKmPerPersonYear": round(central.passenger_km / people, 1),
        },
        "band": [
            {
                "loadFactor": row["loadFactor"],
                "revenueRon": round(row["revenueRon"]),
                "subsidyRon": round(row["subsidyRon"]),
                "recovery": round(row["recovery"], 3),
            }
            for row in band
        ],
        "benchmark": {
            "moviaRecovery": movia,
            "modelRecovery": round(central.recovery, 3),
            # An agreement, not a fit: the fare comes from Romanian county decisions and the
            # load factor from a literature range, both chosen before this ratio was computed.
            # It is still only as good as the load factor, which is why the band ships too.
            "withinBand": bool(band[0]["recovery"] <= movia <= band[-1]["recovery"]),
        },
        "limitations": inputs["limitations"],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"  fare {prices.fare_per_passenger_km:.2f} lei/passenger-km, {prices.mean_seats:.0f} seats"
    )
    print(f"  bus-km/year {bus_km / 1e6:,.1f} M   operating {operating / 1e9:,.2f} md lei\n")
    print(f"  {'load':>6}  {'passenger-km':>14}  {'revenue':>12}  {'subsidy':>12}  recovery")
    for row in band:
        print(
            f"  {row['loadFactor']:>5.0%}  {row['passengerKm'] / 1e9:>11,.2f} md  "
            f"{row['revenueRon'] / 1e9:>9,.2f} md  {row['subsidyRon'] / 1e9:>9,.2f} md  "
            f"{row['recovery']:>7.0%}"
        )
    print(
        f"\n  central {prices.load_factor:.0%}: recovery {central.recovery:.0%}, "
        f"subsidy {central.subsidy_ron / 1e9:,.2f} md lei "
        f"({central.subsidy_ron / people:,.0f} lei per person per year)"
    )
    verdict = "inside" if document["benchmark"]["withinBand"] else "OUTSIDE"
    print(f"  Movia benchmark {movia:.0%} — model {verdict} the band")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""What rail service costs, and what a minute of journey time costs to buy.

This is the file that answers §8 of the design document. The claim there is that the cheapest
new transit capacity in Romania may be track already lying in the ground. That is testable
only against an alternative, and the alternative this repository already has on the shelf is
not more buses — it is **coordinating the buses that already run**.

Output:
    data/rail-cost.json

Usage:
    uv run python -m scripts.build_rail_cost
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.rail_costs import (
    RAIL_COST_INPUTS,
    annual_rail_cost,
    cost_per_passenger_hour_saved,
    line_class,
    load_rail_prices,
)
from scripts.rail_speeds import class_commercial_kmh

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "rail-cost.json"
ACCESS = ROOT / "data" / "access.json"

# A representative regional line and service. Not a real corridor — a unit of comparison, so
# the per-passenger-hour figure is not hostage to which line anyone picked.
REFERENCE_LINE_KM = 100.0
REFERENCE_TRAINS_PER_WEEKDAY = 20

# Seats occupied on an average regional working. Assumed, and the single most influential
# number here: halve it and the cost per passenger-hour doubles.
REFERENCE_LOAD = 96

# Trips per person per year the comparison credits to the bus network. Deliberately one — a
# single journey each, which nobody would call an overestimate. The comparison it feeds is a
# floor, and it is already decisive.
TRIPS_PER_PERSON_YEAR = 1


def main() -> int:
    prices = load_rail_prices()
    access = json.loads(ACCESS.read_text(encoding="utf-8"))["summary"]

    slow = class_commercial_kmh("as_is")
    fast = class_commercial_kmh("rehabilitated")

    saved = cost_per_passenger_hour_saved(
        REFERENCE_LINE_KM, REFERENCE_TRAINS_PER_WEEKDAY, REFERENCE_LOAD, prices
    )

    # A year of running the reference service, before any renewal, so the operating side is
    # visible next to the capital side rather than buried in it.
    train_km = REFERENCE_LINE_KM * REFERENCE_TRAINS_PER_WEEKDAY
    train_hours = train_km / slow
    units = 6
    running = annual_rail_cost(train_km, train_hours, units, prices, slow)

    # The bus network's own cheapest minute: pulsing the timetable. Same buses, same
    # kilometres, same drivers — only the departure times move.
    pulse_saving_min = access["medianUncoordinatedMin"] - access["medianPulsedMin"]
    people = access["people"]
    pulse_hours = people * TRIPS_PER_PERSON_YEAR * pulse_saving_min / 60
    equivalent_rail_ron = pulse_hours * saved["ronPerPassengerHour"]

    document = {
        "$schema": "../schema/rail-cost.schema.json",
        "id": "rail-cost",
        "title": "Costul serviciului feroviar și prețul unui minut de călătorie",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": json.loads(RAIL_COST_INPUTS.read_text(encoding="utf-8"))["provenance"],
        "rates": {
            "tuiByClass": {k: round(v, 3) for k, v in prices.tui_by_class.items()},
            "crewRonPerTrainHour": round(prices.per_train_hour, 2),
            "energyRonPerTrainKm": round(prices.energy_per_km, 3),
            "unitPriceRon": prices.unit_price,
            "seats": prices.seats,
        },
        "reference": {
            "lineKm": REFERENCE_LINE_KM,
            "trainsPerWeekday": REFERENCE_TRAINS_PER_WEEKDAY,
            "passengersPerTrain": REFERENCE_LOAD,
            "units": units,
            "asIsKmh": round(slow, 1),
            "rehabilitatedKmh": round(fast, 1),
            "asIsLineClass": line_class(slow),
            "rehabilitatedLineClass": line_class(fast),
            "operatingRon": round(running.operating_ron),
            "capitalRon": round(running.capital_ron),
            "crewRon": round(running.crew_ron),
            "accessRon": round(running.access_ron),
            "energyRon": round(running.energy_ron),
        },
        "rehabilitation": {
            "ronPerKm": prices.rehabilitation_per_km,
            "hoursSavedPerTrip": round(saved["hoursSavedPerTrip"], 3),
            "passengerHoursPerYear": round(saved["passengerHoursPerYear"]),
            "annualCapitalRon": round(saved["annualCapitalRon"]),
            "extraAccessRon": round(saved["extraAccessRon"]),
            "ronPerPassengerHour": round(saved["ronPerPassengerHour"], 1),
        },
        "againstPulsing": {
            "pulseSavingMin": round(pulse_saving_min, 1),
            "peopleServed": people,
            "tripsPerPersonYear": TRIPS_PER_PERSON_YEAR,
            "passengerHoursPerYear": round(pulse_hours),
            "equivalentRailSpendRon": round(equivalent_rail_ron),
            "pulseCapitalRon": 0,
        },
        "limitations": [
            *json.loads(RAIL_COST_INPUTS.read_text(encoding="utf-8"))["limitations"],
            {
                "id": "compara-preturi-unitare-nu-aceiasi-calatori",
                "text": (
                    "Comparația este între prețuri unitare, nu între două feluri de a servi "
                    "aceiași oameni. Reabilitarea unei linii scurtează drumul călătorilor din "
                    "tren; corespondența scurtează drumul celor din autobuz. Sunt persoane "
                    "diferite pe rute diferite, iar cifra comună — leul pe oră de călător "
                    "economisită — spune cât costă un minut cumpărat în fiecare mod, nu că unul "
                    "l-ar putea înlocui pe celălalt. Concluzia care rezistă este despre ordinea "
                    "cheltuielilor: măsura organizatorică se face prima pentru că este aproape "
                    "gratuită, nu pentru că reabilitarea ar fi inutilă."
                ),
                "severity": "material",
                "affects": ["rail-cost"],
            },
            {
                "id": "incarcarea-decide-rezultatul",
                "text": (
                    f"Rezultatul depinde direct de câți oameni sunt în tren. La {REFERENCE_LOAD} "
                    f"de călători pe ramă ora de călător costă "
                    f"{saved['ronPerPassengerHour']:,.0f} de lei; la jumătate din "
                    "încărcare costă dublu. Nu există model de cerere în acest depozit, deci "
                    "încărcarea este presupusă, iar ea este singurul număr care poate răsturna "
                    "ordinul de mărime."
                ),
                "severity": "blocking",
                "affects": ["rail-cost"],
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    per_hour = saved["ronPerPassengerHour"]
    print(f"  TUI lei/train-km  {document['rates']['tuiByClass']}")
    print(f"  crew {prices.per_train_hour:,.2f} lei/train-hour")
    print(f"  energy {prices.energy_per_km:.2f} lei/train-km")
    print()
    print(f"  reference {REFERENCE_LINE_KM:.0f} km, {REFERENCE_TRAINS_PER_WEEKDAY} trains/weekday")
    print(f"    as is          {slow:5.1f} km/h   line class {line_class(slow)}")
    print(f"    rehabilitated  {fast:5.1f} km/h   line class {line_class(fast)}")
    print(f"    operating      {running.operating_ron / 1e6:8,.1f} m lei/yr")
    print(f"    rolling stock  {running.capital_ron / 1e6:8,.1f} m lei/yr")
    print()
    print(f"  rehabilitation buys a passenger-hour for {per_hour:,.0f} lei")
    print(f"  pulsing the buses saves {pulse_saving_min:.0f} min per journey for nothing")
    print(f"  buying the same {pulse_hours / 1e6:,.1f} m passenger-hours by rehabilitation:")
    print(f"    {equivalent_rail_ron / 1e9:,.2f} md lei/yr")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

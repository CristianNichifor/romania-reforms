"""What the network costs a year, beside what the consolidation claims to save.

This is the page the whole simulator was built to produce. Consolidation is argued as an
administrative saving; to the person who has to reach the centre it is a journey, and the
journey has a price. Both numbers come from the same scenario and sit in one document, so
neither can be quoted without the other.

**It is a cost, not a subsidy.** No demand model exists in this repository and no fare revenue
is estimated, so what comes out is what running the service costs — not what a public budget
would still owe after tickets. The two differ by however much fare revenue there would be, and
that is not a small or knowable difference.

**Spares are applied once per vehicle class, not per route.** A workshop float covers many
routes but a minibus spare cannot substitute for a coach, so the ratio lands on each class's
peak rather than on each route's. Applying it per route bought a spare for every single-bus
service and produced 6 809 vehicles where 4 502 were asked for.

Output:
    data/cost.json

Usage:
    uv run python -m scripts.build_cost
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
ADMINISTRATIV = ROOT.parent / "administrativ"
OUT = ROOT / "data" / "cost.json"

from scripts.costs import WEEKDAYS_PER_YEAR, annual_cost, load_prices  # noqa: E402
from scripts.fleet import resources_for_route  # noqa: E402
from scripts.tiers import DAY_PROFILE, classify, service_for  # noqa: E402

LAYOVER_MIN: Final[float] = 10.0
SPARE_RATIO: Final[float] = 0.15


def class_of(route: dict, population: dict[str, int]) -> str:
    """Which vehicle a route runs.

    A trunk route connects centres and is trunk class by definition. A feeder takes the class
    of the **largest** UAT on its branch: one bus serves the whole branch, and sizing it to the
    smallest would run a 20-seat minibus past a town of 8 000.
    """
    if route["tier"] == "T2":
        return "trunk"
    largest = max((int(population[s]) for s in route["serves"]), default=0)
    return classify(largest, is_hub=False)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    import geopandas as gpd

    network_file = ROOT / "data" / "network.json"
    hubs_file = ROOT / "data" / "hubs.json"
    for path, how in (
        (network_file, "uv run python -m scripts.build_network"),
        (hubs_file, "uv run python -m scripts.export_hubs"),
    ):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run: {how}")

    network = json.loads(network_file.read_text(encoding="utf-8"))
    hubs = json.loads(hubs_file.read_text(encoding="utf-8"))
    prices = load_prices()
    items = json.loads((ROOT / "data" / "cost-inputs.json").read_text(encoding="utf-8"))["items"]
    dwell_per_stop = items["dwellMinPerStop"]["value"]
    service_factor = items["serviceSpeedFactor"]["value"]

    uats = gpd.read_file(ADMINISTRATIV / "data/processed/uat_geometry.gpkg", layer="uat")
    population = dict(zip(uats.siruta, uats.population, strict=True))

    hours = 0.0
    km_by_class: dict[str, float] = collections.defaultdict(float)
    peak_by_class: dict[str, int] = collections.defaultdict(int)
    unmeasured = 0

    for route in network["routes"]:
        if route["oneWayKm"] is None:
            unmeasured += 1
            continue
        name = class_of(route, population)
        service = service_for(name)
        # A bus stops in every locality on its branch; a car does not. Dwell goes into the
        # cycle rather than into the cost, because standing at a stop lengthens the round trip
        # and can therefore buy a vehicle as well as a driver-hour.
        dwell = len(route["stops"]) * dwell_per_stop
        # Free-flow road time is not service time. The road model gives a car an unobstructed
        # run; a scheduled bus loses a quarter of that to junctions, to the padding a
        # timetable needs to be keepable, and to being a heavy vehicle on a communal road.
        # Stops are *not* in this factor — standing is `dwell`, and braking away from a stop
        # was measured against the kinematics in speeds.py at 14,5 s, which over a median
        # three stops is 3% and nowhere near the gap.
        running_min = 2 * route["oneWayMin"] / service_factor
        resources = resources_for_route(
            round_trip_min=running_min + dwell,
            layover_min=LAYOVER_MIN,
            departures=service.departures,
            period_hours=DAY_PROFILE,
            km_round_trip=2 * route["oneWayKm"],
        )
        hours += resources.bus_hours
        km_by_class[name] += resources.bus_km
        peak_by_class[name] += resources.peak_vehicles

    fleet_by_class = {
        name: math.ceil(peak * (1 + SPARE_RATIO)) for name, peak in peak_by_class.items()
    }
    cost = annual_cost(hours, dict(km_by_class), fleet_by_class, prices)

    saving_admin = hubs["savingsRon"]["administrative"]
    saving_operating = hubs["savingsRon"]["operating"]

    document = {
        "$schema": "../schema/cost.schema.json",
        "id": "cost",
        "title": "Costul anual al rețelei, față de economia pe care o revendică comasarea",
        "publisher": "Cristian Nichifor",
        "period": "2026",
        "provenance": {
            "source": "retea-plus-preturi-unitare",
            "locator": (
                "orele și kilometrii din data/network.json, prețurile unitare din "
                "data/cost-inputs.json, economiile din data/hubs.json"
            ),
            "confidence": "derived",
            "note": (
                "Derivat dintr-un lanț în care nimic nu este verificat pe teren: vitezele "
                "sunt modelate, prețurile unitare sunt estimate, iar economiile vin de la "
                "simulatorul administrativ cu limitările lui."
            ),
        },
        "perWeekday": {
            "busHours": round(hours, 1),
            "busKm": round(sum(km_by_class.values()), 1),
            "kmPerBusHour": round(sum(km_by_class.values()) / hours, 1),
            "routesCosted": len(network["routes"]) - unmeasured,
            "routesWithoutLength": unmeasured,
        },
        "fleet": {
            "byClass": fleet_by_class,
            "peakByClass": dict(peak_by_class),
            "total": sum(fleet_by_class.values()),
            "spareRatio": SPARE_RATIO,
        },
        "annualRon": {
            "driver": round(cost.driver_ron),
            "running": round(cost.running_ron),
            "standing": round(cost.standing_ron),
            "admin": round(cost.admin_ron),
            "operating": round(cost.operating_ron),
            "capital": round(cost.capital_ron),
            "total": round(cost.total_ron),
        },
        "ledgerRon": {
            "transportCost": round(cost.total_ron),
            "administrativeSaving": saving_admin,
            "operatingSaving": saving_operating,
            "netAgainstAdministrativeSaving": round(saving_admin - cost.total_ron),
        },
        "limitations": [
            {
                "id": "cost-nu-subventie",
                "text": (
                    "Este costul serviciului, nu subvenția. Nu există model de cerere și "
                    "niciun venit din bilete în acest depozit, deci diferența dintre cifra "
                    "de aici și ce ar rămâne de acoperit din buget public nu este cunoscută."
                ),
                "severity": "blocking",
                "affects": ["cost"],
            },
            {
                "id": "preturile-nu-sunt-citate",
                "text": (
                    "Niciun preț unitar din data/cost-inputs.json nu provine dintr-o sursă "
                    "publică citată. Sunt estimări de lucru și costul total le moștenește "
                    "incertitudinea în întregime."
                ),
                "severity": "blocking",
                "affects": ["cost"],
            },
            {
                "id": "vitezele-nu-sunt-verificate",
                "text": (
                    "Orele de autobuz vin din timpi de parcurs modelați, niciodată comparați "
                    "cu o călătorie reală. O eroare sistematică de viteză se transmite direct "
                    "în ore și în costul șoferilor, care este cea mai mare poziție."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "factorul-de-viteza-de-serviciu",
                "text": (
                    "Timpii de drum liber sunt împărțiți la un factor de 0,75 ca să devină "
                    "timpi de serviciu — intersecții, marja pusă în orar ca traseul să poată "
                    "fi respectat, conducerea unui vehicul greu. Factorul este presupus, "
                    "calibrat astfel încât viteza comercială să cadă în intervalul observat "
                    "de 25-40 km/h, și este presupunerea cu cea mai mare influență asupra "
                    "orelor. Opririle nu sunt în el: staționarea se socotește separat, iar "
                    "frânarea și repornirea din stație au fost măsurate și fac 3%."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "cost-pe-km-sub-referinta-ajustata",
                "text": (
                    "Costul de funcționare iese 5,7 lei pe kilometru, față de circa 8,8 lei "
                    "cât ar fi o operare rurală vest-europeană cu partea de salarii ajustată "
                    "la nivelul românesc. Ponderea șoferilor, ajustată la fel, se potrivește "
                    "— 27% față de 22% așteptat — deci diferența stă în costurile care nu "
                    "depind de salarii. Este întrebarea deschisă a acestui nivel."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "economiile-sunt-ale-altui-simulator",
                "text": (
                    "Economiile administrative și de funcționare sunt calculate de "
                    "simulatorul administrativ, preluate ca atare, cu limitările lui. "
                    "Comparația are sens doar în cadrul aceluiași scenariu de comasare."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def bn(value: float) -> str:
        return f"{value / 1e9:,.2f} mld"

    a = document["annualRon"]
    print(f"Per weekday: {hours:,.0f} bus-hours, {sum(km_by_class.values()):,.0f} bus-km")
    print(f"Fleet: {sum(fleet_by_class.values()):,} vehicles {dict(fleet_by_class)}\n")
    print("Annual cost, RON:")
    for label, key in (
        ("  drivers", "driver"),
        ("  fuel, tyres, maintenance", "running"),
        ("  insurance and depot", "standing"),
        ("  administration", "admin"),
        ("  = operating", "operating"),
        ("  capital (fleet, annualised)", "capital"),
        ("  = total", "total"),
    ):
        print(f"{label:32}{a[key]:>16,}   {bn(a[key])}")
    print("\nAgainst the same consolidation scenario:")
    print(f"{'  administrative saving':32}{saving_admin:>16,}   {bn(saving_admin)}")
    print(f"{'  operating saving':32}{saving_operating:>16,}   {bn(saving_operating)}")
    print(f"\n  transport costs {a['total'] / saving_admin:.1f}x the administrative saving")

    # Two checks against how bus operations are known to behave. Neither is fatal: they are
    # printed so that a number outside its band is argued with rather than quoted. Tuning the
    # inputs until these land inside would be fitting the model to a prior, which is the
    # failure the whole repository is built to avoid.
    driver_share = cost.driver_ron / cost.operating_ron
    ron_per_km = cost.operating_ron / (sum(km_by_class.values()) * WEEKDAYS_PER_YEAR)
    speed = sum(km_by_class.values()) / hours

    # The benchmarks have to be wage-adjusted or they are answers about a different country.
    # A western rural operation runs near 2,5 EUR/km at roughly 45% driver — but its drivers
    # cost about 32 EUR/hour against ours at 11,3. Scaling only the driver half by that ratio
    # gives what Romania should look like, and it moves the expected driver share from 45% to
    # about 22%. An earlier version of this check used the unadjusted western figures and
    # reported the model as wrong when it was the benchmark that was.
    ron_per_eur = 4.97
    western_per_km_eur, western_driver_share, western_driver_eur_h = 2.5, 0.45, 32.0
    wage_ratio = (prices.per_bus_hour / ron_per_eur) / western_driver_eur_h
    scaled_driver = western_per_km_eur * western_driver_share * wage_ratio
    other = western_per_km_eur * (1 - western_driver_share)
    expect_share = scaled_driver / (scaled_driver + other)
    expect_per_km = (scaled_driver + other) * ron_per_eur

    print("\nSanity, against bus operations wage-adjusted to Romanian pay:")
    print(
        f"  driver cost                {prices.per_bus_hour:>6.1f} RON/bus-hour"
        f" = {prices.per_bus_hour / ron_per_eur:.1f} EUR/h, {wage_ratio:.0%} of western"
    )
    print(
        f"  driver share of operating  {driver_share:>6.0%}   expect ~{expect_share:.0%}   "
        f"{'ok' if abs(driver_share - expect_share) < 0.12 else 'OUTSIDE'}"
    )
    print(
        f"  operating cost per bus-km  {ron_per_km:>6.2f}   expect ~{expect_per_km:.1f} RON  "
        f"{'ok' if ron_per_km >= expect_per_km * 0.75 else 'LOW — the open question'}"
    )
    # The benchmark that judges the total rather than a line — but it converts only with a
    # fleet composition, and that is the trap. ANRSC divides cost per vehicle-km by the
    # operator's average SEATS, and cost per vehicle-km does *not* scale with seats: a
    # 40-seater does not cost twice a 20-seater. So lei/km/loc does not normalise across
    # fleets, and comparing ours (41 seats) against Buzau's (unknown, but county programmes
    # specify capacities in the 20s) reads as a factor-of-two error when there may be none.
    #
    # An earlier version of this check did exactly that and reported the model 2,3x low. The
    # band is printed instead, because the honest answer is a range and the width of it is
    # the missing fact.
    seats = {"basic": 20, "feeder": 40, "trunk": 50}
    mean_seats = sum(seats[c] * n for c, n in fleet_by_class.items()) / sum(fleet_by_class.values())
    benchmark = json.loads((ROOT / "data" / "cost-inputs.json").read_text(encoding="utf-8"))[
        "benchmarks"
    ]["buzauTariffLeiKmLoc"]["value"]
    print(f"\n  against Buzau 2025 ({benchmark:.2f} lei/km/loc), by their fleet's mean seats:")
    for their_seats in (20, 23, 30, mean_seats):
        implied = benchmark * their_seats
        label = "= ours" if abs(their_seats - mean_seats) < 0.5 else ""
        print(
            f"    {their_seats:>5.0f} seats {label:<7} -> {implied:>6.2f} lei/km   "
            f"we are {ron_per_km / implied:.2f}x"
        )
    print("    county programmes specify capacities in the 20s, so nearer the top of that")

    print(
        f"  commercial speed           {speed:>6.1f}   expect 25-40 km/h  "
        f"{'ok' if 25 <= speed <= 40 else 'OUTSIDE'}"
    )

    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

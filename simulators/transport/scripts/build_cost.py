"""What the network costs a year, beside what the consolidation claims to save.

This is the page the whole simulator was built to produce. Consolidation is argued as an
administrative saving; to the person who has to reach the centre it is a journey, and the
journey has a price. Both numbers come from the same scenario and sit in one document, so
neither can be quoted without the other.

**It is a cost, not a subsidy.** What comes out here is what running the service costs, not
what a public budget would still owe after tickets. That second figure exists — `build_fares.py`
puts county-council fares over a population-extrapolated demand and lands near 46% farebox
recovery — but it lives one layer downstream on purpose, because what a bus costs to run does
not depend on what is charged to sit in it. Quoting this file's total as a subsidy overstates
it by the fare revenue.

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

from scripts.authority import authority_cost, share_of_operator_cost  # noqa: E402
from scripts.costs import WEEKDAYS_PER_YEAR, annual_cost, load_prices  # noqa: E402
from scripts.fleet import drivers_required, paid_driver_hours, resources_for_route  # noqa: E402
from scripts.tiers import DAY_PROFILE, classify, duty_span_hours, service_for  # noqa: E402

LAYOVER_MIN: Final[float] = 10.0
SPARE_RATIO: Final[float] = 0.15

OBSERVED = ROOT / "data" / "observed-journeys.json"


def observed_speeds() -> dict:
    """The measured commercial-speed distribution from `data/observed-journeys.json`.

    This is the one check in this file that compares the model against a recorded Romanian
    journey rather than against a western benchmark scaled to Romanian wages. It is also the
    check most easily corrupted: the temptation is to move `serviceSpeedFactor` until the gap
    closes, which would convert the only independent test in the repository into a fit. The
    factor stays where it was set before these observations existed.
    """
    return json.loads(OBSERVED.read_text(encoding="utf-8"))["summary"]


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
    paid_hours = 0.0
    duties = 0
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

        # Drivers are staffed against the vehicle's DAY, not its driving. A route on the peaks
        # spans twelve hours to move for three, and someone has to be there for the span.
        vehicles = max(1, resources.peak_vehicles)
        per_vehicle_hours, per_vehicle_duties = paid_driver_hours(
            resources.bus_hours / vehicles,
            duty_span_hours(service.departures),
            items["platformToPaidRatio"]["value"],
            items["maxDutySpanHours"]["value"],
            items["minimumPaidShiftHours"]["value"],
            items["maxDrivingHoursDay"]["value"],
        )
        paid_hours += per_vehicle_hours * vehicles
        duties += per_vehicle_duties * vehicles
        km_by_class[name] += resources.bus_km
        peak_by_class[name] += resources.peak_vehicles

    fleet_by_class = {
        name: math.ceil(peak * (1 + SPARE_RATIO)) for name, peak in peak_by_class.items()
    }
    # The authority is costed before the operator's total is known, because it does not depend
    # on it: it is a staff of planners and procurement people, not a share of anything.
    authority = authority_cost(
        count=items["authorityCount"]["value"],
        staff_each=items["authorityStaffEach"]["value"],
        gross_monthly_ron=items["authorityStaffGrossMonthly"]["value"],
        employer_rate=items["employerContributionRate"]["value"],
        non_staff_share=items["authorityNonStaffShare"]["value"],
    )
    cost = annual_cost(
        paid_hours,
        dict(km_by_class),
        fleet_by_class,
        prices,
        authority_ron=authority.total_ron,
    )
    authority_share = share_of_operator_cost(authority, cost.operating_ron)

    saving_admin = hubs["savingsRon"]["administrative"]
    saving_operating = hubs["savingsRon"]["operating"]

    # Computed here rather than in the sanity-check section below, because the limitations
    # quote them. A limitation carrying a frozen number goes stale the first time an input
    # moves, and this file has already published two that did.
    ron_per_bus_km = cost.operating_ron / (sum(km_by_class.values()) * WEEKDAYS_PER_YEAR)
    driver_share = cost.driver_ron / cost.operating_ron
    speed = sum(km_by_class.values()) / hours
    observed = observed_speeds()

    def ro(value: float, places: int = 2) -> str:
        """Romanian decimal comma. The limitations are Romanian prose; 6.47 reads as a typo."""
        return f"{value:.{places}f}".replace(".", ",")

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
                "Derivat dintr-un lanț verificat în ansamblu, nu pe verigi: viteza comercială "
                f"care rezultă se compară cu {observed['count']} curse reale din programele "
                "județene și cade în intervalul lor, însă prețurile unitare rămân în parte "
                "estimate, iar economiile vin de la simulatorul administrativ cu limitările lui."
            ),
        },
        "drivers": drivers_required(
            paid_hours * WEEKDAYS_PER_YEAR, items["driverPaidHoursMonth"]["value"]
        ),
        "perWeekday": {
            "busHours": round(hours, 1),
            "paidDriverHours": round(paid_hours, 1),
            "duties": duties,
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
        # Published rather than only printed, so the one check against recorded Romanian
        # journeys is quotable and can be regression-tested. Both figures are the same
        # quantity — total kilometres over total hours — which is what makes them comparable.
        "speedCheck": {
            "modelledKmh": round(speed, 1),
            "observedKmh": observed["kmhWeighted"],
            "observedP25Kmh": observed["kmhP25"],
            "observedP75Kmh": observed["kmhP75"],
            "observedJourneys": observed["count"],
            "gap": round(speed / observed["kmhWeighted"] - 1, 4),
            "source": "data/observed-journeys.json",
            "tuned": False,
        },
        "annualRon": {
            "driver": round(cost.driver_ron),
            "running": round(cost.running_ron),
            "standing": round(cost.standing_ron),
            "admin": round(cost.admin_ron),
            "operating": round(cost.operating_ron),
            "authority": round(cost.authority_ron),
            "annualPublic": round(cost.annual_public_ron),
            "capital": round(cost.capital_ron),
            "total": round(cost.total_ron),
        },
        # The buyer, costed. `operating` is the operator alone, because every benchmark in this
        # file describes a bus company; `annualPublic` is what the system costs in a year.
        "authority": {
            "count": authority.count,
            "staffEach": authority.staff_each,
            "staffTotal": authority.staff_total,
            "salariesRon": round(authority.salaries_ron),
            "nonStaffRon": round(authority.non_staff_ron),
            "perAuthorityRon": round(authority.per_authority_ron),
            "shareOfOperatorCost": round(authority_share, 4),
            "moviaShare": 0.156,
        },
        "ledgerRon": {
            # Buses only. Rail is NOT added: rail-cost.json prices track and train-hours to
            # compare UNIT prices against the bus network, and its passengers are different
            # people on different routes. Summing the two would assert you buy both to serve
            # the same journeys, which is a claim this repository declines to make.
            "scope": "autobuz, inclusiv autoritatea; fără cale ferată",
            "transportCost": round(cost.total_ron),
            "administrativeSaving": saving_admin,
            "operatingSaving": saving_operating,
            "netAgainstAdministrativeSaving": round(saving_admin - cost.total_ron),
        },
        "limitations": [
            {
                "id": "cost-nu-subventie",
                "text": (
                    "Este costul serviciului, nu subvenția. Diferența se calculează în "
                    "data/fares.json, care pune tarife pe kilometru-călător din hotărâri de "
                    "consiliu județean peste o cerere extrapolată din populație și scoate o "
                    "acoperire din bilete de circa 46%. Rămâne o limitare care blochează citirea "
                    "directă: cifra de aici nu este subvenția, iar cea din fares.json atârnă "
                    "complet de gradul de ocupare, care este parametrul liber al acelui nivel. O "
                    "versiune anterioară a acestei limitări spunea că nu există niciun model de "
                    "cerere și niciun venit din bilete în depozit, ceea ce a încetat să fie "
                    "adevărat când s-a construit fares.json."
                ),
                "severity": "blocking",
                "affects": ["cost"],
            },
            {
                "id": "preturile-nu-sunt-citate",
                "text": (
                    "O parte dintre prețurile unitare din data/cost-inputs.json au sursă "
                    "publică — salariul șoferului, motorina fără TVA, rovinieta, prețurile de "
                    "referință ale vehiculelor, durata anvelopelor — iar întreținerea este "
                    "derivată dintr-un reper european ajustat salarial. Fără sursă rămân "
                    "anvelopele pe kilometru, asigurarea, gararea și cota de administrație. "
                    "Fiecare poziție își poartă propria proveniență în fișier: o versiune "
                    "anterioară a acestei limitări spunea că niciun preț nu are sursă, ceea ce "
                    "nu mai este adevărat de la sursarea salariului și a motorinei."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "vitezele-sunt-verificate-doar-in-ansamblu",
                "text": (
                    f"Viteza comercială a modelului este {ro(speed)} km/h, față de "
                    f"{ro(observed['kmhWeighted'])} km/h măsurați pe {observed['count']} curse "
                    "reale din programele de transport a șase consilii județene "
                    f"(data/observed-journeys.json), adică o abatere de "
                    f"{speed / observed['kmhWeighted'] - 1:+.1%}, în interiorul intervalului "
                    f"intercuartilic observat de {ro(observed['kmhP25'])}-"
                    f"{ro(observed['kmhP75'])} km/h. Factorul de viteză de serviciu NU a fost "
                    "ajustat ca să închidă diferența — altfel singura verificare independentă "
                    "din depozit ar fi devenit o potrivire. Ce rămâne neverificat este "
                    "descompunerea exactă. Stratul rutier are verificarea lui separată, în "
                    "scripts/check_gate.py, față de douăsprezece trasee auto rutate de OSRM în "
                    "Vâlcea: acolo modelul iese cu circa 10% mai RAPID, iar acumularea prin "
                    "reședințele intermediare costă doar 1,6 puncte, nu penalizarea mare pentru "
                    "care fusese construită verificarea. Deci abaterea de aici, -3,7% pe "
                    "ansamblu, și cea de +10% pe drum sunt de sensuri opuse și se compensează "
                    "parțial — ceea ce înseamnă că factorul de serviciu și staționarea absorb "
                    "mai mult decât ar cere un strat rutier corect, sau că profilul rural al "
                    "OSRM este prudent. Nu se poate departaja: nici orarul publicat, nici OSRM "
                    "nu sunt adevăr de teren. Vezi și limitările din data/observed-journeys.json "
                    "privind eșantionul."
                ),
                "severity": "note",
                "affects": ["cost"],
            },
            {
                "id": "factorul-de-viteza-de-serviciu",
                "text": (
                    "Timpii de drum liber sunt împărțiți la un factor de 0,75 ca să devină "
                    "timpi de serviciu — intersecții, marja pusă în orar ca traseul să poată "
                    "fi respectat, conducerea unui vehicul greu. Factorul este presupus, "
                    "presupus, fixat înainte să existe observațiile, și este presupunerea cu "
                    "cea mai mare influență asupra orelor. Nu a fost mutat după ce au apărut "
                    f"cele {observed['count']} curse măsurate, tocmai ca verificarea vitezei "
                    "comerciale să rămână un test și să nu devină o potrivire. Opririle nu "
                    "sunt în el: staționarea se socotește separat, iar frânarea și repornirea "
                    "din stație au fost măsurate și fac 3%."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "reperul-buzau-nu-se-poate-converti",
                "text": (
                    f"Costul de funcționare iese {ro(ron_per_bus_km)} lei pe kilometru, față de "
                    "circa 9 lei cât ar fi o operare rurală vest-europeană cu partea de salarii "
                    "ajustată la nivelul românesc — deci verificarea care se poate face TRECE. "
                    "Ce nu se poate face este conversia tarifului aprobat la Buzău în 2025, "
                    "0,35 lei/km/loc: metodologia ANRSC împarte costul pe kilometru-vehicul la "
                    "numărul mediu de LOCURI, iar costul pe kilometru nu crește proporțional cu "
                    "locurile — același șofer, aceleași anvelope, ceva mai multă motorină. "
                    "Înmulțirea cu numărul de locuri nu corespunde nici unei mărimi reale, iar "
                    "compoziția parcului din Buzău, care ar fi singura cale de conversie, este "
                    "într-un PDF scanat. Cifra rămâne consemnată pentru că este singura "
                    "măsurătoare românească de exploatare găsită, dar nu este un test picat: "
                    "este un test care nu se poate da."
                ),
                "severity": "note",
                "affects": ["cost"],
            },
            {
                "id": "personalul-autoritatii-e-parametrul-liber",
                "text": (
                    f"Autoritatea de transport costă {ro(authority.total_ron / 1e6, 1)} milioane "
                    f"de lei pe an, adică {ro(authority.per_authority_ron / 1e6, 2)} milioane pe "
                    f"județ, și se construiește de jos în sus din {authority.staff_each} oameni "
                    "de autoritate — planificare, licitații, contracte, venituri, IT, juridic. "
                    "Numărul de oameni este PRESUPUS și este singura cifră care contează aici: "
                    f"iese {ro(authority_share * 100, 1)}% din plățile către operator, față de "
                    "15,6% cât costă Movia să fie Movia pe partea de autobuz. Sub reperul danez, "
                    "cum era de așteptat pentru o autoritate pornită de la zero față de una care "
                    "rulează Rejsekort și centre de clienți — dar dacă adevărul este mai aproape "
                    "de Movia, costul de aici crește cu circa o treime. Ce lipsește complet: "
                    "costul de înființare, pentru că modelul dă un an de regim permanent."
                ),
                "severity": "material",
                "affects": ["cost"],
            },
            {
                "id": "biletele-sunt-numarate-de-doua-ori",
                "text": (
                    "Cota de administrație a operatorului, 12%, include vânzarea biletelor și "
                    "controlul, iar în regimul gross-cost din INSTITUTIONS.md acestea aparțin "
                    "autorității, care este acum o linie separată. Deci sunt numărate de două "
                    "ori. Suprapunerea umflă costul transportului, ceea ce este sensul prudent "
                    "atunci când cifra se pune alături de o economie administrativă — dar este o "
                    "eroare cunoscută, nu o marjă. Împărțirea celor 12% între operator și "
                    "autoritate ar cere o bază pe care acest depozit nu o are."
                ),
                "severity": "note",
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
        ("  = operating (operator)", "operating"),
        ("  authority (42 bodies)", "authority"),
        ("  = annual public", "annualPublic"),
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
    ron_per_km = ron_per_bus_km

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
    # The Buzau tariff is NOT printed as a check, because it is not one.
    #
    # ANRSC divides cost per vehicle-km by the operator's average SEATS, so converting their
    # 0,35 lei/km/loc into a cost per kilometre means multiplying by a seat count. Cost per
    # kilometre does not scale with seats — same driver, similar tyres, somewhat more fuel — so
    # that multiplication corresponds to nothing. Their fleet composition would be needed to
    # convert at all, and it is in a scanned PDF nobody has run through OCR.
    #
    # It was reported as a check for most of this project's life, first as "the model is 2,3x
    # too low" (wrong, and withdrawn) and then as a band of ratios that a reader would still
    # read as a failing test. Four checks that DO convert all pass — the wage-adjusted driver
    # share, cost per bus-km, commercial speed, and kilometres per bus per year — and carrying
    # an unconvertible fifth alongside them gave a non-result the weight of a problem.
    #
    # The figure stays in data/cost-inputs.json under `benchmarks`, with the reason it cannot
    # be used, because a Romanian operating figure is worth recording even when it will not
    # convert.

    # Against 552 real journeys rather than against a prior. Both sides are the same
    # quantity — total kilometres over total hours — so they compare directly.
    inside = observed["kmhP25"] <= speed <= observed["kmhP75"]
    print(
        f"  commercial speed           {speed:>6.1f}   observed {observed['kmhWeighted']} km/h "
        f"({observed['count']} curse reale, IQR {observed['kmhP25']}-{observed['kmhP75']})  "
        f"{'ok' if inside else 'OUTSIDE'}"
    )
    print(
        f"    gap vs observed          {speed / observed['kmhWeighted'] - 1:>+6.1%}   "
        "the factor was NOT tuned to close this"
    )
    # Below Movia is the expected result, not a failure: Movia runs Rejsekort, DOT, marketing
    # and customer centres for 45 municipalities. Far below would mean the staffing is thin.
    print(
        f"  authority vs operator      {authority_share:>6.1%}   Movia 15.6%  "
        f"{'ok' if 0.5 <= authority_share / 0.156 <= 1.1 else 'OUTSIDE'}"
        f"  ({authority.staff_total} staff over {authority.count} bodies)"
    )

    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

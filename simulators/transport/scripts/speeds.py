"""Effective travel speed by road class, derived rather than asserted.

An earlier version of this file was a column of numbers with a paragraph of justification —
`trunk: 75.0` and a claim that Romanian national roads do not deliver their legal 90. The
claim was right and the number was not, and nothing in the file could tell you which.

This derives the same table from three separable parts, so a critic can attack one without
having to accept the others:

1. **Measured limits.** `data/road-limits.json`, from `scripts/measure_limits.py`, holds the
   length-weighted signed limits per class. The finding that shapes everything: below
   motorway, the *open-road* limit is essentially the national 90 on every class. What
   separates a national road from a communal one is how much of its length runs **inside a
   locality** at 50 — 32% for trunk, 59% for secondary, 80% for tertiary. A DN is not slow
   because it is a worse road; it is slow because a third of it threads through villages.
   `derived`, from OSM, at 84–96% coverage on the classes that carry most traffic.

2. **Physics.** A vehicle leaving a 90 zone for a 50 zone must brake and then accelerate
   again, and both cost time against cruising. That loss is computed from the speed change
   and the vehicle's acceleration, not guessed. It is smaller than intuition suggests —
   about five seconds per village for a bus — which is itself worth knowing: the cost of a
   village is overwhelmingly the slower crawl through it, not the braking at its edge.

3. **Efficiency.** What remains: curves, junctions, surface, traffic, and the fact that
   nobody drives at the limit continuously. This is the one genuinely assumed term, it is
   per class because a motorway has no junctions and a village lane is all junction, and it
   is where a dispute about these numbers should land.

**Vehicles differ less than expected.** Below trunk, a bus and a car model within a km/h of
each other, because those roads are limited by their geometry rather than by the vehicle.
The bus penalty is real only on motorway and trunk. That is a result, not an oversight.

**What is checked, and against what.** No class in this table is verified against a recorded
free-flow journey, because no published dataset of Romanian speeds by road class exists. Two
checks exist instead, at opposite ends of the chain, and neither is ground truth.

At the far end, `data/observed-journeys.json` holds 552 timetabled county bus runs read out of
six county councils' transport programmes. The commercial speed this model eventually produces,
36,8 km/h, sits 3,7% below their kilometre-weighted 38,2 and inside their interquartile range.

That test constrains the *composite* — these speeds, plus routing, plus the service factor,
plus dwell — and cannot separate the terms on its own.

The road layer is now checked separately, by `check_gate.py`, against twelve routed car
journeys in Vâlcea from OSRM's public server. **This table runs about 10% faster than OSRM
over the same OpenStreetMap data**, uniformly rather than in one class, and the accumulation
through intermediate seats turns out to cost only ~1,6 points on top. Both are inside the
gate's tolerance and its bias limit.

So: composite 3,7% *slow* against recorded buses, road layer ~10% *fast* against an independent
router. Those point opposite ways, which means the service factor and dwell are absorbing more
than a correct road layer would need — or OSRM's rural profile is conservative and this table is
closer than it looks. Neither OSRM nor a published timetable is ground truth, and no measurement
of Romanian free-flow speed by road class exists to settle it. The efficiency figures below
remain the assumed term and the first thing to argue with; what has changed is that the size and
direction of their error are now bounded rather than unknown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LIMITS_FILE = ROOT / "data" / "road-limits.json"

# Kept in step with administrativ's pipeline.build_road_distance.ROUTING_CLASSES. Repeated
# rather than imported so this module keeps no dependency on the geo stack; the test
# `test_every_routable_class_has_a_speed` fails loudly if the two ever drift.
ROUTING_CLASSES: Final[tuple[str, ...]] = (
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "road",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
)

# How much of a class's signed limit is actually achieved, once curves, junctions, surface
# and ordinary traffic are allowed for. The assumed term, and deliberately per class: a
# motorway is grade-separated and nearly frictionless, a residential street is continuous
# junction. These are engineering judgement and the first thing to argue with.
EFFICIENCY: Final[dict[str, float]] = {
    "motorway": 0.95,
    "trunk": 0.88,
    "primary": 0.88,
    "secondary": 0.85,
    "tertiary": 0.85,
    "unclassified": 0.80,
    "residential": 0.80,
    "living_street": 0.75,
    "road": 0.80,
}

# Mean length of a Romanian locality along a through road, in km. Sets how many braking and
# re-acceleration cycles a kilometre of road contains: a class that is 32% locality at 1,5 km
# per village meets one village every 4,7 km. Assumed; the model is barely sensitive to it,
# because the transition loss is small next to the crawl through the village itself.
LOCALITY_LENGTH_KM: Final[float] = 1.5


class Vehicle:
    """Acceleration and legal ceiling for one kind of road user.

    Braking and acceleration rates are ordinary engineering figures for comfortable service —
    a bus cannot use a car's rates with passengers standing. The bus legal ceilings are
    marked assumed rather than cited: OUG 195/2002 art. 49 sets lower maxima for vehicles
    carrying more than nine people, and the exact figures should be checked against the
    article before any published number leans on them.
    """

    def __init__(self, name: str, accel: float, decel: float, cap_motorway: float, cap_open: float):
        self.name = name
        self.accel = accel
        self.decel = decel
        self.cap_motorway = cap_motorway
        self.cap_open = cap_open

    def cap(self, road_class: str) -> float:
        return self.cap_motorway if road_class.startswith("motorway") else self.cap_open


VEHICLES: Final[dict[str, Vehicle]] = {
    # Legal maxima for a car: 130 motorway, 90 outside localities.
    "car": Vehicle("car", accel=1.5, decel=2.5, cap_motorway=130.0, cap_open=90.0),
    # A coach: gentler rates for standing passengers, and lower legal ceilings.
    "bus": Vehicle("bus", accel=0.8, decel=1.2, cap_motorway=100.0, cap_open=80.0),
}

# L0 is a road travel-time substrate, not a bus timetable — justitie reads the same graph to
# ask how far a citizen is from a courthouse, which is a car journey. The bus profile applies
# in the timetable layer above, together with dwell time, which is not a road property.
DEFAULT_VEHICLE: Final[str] = "car"

# For a class the measurement cannot speak to: below 30% tagged coverage, or an OSM value
# this table has never seen. Pessimistic on purpose — an unrecognised class must never become
# a shortcut, because a shortcut is invisible in the output while a slow road shows up as an
# implausible time a plausibility check can catch.
FALLBACK_KMH: Final[float] = 20.0


def _transition_loss_s(open_ms: float, locality_ms: float, vehicle: Vehicle) -> float:
    """Seconds lost braking into a locality and accelerating back out, against cruising.

    Decelerating from v1 to v2 covers (v1+v2)/2 × Δv/a in the time Δv/a; cruising that same
    ground at v1 would have taken less. The difference, both ways, is Δv²/(2·v1)·(1/a_d+1/a_a).
    """
    change = open_ms - locality_ms
    if change <= 0:
        return 0.0
    return (change * change / (2 * open_ms)) * (1 / vehicle.decel + 1 / vehicle.accel)


def _class_speed(measured: dict, road_class: str, vehicle: Vehicle) -> float | None:
    """Effective km/h for one class, or None if the measurement cannot support it."""
    if not measured.get("usable"):
        return None
    share = measured["locality_share"]
    efficiency = EFFICIENCY.get(road_class, 0.80)
    ceiling = vehicle.cap(road_class)

    open_ms = min(measured["open_road_kmh"], ceiling) * efficiency / 3.6
    locality_ms = min(measured["locality_kmh"], ceiling) * efficiency / 3.6
    if open_ms <= 0 or locality_ms <= 0:
        return None

    seconds_per_km = (
        share * 1000 / locality_ms
        + (1 - share) * 1000 / open_ms
        + (share / LOCALITY_LENGTH_KM) * _transition_loss_s(open_ms, locality_ms, vehicle)
    )
    return 3600 / seconds_per_km


def load_limits(path: Path = LIMITS_FILE) -> dict:
    """The measured limits. Committed, so this needs no OSM extract to import."""
    return json.loads(path.read_text(encoding="utf-8"))


def effective_kmh(vehicle: str = DEFAULT_VEHICLE, path: Path = LIMITS_FILE) -> dict[str, float]:
    """Derive the whole table for one vehicle.

    A `*_link` slip road inherits its parent's speed capped at the locality limit: links are
    short, taken at the speed of the slower end, and too sparsely tagged to measure.
    """
    if vehicle not in VEHICLES:
        raise ValueError(f"unknown vehicle {vehicle!r}; have {sorted(VEHICLES)}")
    profile = VEHICLES[vehicle]
    measured = load_limits(path)["classes"]

    table: dict[str, float] = {}
    for road_class in ROUTING_CLASSES:
        if road_class.endswith("_link"):
            continue
        speed = _class_speed(measured.get(road_class, {}), road_class, profile)
        table[road_class] = round(speed, 1) if speed else FALLBACK_KMH

    for road_class in ROUTING_CLASSES:
        if not road_class.endswith("_link"):
            continue
        parent = road_class.removesuffix("_link")
        table[road_class] = round(min(table.get(parent, FALLBACK_KMH), 60.0), 1)

    return table


EFFECTIVE_KMH: Final[dict[str, float]] = effective_kmh()

SPEED_PROVENANCE: Final[dict[str, str]] = {
    "source": "osm-maxspeed-plus-cinematica",
    "locator": (
        "Limitele semnalizate măsurate în data/road-limits.json, combinate cu pierderile de "
        "frânare și accelerare la intrarea în localitate; limitele legale din OUG 195/2002 art. 49"
    ),
    "confidence": "derived",
    "note": (
        "Limitele sunt măsurate, cinematica este calculată, iar randamentul pe clasă de drum "
        "este presupus. Nicio clasă nu este verificată separat, pentru că nu există o "
        "măsurătoare publică a vitezelor de drum liber pe clase în România. Există însă "
        "două verificări la capete diferite: viteza comercială rezultată se compară cu 552 "
        "de curse reale din data/observed-journeys.json și cade în intervalul lor, iar "
        "stratul rutier singur se compară, prin scripts/check_gate.py, cu douăsprezece "
        "trasee auto rutate de OSRM în Vâlcea — unde tabelul iese cu circa 10% mai rapid. "
        "Cele două abateri sunt de sensuri opuse, deci se compensează parțial; niciuna "
        "dintre referințe nu este adevăr de teren."
    ),
}


def speeds_for_classes(classes: np.ndarray) -> np.ndarray:
    """Map an array of OSM `highway` values to effective speeds in km/h.

    Unknown or missing values take FALLBACK_KMH rather than raising: OSM gains new highway
    values without notice, and one unrecognised way must not fail a national build.
    """
    out = np.full(len(classes), FALLBACK_KMH, dtype=np.float64)
    for name, kmh in EFFECTIVE_KMH.items():
        out[classes == name] = kmh
    return out

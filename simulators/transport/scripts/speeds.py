"""Assumed effective speed by OSM road class.

This is the weakest thing in L0 and it is deliberately alone in one file, so that the whole
assumption set can be read in one screen and disputed as a unit.

These are **effective** speeds, not legal limits. The legal limits (OUG 195/2002) are 130
km/h on motorways, 100 on expressways and European national roads, 90 on other roads outside
localities and 50 inside them. Nobody averages those over a real journey: junctions, villages
strung along national roads, agricultural traffic and the state of the surface all take their
cut, and a Romanian DN through a string of communes does not deliver 90 km/h over any distance
that matters.

So each figure below is the legal limit discounted toward what a journey actually averages.
That discount is a judgement, and it is the single assumption most likely to be wrong.

**What makes it defensible is not this file.** It is the one-county gate in
`scripts/check_gate.py`, which compares these speeds' output against real recorded drive
times and fails the build when they disagree. Changing a number here without re-running that
gate is how the whole substrate becomes plausible and quietly wrong.

The classes are administrativ's `ROUTING_CLASSES`, repeated here rather than imported: this
module has no dependency on the geo stack and is the poorer for gaining one, and the test
`test_every_routable_class_has_a_speed` fails loudly if the two lists ever drift apart.
"""

from __future__ import annotations

from typing import Final

import numpy as np

# Kept in step with administrativ's pipeline.build_road_distance.ROUTING_CLASSES.
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

EFFECTIVE_KMH: Final[dict[str, float]] = {
    # Free-flowing and grade-separated; the one class that comes close to its limit.
    "motorway": 110.0,
    # DN-grade. The legal 90 is rarely achieved: these run through the villages they connect.
    "trunk": 75.0,
    "primary": 65.0,
    # DJ-grade county roads, the backbone of everything this simulator models.
    "secondary": 55.0,
    # DC-grade communal roads, frequently unsurfaced in part.
    "tertiary": 45.0,
    # Inside a locality, where the limit is 50 and the achieved speed is lower.
    "unclassified": 35.0,
    "residential": 30.0,
    "living_street": 20.0,
    # OSM's "we know it is a road and no more than that".
    "road": 30.0,
    # Slip roads: short, and taken at the speed of the slower end.
    "motorway_link": 60.0,
    "trunk_link": 50.0,
    "primary_link": 45.0,
    "secondary_link": 40.0,
    "tertiary_link": 35.0,
}

# An OSM value the table does not know. Pessimistic on purpose: an unrecognised class must
# never become a shortcut, because a shortcut is invisible in the output while a slow road
# shows up as an implausible time the gate can catch.
FALLBACK_KMH: Final[float] = 20.0

SPEED_PROVENANCE: Final[dict[str, str]] = {
    "source": "oug-195-2002-plus-judecata",
    "locator": (
        "Limitele legale din OUG 195/2002 art. 49, reduse la viteze efective de parcurs; "
        "calibrate prin verificarea pe județul de control"
    ),
    "confidence": "assumed",
    "note": (
        "Vitezele sunt estimate pe clasa drumului din OSM, nu măsurate. Nu există date "
        "publice de viteză reală pe rețeaua rutieră din România la nivel de segment."
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

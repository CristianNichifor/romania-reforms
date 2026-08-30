"""Commercial speed on Romanian track, by condition class.

The counterfactual this repository models is "what if Romania ran its network the way Denmark
does". For rail that makes CFR's published timetable the **wrong** input, not a missing one: it
encodes today's speed restrictions and today's stopping patterns, so a model fed from it could
never show a rehabilitated line as anything but the slow line it is now. What is genuinely fixed
is the track — a slow order on worn rail cannot be decreed away — so condition enters here as an
explicit class with a price, and the timetable enters only as a check.

Three separable parts, same shape as `speeds.py`:

1. **Measured line speed.** OSM tags `maxspeed` on 8.485 of Romania's main and branch line
   segments; length-weighted the mean is 88 km/h and the median 80. This is the permitted speed
   the infrastructure manager signs today, and it is a measurement rather than a design figure.

2. **Physics.** A train that stops must brake and accelerate again, and it dwells. Both are
   computed from stop spacing and regional-EMU rates, not guessed — the same treatment the road
   model gives a village.

3. **Condition.** What remains, and the interesting part. See below.

**The result worth stating.** Run the kinematics on the measured line speed and a regional
stopping pattern and the track supports roughly **74 km/h** commercially. Romania actually
achieves **45**. That gap is not physics and not geometry — the curves are where they are in both
numbers. It is condition and operations: slow orders over worn rail, single-track crossing waits,
and the 65% of track, 80% of turnouts and 85% of catenary that CFR's own renewal figures describe
as life-expired. So this module does not *assume* a condition penalty; it **measures one as the
residual** between what the alignment permits and what the network delivers.

That residual is the whole argument of §8 made numeric. "The cheapest new capacity in the country
is track already in the ground" is a claim about whether closing that 45→74 gap costs less per
minute saved than running more buses, and both sides of that comparison are now computed.

**Calibrated at both ends, which the bus model never was.** The upper bound is derived from a
measurement; the lower bound is a published national figure. Neither is a free parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Length-weighted mean of the `maxspeed` tag over OSM ways with `railway=rail` and
# `usage IN (main, branch)`, excluding yards, sidings and spurs: 8.485 tagged segments, mean
# 83,4 km/h over main and branch together, 88,0 over main line alone. Main-line figure used,
# because a passenger service between county seats runs on main line.
MEASURED_LINE_KMH: Final[float] = 88.0

# What CFR actually achieves, all passenger services, all line classes. The anchor for `as_is`
# and the lower end of the calibration. Widely reported national average; see the limitation
# `viteza-comerciala-din-presa` for how weakly it is sourced.
OBSERVED_COMMERCIAL_KMH: Final[float] = 45.0

# Danish regional practice: a rehabilitated regional line is signed at 120, and the alignment
# rather than the rail becomes the constraint. Used as a ceiling, never as a target — a
# rehabilitated mountain branch does not become straight.
DANISH_REGIONAL_CEILING_KMH: Final[float] = 120.0

# How much of its signed speed a rehabilitated Romanian line could hold. Below 1 because
# renewal restores the permitted speed rather than raising it: the curves, gradients and
# level crossings are unchanged by new rail.
REHABILITATION_UPLIFT: Final[float] = 1.0


@dataclass(frozen=True)
class Rolling:
    """Acceleration, braking and dwell for one kind of train.

    Regional EMU rates for comfortable service with standing passengers. A locomotive-hauled
    consist accelerates appreciably worse, which is itself part of what modernisation buys.
    """

    name: str
    accel: float
    decel: float
    dwell_s: float


ROLLING: Final[dict[str, Rolling]] = {
    "regional_emu": Rolling("regional_emu", accel=0.6, decel=0.8, dwell_s=40.0),
    "loco_hauled": Rolling("loco_hauled", accel=0.35, decel=0.7, dwell_s=60.0),
}

DEFAULT_ROLLING: Final[str] = "regional_emu"

# Mean distance between passenger stops on a Romanian regional service, in km. Sets how many
# brake-and-accelerate cycles a kilometre contains. Assumed; the model is moderately sensitive
# to it, which is why it is a named constant rather than buried in a formula.
STOP_SPACING_KM: Final[float] = 10.0


def _stop_penalty_s(cruise_ms: float, stock: Rolling) -> float:
    """Seconds lost to one stop, against a train that did not stop.

    Braking from v to rest covers v/2 × v/a_d in time v/a_d; cruising that ground takes half as
    long. The same holds accelerating away. The loss is therefore v/2 × (1/a_d + 1/a_a), plus
    the dwell, which is pure addition.
    """
    if cruise_ms <= 0:
        return 0.0
    return cruise_ms / 2 * (1 / stock.decel + 1 / stock.accel) + stock.dwell_s


def commercial_kmh(
    line_kmh: float,
    stop_spacing_km: float = STOP_SPACING_KM,
    stock: str = DEFAULT_ROLLING,
) -> float:
    """Door-to-door speed a service holds on track signed at `line_kmh`.

    This is the physics ceiling for that line speed and stopping pattern: what a train would
    achieve if every metre of the route were actually good for its signed speed.
    """
    if line_kmh <= 0 or stop_spacing_km <= 0:
        raise ValueError("line speed and stop spacing must both be positive")
    if stock not in ROLLING:
        raise ValueError(f"unknown rolling stock {stock!r}; have {sorted(ROLLING)}")
    profile = ROLLING[stock]

    cruise_ms = line_kmh / 3.6
    seconds_per_km = 1000 / cruise_ms + _stop_penalty_s(cruise_ms, profile) / stop_spacing_km
    return 3600 / seconds_per_km


def condition_factor() -> float:
    """The residual: what share of the achievable speed the network actually delivers.

    Measured, not assumed — the ratio of a published national average to a figure derived from
    measured line speeds and computed kinematics. Everything the model does not explicitly
    represent lands here: slow orders, single-track crossing waits, signalling, dwell overruns
    at understaffed halts.
    """
    return OBSERVED_COMMERCIAL_KMH / commercial_kmh(MEASURED_LINE_KMH)


# The two classes that ship. `as_is` reproduces the observed national average by construction;
# `rehabilitated` removes the condition residual and lets the alignment bind instead.
CONDITION_CLASSES: Final[tuple[str, ...]] = ("as_is", "rehabilitated")


def class_commercial_kmh(
    condition: str,
    line_kmh: float = MEASURED_LINE_KMH,
    stop_spacing_km: float = STOP_SPACING_KM,
    stock: str = DEFAULT_ROLLING,
) -> float:
    """Commercial speed for one condition class, in km/h.

    `as_is` applies the measured condition residual to the physics ceiling, and therefore
    reproduces the observed 45 km/h when handed the measured line speed. `rehabilitated` drops
    the residual entirely: renewed track holds its signed speed, capped at Danish regional
    practice because a renewed branch is still the branch it was.
    """
    if condition not in CONDITION_CLASSES:
        raise ValueError(f"unknown condition {condition!r}; have {list(CONDITION_CLASSES)}")

    if condition == "as_is":
        return commercial_kmh(line_kmh, stop_spacing_km, stock) * condition_factor()

    signed = min(line_kmh * REHABILITATION_UPLIFT, DANISH_REGIONAL_CEILING_KMH)
    return commercial_kmh(signed, stop_spacing_km, stock)


RAIL_SPEED_PROVENANCE: Final[dict[str, str]] = {
    "source": "osm-maxspeed-feroviar-plus-cinematica",
    "locator": (
        "maxspeed măsurat pe liniile OSM railway=rail cu usage main/branch (8.485 segmente "
        "etichetate, media 88 km/h pe linie principală); viteza comercială observată de "
        "45 km/h raportată public pentru trenurile de călători din România"
    ),
    "confidence": "derived",
    "note": (
        "Viteza de linie este măsurată, cinematica este calculată, iar penalizarea de stare a "
        "infrastructurii este dedusă ca reziduu între cele două — nu presupusă. Mersul "
        "Trenurilor NU este folosit: el descrie sistemul care se reformează, deci ar fixa în "
        "model exact restricțiile pe care reforma le elimină."
    ),
}

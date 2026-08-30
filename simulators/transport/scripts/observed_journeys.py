"""Real Romanian bus journey times, read out of county transport programmes.

For most of this project the speed model was defensible in its parts and unvalidated as a
whole, and the file that produced it said so: "nothing here is verified against a recorded
journey; no observations of real Romanian travel time exist in this repository." That was
true of the repository and false of the world. County councils publish their `program de
transport judeţean` as a table with one row per route, and the row carries **distance per
direction next to departure and arrival time**. Divide one by the other and you have an
observed commercial speed — door to door, dwell included, on exactly the kind of rural route
this model builds.

**What these observations can and cannot settle.** They validate the *composite*: road speed
by class, routing, the service-speed factor and station dwell, all collapsed into the one
number a passenger experiences. They cannot separate those terms. A model that ran the roads
too fast and dwelt too long would land in the same place. So this closes "the chain has never
been compared to reality" and does not close "each link is right".

**These are the routes that exist, which is not a random sample.** A commercial route runs
where there is demand, and demand follows the better roads. The network this repository
builds must also serve communes that no operator chose, which are on worse roads. If the
sample is biased it is biased *fast*, so a model matching it is if anything optimistic.

**Why the numbers are committed rather than fetched.** The programmes are PDFs on county
council servers, several already superseded, one covering a period that ended in 2019. They
move and they disappear. `build_observed.py` re-derives this file from the sources; the
extracted observations are committed so no reader needs those servers to be up.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Final

# A time is 7:00 or 07:00 or 8.30 — Sălaj's programme uses the full stop.
TIME = re.compile(r"^(\d{1,2})[:.](\d{2})$")

# Tokens that look like place names but are column headings. Caraş-Severin writes the journey
# time in its own column as "32 Min", which would otherwise be read as the distance.
UNIT_WORDS: Final[frozenset[str]] = frozenset({"min", "minute", "km", "ora", "ore", "h"})

# A route shorter than this is usually a town service where the programme's km column means
# something else; longer than this is an interurban coach, not a county route. Journey-time
# bounds catch rows where the arrival belongs to a different column.
MIN_KM: Final[int] = 8
MAX_KM: Final[int] = 200
MIN_MINUTES: Final[int] = 5
MAX_MINUTES: Final[int] = 300

# Outside this, the row was misparsed rather than unusual. 8 km/h is slower than a bicycle and
# 90 km/h is above the legal ceiling for a bus outside a locality.
MIN_KMH: Final[float] = 8.0
MAX_KMH: Final[float] = 90.0


@dataclass(frozen=True)
class Journey:
    """One timetabled run: its length in one direction and how long it is booked to take."""

    county: str
    km: int
    minutes: int

    @property
    def kmh(self) -> float:
        return self.km / (self.minutes / 60)


def _minutes_of(token: str) -> int | None:
    match = TIME.match(token)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def parse_programme_line(line: str, county: str) -> list[Journey]:
    """Read the journeys off one row of a county transport programme.

    The layout is stable across counties even though the column count is not:

        01 01 001 BRAILA CHISCANI TUFESTI 41 8 10 1 7:00 8:20 8:25 9:45 1,2,3,4,5,6,7

    place names, then a block of integers of which **the first is the distance per
    direction**, then departure and arrival for the outbound run and again for the return.
    Both directions are taken: they share a distance and are separately timed, and an operator
    often books more time against the morning peak than for the evening.

    The distance is found by walking back to the last word — not by column index, which
    differs by county — and taking the first integer after it. Caraş-Severin puts a "32 Min"
    column between the two, which is why unit words are skipped rather than treated as places.
    """
    tokens = line.split(" ")
    times = [i for i, token in enumerate(tokens) if TIME.match(token)]
    if len(times) < 2:
        return []

    first_time = times[0]
    last_word = None
    for index in range(first_time):
        word = tokens[index].strip("/.,").replace(".", "")
        if len(word) >= 3 and any(c.isalpha() for c in word) and word.lower() not in UNIT_WORDS:
            last_word = index
    if last_word is None:
        # A continuation row: further departures for the route named on the row above. It has
        # times but no distance of its own, and guessing that it inherits the one above would
        # silently multiply whatever that row got wrong.
        return []

    km = None
    for index in range(last_word + 1, first_time):
        if tokens[index].isdigit():
            km = int(tokens[index])
            break
    if km is None or not MIN_KM <= km <= MAX_KM:
        return []

    journeys = []
    for start, end in ((0, 1), (2, 3)):
        if end >= len(times):
            break
        departure = _minutes_of(tokens[times[start]])
        arrival = _minutes_of(tokens[times[end]])
        if departure is None or arrival is None:
            continue
        minutes = arrival - departure
        if minutes < 0:
            minutes += 1440  # a run that crosses midnight
        if not MIN_MINUTES <= minutes <= MAX_MINUTES:
            continue
        journey = Journey(county=county, km=km, minutes=minutes)
        if MIN_KMH <= journey.kmh <= MAX_KMH:
            journeys.append(journey)
    return journeys


def summarise(journeys: list[Journey]) -> dict:
    """The distribution a speed model has to land inside.

    The headline is the **kilometre-weighted** mean rather than the mean of the per-route
    speeds. A network's total bus-hours is total distance over the speed at which that
    distance is covered, so a 90 km route matters more than a 10 km one; averaging the ratios
    would weight them equally and overstate the influence of short village runs, which are the
    slowest rows in every one of these programmes.
    """
    if not journeys:
        raise ValueError("no journeys to summarise")
    speeds = sorted(journey.kmh for journey in journeys)

    def percentile(fraction: float) -> float:
        return speeds[int(fraction * (len(speeds) - 1))]

    total_km = sum(journey.km for journey in journeys)
    total_hours = sum(journey.minutes for journey in journeys) / 60
    by_county: dict[str, int] = {}
    for journey in journeys:
        by_county[journey.county] = by_county.get(journey.county, 0) + 1

    return {
        "count": len(journeys),
        "byCounty": dict(sorted(by_county.items())),
        "kmhWeighted": round(total_km / total_hours, 1),
        "kmhMean": round(statistics.mean(speeds), 1),
        "kmhMedian": round(percentile(0.50), 1),
        "kmhP10": round(percentile(0.10), 1),
        "kmhP25": round(percentile(0.25), 1),
        "kmhP75": round(percentile(0.75), 1),
        "kmhP90": round(percentile(0.90), 1),
        "totalKm": total_km,
        "totalHours": round(total_hours, 1),
    }

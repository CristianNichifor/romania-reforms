"""Seat-to-seat journey time within one county, accumulated over the adjacency graph.

The time-domain counterpart of `reference_model._county_road_distances`. Like it, this is a
Dijkstra over the **UAT adjacency graph** rather than over the road network: a journey from a
commune to a distant seat is the sum of the seat-to-seat hops between them.

That approximation always overstates, never understates, because it forces the route through
each intermediate seat village rather than past it. Overstating is the safe direction for a
substrate: a network built on times that are slightly too long is conservative, while one
built on times that are too short promises journeys that do not exist.

Journeys never cross a county line, matching administrativ's constraint that regions do not.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable


def county_times(
    county: dict[str, str],
    neighbours: dict[str, list[str]],
    edge_s: dict[tuple[str, str], float],
    county_code: str,
    sources: Iterable[str],
) -> dict[str, float]:
    """Seconds from the nearest source to every reachable UAT in `county_code`.

    A UAT with no route is **absent from the result**, not zero: absent is a hole the caller
    has to handle, and zero is a hole that reads as an answer. An adjacency edge with no
    measured time is likewise not traversable — treating it as free would route journeys
    through precisely the pairs the router failed to measure.
    """
    best: dict[str, float] = {}
    queue: list[tuple[float, str]] = []

    for source in sources:
        if county.get(source) == county_code and source not in best:
            best[source] = 0.0
            heapq.heappush(queue, (0.0, source))

    while queue:
        seconds, uat = heapq.heappop(queue)
        if seconds > best.get(uat, float("inf")):
            continue
        for neighbour in neighbours.get(uat, ()):
            if county.get(neighbour) != county_code:
                continue
            step = edge_s.get((uat, neighbour))
            if step is None:
                continue
            through = seconds + step
            if through < best.get(neighbour, float("inf")):
                best[neighbour] = through
                heapq.heappush(queue, (through, neighbour))

    return best

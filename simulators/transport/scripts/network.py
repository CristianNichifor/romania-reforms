"""Routes, from a hub and the road network around it."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Final

LONG_ROUTE_MIN: Final[float] = 60.0


@dataclass(frozen=True)
class Route:
    hub: str
    leaf: str
    stops: list[str]
    serves: list[str]
    one_way_min: float

    @property
    def is_long(self) -> bool:
        return self.one_way_min > LONG_ROUTE_MIN


def shortest_path_tree(hub, zone, neighbours, edge_s):
    distance = {hub: 0.0}
    parent: dict[str, str | None] = {hub: None}
    queue = [(0.0, hub)]
    while queue:
        so_far, here = heapq.heappop(queue)
        if so_far > distance.get(here, float("inf")):
            continue
        for neighbour in neighbours.get(here, ()):
            if neighbour not in zone:
                continue
            step = edge_s.get((here, neighbour))
            if step is None:
                continue
            through = so_far + step
            if through < distance.get(neighbour, float("inf")):
                distance[neighbour] = through
                parent[neighbour] = here
                heapq.heappush(queue, (through, neighbour))
    return distance, parent


def _chain(node, parent):
    out = [node]
    while parent.get(out[-1]) is not None:
        out.append(parent[out[-1]])
    return out


def routes_for_hub(hub, members, zone, neighbours, edge_s, population):
    distance, parent = shortest_path_tree(hub, zone, neighbours, edge_s)
    reachable = {m for m in members if m in distance and m != hub}
    if not reachable:
        return []
    ancestors = set()
    for m in reachable:
        ancestors.update(_chain(m, parent)[1:])
    leaves = sorted(reachable - ancestors, key=lambda s: (-population.get(s, 0), s))
    routes, served = [], set()
    for leaf in leaves:
        stops = _chain(leaf, parent)
        serves = [s for s in stops if s in members and s != hub and s not in served]
        served.update(serves)
        routes.append(Route(hub, leaf, stops, serves, distance[leaf] / 60.0))
    return routes

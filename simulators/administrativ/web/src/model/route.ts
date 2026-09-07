/**
 * Walking a commune back to the centre that absorbed it.
 *
 * `parentOf` records the commune each UAT was reached through during accretion, and walking it
 * repeatedly gives the sequence of hops the accumulated road distance was measured over.
 *
 * **Accretion is not the last word.** Leftovers, the orphan tier, consolidation to the target,
 * rebalancing and pins all move communes afterwards, and none of them rewrites `parentOf`. So a
 * commune moved after accretion keeps a route that leads into the unit it used to belong to —
 * on the map, a road highlighted through some other merged UAT entirely. Across the default
 * map that is 659 legs over 368 communes: VICTORIA sits in MUNICIPIUL IAȘI and its recorded
 * route walks through four communes of the TOMEȘTI unit.
 *
 * Passing `regionOf` stops the walk at the unit boundary, which is what anything drawing on the
 * map wants: never a road outside the unit being pointed at. It shortens 95 routes and empties
 * 273 of them, and that is the honest outcome — those 273 had no valid route left to show, and
 * they join the ~675 communes that already show none because no route was ever measured for
 * them. Drawing nothing beats drawing a road to the wrong town.
 *
 * Lives here rather than beside the drawing code because the worker needs it too, and one
 * implementation is one thing to get wrong.
 */

/**
 * The route from `uat` back to its centre, nearest-first, starting at `uat` itself.
 *
 * Null where the commune was not placed by accretion at all — a leftover, an orphan cluster, a
 * consolidation or a pin. Those have no route because none was measured, and saying so is
 * better than drawing a plausible line.
 *
 * With `regionOf`, the walk stops before the first hop that would leave the commune's own unit.
 *
 * The visited set is a guard, not an expectation: a cycle would be a bug in the model, and
 * returning null keeps a bug from becoming an infinite loop in the render path.
 */
export function routeTo(
  parentOf: Int16Array,
  uat: number,
  regionOf?: Uint16Array,
): number[] | null {
  const unit = regionOf?.[uat];
  const route = [uat];
  const seen = new Set<number>([uat]);
  let node = uat;

  while (parentOf[node]! >= 0) {
    const parent = parentOf[node]!;
    if (seen.has(parent)) return null;
    if (regionOf && regionOf[parent] !== unit) break;
    seen.add(parent);
    route.push(parent);
    node = parent;
  }

  return route.length > 1 ? route : null;
}

/** Consecutive pairs along a route: the legs actually travelled. */
export function hopsOf(route: readonly number[]): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i < route.length - 1; i += 1) out.push([route[i]!, route[i + 1]!]);
  return out;
}

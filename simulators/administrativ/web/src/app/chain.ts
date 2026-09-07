/**
 * The route a commune was absorbed along, ready to draw.
 *
 * The model records which commune each UAT was reached through; walking that back gives the
 * sequence of hops the accumulated road distance was measured over. This turns that sequence
 * into lines — the real routed geometry where the county's shard has it, and a straight
 * schematic where it does not.
 *
 * The distinction is kept all the way to the map on purpose. A straight line labelled
 * "12.1 km" that is not 12.1 km long is the exact misreading this feature exists to prevent,
 * so a schematic leg is drawn dashed and never silently passes for a road.
 */

import type { ChainFeature } from '../map/map';

/**
 * The walk itself lives in the model, because the worker needs it too. Re-exported here so
 * the drawing code keeps importing its route from one place.
 */
import { hopsOf } from '../model/route';

export { hopsOf, routeTo } from '../model/route';

/**
 * A key for one leg, independent of which end you name first.
 *
 * The shards are written from the adjacency table, which stores each border once in whichever
 * order the pipeline produced. A route walks its legs in the direction it was grown, which is
 * frequently the other one, so keying on the pair unordered is what makes the lookup hit.
 */
export function edgeKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

/** A county's shard, parsed into a lookup from border to routed coordinates. */
export function indexShard(raw: unknown): Map<string, [number, number][]> {
  const index = new Map<string, [number, number][]>();
  if (typeof raw !== 'object' || raw === null) return index;
  const features = (raw as { features?: unknown }).features;
  if (!Array.isArray(features)) return index;
  for (const feature of features) {
    const properties = (feature as { properties?: { a?: unknown; b?: unknown } }).properties;
    const geometry = (feature as { geometry?: { coordinates?: unknown } }).geometry;
    const coordinates = geometry?.coordinates;
    if (typeof properties?.a !== 'string' || typeof properties?.b !== 'string') continue;
    if (!Array.isArray(coordinates) || coordinates.length < 2) continue;
    index.set(edgeKey(properties.a, properties.b), coordinates as [number, number][]);
  }
  return index;
}

export interface ChainLeg {
  from: number;
  to: number;
  metres: number;
  /** True where the drawn line is the routed geometry rather than a straight stand-in. */
  real: boolean;
}

/**
 * Build the drawable legs of a route.
 *
 * `geometryFor` returns the routed coordinates for a leg, or null when the shard is not
 * loaded or has nothing for it; `seatOf` is the fallback. A leg with neither is dropped
 * rather than drawn from nothing.
 */
export function buildChain(
  route: readonly number[],
  roadMetres: (a: number, b: number) => number,
  geometryFor: (a: number, b: number) => [number, number][] | null,
  seatOf: (uat: number) => [number, number] | undefined,
): { features: ChainFeature[]; legs: ChainLeg[]; totalMetres: number } {
  const features: ChainFeature[] = [];
  const legs: ChainLeg[] = [];
  let totalMetres = 0;

  for (const [from, to] of hopsOf(route)) {
    const metres = roadMetres(from, to);
    totalMetres += Number.isFinite(metres) ? metres : 0;

    const routed = geometryFor(from, to);
    if (routed && routed.length > 1) {
      features.push({
        type: 'Feature',
        properties: { kind: 'road' },
        geometry: { type: 'LineString', coordinates: routed },
      });
      legs.push({ from, to, metres, real: true });
      continue;
    }

    const a = seatOf(from);
    const b = seatOf(to);
    if (!a || !b) continue;
    features.push({
      type: 'Feature',
      properties: { kind: 'schematic' },
      geometry: { type: 'LineString', coordinates: [a, b] },
    });
    legs.push({ from, to, metres, real: false });
  }

  return { features, legs, totalMetres };
}

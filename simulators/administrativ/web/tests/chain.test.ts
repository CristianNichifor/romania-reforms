/**
 * The chain back to the centre.
 *
 * `parentOf` records the commune each UAT was reached through during accretion. Walking it
 * repeatedly should arrive at the unit's centre, and that walk is the route the accumulated
 * road distance was measured along — which is the whole basis for drawing it on the map.
 *
 * The subtlety these tests exist to pin down: accretion is not the last word. Leftovers,
 * the orphan tier, consolidation to the target, rebalancing and pins all move communes
 * afterwards, and a commune moved after accretion keeps a chain that no longer leads to the
 * unit it is now in. Drawing that chain would show a route to the wrong town. So the tests
 * measure how often the chain is still valid, and assert that every hop it does contain is a
 * real road-connected border.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

import { decode } from '../src/model/load';
import { runModel } from '../src/model/model';
import { DEFAULT_PARAMS, REASON, type ModelData } from '../src/model/types';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const rb = (n: string): ArrayBuffer => {
  const b = readFileSync(resolve(dataDir, n));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};
const rj = (n: string): never => JSON.parse(readFileSync(resolve(dataDir, n), 'utf8')) as never;

let data: ModelData;

beforeAll(() => {
  data = decode({
    manifest: rj('manifest.json'),
    attributes: rj('attributes.json'),
    attributesBin: rb('attributes.bin'),
    adjacencyBin: rb('adjacency.bin'),
    candidacyBin: rb('candidacy.bin'),
  });
});

/** The road distance between two adjacent communes' seats, or Infinity if not adjacent. */
function roadBetween(a: number, b: number): number {
  for (let e = data.neighbourStart[a]!; e < data.neighbourStart[a + 1]!; e += 1) {
    if (data.neighbours[e] === b) return data.neighbourRoadM[e]!;
  }
  return Infinity;
}

/** Are these two communes neighbours with a road across the border? */
function adjacent(a: number, b: number): boolean {
  for (let e = data.neighbourStart[a]!; e < data.neighbourStart[a + 1]!; e += 1) {
    if (data.neighbours[e] === b) return true;
  }
  return false;
}

/**
 * Walk a commune back to the centre that absorbed it.
 *
 * The root of the walk — the commune with no parent — is the centre accretion grew from, and
 * the chain is the route the accumulated road distance was measured along. That is what the
 * map wants to draw, and it is not the same question as "where is this unit seated now":
 * re-seating can move a unit's seat onto a different member afterwards without changing the
 * route anybody measured.
 */
function walk(parentOf: Int16Array, uat: number): number[] | null {
  const chain = [uat];
  let node = uat;
  const seen = new Set<number>([uat]);
  while (parentOf[node]! >= 0) {
    const parent = parentOf[node]!;
    if (seen.has(parent)) return null; // a cycle is a bug, not a route
    seen.add(parent);
    chain.push(parent);
    node = parent;
  }
  return chain.length > 1 ? chain : null;
}

describe('the chain a commune was reached along', () => {
  it('never contains a cycle', () => {
    const result = runModel(data, DEFAULT_PARAMS);
    for (let i = 0; i < data.uatCount; i += 1) {
      const seen = new Set<number>([i]);
      let node = i;
      let steps = 0;
      while (result.parentOf[node]! >= 0 && steps < data.uatCount) {
        node = result.parentOf[node]!;
        expect(seen.has(node), `cycle through ${data.attributes.name[node]}`).toBe(false);
        seen.add(node);
        steps += 1;
      }
      expect(steps).toBeLessThan(data.uatCount);
    }
  });

  it('only ever steps across a road-connected border', () => {
    // Every hop must be an edge the model was allowed to grow over. A chain that steps
    // between two communes with no road between them is describing a route that cannot be
    // driven, whatever its arithmetic says.
    const result = runModel(data, DEFAULT_PARAMS);
    const bad: string[] = [];
    for (let i = 0; i < data.uatCount; i += 1) {
      const parent = result.parentOf[i]!;
      if (parent < 0) continue;
      if (!adjacent(i, parent)) {
        bad.push(`${data.attributes.name[i]} <- ${data.attributes.name[parent]}`);
      }
    }
    expect(bad.slice(0, 5)).toEqual([]);
  });

  it('never records a route longer than the cap the model enforced', () => {
    // The invariant accretion actually guarantees. A commune was only ever admitted while the
    // accumulated road distance stayed under maxRoadM, so a chain that sums past it would be
    // describing a route the model would have refused — which is the one way a drawn road
    // could contradict the number beside it.
    const params = { ...DEFAULT_PARAMS };
    const result = runModel(data, params);
    let checked = 0;
    let longest = 0;
    const over: string[] = [];

    for (let i = 0; i < data.uatCount; i += 1) {
      const chain = walk(result.parentOf, i);
      if (chain === null) continue;
      checked += 1;
      let metres = 0;
      for (let step = 0; step < chain.length - 1; step += 1) {
        metres += roadBetween(chain[step]!, chain[step + 1]!);
      }
      longest = Math.max(longest, metres);
      if (params.maxRoadM > 0 && metres > params.maxRoadM + 1) {
        over.push(`${data.attributes.name[i]}: ${(metres / 1000).toFixed(1)} km`);
      }
    }

    expect(checked).toBeGreaterThan(1_000);
    expect(over.slice(0, 5)).toEqual([]);
    console.log(
      `${checked} routes, longest ${(longest / 1000).toFixed(1)} km ` +
        `against a ${(params.maxRoadM / 1000).toFixed(0)} km cap`,
    );
  });

  it('reports how often a route still ends at the unit seat', () => {
    // Not an assertion, because neither end of it is stable: re-seating moves a unit's seat
    // onto its highest-ranking member, and consolidation can absorb a centre into a
    // neighbouring unit, overwriting the reason that said it was one. The route is still the
    // route that was measured — the panel therefore says "absorbed along this route by X"
    // rather than implying X is where the town hall ends up.
    const result = runModel(data, DEFAULT_PARAMS);
    let withRoute = 0;
    let rootIsSeat = 0;
    for (let i = 0; i < data.uatCount; i += 1) {
      const chain = walk(result.parentOf, i);
      if (chain === null) continue;
      withRoute += 1;
      if (chain[chain.length - 1] === result.regionOf[i]) rootIsSeat += 1;
    }
    expect(withRoute).toBeGreaterThan(1_000);
    console.log(
      `routes: ${withRoute}; root still the unit seat for ${rootIsSeat} ` +
        `(${((100 * rootIsSeat) / withRoute).toFixed(1)}%)`,
    );
  });

  it('records a route only for communes accretion itself placed', () => {
    // `reasonOf` cannot answer this. Later passes — leftovers, the orphan tier, consolidation
    // to the target, rebalancing — also mark a commune ABSORBED_*, and those placements were
    // never reached along a chain. 446 communes at the default settings carry an absorbed
    // reason and no route, which is correct: `parentOf` is the authority on what was measured,
    // and the panel names the rule that placed the rest instead of drawing a road for them.
    const result = runModel(data, DEFAULT_PARAMS);
    let absorbedReason = 0;
    let absorbedWithRoute = 0;
    for (let i = 0; i < data.uatCount; i += 1) {
      const reason = result.reasonOf[i]!;
      if (reason !== REASON.ABSORBED_OVERLAP && reason !== REASON.ABSORBED_SEAT) continue;
      absorbedReason += 1;
      if (result.parentOf[i]! >= 0) absorbedWithRoute += 1;
    }
    expect(absorbedWithRoute).toBeLessThan(absorbedReason);
    expect(absorbedWithRoute / absorbedReason).toBeGreaterThan(0.7);
    console.log(
      `absorbed reason: ${absorbedReason}, of which ${absorbedWithRoute} were reached ` +
        `along a chain (${((100 * absorbedWithRoute) / absorbedReason).toFixed(1)}%)`,
    );
  });

  it('gives a centre no parent, because it is where the chain ends', () => {
    const result = runModel(data, DEFAULT_PARAMS);
    // Tested against the reason the growth pass recorded, not the final tier. Re-seating can
    // hand a tier to a commune that accretion had absorbed — Oras Budesti is one — so it has
    // both a tier and a parent, and neither is wrong.
    for (let i = 0; i < data.uatCount; i += 1) {
      const reason = result.reasonOf[i]!;
      const isCentre =
        reason === REASON.CENTRE_CAPITAL ||
        reason === REASON.CENTRE_THRESHOLD ||
        reason === REASON.CENTRE_PROMOTED;
      if (!isCentre) continue;
      expect(result.parentOf[i], data.attributes.name[i]).toBe(-1);
    }
  });
});

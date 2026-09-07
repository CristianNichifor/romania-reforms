/**
 * A highlighted road never leaves the unit being pointed at.
 *
 * `parentOf` records the route a commune was absorbed along, and accretion is not the last
 * word: leftovers, the orphan tier, consolidation, rebalancing and pins all move communes
 * afterwards without rewriting it. A commune moved after accretion therefore keeps a route
 * leading into the unit it used to belong to — and drawing that lights up roads through some
 * other merged UAT, which is exactly the thing a reader would take as evidence of a merge that
 * did not happen.
 *
 * `tests/chain.test.ts` measures how often the raw chain is stale. These tests assert what the
 * drawing code does about it, which is the part a reader actually sees.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

import { decode } from '../src/model/load';
import { runModel } from '../src/model/model';
import { hopsOf, routeTo } from '../src/model/route';
import { DEFAULT_PARAMS, type ModelData, type ModelResult, type Params } from '../src/model/types';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');

const readBuffer = (name: string): ArrayBuffer => {
  const buf = readFileSync(resolve(dataDir, name));
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
};
const readJson = <T>(name: string): T =>
  JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')) as T;

let data: ModelData;
let result: ModelResult;

beforeAll(() => {
  data = decode({
    manifest: readJson('manifest.json'),
    attributes: readJson('attributes.json'),
    attributesBin: readBuffer('attributes.bin'),
    adjacencyBin: readBuffer('adjacency.bin'),
    candidacyBin: readBuffer('candidacy.bin'),
  });
  result = runModel(data, DEFAULT_PARAMS);
});

const CASES: [string, Params][] = [
  ['default', DEFAULT_PARAMS],
  ['a coarser map', { ...DEFAULT_PARAMS, pTarget: 40_000 }],
  ['no orphan tier', { ...DEFAULT_PARAMS, pOrphan: 0 }],
];

describe('the contained walk', () => {
  it.each(CASES)('draws no leg outside the commune’s own unit: %s', (_label, params) => {
    const run = runModel(data, params);
    const strayed: string[] = [];

    for (let i = 0; i < data.uatCount; i += 1) {
      const route = routeTo(run.parentOf, i, run.regionOf);
      if (!route) continue;
      const unit = run.regionOf[i];
      for (const node of route) {
        if (run.regionOf[node] !== unit) {
          strayed.push(`${data.attributes.name[i]} -> ${data.attributes.name[node]}`);
        }
      }
    }

    expect(strayed.slice(0, 5)).toEqual([]);
    expect(strayed).toHaveLength(0);
  });

  it('is a prefix of the uncontained walk, never a different road', () => {
    // Containment may only truncate. If it ever rerouted, the map would show a road the model
    // did not measure, which is a worse failure than the one being fixed.
    for (let i = 0; i < data.uatCount; i += 1) {
      const full = routeTo(result.parentOf, i);
      const held = routeTo(result.parentOf, i, result.regionOf);
      if (!held) continue;
      expect(full, data.attributes.name[i]).not.toBeNull();
      expect(full!.slice(0, held.length), data.attributes.name[i]).toEqual(held);
    }
  });

  it('keeps every leg a real road-connected border', () => {
    const notAdjacent: string[] = [];
    for (let i = 0; i < data.uatCount; i += 1) {
      const route = routeTo(result.parentOf, i, result.regionOf);
      if (!route) continue;
      for (const [from, to] of hopsOf(route)) {
        let found = false;
        for (let e = data.neighbourStart[from]!; e < data.neighbourStart[from + 1]!; e += 1) {
          if (data.neighbours[e] === to) { found = true; break; }
        }
        if (!found) notAdjacent.push(`${data.attributes.name[from]}|${data.attributes.name[to]}`);
      }
    }
    expect(notAdjacent.slice(0, 5)).toEqual([]);
  });
});

describe('what containment costs, stated rather than assumed', () => {
  it('truncates a minority and empties fewer still', () => {
    let shortened = 0;
    let emptied = 0;
    let unchanged = 0;

    for (let i = 0; i < data.uatCount; i += 1) {
      const full = routeTo(result.parentOf, i);
      if (!full) continue;
      const held = routeTo(result.parentOf, i, result.regionOf);
      if (!held) emptied += 1;
      else if (held.length < full.length) shortened += 1;
      else unchanged += 1;
    }

    // Measured on the default map, over every UAT that has a route at all — including the
    // handful of centres that carry one, since consolidation can reseat a unit onto a commune
    // accretion had already given a parent. The point of pinning these is that a change means
    // the model started moving communes around differently, which is worth noticing on purpose.
    expect(emptied).toBe(273);
    expect(shortened).toBe(95);
    expect(unchanged).toBeGreaterThan(1_800);
  });

  it('never empties a route for a commune that still sits where accretion left it', () => {
    // The communes losing their road are exactly the ones a later pass moved. If one that
    // accretion placed lost its route, containment would be eating valid geometry.
    for (let i = 0; i < data.uatCount; i += 1) {
      const parent = result.parentOf[i]!;
      if (parent < 0) continue;
      if (result.regionOf[parent] !== result.regionOf[i]) continue;
      expect(routeTo(result.parentOf, i, result.regionOf), data.attributes.name[i]).not.toBeNull();
    }
  });
});

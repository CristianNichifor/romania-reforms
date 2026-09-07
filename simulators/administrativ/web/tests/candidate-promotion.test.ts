/**
 * Promoting a candidate from the list, and the one state that cannot be promoted.
 *
 * The candidate panel offers a button on some states and a refusal on another, which is a
 * claim about the model: forcing waives the population threshold and the separation floor —
 * the two rules that are matters of judgement — and does not waive a capital's ring, which is
 * a matter of geography.
 *
 * If that claim is wrong the panel is worse than useless: it either hides an override that
 * would have worked, or offers one the model silently drops. So it is checked here against
 * real UATs in each state rather than asserted in a comment beside the button.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

import { decode } from '../src/model/load';
import { candidacyReport, runModel } from '../src/model/model';
import { CANDIDACY, DEFAULT_PARAMS, type ModelData } from '../src/model/types';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');

const readBuffer = (name: string): ArrayBuffer => {
  const buf = readFileSync(resolve(dataDir, name));
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
};
const readJson = <T>(name: string): T =>
  JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')) as T;

let data: ModelData;
let report: Uint8Array;

beforeAll(() => {
  data = decode({
    manifest: readJson('manifest.json'),
    attributes: readJson('attributes.json'),
    attributesBin: readBuffer('attributes.bin'),
    adjacencyBin: readBuffer('adjacency.bin'),
    candidacyBin: readBuffer('candidacy.bin'),
  });
  report = candidacyReport(data, DEFAULT_PARAMS, []);
});

/** The largest few UATs in a state — largest first, so the cases are ones a reader would meet. */
const inState = (state: number, take: number): number[] =>
  [...report.keys()]
    .filter((i) => report[i] === state)
    .sort((a, b) => data.population[b]! - data.population[a]!)
    .slice(0, take);

// The states the panel puts a button on.
const FORCEABLE = [
  ['eligible but unused', CANDIDACY.ELIGIBLE_UNUSED],
  ['refused for separation', CANDIDACY.REFUSED_SEPARATION],
] as const;

// The states it shows a reason on instead, and the reason the model gives for each.
const BARRED = [
  ['inside a capital ring', CANDIDACY.IN_CAPITAL_RING, 'capital-ring'],
  ['stood down for its capital', CANDIDACY.STOOD_DOWN, 'already-a-centre'],
] as const;

describe('the states the panel offers a button on', () => {
  it.each(FORCEABLE)('accepts a forced centre that was %s', (_label, state) => {
    const cases = inState(state, 4);
    expect(cases.length).toBeGreaterThan(0);

    for (const uat of cases) {
      const result = runModel(data, DEFAULT_PARAMS, [], [uat]);
      const name = data.attributes.name[uat];
      expect(result.forcedApplied, name).toContain(uat);
      expect(result.forcedRejected.map((r) => r.uat), name).not.toContain(uat);
    }
  });

  it('does not promise the forced centre keeps its own unit', () => {
    // Accepting an override is not the same as the map showing a new unit: consolidation and
    // rebalancing run afterwards and can absorb the centre again. The panel says "make it a
    // centre", which is what the model is asked; the forced-centres block reports what came
    // of it. Asserted so that nobody later strengthens the button's wording to match a
    // guarantee the model does not make.
    const cases = inState(CANDIDACY.ELIGIBLE_UNUSED, 12);
    const kept = cases.filter((uat) => runModel(data, DEFAULT_PARAMS, [], [uat]).regionOf[uat] === uat);
    expect(kept.length).toBeGreaterThan(0);
    expect(kept.length).toBeLessThan(cases.length);
  });
});

describe('the states it refuses instead', () => {
  it.each(BARRED)('refuses a centre %s, and names the rule', (_label, state, why) => {
    const cases = inState(state, 4);
    expect(cases.length).toBeGreaterThan(0);

    for (const uat of cases) {
      const result = runModel(data, DEFAULT_PARAMS, [], [uat]);
      const name = data.attributes.name[uat];
      expect(result.forcedApplied, name).not.toContain(uat);
      expect(result.forcedRejected.find((r) => r.uat === uat)?.why, name).toBe(why);
    }
  });
});

describe('what promoting one candidate costs', () => {
  it('never moves a commune in another county', () => {
    // The panel invites the reader to compare candidates against each other, so a promotion
    // that quietly reshuffled a distant county would make every comparison they had just
    // made wrong. Counties are sealed in this model, and this is that rule seen from the
    // override rather than from the growth pass.
    const before = runModel(data, DEFAULT_PARAMS);

    for (const uat of inState(CANDIDACY.ELIGIBLE_UNUSED, 5)) {
      const after = runModel(data, DEFAULT_PARAMS, [], [uat]);
      const county = data.attributes.county[uat];
      const strayed: string[] = [];
      for (let i = 0; i < before.regionOf.length; i += 1) {
        if (before.regionOf[i] === after.regionOf[i]) continue;
        if (data.attributes.county[i] !== county) strayed.push(data.attributes.name[i]!);
      }
      expect(strayed.slice(0, 5), data.attributes.name[uat]).toEqual([]);
    }
  });
});

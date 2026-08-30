/**
 * The browser's arondare must agree with the Python reference, exactly.
 *
 * This page now computes the judicial map twice: once in Python, shipped as
 * `arondare-noua.json`, and once here in the browser so it can follow the reader's own
 * administrative settings. Two implementations of the same claim are two chances to be wrong,
 * and the failure mode is silent — the page would keep rendering plausible numbers that no
 * longer match the document beside them.
 *
 * So the shipped document is the fixture. At the administrative model's default parameters the
 * two must produce the same units, the same crossings, the same population and the same split
 * count. Both discrepancies found while writing this were real: `x` copied by hand as 0 rather
 * than 7.500 (259 units against 249), and unreachable communes counted as disagreement in the
 * split test (113 against 110).
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';

import { DEFAULT_PARAMS } from '../../../administrativ/web/src/model/types';
import { assign, loadCoupling, type Coupled } from './arondare';

const DATA = resolve(__dirname, '../public/data');
const REFERENCE = resolve(__dirname, '../../data/arondare-noua.json');

/** Serve `public/data` off the filesystem so the module under test is exercised unchanged. */
function stubFetch(): void {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const name = String(input).replace(/^.*\/data\//, '');
    const bytes = readFileSync(resolve(DATA, name));
    return {
      ok: true,
      json: async () => JSON.parse(bytes.toString('utf8')) as unknown,
      arrayBuffer: async () =>
        bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    };
  }) as typeof fetch;
}

describe('the browser arondare against the Python reference', () => {
  let coupled: Coupled;
  let reference: {
    summary: Record<string, number>;
    units: { crossesCounty: boolean; population: number }[];
  };

  beforeAll(async () => {
    stubFetch();
    coupled = await loadCoupling('/');
    reference = JSON.parse(readFileSync(REFERENCE, 'utf8'));
  });

  it('starts from the administrative model’s own defaults, not a retyped copy', () => {
    expect(coupled.defaults).toEqual(DEFAULT_PARAMS);
    expect(coupled.defaults.x).toBe(7_500);
  });

  it('reproduces the reference summary exactly at default parameters', () => {
    const { summary } = assign(coupled, coupled.defaults);
    expect(summary.units).toBe(reference.summary.units);
    expect(summary.routed).toBe(reference.summary.routed);
    expect(summary.crossingCounty).toBe(reference.summary.crossingCounty);
    expect(summary.peopleCrossingCounty).toBe(reference.summary.peopleCrossingCounty);
    expect(summary.wouldSplitByCommune).toBe(reference.summary.wouldSplitByCommune);
    // Every discrete outcome above must match exactly — which court, how many, who crosses.
    // The weighted means are allowed the quantisation the matrix was built with: the browser
    // reads hundreds of metres where Python had metres. That is the claim the encoding makes,
    // and this is where it is checked rather than asserted in a docstring: no assignment
    // moves, and the national mean lands within a rounding step. It currently differs by 1 m.
    const step = 100;
    expect(summary.meanMetresNearest).toBeCloseTo(reference.summary.meanMetresNearest, -2);
    expect(
      Math.abs(summary.meanMetresNearest - reference.summary.meanMetresNearest),
    ).toBeLessThanOrEqual(step);
    expect(
      Math.abs(summary.meanMetresOwnCounty - reference.summary.meanMetresOwnCounty),
    ).toBeLessThanOrEqual(step);
    expect(
      Math.abs(summary.metresSavedEachCrossing - reference.summary.metresSavedEachCrossing),
    ).toBeLessThanOrEqual(step);
  });

  it('gives every commune exactly one court, or none where no road reaches it', () => {
    const { courtOf } = assign(coupled, coupled.defaults);
    expect(courtOf.length).toBe(coupled.data.uatCount);
    const unreachable = [...courtOf].filter((row) => row < 0).length;
    // Eleven communes have no road; eight of them are in the Delta.
    expect(unreachable).toBeGreaterThan(0);
    expect(unreachable).toBeLessThan(30);
  });

  it('never sends a unit further than the court inside its own county', () => {
    const { units } = assign(coupled, coupled.defaults);
    const worse = units.filter(
      (u) => u.metres !== null && u.ownCountyMetres !== null && u.metres > u.ownCountyMetres,
    );
    expect(worse).toEqual([]);
  });

  it('responds to the target population rather than ignoring it', () => {
    // The whole point of computing here rather than shipping a static answer. A larger target
    // means larger units, so there must be fewer of them.
    const small = assign(coupled, { ...coupled.defaults, pTarget: 25_000 }).summary;
    const large = assign(coupled, { ...coupled.defaults, pTarget: 100_000 }).summary;
    expect(small.units).toBeGreaterThan(large.units);
  });

  it('is deterministic', () => {
    const once = assign(coupled, coupled.defaults).summary;
    const twice = assign(coupled, coupled.defaults).summary;
    expect(once).toEqual(twice);
  });
});

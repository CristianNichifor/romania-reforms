/**
 * The candidate report: who could have been a centre, and what became of them.
 *
 * The report is an observation of a run, not an input to one, and the first test here is the
 * one that matters most — asking for it must not change the map. Everything else checks that
 * a state is only ever given to a UAT the rules could actually have given it to, because a
 * label that is merely plausible is worse than no label: this list exists to be argued with,
 * and an argument against a state the model never assigned is an argument about nothing.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

import { decode } from '../src/model/load';
import { candidacyReport, runModel } from '../src/model/model';
import {
  CANDIDACY,
  DEFAULT_PARAMS,
  REASON,
  type ModelData,
  type Params,
} from '../src/model/types';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');

function readBuffer(name: string): ArrayBuffer {
  const buf = readFileSync(resolve(dataDir, name));
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

function readJson<T>(name: string): T {
  return JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')) as T;
}

let data: ModelData;

beforeAll(() => {
  data = decode({
    manifest: readJson('manifest.json'),
    attributes: readJson('attributes.json'),
    attributesBin: readBuffer('attributes.bin'),
    adjacencyBin: readBuffer('adjacency.bin'),
    candidacyBin: readBuffer('candidacy.bin'),
  });
});

/** Counties large enough to have needed promotion at these settings, and ones that did not. */
const CASES: [string, Params][] = [
  ['default', DEFAULT_PARAMS],
  ['every county short, so promotion runs everywhere', { ...DEFAULT_PARAMS, nMin: 10 }],
  ['no county short, so promotion runs nowhere', { ...DEFAULT_PARAMS, nMin: 1 }],
  ['separation off', { ...DEFAULT_PARAMS, nMin: 10, rSepM: 0 }],
];

describe('asking for the report changes nothing', () => {
  it.each(CASES)('leaves the assignment identical: %s', (_name, params) => {
    const before = runModel(data, params).regionOf;
    candidacyReport(data, params);
    const after = runModel(data, params).regionOf;
    expect(Array.from(after)).toEqual(Array.from(before));
  });
});

describe('every centre is accounted for', () => {
  it.each(CASES)('agrees with the reason the model recorded: %s', (_name, params) => {
    const result = runModel(data, params);
    const candidacy = candidacyReport(data, params);

    // Two independent recordings of the same decision: `reasonOf` is written by the growth
    // pass, `candidacyOf` by the selection pass. Where growth says "this is a centre because
    // it is a capital", the report must say capital, and so on. If these ever disagree one
    // of them is describing a run that did not happen.
    //
    // Deliberately not compared against the final `tierOf`: re-seating can move a unit's
    // seat onto a commune that was never selected as a centre, and that commune's candidacy
    // is honestly "eligible, never chosen". Seat and centre are different questions.
    const expected: Record<number, number> = {
      [REASON.CENTRE_CAPITAL]: CANDIDACY.CAPITAL,
      [REASON.CENTRE_THRESHOLD]: CANDIDACY.THRESHOLD,
      [REASON.CENTRE_PROMOTED]: CANDIDACY.PROMOTED,
    };

    let checked = 0;
    for (let i = 0; i < data.uatCount; i += 1) {
      const want = expected[result.reasonOf[i]!];
      if (want === undefined) continue;
      checked += 1;
      expect(candidacy[i]).toBe(want);
    }
    expect(checked).toBeGreaterThan(0);
  });

  it('calls capitals capitals, and nothing else', () => {
    const candidacy = candidacyReport(data, DEFAULT_PARAMS);
    for (let i = 0; i < data.uatCount; i += 1) {
      if (candidacy[i] !== CANDIDACY.CAPITAL) continue;
      expect(data.attributes.isCapital[i]).toBe(true);
    }
  });

  it('only calls a UAT over-threshold when it is over the threshold', () => {
    const params = { ...DEFAULT_PARAMS, x: 10_000 };
    const candidacy = candidacyReport(data, params);
    for (let i = 0; i < data.uatCount; i += 1) {
      if (candidacy[i] !== CANDIDACY.THRESHOLD) continue;
      expect(data.population[i]!).toBeGreaterThanOrEqual(params.x);
    }
  });
});

describe('the ones that did not make it', () => {
  it('reports a stood-down centre as stood down, not as a centre', () => {
    const result = runModel(data, DEFAULT_PARAMS);
    const candidacy = candidacyReport(data, DEFAULT_PARAMS);
    let stoodDown = 0;
    for (let i = 0; i < data.uatCount; i += 1) {
      if (candidacy[i] !== CANDIDACY.STOOD_DOWN) continue;
      stoodDown += 1;
      // Standing down is exactly the loss of the centre role.
      expect(result.tierOf[i]).toBe(-1);
    }
    // Cumpana beside Constanta and the ring around Bucharest: if this is ever zero the rule
    // has stopped firing and the test has stopped meaning anything.
    expect(stoodDown).toBeGreaterThan(0);
  });

  it('never refuses anyone for separation when separation is switched off', () => {
    const candidacy = candidacyReport(data, { ...DEFAULT_PARAMS, nMin: 10, rSepM: 0 });
    expect(candidacy).not.toContain(CANDIDACY.REFUSED_SEPARATION);
  });

  it('refuses nobody for separation in a county that never promoted', () => {
    // With nMin at 1 no county is short, so no county ever consults the separation floor.
    // "Too close to another centre" would be a reason no county actually gave.
    const candidacy = candidacyReport(data, { ...DEFAULT_PARAMS, nMin: 1 });
    expect(candidacy).not.toContain(CANDIDACY.REFUSED_SEPARATION);
  });

  it('does refuse somebody for separation when counties are short and the floor is high', () => {
    const candidacy = candidacyReport(data, { ...DEFAULT_PARAMS, nMin: 10, rSepM: 30_000 });
    expect(candidacy).toContain(CANDIDACY.REFUSED_SEPARATION);
  });

  it('names the capital ring as the reason, rather than calling a town no candidate at all', () => {
    const candidacy = candidacyReport(data, DEFAULT_PARAMS);
    const ADMIN_RANK_ORAS = 3;
    const absorbers = new Set(Array.from(data.absorbers));

    // Nobody eligible by rank or by being an absorber anywhere may be left unlabelled. Those
    // 90 UATs were reported as "not a candidate under any rule", which said the model had
    // never considered them when in fact the capital's ring had refused them.
    const unexplained: string[] = [];
    for (let i = 0; i < data.uatCount; i += 1) {
      if (candidacy[i] !== CANDIDACY.NONE) continue;
      // Bucharest's sectors are not candidates: the city is one centre by construction.
      if (data.countyOf[i] === data.bucharestCounty) continue;
      if (absorbers.has(i) || data.attributes.adminRank[i]! <= ADMIN_RANK_ORAS) {
        unexplained.push(`${data.attributes.name[i]} (${data.attributes.county[i]})`);
      }
    }
    expect(unexplained).toEqual([]);
  });

  it('bars the communes the source names as inside Bucharest’s ring', () => {
    const candidacy = candidacyReport(data, DEFAULT_PARAMS);
    // Cornetu and Ganeasa are the two the model's own comments cite for this rule; each came
    // out a unit of one UAT before it existed.
    for (const name of ['CORNETU', 'GĂNEASA']) {
      const index = data.attributes.name.indexOf(name);
      expect(index, `${name} missing from the payload`).toBeGreaterThanOrEqual(0);
      expect(candidacy[index], name).toBe(CANDIDACY.IN_CAPITAL_RING);
    }
  });

  it('gives a state to more UATs than just the centres', () => {
    // The whole point: the list is longer than the winners, or it is not a rules chart.
    const result = runModel(data, DEFAULT_PARAMS);
    const candidacy = candidacyReport(data, DEFAULT_PARAMS);
    let seeds = 0;
    let labelled = 0;
    for (let i = 0; i < data.uatCount; i += 1) {
      if (result.tierOf[i] !== -1) seeds += 1;
      if (candidacy[i] !== CANDIDACY.NONE) labelled += 1;
    }
    expect(labelled).toBeGreaterThan(seeds);
  });
});

describe('determinism', () => {
  it('gives the same report twice', () => {
    const a = candidacyReport(data, DEFAULT_PARAMS);
    const b = candidacyReport(data, DEFAULT_PARAMS);
    expect(Array.from(a)).toEqual(Array.from(b));
  });
});

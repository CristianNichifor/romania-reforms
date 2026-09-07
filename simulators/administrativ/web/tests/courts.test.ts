/**
 * Judicial circumscriptions, and the units that straddle them.
 *
 * The claim this payload exists to support is that a merger can put one administrative unit
 * across two judecătorii — an argument about a boundary that needs no modelling, because the
 * assignment is published. These tests hold the payload to that: aligned to the UAT order,
 * naming a real court for every index it uses, and covering enough of the country that the
 * "spans two courts" count means something.
 *
 * The 2023 decision predates two communes and does not mention them. That is the decision's
 * own limitation, recorded here as a bound rather than hidden — if it ever grows, the source
 * has drifted from the UAT list and the join is wrong.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const readJson = <T>(n: string): T => JSON.parse(readFileSync(resolve(dataDir, n), 'utf8')) as T;

interface Courts {
  courts: string[];
  courtOf: number[];
  period?: string;
  publisher?: string;
}

let courts: Courts;
let names: string[];
let counties: string[];

beforeAll(() => {
  courts = readJson<Courts>('courts.json');
  const attributes = readJson<{ name: string[]; county: string[] }>('attributes.json');
  names = attributes.name;
  counties = attributes.county;
});

describe('the payload', () => {
  it('carries one entry per UAT, in the UAT order', () => {
    expect(courts.courtOf).toHaveLength(names.length);
  });

  it('names every court index it uses', () => {
    for (let i = 0; i < courts.courtOf.length; i += 1) {
      const c = courts.courtOf[i]!;
      if (c < 0) continue;
      expect(courts.courts[c], `${names[i]}`).toBeTypeOf('string');
      expect(courts.courts[c]!.length).toBeGreaterThan(0);
    }
  });

  it('has a judecătorie for all but the handful the 2023 decision predates', () => {
    const unassigned = courts.courtOf.filter((c) => c < 0).length;
    expect(unassigned).toBeLessThanOrEqual(5);
    expect(names.length - unassigned).toBeGreaterThan(3_100);
  });

  it('has far more courts than counties, which is the level that makes this worth asking', () => {
    // One tribunal per county could never be straddled, since no unit may cross a county line.
    // Judecătorii can be, and there are several per county.
    expect(courts.courts.length).toBeGreaterThan(150);
    expect(new Set(counties).size).toBeLessThan(courts.courts.length);
  });

  it('keeps every circumscription inside one county', () => {
    // A judecătorie spanning two counties would break the reading of the split note: the unit
    // would have to cross a county line to straddle it, and the model forbids that.
    const countiesOf = new Map<number, Set<string>>();
    for (let i = 0; i < courts.courtOf.length; i += 1) {
      const c = courts.courtOf[i]!;
      if (c < 0) continue;
      if (!countiesOf.has(c)) countiesOf.set(c, new Set());
      countiesOf.get(c)!.add(counties[i]!);
    }
    const crossing = [...countiesOf.entries()]
      .filter(([, set]) => set.size > 1)
      .map(([c, set]) => `${courts.courts[c]}: ${[...set].join(', ')}`);
    expect(crossing.slice(0, 5)).toEqual([]);
  });

  it('says where it came from, because the panel cites it', () => {
    expect(courts.publisher).toBeTruthy();
    expect(courts.period).toBeTruthy();
  });
});

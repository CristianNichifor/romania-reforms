import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { asOfForYear, periodForYear, phaseYears, phases, yearOfAsOf } from './phase';
import { structure } from './structure';
import type { Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const BASE: Regime = JSON.parse(
  readFileSync(resolve(here, '../data/regimes/ro-draft-2026-07-16.json'), 'utf8'),
);

describe('the years the draft phases itself over', () => {
  it('reads the phases out of the data, not out of code', () => {
    expect(phases(BASE).map((p) => p.period)).toEqual([
      '2026/2027', '2028', '2029', '2030', '2031',
    ]);
  });

  it('covers the years inside a two-year column', () => {
    // "2026/2027" names its endpoints; a slider that stepped straight from 2026 to 2028
    // would skip a year the law does describe.
    expect(phaseYears(BASE)).toEqual([2026, 2027, 2028, 2029, 2030, 2031]);
    expect(periodForYear(BASE, 2027)).toBe('2026/2027');
  });

  it('keeps the last published column in force after it', () => {
    // The law does not expire in 2032; it stops changing.
    expect(periodForYear(BASE, 2031)).toBe('2031');
    expect(periodForYear(BASE, 2035)).toBe('2031');
  });

  it('reads a year as December, so the reference value has commenced', () => {
    // The reference amount is dated 2026-12-01. Read at 1 January, 2026 would resolve to
    // whatever applied before the law started.
    expect(asOfForYear(2026)).toBe('2026-12-01');
    expect(yearOfAsOf('2028-12-01', 2026)).toBe(2028);
    expect(yearOfAsOf(undefined, 2026)).toBe(2026);
    expect(yearOfAsOf('nonsense', 2026)).toBe(2026);
  });

  it('makes the declared ratio a destination rather than a starting point', () => {
    // This is the whole point of the control: 1:8 is what the grid reaches in 2031, and
    // 1:7,39 is what it is on the day it commences. Both are true; only one is quoted.
    const first = structure(BASE, { period: periodForYear(BASE, 2026)! });
    const last = structure(BASE, { period: periodForYear(BASE, 2031)! });
    expect(first.span.ratio).toBeLessThan(last.span.ratio);
    expect(last.span.ratio).toBeCloseTo(8, 1);
    expect(structure(BASE).span.ratio).toBeCloseTo(last.span.ratio, 6);
  });

  it('keeps every position that carries no year at all', () => {
    // Only Annex IX is phased. Restricting to a period must not drop the rest of the grid.
    const all = structure(BASE).positions;
    const one = structure(BASE, { period: '2028' }).positions;
    expect(one).toBeGreaterThan(all - 20);
  });
});

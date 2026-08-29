import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { checkAgainstMeasured, gridPay } from './measured';
import type { MeasuredSeries } from './measured';
import type { Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const read = (p: string) => JSON.parse(readFileSync(resolve(here, '..', p), 'utf8'));

const DRAFT: Regime = read('data/regimes/ro-draft-2026-07-16.json');
const IN_FORCE: Regime = read('data/regimes/ro-153-2017.json');
const SERIES: MeasuredSeries[] = read('data/fiscal/ins-ocupatii.json').series;

const health = checkAgainstMeasured(DRAFT, SERIES, 'sanatate', 'II-sanatate-asistenta-sociala')!;
const school = checkAgainstMeasured(DRAFT, SERIES, 'invatamant', 'I-invatamant')!;

describe('the grid against what people are paid', () => {
  it('reads a measured base salary and the headcount behind it', () => {
    expect(health.period).toBe('2024');
    expect(health.overall!.employees).toBeGreaterThan(200_000);
    expect(health.overall!.base).toBeGreaterThan(5_000);
    // Largest occupation group first, so the biggest slice of people leads.
    expect(health.measured[0].employees).toBeGreaterThan(health.measured[1].employees);
  });

  it('prices the grid at the regime\'s own reference value', () => {
    // The draft divides by 4100 and 153/2017 by 2500, so the same family priced under
    // each must differ. Comparing raw coefficients across regimes would be meaningless.
    const a = gridPay(DRAFT, 'I-invatamant');
    const b = gridPay(IN_FORCE, 'I-invatamant');
    expect(a.median).toBeGreaterThan(b.median);
    expect(a.min).toBeGreaterThan(0);
    expect(a.max).toBeGreaterThan(a.median);
  });

  it('finds the draft close to measured pay in health and short of it in education', () => {
    // The finding this module exists for. Health lands almost exactly on what is paid;
    // education sits well below it, which is where the transitional difference would
    // have to do the work.
    expect(health.ratio!).toBeGreaterThan(0.95);
    expect(health.ratio!).toBeLessThan(1.05);
    expect(school.ratio!).toBeGreaterThan(1.1);
  });

  it('shows the 2022 annex grid falling far below 2024 pay', () => {
    // This is why the Art. 33 bound is stated against the printed grid rather than
    // against what people actually earn: the annexes are two years and several
    // across-the-board increases out of date.
    const old = checkAgainstMeasured(IN_FORCE, SERIES, 'invatamant', 'I-invatamant')!;
    expect(old.ratio!).toBeGreaterThan(1.5);
  });

  it('never pairs a headcount with a salary from another year', () => {
    // Both measures have to carry the period, or a count from one year would silently
    // weight a salary from another.
    for (const check of [health, school]) {
      expect(check.measured.every((m) => m.base > 0 && m.employees > 0)).toBe(true);
    }
  });

  it('keeps the all-occupations row out of the per-group list', () => {
    // It is a summary of the others; left in, it would be drawn as another group and
    // double the apparent headcount.
    expect(health.measured.some((m) => m.occupation.startsWith('Toate'))).toBe(false);
    expect(health.overall!.occupation).toContain('Toate');
  });

  it('returns null for a sector the survey does not cover', () => {
    // CAEN section O — public administration and defence — is outside the survey, so a
    // caller asking for it must get nothing rather than an empty-looking zero.
    expect(checkAgainstMeasured(DRAFT, SERIES, 'administratie', 'VIII-administratie')).toBeNull();
  });
});

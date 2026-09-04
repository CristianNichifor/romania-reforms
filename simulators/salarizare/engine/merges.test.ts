/**
 * The cards, checked against the real documents rather than a fixture.
 *
 * What matters here is not that the arithmetic divides — `payslip` is tested for that —
 * but that an absence stays an absence. The old pay is known for 227 links out of 1 031
 * positions and the Danish figure only where an occupation group reaches, so the easy bug
 * is a card that quietly shows a number it does not have.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { byFanIn, mergeCards } from './merges';
import type { DkOccupation, GroupsDocument } from './occupations';
import type { Crosswalk, Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const read = (path: string) => JSON.parse(readFileSync(resolve(here, '..', path), 'utf8'));

const DRAFT: Regime = read('data/regimes/ro-draft-2026-07-16.json');
const IN_FORCE: Regime = read('data/regimes/ro-153-2017.json');
const CROSSWALK: Crosswalk = read('data/crosswalks/ro-153-2017--ro-draft-2026-07-16.json');
const GROUPS: GroupsDocument = read('data/groups/ro-dk-occupations.json');
// The quartiles are published as three series per occupation. Folded here the way the app
// folds them, because a test that reshaped the data its own way would be testing a shape
// nothing else produces.
const DANISH: DkOccupation[] = (() => {
  const byOccupation = new Map<string, DkOccupation>();
  for (const series of read('data/fiscal/dk-occupations.json').series) {
    if (series.dims.kind !== 'occupation') continue;
    const name = series.dims.occupation as string;
    const entry = byOccupation.get(name) ?? { occupation: name, q1: 0, median: 0, q3: 0 };
    (entry as unknown as Record<string, number>)[series.dims.quartile] =
      series.observations.at(-1)?.value ?? 0;
    byOccupation.set(name, entry);
  }
  return [...byOccupation.values()];
})();

const cards = mergeCards({
  draft: DRAFT,
  ours: null,
  inForce: IN_FORCE,
  crosswalk: CROSSWALK,
  groups: GROUPS,
  danish: DANISH,
});

describe('mergeCards', () => {
  it('produces one card per position in the draft', () => {
    expect(cards).toHaveLength(DRAFT.positions.length);
  });

  it('prices the draft for every card it can', () => {
    const priced = cards.filter((c) => c.draft !== null);
    expect(priced.length).toBeGreaterThan(DRAFT.positions.length * 0.9);
  });

  it('leaves the old pay null where the crosswalk does not reach', () => {
    // The mapping Art. 32 requires was never published, so most positions have no
    // predecessor. That has to read as "not known", never as zero.
    const withOld = cards.filter((c) => c.inForce !== null);
    expect(withOld.length).toBeGreaterThan(0);
    expect(withOld.length).toBeLessThan(cards.length);
    expect(cards.every((c) => c.inForce === null || c.inForce > 0)).toBe(true);
  });

  it('leaves the Danish figure null outside the occupation groups', () => {
    const withDk = cards.filter((c) => c.dk !== null);
    expect(withDk.length).toBeGreaterThan(0);
    expect(withDk.length).toBeLessThan(cards.length);
    for (const card of withDk) {
      expect(card.dk!.q1).toBeLessThanOrEqual(card.dk!.median);
      expect(card.dk!.median).toBeLessThanOrEqual(card.dk!.q3);
    }
  });

  it('counts a fan-in of at least one, and finds real merges', () => {
    expect(cards.every((c) => c.fanIn >= 1)).toBe(true);
    // The whole point of the page: some cells collapsed many titles into one job.
    expect(cards.some((c) => c.fanIn > 3)).toBe(true);
  });

  it('carries every merged title rather than a count of them', () => {
    const merged = byFanIn(cards)[0];
    expect(merged.titles.length).toBeGreaterThan(1);
    expect(merged.titles.every((t) => t.length > 0)).toBe(true);
  });

  it('reports no delta when our proposal is not loaded', () => {
    expect(cards.every((c) => c.delta === null)).toBe(true);
  });

  it('sorts the biggest merges first', () => {
    const sorted = byFanIn(cards);
    expect(sorted[0].fanIn).toBeGreaterThanOrEqual(sorted[sorted.length - 1].fanIn);
  });
});

/**
 * The regrouping is an editorial act, so it is the part of this codebase most able to
 * mislead quietly: a rule that catches nothing renders as an empty row, and a rule that
 * catches too much renders as a confident range over the wrong jobs. These tests pin the
 * rules that were actually wrong at some point.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { resolveGroups } from './occupations';
import type { DkOccupation, GroupsDocument } from './occupations';
import type { Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const load = (p: string) => JSON.parse(readFileSync(resolve(here, '../data', p), 'utf8'));

const REGIME: Regime = load('regimes/ro-draft-2026-07-16.json');
const GROUPS: GroupsDocument = load('groups/ro-dk-occupations.json');

const DK: DkOccupation[] = (() => {
  const byOcc = new Map<string, DkOccupation>();
  for (const s of load('fiscal/dk-occupations.json').series) {
    const name = s.dims.occupation as string;
    const entry = byOcc.get(name) ?? { occupation: name, q1: 0, median: 0, q3: 0 };
    if (s.dims.kind !== 'composition' && s.dims.kind !== 'composition-subitem') {
      (entry as unknown as Record<string, number>)[s.dims.quartile] = s.observations.at(-1)?.value ?? 0;
    }
    byOcc.set(name, entry);
  }
  return [...byOcc.values()];
})();

const rows = resolveGroups(REGIME, GROUPS, DK, { roPublicAverage: 8000, dkPublicMedian: 45000 });
const byId = new Map(rows.map((r) => [r.group.id, r]));

describe('the occupation groups', () => {
  it('every group catches something', () => {
    // An empty group is worse than a missing one: it renders as a row of dashes that
    // reads as "this occupation earns nothing" rather than "this rule matched nobody".
    const empty = rows.filter((r) => r.matched.length === 0).map((r) => r.group.id);
    expect(empty).toEqual([]);
  });

  it('a trade can span more than one annex', () => {
    // The whole point of the driver group. Before the rule took a list of families it
    // could only name one, which meant either dropping the ambulance drivers or
    // pretending they are a different occupation from the town hall's driver.
    const drivers = byId.get('soferi')!;
    const families = new Set(
      drivers.matched.map((m) => REGIME.positions.find((p) => p.code === m.code)!.family),
    );
    expect(families.size).toBeGreaterThan(1);
    expect(families).toContain('II-sanatate-asistenta-sociala');
    expect(families).toContain('VIII-administratie');
  });

  it('a single-family rule still means exactly one family', () => {
    const medics = byId.get('medici')!;
    for (const m of medics.matched) {
      const position = REGIME.positions.find((p) => p.code === m.code)!;
      expect(position.family).toBe('II-sanatate-asistenta-sociala');
    }
  });

  it('the bottom of the grid is on the page', () => {
    // The floor coefficient is 1,00 and it belongs to a cleaner, a porter and an unskilled
    // worker. For as long as no group covered them, the page's lowest Romanian bar was a
    // clerk's, and the grid looked narrower at the bottom than it is.
    const support = byId.get('curatenie-paza-suport')!;
    const lowest = Math.min(...rows.map((r) => r.roMin ?? Infinity));
    expect(support.roMin).toBe(lowest);
  });

  it('a group with no Danish comparator says so instead of borrowing one', () => {
    // LONSOFF publishes no driver or manual-trade group. Filling the row from the nearest
    // occupation would be the easiest invented comparison in the project.
    for (const id of ['soferi', 'meserii-calificate', 'curatenie-paza-suport']) {
      const row = byId.get(id)!;
      expect(row.group.dkOccupations).toEqual([]);
      expect(row.dk, `${id} must not acquire a comparator`).toBeNull();
      expect(row.dkRatio, id).toBeNull();
      expect(row.group.confidence, id).toBe('assumed');
      expect(row.group.disputed, id).toBe(true);
    }
  });

  it('every group states the rule that selected it', () => {
    for (const row of rows) {
      expect(row.group.basis, `${row.group.id} must say what it caught and why`).toBeTruthy();
      expect(row.group.basis.length, row.group.id).toBeGreaterThan(25);
    }
  });
});

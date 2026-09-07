/**
 * Statutory representation.
 *
 * These are numbers from a law, so the tests are mostly the law: every band boundary in
 * Art. 112, checked on both sides. A band read one person wide of the statute is the kind of
 * error that looks completely plausible on screen and is wrong in a way nobody catches, which
 * is exactly why the boundaries and not the middles are what is asserted here.
 */

import { describe, expect, it } from 'vitest';

import {
  BUCHAREST_COUNCIL,
  councillorsFor,
  danishBandFor,
  representationAfter,
  representationBefore,
  viceMayorsFor,
} from '../src/model/representation';

describe('Art. 112 — councillors by population', () => {
  // Each row is the top of a band and the first person into the next one.
  it.each([
    [1, 9],
    [1_500, 9],
    [1_501, 11],
    [3_000, 11],
    [3_001, 13],
    [5_000, 13],
    [5_001, 15],
    [10_000, 15],
    [10_001, 17],
    [20_000, 17],
    [20_001, 19],
    [50_000, 19],
    [50_001, 21],
    [100_000, 21],
    [100_001, 23],
    [200_000, 23],
    [200_001, 27],
    [400_000, 27],
    [400_001, 31],
    [2_000_000, 31],
  ])('a unit of %i elects %i councillors', (population, expected) => {
    expect(councillorsFor(population)).toBe(expected);
  });

  it('never returns an even number', () => {
    // Not required by Art. 112 in so many words, but true of every band in it, and a council
    // that can tie is a drafting error rather than a design.
    for (let p = 0; p < 500_000; p += 997) {
      expect(councillorsFor(p) % 2).toBe(1);
    }
  });

  it('treats an absent or nonsensical population as the smallest band', () => {
    expect(councillorsFor(0)).toBe(9);
    expect(councillorsFor(-5)).toBe(9);
  });

  it('does not apply the bands to Bucharest', () => {
    // The Consiliul General is fixed at 55 by statute, not banded. Applying the top band
    // would report 31 and be quietly wrong.
    expect(BUCHAREST_COUNCIL).toBe(55);
    expect(councillorsFor(1_800_000)).not.toBe(BUCHAREST_COUNCIL);
  });
});

describe('Art. 148 — mayors and vice-mayors', () => {
  it('gives a county capital two vice-mayors and everyone else one', () => {
    expect(viceMayorsFor(true)).toBe(2);
    expect(viceMayorsFor(false)).toBe(1);
  });
});

describe('what a merger removes', () => {
  const commune = (population: number) => ({ population, isCountyCapital: false });

  it('adds up the communes as they are today', () => {
    // Four communes of 3,000: four town halls, four mayors, 4 x 11 councillors.
    const before = representationBefore([3_000, 3_000, 3_000, 3_000].map(commune));
    expect(before).toEqual({ councillors: 44, mayors: 4, viceMayors: 4 });
  });

  it('leaves one of each, and a council sized on the merged population', () => {
    // The same 12,000 people in one unit fall in the 10,001-20,000 band.
    const after = representationAfter(12_000, false);
    expect(after).toEqual({ councillors: 17, mayors: 1, viceMayors: 1 });
  });

  it('is the real Sarichioi case', () => {
    // The unit forcing SARICHIOI produces, with the populations the payload actually carries:
    // Sarichioi 5,226, Jurilovca 3,694, Murighiol 2,959, Valea Nucarilor 2,892 — 14,771
    // between them, which is the figure the model reports for that unit.
    const members = [5_226, 3_694, 2_959, 2_892].map(commune);
    const total = members.reduce((sum, m) => sum + m.population, 0);
    expect(total).toBe(14_771);

    const before = representationBefore(members);
    const after = representationAfter(total, false);

    // Four town halls become one.
    expect(before.mayors).toBe(4);
    expect(after.mayors).toBe(1);
    expect(before.viceMayors).toBe(4);
    expect(after.viceMayors).toBe(1);
    // 15 + 13 + 11 + 11 today, against 17 for a unit of 14,771.
    expect(before.councillors).toBe(50);
    expect(after.councillors).toBe(17);
  });

  it('keeps the two vice-mayors when the unit is seated on a county capital', () => {
    expect(representationAfter(300_000, true).viceMayors).toBe(2);
  });

  it('counts a county capital among the members correctly', () => {
    const before = representationBefore([
      { population: 250_000, isCountyCapital: true },
      commune(4_000),
    ]);
    expect(before.viceMayors).toBe(3);
    expect(before.mayors).toBe(2);
  });
});

describe('the Danish comparator', () => {
  it('is a band, because Denmark has no formula to copy', () => {
    // Kommunestyrelsesloven § 5 leaves the number to each municipality's own statute.
    expect(danishBandFor(5_000)).toEqual({ min: 9, max: 31 });
    expect(danishBandFor(60_000)).toEqual({ min: 19, max: 31 });
  });

  it('puts exactly 20,000 in the lower band', () => {
    // The statute says "over 20.000" and "under 20.000", so 20,000 itself is in neither.
    // The lower band is the reading that does not invent a constraint.
    expect(danishBandFor(20_000)).toEqual({ min: 9, max: 31 });
    expect(danishBandFor(20_001)).toEqual({ min: 19, max: 31 });
  });
});

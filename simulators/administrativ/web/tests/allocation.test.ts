/**
 * Seat allocation under Legea 115/2015.
 *
 * Worked by hand from the law rather than from the implementation, because a test that only
 * agrees with the code it tests proves the code is consistent, not correct. Each case below
 * states the coefficient and the arithmetic it implies.
 *
 * The threshold is where the interesting behaviour is. It is the rule that makes merging cost
 * small lists their seats, so it is the rule most worth being sure of.
 */

import { describe, expect, it } from 'vitest';

import {
  allocateSeats,
  representationShift,
  thresholdFor,
  type SeatAward,
} from '../src/model/allocation';

const seatsOf = (awards: SeatAward[]): Record<number, number> =>
  Object.fromEntries(awards.map((a) => [a.party, a.seats]));

describe('the threshold', () => {
  it('is 5% for a single party, 7% for a pair, 8% for three or more', () => {
    expect(thresholdFor(1)).toBeCloseTo(0.05);
    expect(thresholdFor(2)).toBeCloseTo(0.07);
    expect(thresholdFor(3)).toBeCloseTo(0.08);
    expect(thresholdFor(9)).toBeCloseTo(0.08);
  });
});

describe('the coefficient and the first pass', () => {
  it('gives each list the whole coefficients its votes contain', () => {
    // 1,000 votes, 10 seats -> coefficient 100. 550/100 = 5, 300/100 = 3, 150/100 = 1.
    // Nine seats by whole coefficients; the tenth goes to the largest remainder.
    const awards = allocateSeats(
      [
        { party: 0, votes: 550 },
        { party: 1, votes: 300 },
        { party: 2, votes: 150 },
      ],
      10,
    );
    // Unused after the first pass: 50, 0, 50. Party 0 and 2 tie on 50; party 0 has more votes.
    expect(seatsOf(awards)).toEqual({ 0: 6, 1: 3, 2: 1 });
    expect(awards.reduce((n, a) => n + a.seats, 0)).toBe(10);
  });

  it('takes the coefficient as a whole number, discarding the decimals', () => {
    // 1,007 votes, 10 seats -> 100.7 truncated to 100, not rounded to 101.
    const awards = allocateSeats([{ party: 0, votes: 1_007 }], 10);
    expect(awards[0]!.seats).toBe(10);
  });

  it('always fills the council exactly', () => {
    for (const seats of [9, 11, 13, 15, 17, 19, 21, 23, 27, 31]) {
      const awards = allocateSeats(
        [
          { party: 0, votes: 4_321 },
          { party: 1, votes: 2_222 },
          { party: 2, votes: 1_111 },
          { party: 3, votes: 999 },
        ],
        seats,
      );
      expect(awards.reduce((n, a) => n + a.seats, 0), `${seats} seats`).toBe(seats);
    }
  });
});

describe('the threshold excludes, and that is the point', () => {
  it('gives nothing to a list under 5%, however close', () => {
    // 10,000 votes total; party 2 has 499, which is 4.99%.
    const awards = allocateSeats(
      [
        { party: 0, votes: 6_000 },
        { party: 1, votes: 3_501 },
        { party: 2, votes: 499 },
      ],
      15,
    );
    expect(awards.find((a) => a.party === 2)!.belowThreshold).toBe(true);
    expect(awards.find((a) => a.party === 2)!.seats).toBe(0);
    // Its seats do not vanish: the council is still full.
    expect(awards.reduce((n, a) => n + a.seats, 0)).toBe(15);
  });

  it('admits a list at exactly the threshold', () => {
    const awards = allocateSeats(
      [
        { party: 0, votes: 9_500 },
        { party: 1, votes: 500 },
      ],
      10,
    );
    expect(awards.find((a) => a.party === 1)!.belowThreshold).toBe(false);
  });

  it('holds an alliance to a higher bar than a single party', () => {
    // 6% of the vote: enough alone, not enough for a pair.
    const alone = allocateSeats(
      [
        { party: 0, votes: 9_400 },
        { party: 1, votes: 600, allianceSize: 1 },
      ],
      10,
    );
    const paired = allocateSeats(
      [
        { party: 0, votes: 9_400 },
        { party: 1, votes: 600, allianceSize: 2 },
      ],
      10,
    );
    expect(alone.find((a) => a.party === 1)!.belowThreshold).toBe(false);
    expect(paired.find((a) => a.party === 1)!.belowThreshold).toBe(true);
  });

  it('divides by the votes for all lists, including those excluded', () => {
    // The law says the coefficient comes from the total for all lists. With 10,000 votes and
    // 10 seats the coefficient is 1,000 whether or not party 2 qualifies — if only qualifying
    // votes counted it would be 950 and party 0 would take an extra seat in the first pass.
    const awards = allocateSeats(
      [
        { party: 0, votes: 5_000 },
        { party: 1, votes: 4_500 },
        { party: 2, votes: 500 },
      ],
      10,
    );
    expect(seatsOf(awards)).toEqual({ 0: 5, 1: 5, 2: 0 });
  });
});

describe('degenerate elections', () => {
  it('awards nothing when nobody voted', () => {
    const awards = allocateSeats([{ party: 0, votes: 0 }], 11);
    expect(awards.every((a) => a.seats === 0)).toBe(true);
  });

  it('leaves the council empty rather than inventing a winner when no list qualifies', () => {
    // Twenty-one lists at 1/21 each: every one under 5%. A strange election, and the honest
    // answer is that this rule fills no seats, not that the largest list takes them all.
    const lists = Array.from({ length: 21 }, (_, i) => ({ party: i, votes: 100 }));
    const awards = allocateSeats(lists, 15);
    expect(awards.every((a) => a.belowThreshold)).toBe(true);
    expect(awards.reduce((n, a) => n + a.seats, 0)).toBe(0);
  });

  it('is deterministic when two lists tie exactly', () => {
    const once = allocateSeats([{ party: 0, votes: 500 }, { party: 1, votes: 500 }], 9);
    const twice = allocateSeats([{ party: 1, votes: 500 }, { party: 0, votes: 500 }], 9);
    expect(seatsOf(once)).toEqual(seatsOf(twice));
    expect(once.reduce((n, a) => n + a.seats, 0)).toBe(9);
  });
});

describe('what merging costs a small list', () => {
  it('names the party that held seats and now holds none', () => {
    // A local list dominant in a small commune, pooled with a much larger neighbour.
    const small = allocateSeats(
      [
        { party: 0, votes: 400 },
        { party: 9, votes: 600 },
      ],
      9,
    );
    const large = allocateSeats(
      [
        { party: 0, votes: 18_000 },
        { party: 1, votes: 6_000 },
      ],
      17,
    );
    const merged = allocateSeats(
      [
        { party: 0, votes: 18_400 },
        { party: 1, votes: 6_000 },
        { party: 9, votes: 600 },
      ],
      19,
    );

    const shift = representationShift([small, large], merged);
    // Party 9 held a majority of a nine-seat council and is now under 5% of 25,000 votes.
    expect(shift.before.get(9)).toBeGreaterThan(0);
    expect(shift.after.get(9)).toBeUndefined();
    expect(shift.losesAllSeats).toContain(9);
    expect(shift.newlyBelowThreshold).toContain(9);
  });

  it('does not report a loss for a party that keeps seats', () => {
    const a = allocateSeats([{ party: 0, votes: 1_000 }], 9);
    const b = allocateSeats([{ party: 0, votes: 2_000 }], 11);
    const merged = allocateSeats([{ party: 0, votes: 3_000 }], 15);
    const shift = representationShift([a, b], merged);
    expect(shift.losesAllSeats).toEqual([]);
    expect(shift.newlyBelowThreshold).toEqual([]);
  });
});

/**
 * The allocation, against every real election in the country.
 *
 * Two things built separately have to agree here, and neither knows about the other:
 *
 *  - `representation.ts` says how many councillors a commune of a given population elects,
 *    from Art. 112 of the Codul administrativ.
 *  - `allocation.ts` says how those seats are distributed, from Legea 115/2015.
 *
 * Run the second over the 2020 votes with the first supplying the seat count, and the seats
 * awarded must come to exactly the seats available — in all 3,186 communes, independently. If
 * either implementation is wrong the totals diverge, and the failure names the communes.
 *
 * That is a far stronger check than any hand-built fixture, and it costs one pass over a
 * 153 KB payload.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

import { allocateSeats, type VoteList } from '../src/model/allocation';
import { councillorsFor } from '../src/model/representation';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const readJson = <T>(n: string): T => JSON.parse(readFileSync(resolve(dataDir, n), 'utf8')) as T;

interface Votes {
  mandate: string;
  parties: string[];
  partyOf: number[][];
  votesOf: number[][];
}

let votes: Votes;
let population: Uint32Array;
let names: string[];
let counties: string[];

beforeAll(() => {
  votes = readJson<Votes>('votes.json');
  const attributes = readJson<{ name: string[]; county: string[] }>('attributes.json');
  names = attributes.name;
  counties = attributes.county;
  const buf = readFileSync(resolve(dataDir, 'attributes.bin'));
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
  population = new Uint32Array(ab, 0, names.length);
});

const listsFor = (i: number): VoteList[] =>
  votes.partyOf[i]!.map((party, k) => ({ party, votes: votes.votesOf[i]![k]! }));

describe('the payload itself', () => {
  it('covers every UAT and keeps its arrays aligned', () => {
    expect(votes.partyOf).toHaveLength(names.length);
    expect(votes.votesOf).toHaveLength(names.length);
    for (let i = 0; i < names.length; i += 1) {
      expect(votes.partyOf[i]!.length, names[i]).toBe(votes.votesOf[i]!.length);
    }
  });

  it('names every party index it uses', () => {
    for (const row of votes.partyOf) {
      for (const p of row) expect(votes.parties[p]).toBeTypeOf('string');
    }
  });

  it('says which mandate it is, because it is not the current one', () => {
    expect(votes.mandate).toBe('2020-2024');
  });
});

describe('allocation over all 3,186 real elections', () => {
  it('fills exactly the council Art. 112 provides for', () => {
    const wrong: string[] = [];
    let checked = 0;
    let noQualifier = 0;

    for (let i = 0; i < names.length; i += 1) {
      const lists = listsFor(i);
      if (lists.length === 0) continue;
      const seats = councillorsFor(population[i]!);
      const awards = allocateSeats(lists, seats);
      const given = awards.reduce((n, a) => n + a.seats, 0);

      // An election where no list clears its threshold fills nothing, by the rule. Counted
      // rather than excused, because a large count would mean the threshold is misread.
      if (awards.every((a) => a.belowThreshold)) {
        noQualifier += 1;
        continue;
      }
      checked += 1;
      if (given !== seats) {
        wrong.push(`${names[i]} (${counties[i]}): ${given} of ${seats}`);
      }
    }

    expect(checked).toBeGreaterThan(3_000);
    expect(wrong.slice(0, 10)).toEqual([]);
    expect(wrong).toHaveLength(0);
    // If this ever grows, the threshold rule is wrong rather than the country strange.
    expect(noQualifier).toBeLessThan(20);
  });

  it('never awards a seat to a list under its threshold', () => {
    const wrong: string[] = [];
    for (let i = 0; i < names.length; i += 1) {
      const lists = listsFor(i);
      if (lists.length === 0) continue;
      for (const a of allocateSeats(lists, councillorsFor(population[i]!))) {
        if (a.belowThreshold && a.seats > 0) wrong.push(`${names[i]}: ${votes.parties[a.party]}`);
      }
    }
    expect(wrong.slice(0, 5)).toEqual([]);
  });

  it('gives the largest list at least as many seats as any smaller one', () => {
    // Monotonicity: more votes cannot mean fewer seats under this rule. A violation would be
    // a bug in the remainder pass, and it is the kind that hides in the tail.
    const wrong: string[] = [];
    for (let i = 0; i < names.length; i += 1) {
      const lists = listsFor(i);
      if (lists.length < 2) continue;
      const awards = allocateSeats(lists, councillorsFor(population[i]!)).filter(
        (a) => !a.belowThreshold,
      );
      for (const a of awards) {
        for (const b of awards) {
          if (a.votes > b.votes && a.seats < b.seats) {
            wrong.push(`${names[i]}: ${a.votes}v/${a.seats}s vs ${b.votes}v/${b.seats}s`);
          }
        }
      }
    }
    expect(wrong.slice(0, 5)).toEqual([]);
  });
});

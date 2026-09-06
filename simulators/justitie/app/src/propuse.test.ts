/**
 * Tests for routing today's caseload onto courts that do not exist.
 *
 * The output is unfalsifiable by inspection — every proposed court gets a plausible caseload for
 * a plausible population, whatever the routing did. So the tests fix the cases where a wrong
 * answer and a right one look alike:
 *
 *   * a court split between two seats must divide, not go whole to one of them
 *   * a court that is not split must be immune to the population weighting entirely, which is
 *     the claim `cotaInvarianta` makes
 *   * a court the crawl did not finish must not be routed at all, or its handful of cases drags
 *     a seat's median toward whatever they happened to be
 *   * the UAT indices are positions in an array, so a payload of a different size must throw
 *     rather than address the wrong communes
 */

import { describe, expect, it } from 'vitest';
import { proposedCourts, type ArondareInstante } from './propuse';
import type { Court, CourtsFile, Edges } from './aggregate';
import type { Arondare, Coupled } from './arondare';

const EDGES: Edges = {
  termene: [0, 7, 14, 28],
  durata: [0, 30, 60, 90],
  peRol: [0, 90, 180, 365],
};

function court(institutie: string, dosare: number, truncated = false): Court {
  return {
    institutie,
    nume: institutie,
    level: 'judecătorie',
    judet: 'TM',
    siruta: '1',
    acoperire: { volumCsm: 1000, raportFataDeVolum: truncated ? 0.004 : 1.5, trunchiat: truncated },
    dosare,
    dosarePenale: 0,
    sectii: 1,
    completuri: 10,
    peCategorie: { Civil: dosare },
    amanari: {
      termeneCuSolutie: dosare * 2,
      amanareCauza: dosare,
      amanarePronuntare: 0,
      termenPreschimbat: 0,
    },
    peRol: [dosare, 0, 0, 0],
    primulTermen: [dosare, 0, 0, 0],
    intervalTermene: [dosare, 0, 0, 0],
    durata: { dosare, urmarireZile: 90, evenimente: [dosare, 0, 0, 0], cenzurate: [0, 0, 0, 0] },
  };
}

/** Four communes: 0 and 1 reach seat 0, 2 and 3 reach seat 1. */
function scene(populations: number[], seats: number[]) {
  const coupled = {
    data: { uatCount: populations.length, population: populations },
    meta: {
      courts: [
        { county: 'TM', siruta: 'a', name: 'Seat A' },
        { county: 'AR', siruta: 'b', name: 'Seat B' },
      ],
    },
  } as unknown as Coupled;

  const arondare = {
    courtOf: Int16Array.from(seats),
    units: seats.map((seat, index) => ({
      seatIndex: index,
      name: `u${index}`,
      county: 'TM',
      members: 1,
      population: populations[index] ?? 0,
      courtRow: seat,
      metres: 0,
      ownCountyMetres: 0,
      crossesCounty: false,
    })),
  } as unknown as Arondare;

  return { coupled, arondare };
}

const file = (courts: Court[]) =>
  ({ instante: courts, praguriZile: EDGES } as unknown as CourtsFile);

const communes = (entries: { institutie: string; uat: number[] }[], uatCount = 4): ArondareInstante => ({
  summary: { uatCount },
  instante: entries.map((entry) => ({ ...entry, grad: 'judecatorie', judet: 'TM' })),
});

describe('proposedCourts', () => {
  it('splits a court between the seats its communes reach', () => {
    // Three quarters of the population is in the two communes that reach seat A.
    const { coupled, arondare } = scene([300, 300, 100, 100], [0, 0, 1, 1]);
    const result = proposedCourts(
      arondare,
      coupled,
      communes([{ institutie: 'J', uat: [0, 1, 2, 3] }]),
      file([court('J', 1000)]),
      EDGES,
    );
    const a = result.courts.find((c) => c.seat === 0);
    const b = result.courts.find((c) => c.seat === 1);
    expect(a?.pooled.dosare).toBeCloseTo(750, 6);
    expect(b?.pooled.dosare).toBeCloseTo(250, 6);
    // Nothing arrived whole, so none of this survives a different weighting.
    expect(result.cotaInvariantaNationala).toBe(0);
  });

  it('gives an undivided court entirely to one seat, whatever the weights', () => {
    // The claim behind cotaInvarianta: when every commune lands together, the population split
    // has no effect at all. Two very different weightings, one answer.
    for (const populations of [
      [10, 10, 10, 10],
      [1, 999, 5, 5],
    ]) {
      const { coupled, arondare } = scene(populations, [0, 0, 0, 0]);
      const result = proposedCourts(
        arondare,
        coupled,
        communes([{ institutie: 'J', uat: [0, 1, 2, 3] }]),
        file([court('J', 1000)]),
        EDGES,
      );
      expect(result.courts).toHaveLength(1);
      expect(result.courts[0]?.pooled.dosare).toBeCloseTo(1000, 6);
      expect(result.courts[0]?.cotaInvarianta).toBe(1);
    }
  });

  it('does not route a court the crawl did not finish', () => {
    // 69 cases from a court that files 20.000 a year is not a small court, it is an unmeasured
    // one, and blending it in would pull the seat's every ratio toward those 69.
    const { coupled, arondare } = scene([10, 10, 10, 10], [0, 0, 0, 0]);
    const result = proposedCourts(
      arondare,
      coupled,
      communes([
        { institutie: 'J', uat: [0, 1] },
        { institutie: 'BAD', uat: [2, 3] },
      ]),
      file([court('J', 1000), court('BAD', 69, true)]),
      EDGES,
    );
    expect(result.trunchiate).toBe(1);
    expect(result.courts[0]?.pooled.dosare).toBeCloseTo(1000, 6);
  });

  it('counts a court no road reaches rather than dropping it silently', () => {
    // Eight of the eleven unreachable communes are in the Delta. A court whose whole territory
    // is unroutable has to be reported, not absorbed into a rounding difference.
    const { coupled, arondare } = scene([10, 10, 10, 10], [-1, -1, 0, 0]);
    const result = proposedCourts(
      arondare,
      coupled,
      communes([
        { institutie: 'DELTA', uat: [0, 1] },
        { institutie: 'J', uat: [2, 3] },
      ]),
      file([court('DELTA', 500), court('J', 1000)]),
      EDGES,
    );
    expect(result.nerutate).toBe(1);
    expect(result.courts).toHaveLength(1);
  });

  it('refuses a payload that addresses a different number of communes', () => {
    // The commune lists are array positions. A model rebuilt with more or fewer units would make
    // every index point somewhere else — still a valid index, still a plausible court, wrong.
    const { coupled, arondare } = scene([10, 10, 10, 10], [0, 0, 0, 0]);
    expect(() =>
      proposedCourts(
        arondare,
        coupled,
        communes([{ institutie: 'J', uat: [0] }], 3186),
        file([court('J', 1000)]),
        EDGES,
      ),
    ).toThrow(/3186/);
  });
});

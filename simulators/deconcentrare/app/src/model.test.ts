import { describe, expect, it } from 'vitest';
import {
  TIER_LABELS,
  filtered,
  reduction,
  regionsOf,
  sortBy,
  type Document,
  type Family,
} from './model';

const family = (over: Partial<Family>): Family => ({
  code: 'cas',
  name: 'Casa de Asigurări de Sănătate',
  tier: 'regional',
  officesToday: 42,
  officesProposed: 8,
  counties: ['AB', 'AR'],
  regions: [
    { region: 'Centru', seat: 'AB', seatPopulation: 363660, counties: ['AB'] },
    { region: 'Vest', seat: 'AR', seatPopulation: 409000, counties: ['AR'] },
  ],
  ...over,
});

describe('reduction', () => {
  it('is the integer percent of offices the merge removes', () => {
    expect(reduction(family({ officesToday: 42, officesProposed: 8 }))).toBe(81);
    expect(reduction(family({ officesToday: 549, officesProposed: 117 }))).toBe(79);
  });

  it('is zero when the family has no offices', () => {
    expect(reduction(family({ officesToday: 0, officesProposed: 0 }))).toBe(0);
  });
});

describe('tier labels', () => {
  it('covers every tier the payload can carry', () => {
    expect(Object.keys(TIER_LABELS).sort()).toEqual([
      'regional',
      'regional-de-facto',
      'special',
    ]);
  });
});

describe('regionsOf', () => {
  it('returns the union of every family region, ordered by size', () => {
    const doc: Document = {
      title: '',
      period: '',
      summary: {
        deconcentratedOfficesTotal: 2,
        matchedOffices: 2,
        regionalFamilies: 1,
        officesTodayInRegionalFamilies: 2,
        officesProposedOnEightRegions: 2,
        reductionPercent: 0,
        municipalExcluded: 0,
        unmatched: 0,
      },
      limitations: [],
      families: [
        family({
          regions: [
            { region: 'Centru', seat: 'BV', seatPopulation: 1, counties: ['AB', 'BV'] },
            { region: 'Nord-Est', seat: 'IS', seatPopulation: 1, counties: ['IS', 'BC'] },
          ],
        }),
        family({
          code: 'itm',
          regions: [{ region: 'Centru', seat: 'AB', seatPopulation: 1, counties: ['AB'] }],
        }),
      ],
    };
    expect(regionsOf(doc)).toEqual(['Centru', 'Nord-Est']);
  });
});

describe('filtered', () => {
  const doc: Document = {
    title: '',
    period: '',
    summary: {
      deconcentratedOfficesTotal: 0,
      matchedOffices: 0,
      regionalFamilies: 0,
      officesTodayInRegionalFamilies: 0,
      officesProposedOnEightRegions: 0,
      reductionPercent: 0,
      municipalExcluded: 0,
      unmatched: 0,
    },
    limitations: [],
    families: [
      family({ code: 'cas', tier: 'regional' }),
      family({ code: 'dgfp', tier: 'regional-de-facto' }),
      family({ code: 'anrsps', tier: 'special' }),
    ],
  };

  it('keeps only the selected tiers', () => {
    expect(filtered(doc, new Set(['regional']))).toHaveLength(1);
    expect(filtered(doc, new Set(['regional', 'special']))).toHaveLength(2);
  });
});

describe('sortBy', () => {
  const list = [
    family({ code: 'a', name: 'Apă', officesToday: 10, officesProposed: 8 }),
    family({ code: 'b', name: 'Deșeuri', officesToday: 42, officesProposed: 8 }),
  ];

  it('sorts by office count descending', () => {
    expect(sortBy(list, 'officesToday', 'desc').map((f) => f.code)).toEqual(['b', 'a']);
  });

  it('sorts by name with Romanian collation when ascending', () => {
    expect(sortBy(list, 'name', 'asc').map((f) => f.code)).toEqual(['a', 'b']);
  });

  it('sorts by the computed reduction', () => {
    const byReduction = sortBy(list, 'reduction', 'desc').map((f) => f.code);
    expect(byReduction).toEqual(['b', 'a']);
  });
});

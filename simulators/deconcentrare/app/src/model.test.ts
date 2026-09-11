import { describe, expect, it } from 'vitest';
import {
  TIER_LABELS,
  absorbedOffices,
  filtered,
  groupOfficesByFamily,
  officeList,
  proposedDirections,
  reduction,
  regionsOf,
  sortBy,
  type Document,
  type Family,
  type OfficeRegistryDocument,
  type OfficeRow,
} from './model';

const family = (over: Partial<Family>): Family => ({
  code: 'cas',
  name: 'Casa de Asigurări de Sănătate',
  tier: 'regional',
  officesToday: 42,
  officesProposed: 8,
  sources: { anfp: 42, portal: 0 },
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
        anfp: { deconcentratedOfficesTotal: 0, matchedOffices: 0, regionalFamilies: 0, officesTodayInRegionalFamilies: 0, officesProposedOnEightRegions: 0 },
        portal: { matched: 0, kept: 0, droppedDuplicate: 0, municipalExcluded: 0, unmatched: 0 },
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
      anfp: { deconcentratedOfficesTotal: 0, matchedOffices: 0, regionalFamilies: 0, officesTodayInRegionalFamilies: 0, officesProposedOnEightRegions: 0 },
      portal: { matched: 0, kept: 0, droppedDuplicate: 0, municipalExcluded: 0, unmatched: 0 },
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

const office = (over: Partial<OfficeRow>): OfficeRow => ({
  name: 'Birou',
  type: 'TERITORIAL - SERVICIU PUBLIC DECONCENTRAT',
  county: 'AB',
  locality: '',
  family: 'cas',
  familyName: 'Casa de Asigurări de Sănătate',
  tier: 'regional',
  source: 'anfp',
  ...over,
});

const officeRegistry = (offices: OfficeRow[]): OfficeRegistryDocument => ({
  title: '',
  period: '',
  summary: { offices: offices.length, withCounty: 0, matched: 0, regional: 0, municipal: 0, unmatched: 0, sources: { anfp: 0, portal: 0 } },
  offices,
});

describe('officeList', () => {
  const doc = officeRegistry([
    office({ name: 'CAS AB', tier: 'regional' }),
    office({ name: 'DGRFP', family: 'dgfp', familyName: 'DGRFP', tier: 'regional-de-facto' }),
    office({ name: 'Primăria', family: null, familyName: null, tier: 'municipal' }),
  ]);

  it('keeps regional rows only when asked', () => {
    expect(officeList(doc, 'regional').map((o) => o.name)).toEqual(['CAS AB']);
  });

  it('returns everything for all, municipal included', () => {
    expect(officeList(doc, 'all')).toHaveLength(3);
  });
});

describe('groupOfficesByFamily', () => {
  it('groups by family name and buckets municipal rows', () => {
    const groups = groupOfficesByFamily([
      office({ name: 'A' }),
      office({ name: 'B', family: 'dgfp', familyName: 'DGRFP' }),
      office({ name: 'C' }),
      office({ name: 'M', family: null, familyName: null, tier: 'municipal' }),
    ]);
    expect(groups.map((g) => [g.label, g.offices.length])).toEqual([
      ['Casa de Asigurări de Sănătate', 2],
      ['DGRFP', 1],
      ['servicii municipale (excluse)', 1],
    ]);
  });
});

describe('proposedDirections', () => {
  it('lists one directorate per regional family per region it reaches', () => {
    const doc: Document = {
      title: '',
      period: '',
      summary: { deconcentratedOfficesTotal: 0, matchedOffices: 0, regionalFamilies: 1, officesTodayInRegionalFamilies: 0, officesProposedOnEightRegions: 0, reductionPercent: 0, municipalExcluded: 0, unmatched: 0, anfp: { deconcentratedOfficesTotal: 0, matchedOffices: 0, regionalFamilies: 0, officesTodayInRegionalFamilies: 0, officesProposedOnEightRegions: 0 }, portal: { matched: 0, kept: 0, droppedDuplicate: 0, municipalExcluded: 0, unmatched: 0 } },
      limitations: [],
      families: [
        family({ tier: 'regional' }),
        family({ code: 'dgfp', tier: 'regional-de-facto', regions: [{ region: 'Vest', seat: 'AR', seatPopulation: 1, counties: ['AR'] }] }),
      ],
    };
    expect(proposedDirections(doc)).toEqual([
      { family: 'Casa de Asigurări de Sănătate', region: 'Centru', seat: 'AB' },
      { family: 'Casa de Asigurări de Sănătate', region: 'Vest', seat: 'AR' },
    ]);
  });
});

describe('absorbedOffices', () => {
  const doc: Document = {
    title: '',
    period: '',
    summary: { deconcentratedOfficesTotal: 0, matchedOffices: 0, regionalFamilies: 1, officesTodayInRegionalFamilies: 0, officesProposedOnEightRegions: 0, reductionPercent: 0, municipalExcluded: 0, unmatched: 0, anfp: { deconcentratedOfficesTotal: 0, matchedOffices: 0, regionalFamilies: 0, officesTodayInRegionalFamilies: 0, officesProposedOnEightRegions: 0 }, portal: { matched: 0, kept: 0, droppedDuplicate: 0, municipalExcluded: 0, unmatched: 0 } },
    limitations: [],
    families: [
      family({
        tier: 'regional',
        regions: [
          { region: 'Centru', seat: 'AB', seatPopulation: 1, counties: ['AB', 'BV'] },
          { region: 'Vest', seat: 'AR', seatPopulation: 1, counties: ['AR'] },
        ],
      }),
    ],
  };

  it('keeps exactly one office per seat county, absorbs the rest', () => {
    const rows = absorbedOffices(doc, officeRegistry([
      office({ name: 'AB 1', county: 'AB' }),
      office({ name: 'AB 2', county: 'AB' }),
      office({ name: 'BV', county: 'BV' }),
      office({ name: 'AR', county: 'AR' }),
    ]));
    expect(rows.map((o) => o.name).sort()).toEqual(['AB 2', 'BV']);
  });

  it('ignores offices outside the regional families', () => {
    const rows = absorbedOffices(doc, officeRegistry([
      office({ name: 'X', county: 'BV', family: 'dgfp', familyName: 'DGRFP', tier: 'regional-de-facto' }),
      office({ name: 'BV', county: 'BV' }),
    ]));
    expect(rows.map((o) => o.name)).toEqual(['BV']);
  });
});

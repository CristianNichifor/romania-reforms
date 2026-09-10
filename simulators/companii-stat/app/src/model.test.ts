import { describe, expect, it } from 'vitest';
import {
  TIER_LABELS,
  filtered,
  reduction,
  sortBy,
  type Cluster,
  type Document,
} from './model';

const cluster = (over: Partial<Cluster>): Cluster => ({
  caen: '3600',
  name: 'Captarea, tratarea și distribuția apei',
  tier: 'regional',
  companies: 295,
  employees: 27533,
  headcountKnown: 141,
  micro: 86,
  proposed: 8,
  ...over,
});

describe('reduction', () => {
  it('is the integer percent of entities the merge removes', () => {
    expect(reduction(cluster({ companies: 295, proposed: 8 }))).toBe(97);
    expect(reduction(cluster({ companies: 659, proposed: 56 }))).toBe(92);
  });

  it('is zero when the cluster has no companies', () => {
    expect(reduction(cluster({ companies: 0, proposed: 0 }))).toBe(0);
  });
});

describe('tier labels', () => {
  it('covers every tier the payload can carry', () => {
    expect(Object.keys(TIER_LABELS).sort()).toEqual([
      'local',
      'national',
      'other',
      'regional',
    ]);
  });
});

describe('filtered', () => {
  const doc: Document = {
    title: '',
    period: '',
    summary: {
      companies: 0,
      clusters: 0,
      regionalClusters: 0,
      companiesInRegionalClusters: 0,
      operatorsProposedOnEightRegions: 0,
      reductionPercent: 0,
      microUnder20: 0,
      headcountKnown: 0,
    },
    limitations: [],
    clusters: [
      cluster({ caen: '3600', tier: 'regional' }),
      cluster({ caen: '3511', tier: 'national' }),
      cluster({ caen: '4931', tier: 'local' }),
    ],
  };

  it('keeps only the selected tiers', () => {
    expect(filtered(doc, new Set(['regional']))).toHaveLength(1);
    expect(filtered(doc, new Set(['regional', 'national']))).toHaveLength(2);
  });
});

describe('sortBy', () => {
  const list = [
    cluster({ caen: '3600', companies: 295, employees: 27533 }),
    cluster({ caen: '3811', companies: 139, employees: 16768 }),
  ];

  it('sorts by company count descending', () => {
    expect(sortBy(list, 'companies', 'desc').map((c) => c.caen)).toEqual(['3600', '3811']);
  });

  it('sorts by the computed reduction', () => {
    const byReduction = sortBy(
      [cluster({ caen: '3600', companies: 295, proposed: 8 }), cluster({ caen: '3811', companies: 139, proposed: 8 })],
      'reduction',
      'desc',
    ).map((c) => c.caen);
    expect(byReduction).toEqual(['3600', '3811']);
  });
});

import { describe, expect, it } from 'vitest';
import {
  TIER_LABELS,
  absorbedRows,
  filtered,
  groupByCounty,
  groupRegistryByCluster,
  groupRegistryByCounty,
  operatorRows,
  reduction,
  registryCompanies,
  sortBy,
  type AbsorbedCompany,
  type Cluster,
  type Document,
  type RegionOperator,
  type RegistryCompany,
  type RegistryDocument,
} from './model';

const cluster = (over: Partial<Cluster>): Cluster => ({
  caen: '3600',
  name: 'Captarea, tratarea și distribuția apei',
  tier: 'regional',
  companies: 295,
  employees: 27533,
  headcountKnown: 141,
  micro: 86,
  revenueRon: 0,
  lossCount: 0,
  debtRon: 0,
  distinctOwners: 0,
  subsidisedCount: 0,
  subsidyRon: 0,
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
      revenueRon: 0,
      lossMaking: 0,
      subsidisedCount: 0,
      subsidyRon: 0,
      inFlightMergers: 0,
    },
    limitations: [],
    inFlightMergers: [],
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

describe('groupByCounty', () => {
  const company = (cui: number, county: string | null): AbsorbedCompany => ({
    cui,
    name: `Compania ${cui}`,
    county,
    owner: null,
  });

  const region = (absorbed: AbsorbedCompany[]): RegionOperator => ({
    region: 'Sud',
    seatCounty: 'AG',
    absorber: { cui: 1, name: 'Nucleu', employees: 10 },
    absorbedCount: absorbed.length,
    absorbed,
  });

  it('groups companies by county, largest group first', () => {
    const groups = groupByCounty(
      region([
        company(2, 'PH'),
        company(3, 'AG'),
        company(4, 'PH'),
        company(5, 'GR'),
        company(6, 'AG'),
        company(7, 'AG'),
      ]),
    );
    expect(groups.map((g) => [g.county, g.companies.length])).toEqual([
      ['AG', 3],
      ['PH', 2],
      ['GR', 1],
    ]);
  });

  it('keeps companies with no county in their own group', () => {
    const groups = groupByCounty(region([company(2, null), company(3, 'PH')]));
    expect(groups.map((g) => g.county)).toEqual([null, 'PH']);
  });

  it('returns no groups for an empty absorbed list', () => {
    expect(groupByCounty(region([]))).toEqual([]);
  });
});

const registryCompany = (over: Partial<RegistryCompany>): RegistryCompany => ({
  cui: 1,
  name: 'Compania',
  caen: '3600',
  cluster: 'Captarea, tratarea și distribuția apei',
  tier: 'regional',
  county: 'PH',
  owner: 'CONSILIUL LOCAL',
  employees: 40,
  revenueRon: null,
  netResultRon: null,
  debtRon: null,
  subsidyRon: null,
  status: 'funcţiune',
  ...over,
});

const registryDoc = (companies: RegistryCompany[]): RegistryDocument => ({
  title: '',
  period: '',
  summary: {
    companies: companies.length,
    withCounty: 0,
    withOwner: 0,
    withEmployees: 0,
    microUnder20: 0,
    lossMaking: 0,
    subsidised: 0,
    regional: 0,
  },
  companies,
});

describe('registryCompanies', () => {
  const doc = registryDoc([
    registryCompany({ cui: 1, tier: 'regional', netResultRon: -1000, subsidyRon: 500, employees: 12 }),
    registryCompany({ cui: 2, tier: 'national', netResultRon: 2000, subsidyRon: null, employees: 300 }),
    registryCompany({ cui: 3, tier: 'other', netResultRon: null, subsidyRon: 800, employees: null }),
  ]);

  it('filters loss-makers by negative result only', () => {
    expect(registryCompanies(doc, 'loss').map((c) => c.cui)).toEqual([1]);
  });

  it('filters subsidised by reported subsidy only', () => {
    expect(registryCompanies(doc, 'subsidised').map((c) => c.cui)).toEqual([1, 3]);
  });

  it('filters micro by known headcount only', () => {
    expect(registryCompanies(doc, 'micro').map((c) => c.cui)).toEqual([1]);
  });

  it('filters regional by tier', () => {
    expect(registryCompanies(doc, 'regional').map((c) => c.cui)).toEqual([1]);
  });

  it('returns everything for all', () => {
    expect(registryCompanies(doc, 'all')).toHaveLength(3);
  });
});

describe('groupRegistryByCounty', () => {
  it('groups by county, largest first, null county in its own group', () => {
    const groups = groupRegistryByCounty([
      registryCompany({ cui: 1, county: 'PH' }),
      registryCompany({ cui: 2, county: null }),
      registryCompany({ cui: 3, county: 'PH' }),
      registryCompany({ cui: 4, county: 'AG' }),
      registryCompany({ cui: 5, county: 'PH' }),
    ]);
    expect(groups.map((g) => [g.county, g.companies.length])).toEqual([['PH', 3], [null, 1], ['AG', 1]]);
  });
});

describe('groupRegistryByCluster', () => {
  it('keeps first-seen cluster order', () => {
    const groups = groupRegistryByCluster([
      registryCompany({ cui: 1, cluster: 'Apa', caen: '3600' }),
      registryCompany({ cui: 2, cluster: 'Deșeuri', caen: '3811' }),
      registryCompany({ cui: 3, cluster: 'Apa', caen: '3600' }),
    ]);
    expect(groups.map((g) => [g.cluster, g.companies.length])).toEqual([['Apa', 2], ['Deșeuri', 1]]);
  });
});

describe('operatorRows', () => {
  const regionalCluster = (regions: string[], named: boolean): Cluster =>
    cluster({
      caen: '3600',
      tier: 'regional',
      regions: regions.map((r) => ({
        region: r,
        seatCounty: 'X',
        absorber: named ? { cui: 1, name: `Operator ${r}`, employees: 10 } : null,
        absorbedCount: 0,
        absorbed: [],
      })),
    });

  it('returns one row per cluster per canonical region', () => {
    const doc: Document = {
      title: '',
      period: '',
      summary: { companies: 0, clusters: 0, regionalClusters: 0, companiesInRegionalClusters: 0, operatorsProposedOnEightRegions: 0, reductionPercent: 0, microUnder20: 0, headcountKnown: 0, revenueRon: 0, lossMaking: 0, subsidisedCount: 0, subsidyRon: 0, inFlightMergers: 0 },
      limitations: [],
      inFlightMergers: [],
      clusters: [
        regionalCluster(['Sud', 'Vest'], true),
        regionalCluster(['Sud', 'Vest', 'Centru'], false),
      ],
    };
    const rows = operatorRows(doc);
    expect(rows).toHaveLength(6);
    expect(rows.filter((r) => r.name === null)).toHaveLength(4);
    expect(rows[0]).toEqual({ cluster: 'Captarea, tratarea și distribuția apei', region: 'Sud', name: 'Operator Sud', employees: 10 });
  });
});

describe('absorbedRows', () => {
  it('flattens every absorbed company with its cluster and region', () => {
    const absorbed: AbsorbedCompany[] = [
      { cui: 2, name: 'A', county: 'PH', owner: 'CL' },
      { cui: 3, name: 'B', county: null, owner: null },
    ];
    const doc: Document = {
      title: '',
      period: '',
      summary: { companies: 0, clusters: 0, regionalClusters: 0, companiesInRegionalClusters: 0, operatorsProposedOnEightRegions: 0, reductionPercent: 0, microUnder20: 0, headcountKnown: 0, revenueRon: 0, lossMaking: 0, subsidisedCount: 0, subsidyRon: 0, inFlightMergers: 0 },
      limitations: [],
      inFlightMergers: [],
      clusters: [
        cluster({
          caen: '3600',
          tier: 'regional',
          regions: [{ region: 'Sud', seatCounty: 'AG', absorber: { cui: 1, name: 'N', employees: 9 }, absorbedCount: 2, absorbed }],
        }),
        cluster({ caen: '3511', tier: 'national' }),
      ],
    };
    const rows = absorbedRows(doc);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ cluster: 'Captarea, tratarea și distribuția apei', region: 'Sud', name: 'A', county: 'PH', owner: 'CL' });
  });
});

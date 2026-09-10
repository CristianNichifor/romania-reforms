// The pure half of the page: everything the table computes from the payload, kept free of
// DOM so the tests can pin the numbers the view displays.

export type Tier = 'regional' | 'local' | 'national' | 'other';

export interface AbsorbedCompany {
  cui: number;
  name: string;
  county: string | null;
  owner: string | null;
}

export interface RegionOperator {
  region: string;
  seatCounty: string;
  absorber: { cui: number; name: string; employees: number } | null;
  absorbedCount: number;
  absorbed: AbsorbedCompany[];
}

export interface Cluster {
  caen: string;
  name: string;
  tier: Tier;
  companies: number;
  employees: number;
  headcountKnown: number;
  micro: number;
  revenueRon: number;
  lossCount: number;
  debtRon: number;
  distinctOwners: number;
  subsidisedCount: number;
  subsidyRon: number;
  proposed: number;
  regions?: RegionOperator[];
}

export interface InFlightMerger {
  cui: number;
  name: string;
  caen: string | null;
  status: string;
}

export interface CountyGroup {
  county: string | null;
  companies: AbsorbedCompany[];
}

export interface RegistryCompany {
  cui: number;
  name: string;
  caen: string;
  cluster: string;
  tier: Tier;
  county: string | null;
  owner: string | null;
  employees: number | null;
  revenueRon: number | null;
  netResultRon: number | null;
  debtRon: number | null;
  subsidyRon: number | null;
  status: string;
}

export interface RegistryDocument {
  title: string;
  period: string;
  summary: {
    companies: number;
    withCounty: number;
    withOwner: number;
    withEmployees: number;
    microUnder20: number;
    lossMaking: number;
    subsidised: number;
    regional: number;
  };
  companies: RegistryCompany[];
}

export type RegistryKind = 'all' | 'regional' | 'loss' | 'subsidised' | 'micro';

export interface CountyRegistryGroup {
  county: string | null;
  companies: RegistryCompany[];
}

export interface ClusterRegistryGroup {
  cluster: string;
  companies: RegistryCompany[];
}

export interface OperatorRow {
  cluster: string;
  region: string;
  name: string | null;
  employees: number | null;
}

export interface AbsorbedRow {
  cluster: string;
  region: string;
  name: string;
  county: string | null;
  owner: string | null;
}

export interface Summary {
  companies: number;
  clusters: number;
  regionalClusters: number;
  companiesInRegionalClusters: number;
  operatorsProposedOnEightRegions: number;
  reductionPercent: number;
  microUnder20: number;
  headcountKnown: number;
  revenueRon: number;
  lossMaking: number;
  subsidisedCount: number;
  subsidyRon: number;
  inFlightMergers: number;
}

export interface Limitation {
  id: string;
  text: string;
  severity: 'blocking' | 'material' | 'note';
  affects: string[];
}

export interface Document {
  title: string;
  period: string;
  clusters: Cluster[];
  inFlightMergers: InFlightMerger[];
  summary: Summary;
  limitations: Limitation[];
}

export const TIER_LABELS: Record<Tier, string> = {
  regional: 'de rețea — regionalizabilă',
  local: 'locală',
  national: 'națională',
  other: 'alta',
};

/** Integer percent of operating entities a merge removes. Zero when the cluster is empty. */
export function reduction(cluster: Cluster): number {
  if (cluster.companies === 0) return 0;
  return Math.round(
    (100 * (cluster.companies - cluster.proposed)) / cluster.companies,
  );
}

/**
 * The absorbed companies of one region, grouped by county, largest group first.
 * Companies whose county the payload does not know land in a ``null`` group.
 */
export function groupByCounty(region: RegionOperator): CountyGroup[] {
  const by = new Map<string | null, AbsorbedCompany[]>();
  for (const company of region.absorbed) {
    const list = by.get(company.county) ?? [];
    list.push(company);
    by.set(company.county, list);
  }
  return [...by.entries()]
    .map(([county, companies]) => ({ county, companies }))
    .sort((a, b) => b.companies.length - a.companies.length);
}

/** Clusters the reader selected with the tier filter, in the given sort order. */
export function filtered(doc: Document, tiers: Set<Tier>): Cluster[] {
  return doc.clusters.filter((c) => tiers.has(c.tier));
}

export function sortBy(
  clusters: Cluster[],
  key: 'name' | 'companies' | 'employees' | 'revenue' | 'subsidy' | 'reduction',
  direction: 'asc' | 'desc',
): Cluster[] {
  const order = direction === 'asc' ? 1 : -1;
  const value = (c: Cluster): string | number =>
    key === 'reduction' ? reduction(c) : key === 'name' ? c.name : key === 'revenue' ? c.revenueRon : key === 'subsidy' ? c.subsidyRon : c[key];
  return [...clusters].sort((a, b) => {
    const av = value(a);
    const bv = value(b);
    if (typeof av === 'string' && typeof bv === 'string') {
      return order * av.localeCompare(bv, 'ro');
    }
    return order * (Number(av) - Number(bv));
  });
}

/** The rows behind one summary card: the registry filtered by what the card counts. */
export function registryCompanies(doc: RegistryDocument, kind: RegistryKind): RegistryCompany[] {
  switch (kind) {
    case 'regional':
      return doc.companies.filter((c) => c.tier === 'regional');
    case 'loss':
      return doc.companies.filter((c) => c.netResultRon !== null && c.netResultRon < 0);
    case 'subsidised':
      return doc.companies.filter((c) => c.subsidyRon !== null);
    case 'micro':
      return doc.companies.filter((c) => c.employees !== null && c.employees < 20);
    default:
      return doc.companies;
  }
}

/** Registry rows grouped by county, largest group first; unknown counties in a null group. */
export function groupRegistryByCounty(companies: RegistryCompany[]): CountyRegistryGroup[] {
  const by = new Map<string | null, RegistryCompany[]>();
  for (const company of companies) {
    const list = by.get(company.county) ?? [];
    list.push(company);
    by.set(company.county, list);
  }
  return [...by.entries()]
    .map(([county, companies]) => ({ county, companies }))
    .sort((a, b) => b.companies.length - a.companies.length);
}

/** Registry rows grouped by their cluster name, in first-seen order. */
export function groupRegistryByCluster(companies: RegistryCompany[]): ClusterRegistryGroup[] {
  const groups: ClusterRegistryGroup[] = [];
  for (const company of companies) {
    const group = groups.find((g) => g.cluster === company.cluster);
    if (group) group.companies.push(company);
    else groups.push({ cluster: company.cluster, companies: [company] });
  }
  return groups;
}

/**
 * The proposed operators, one row per (regional cluster, development region): the named
 * absorber where the rule found one, a nameless row where no company of the activity sits
 * in the region. Row count is clusters × 8, exactly the headline "operators on eight regions".
 */
export function operatorRows(doc: Document): OperatorRow[] {
  const regional = doc.clusters.filter((c) => c.tier === 'regional' && c.regions);
  const canonical = [...new Set(regional.flatMap((c) => c.regions!.map((r) => r.region)))];
  const rows: OperatorRow[] = [];
  for (const cluster of regional) {
    for (const region of canonical) {
      const group = cluster.regions!.find((r) => r.region === region);
      rows.push(
        group?.absorber
          ? { cluster: cluster.name, region, name: group.absorber.name, employees: group.absorber.employees }
          : { cluster: cluster.name, region, name: null, employees: null },
      );
    }
  }
  return rows;
}

/** Every company the scenario absorbs, with the cluster and region it disappears into. */
export function absorbedRows(doc: Document): AbsorbedRow[] {
  const rows: AbsorbedRow[] = [];
  for (const cluster of doc.clusters) {
    if (cluster.tier !== 'regional' || !cluster.regions) continue;
    for (const region of cluster.regions) {
      for (const company of region.absorbed) {
        rows.push({
          cluster: cluster.name,
          region: region.region,
          name: company.name,
          county: company.county,
          owner: company.owner,
        });
      }
    }
  }
  return rows;
}

// The pure half of the page: everything the table computes from the payload, kept free of
// DOM so the tests can pin the numbers the view displays.

export type Tier = 'regional' | 'local' | 'national' | 'other';

export interface AbsorbedCompany {
  cui: number;
  name: string;
  county: string | null;
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
  proposed: number;
  regions?: RegionOperator[];
}

export interface InFlightMerger {
  cui: number;
  name: string;
  caen: string | null;
  status: string;
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

/** Clusters the reader selected with the tier filter, in the given sort order. */
export function filtered(doc: Document, tiers: Set<Tier>): Cluster[] {
  return doc.clusters.filter((c) => tiers.has(c.tier));
}

export function sortBy(
  clusters: Cluster[],
  key: 'name' | 'companies' | 'employees' | 'reduction',
  direction: 'asc' | 'desc',
): Cluster[] {
  const order = direction === 'asc' ? 1 : -1;
  const value = (c: Cluster): string | number =>
    key === 'reduction' ? reduction(c) : key === 'name' ? c.name : c[key];
  return [...clusters].sort((a, b) => {
    const av = value(a);
    const bv = value(b);
    if (typeof av === 'string' && typeof bv === 'string') {
      return order * av.localeCompare(bv, 'ro');
    }
    return order * (Number(av) - Number(bv));
  });
}

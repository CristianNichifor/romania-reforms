// The pure half of the page: everything the table and the region grid compute from the
// payload, kept free of DOM so the tests can pin the numbers the view displays.

export type Tier = 'regional' | 'regional-de-facto' | 'special';

export interface RegionGroup {
  region: string;
  seat: string;
  seatPopulation: number | null;
  counties: string[];
}

export interface Family {
  code: string;
  name: string;
  tier: Tier;
  officesToday: number;
  officesProposed: number;
  counties: string[];
  regions: RegionGroup[];
}

export interface Summary {
  deconcentratedOfficesTotal: number;
  matchedOffices: number;
  regionalFamilies: number;
  officesTodayInRegionalFamilies: number;
  officesProposedOnEightRegions: number;
  reductionPercent: number;
  municipalExcluded: number;
  unmatched: number;
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
  families: Family[];
  summary: Summary;
  limitations: Limitation[];
}

export const TIER_LABELS: Record<Tier, string> = {
  regional: 'regionalizabilă',
  'regional-de-facto': 'deja regională',
  special: 'specială',
};

/** Integer percent of offices a merge removes. Zero when the family has no offices. */
export function reduction(family: Family): number {
  if (family.officesToday === 0) return 0;
  return Math.round(
    (100 * (family.officesToday - family.officesProposed)) / family.officesToday,
  );
}

/** The eight development regions, ordered by size so the grid reads consistently. */
export function regionsOf(doc: Document): string[] {
  const names = new Set<string>();
  for (const family of doc.families) {
    for (const group of family.regions) names.add(group.region);
  }
  return [...names].sort((a, b) => {
    const size = (name: string) =>
      Math.max(...doc.families.map((f) => f.regions.find((g) => g.region === name)?.counties.length ?? 0));
    return size(b) - size(a) || a.localeCompare(b, 'ro');
  });
}

/** Families the reader selected with the tier filter, in the given sort order. */
export function filtered(doc: Document, tiers: Set<Tier>): Family[] {
  return doc.families.filter((f) => tiers.has(f.tier));
}

export function sortBy(
  families: Family[],
  key: 'name' | 'officesToday' | 'officesProposed' | 'reduction',
  direction: 'asc' | 'desc',
): Family[] {
  const order = direction === 'asc' ? 1 : -1;
  const value = (f: Family): string | number =>
    key === 'reduction' ? reduction(f) : key === 'name' ? f.name : f[key];
  return [...families].sort((a, b) => {
    const av = value(a);
    const bv = value(b);
    if (typeof av === 'string' && typeof bv === 'string') {
      return order * av.localeCompare(bv, 'ro');
    }
    return order * (Number(av) - Number(bv));
  });
}

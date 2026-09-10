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

export interface OfficeRow {
  name: string;
  type: string;
  county: string | null;
  locality: string;
  family: string | null;
  familyName: string | null;
  tier: 'regional' | 'regional-de-facto' | 'special' | 'municipal' | 'unmatched';
}

export interface OfficeRegistryDocument {
  title: string;
  period: string;
  summary: {
    offices: number;
    withCounty: number;
    matched: number;
    regional: number;
    municipal: number;
    unmatched: number;
  };
  offices: OfficeRow[];
}

export type OfficeKind = 'all' | 'regional';

export interface OfficeGroup {
  label: string;
  offices: OfficeRow[];
}

export interface ProposedDirection {
  family: string;
  region: string;
  seat: string;
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

/** The offices behind one summary card. ``all`` keeps municipal and unmatched rows too. */
export function officeList(doc: OfficeRegistryDocument, kind: OfficeKind): OfficeRow[] {
  return kind === 'regional'
    ? doc.offices.filter((office) => office.tier === 'regional')
    : doc.offices;
}

/** Offices grouped by family, in first-seen order; ungroupable rows get a named bucket. */
export function groupOfficesByFamily(offices: OfficeRow[]): OfficeGroup[] {
  const groups: OfficeGroup[] = [];
  for (const office of offices) {
    const label = office.familyName
      ?? (office.tier === 'municipal' ? 'servicii municipale (excluse)' : 'neidentificate');
    const group = groups.find((g) => g.label === label);
    if (group) group.offices.push(office);
    else groups.push({ label, offices: [office] });
  }
  return groups;
}

/**
 * The proposed regional directorates: one per (regional family, region it reaches), the
 * seat being the region's most populated county — the seatRule of the payload, not a source
 * fact.
 */
export function proposedDirections(doc: Document): ProposedDirection[] {
  const rows: ProposedDirection[] = [];
  for (const family of doc.families) {
    if (family.tier !== 'regional') continue;
    for (const group of family.regions) {
      rows.push({ family: family.name, region: group.region, seat: group.seat });
    }
  }
  return rows;
}

/**
 * The offices the merge absorbs: every office of a regional family except one kept per
 * (family, region) in the region's seat county. Kept and absorbed partition the regional
 * rows exactly, so the count is officesToday minus proposed.
 */
export function absorbedOffices(doc: Document, registry: OfficeRegistryDocument): OfficeRow[] {
  const seats = new Set<string>();
  for (const family of doc.families) {
    if (family.tier !== 'regional') continue;
    for (const group of family.regions) seats.add(`${family.code}:${group.seat}`);
  }
  const kept = new Set<string>();
  const rows: OfficeRow[] = [];
  for (const office of registry.offices) {
    if (office.tier !== 'regional' || !office.family || !office.county) continue;
    const key = `${office.family}:${office.county}`;
    if (seats.has(key) && !kept.has(key)) {
      kept.add(key);
      continue;
    }
    rows.push(office);
  }
  return rows;
}

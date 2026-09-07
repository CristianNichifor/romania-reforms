/**
 * Which development region a county belongs to.
 *
 * Romania's eight development regions are fixed groupings of counties — the NUTS-2 level —
 * and they are not in the payload because nothing in the model uses them: no unit may cross a
 * county line, so a region boundary can never constrain a merge. They exist here only so the
 * map can outline the one a reader is hovering over.
 *
 * The names are spelled exactly as `regions.geojson` spells them, which is where they have to
 * match: the boundary segments carry `leftregion` and `rightregion` as free text, so a
 * mismatch here silently outlines nothing rather than failing.
 *
 * "Sud" and "Sud-Vest" are the file's shorthand for what official documents usually write as
 * Sud-Muntenia and Sud-Vest Oltenia.
 */
export const REGION_OF_COUNTY: Readonly<Record<string, string>> = {
  // Nord-Vest
  BH: 'Nord-Vest', BN: 'Nord-Vest', CJ: 'Nord-Vest', MM: 'Nord-Vest', SM: 'Nord-Vest', SJ: 'Nord-Vest',
  // Centru
  AB: 'Centru', BV: 'Centru', CV: 'Centru', HR: 'Centru', MS: 'Centru', SB: 'Centru',
  // Nord-Est
  BC: 'Nord-Est', BT: 'Nord-Est', IS: 'Nord-Est', NT: 'Nord-Est', SV: 'Nord-Est', VS: 'Nord-Est',
  // Sud-Est
  BR: 'Sud-Est', BZ: 'Sud-Est', CT: 'Sud-Est', GL: 'Sud-Est', TL: 'Sud-Est', VN: 'Sud-Est',
  // Sud (Muntenia)
  AG: 'Sud', CL: 'Sud', DB: 'Sud', GR: 'Sud', IL: 'Sud', PH: 'Sud', TR: 'Sud',
  // Bucuresti-Ilfov
  B: 'București-Ilfov', IF: 'București-Ilfov',
  // Sud-Vest (Oltenia)
  DJ: 'Sud-Vest', GJ: 'Sud-Vest', MH: 'Sud-Vest', OT: 'Sud-Vest', VL: 'Sud-Vest',
  // Vest
  AR: 'Vest', CS: 'Vest', HD: 'Vest', TM: 'Vest',
};

/** The development region a county code sits in, or null for a code we do not know. */
export function regionOfCounty(county: string | undefined): string | null {
  if (!county) return null;
  return REGION_OF_COUNTY[county] ?? null;
}

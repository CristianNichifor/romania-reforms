/**
 * The county-to-region mapping.
 *
 * It is hand-written, and the names have to match `regions.geojson` exactly: the boundary
 * segments carry `leftregion` and `rightregion` as free text, so a typo does not throw — it
 * silently outlines nothing, which is the kind of bug that survives a demo.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { REGION_OF_COUNTY, regionOfCounty } from '../src/model/regions';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const readJson = (n: string): unknown => JSON.parse(readFileSync(resolve(dataDir, n), 'utf8'));

const regionNames = (): Set<string> => {
  const geo = readJson('regions.geojson') as {
    features: { properties: { leftregion?: string | null; rightregion?: string | null } }[];
  };
  const names = new Set<string>();
  for (const f of geo.features) {
    if (f.properties.leftregion) names.add(f.properties.leftregion);
    if (f.properties.rightregion) names.add(f.properties.rightregion);
  }
  return names;
};

const countyCodes = (): Set<string> => {
  const attributes = readJson('attributes.json') as { county: string[] };
  return new Set(attributes.county);
};

describe('development regions', () => {
  it('names only regions the boundary layer actually has', () => {
    const known = regionNames();
    const wrong = [...new Set(Object.values(REGION_OF_COUNTY))].filter((n) => !known.has(n));
    expect(wrong).toEqual([]);
  });

  it('covers every county in the payload', () => {
    // A county with no region would hover with nothing highlighted and no error to explain it.
    const missing = [...countyCodes()].filter((c) => !regionOfCounty(c));
    expect(missing).toEqual([]);
  });

  it('uses all eight regions', () => {
    expect(new Set(Object.values(REGION_OF_COUNTY)).size).toBe(8);
  });

  it('covers the 41 counties and Bucharest, and nothing invented', () => {
    expect(Object.keys(REGION_OF_COUNTY)).toHaveLength(42);
    const known = countyCodes();
    expect(Object.keys(REGION_OF_COUNTY).filter((c) => !known.has(c))).toEqual([]);
  });

  it('has no region for a code that does not exist', () => {
    expect(regionOfCounty('ZZ')).toBeNull();
    expect(regionOfCounty(undefined)).toBeNull();
  });
});

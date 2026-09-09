import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  healthAccessPayloadAligned,
  healthAccessPeriodLabel,
  healthAccessTotals,
  type HealthAccessPayload,
} from '../src/app/health-access';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const rootDir = resolve(here, '../../../..');
const readJson = <T>(name: string): T => JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')) as T;
const readRootJson = <T>(path: string): T =>
  JSON.parse(readFileSync(resolve(rootDir, path), 'utf8')) as T;

const payload: HealthAccessPayload = {
  id: 'administrativ-health-access-uat-2024-2026',
  sourceViewId: 'health-service-access-uat-2024-2026',
  sourceViewSha256: 'a'.repeat(64),
  periodStart: '2024',
  periodEnd: '2026',
  siruta: ['10', '20', '30'],
  hasLocalProvider: [true, false, null],
  localProviderCount: [2, 0, null],
  localClinicalBedProviders: [1, 0, null],
  localClinicalBeds: [20, 0, null],
  countyEligibleProviderCount: [3, 3, 0],
  countyBlockedProviderCount: [1, 1, 0],
  sectorRowExcluded: [false, false, true],
};

describe('the generated health-access payload', () => {
  const generated = readJson<HealthAccessPayload>('health-access-uat.json');
  const attributes = readJson<{ siruta: string[]; county: string[] }>('attributes.json');

  it('is aligned to the same UAT index as attributes.json', () => {
    expect(healthAccessPayloadAligned(generated, attributes.siruta)).toBe(true);
  });

  it('identifies the shared health-access view it was built from', () => {
    expect(generated.sourceViewId).toBe('health-service-access-uat-2024-2026');
    expect(generated.sourceViewSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(healthAccessPeriodLabel(generated)).toBe('2024-2026');
  });

  it('keeps Bucharest sectors as excluded rows rather than copying city counts to each sector', () => {
    const sectorIndexes = attributes.county
      .map((county, index) => (county === 'B' ? index : -1))
      .filter((index) => index >= 0);

    expect(sectorIndexes).toHaveLength(6);
    for (const index of sectorIndexes) {
      expect(generated.sectorRowExcluded[index], generated.siruta[index]).toBe(true);
      expect(generated.localProviderCount[index], generated.siruta[index]).toBeNull();
    }
  });

  it('reports only eligible provider counts from rows with UAT-level evidence', () => {
    const totals = healthAccessTotals(generated, generated.siruta.map((_siruta, index) => index));
    const shared = readRootJson<{
      summary: {
        eligibleProviders: number;
        blockedProviders: number;
        namedExclusions: number;
        uatsWithLocalProvider: number;
        excludedSectorRows: number;
      };
      units: Array<{ siruta: string; hasLocalProvider: boolean; localProviderCount: number }>;
    }>('packages/health_access/data/health-service-access-uat-2024-2026.json');
    const bucharest = shared.units.find((unit) => unit.siruta === '179132');

    expect(generated.summary?.eligibleProviders).toBe(shared.summary.eligibleProviders);
    expect(generated.summary?.blockedProviders).toBe(shared.summary.blockedProviders);
    expect(generated.summary?.namedExclusions).toBe(shared.summary.namedExclusions);
    expect(generated.summary?.sourceExcludedSectorRows).toBe(shared.summary.excludedSectorRows);
    expect(totals).toMatchObject({
      localProviderCount: generated.summary?.localProviderCount,
      uatsWithLocalProvider: generated.summary?.uatsWithLocalProvider,
      sectorRowsExcluded: 6,
    });
    expect(totals!.localProviderCount + (bucharest?.localProviderCount ?? 0)).toBe(
      shared.summary.eligibleProviders,
    );
    expect(totals!.uatsWithLocalProvider + (bucharest?.hasLocalProvider ? 1 : 0)).toBe(
      shared.summary.uatsWithLocalProvider,
    );
  });
});

describe('health-access payload alignment', () => {
  it('accepts a payload with one value per UAT index', () => {
    expect(healthAccessPayloadAligned(payload, ['10', '20', '30'])).toBe(true);
  });

  it('rejects a payload whose arrays would shift the UAT index', () => {
    expect(
      healthAccessPayloadAligned({ ...payload, localProviderCount: [2, 0] }, [
        '10',
        '20',
        '30',
      ]),
    ).toBe(false);
  });

  it('rejects a payload in the wrong SIRUTA order', () => {
    expect(healthAccessPayloadAligned(payload, ['20', '10', '30'])).toBe(false);
  });
});

describe('health-access totals', () => {
  it('sums local providers and keeps excluded sectors out of local counts', () => {
    expect(healthAccessTotals(payload, [0, 1, 2])).toEqual({
      localProviderCount: 2,
      uatsWithLocalProvider: 1,
      uatsWithHealthData: 2,
      sectorRowsExcluded: 1,
      localClinicalBedProviders: 1,
      localClinicalBeds: 20,
    });
  });

  it('stays absent until the lazy payload is loaded', () => {
    expect(healthAccessTotals(null, [0, 1])).toBeNull();
  });
});

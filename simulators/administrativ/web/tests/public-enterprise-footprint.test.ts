import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  publicEnterpriseFootprintPayloadAligned,
  publicEnterpriseFootprintPeriodLabel,
  publicEnterpriseFootprintTotals,
  type PublicEnterpriseFootprintPayload,
} from '../src/app/public-enterprise-footprint';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const readJson = <T>(name: string): T => JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')) as T;

const payload: PublicEnterpriseFootprintPayload = {
  id: 'administrativ-public-enterprise-footprint-2024-2026',
  sourceViewId: 'public-enterprise-administrative-footprint-2024-2026',
  sourceViewSha256: 'a'.repeat(64),
  periodStart: '2024',
  periodEnd: '2026',
  publisher: 'companiidestat.ro',
  license: 'CC BY 4.0',
  attribution: 'companiidestat.ro',
  siruta: ['10', '20', '30'],
  authorityCount: [1, 0, 2],
  companyCount: [2, 0, 3],
  activeCompanyCount: [1, 0, 3],
  companiesWithFinancials: [2, 0, 2],
  lossMakingCompanyCount: [1, 0, 1],
  employeeCount: [10, 0, 20],
  revenueRon: [100, 0, 300],
  profitLossRon: [-10, 0, 50],
  debtRon: [80, 0, 120],
  subsidiesRon: [5, 0, 15],
};

describe('the generated public-enterprise footprint payload', () => {
  const generated = readJson<PublicEnterpriseFootprintPayload>('public-enterprise-footprint.json');
  const attributes = readJson<{ siruta: string[] }>('attributes.json');

  it('is aligned to the same UAT index as attributes.json', () => {
    expect(publicEnterpriseFootprintPayloadAligned(generated, attributes.siruta)).toBe(true);
  });

  it('identifies the aggregate source and keeps finite numeric arrays', () => {
    expect(generated.sourceViewId).toBe('public-enterprise-administrative-footprint-2024-2026');
    expect(generated.sourceViewSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(publicEnterpriseFootprintPeriodLabel(generated)).toBe('2024-2026');
    for (const series of [
      generated.authorityCount,
      generated.companyCount,
      generated.activeCompanyCount,
      generated.companiesWithFinancials,
      generated.lossMakingCompanyCount,
      generated.employeeCount,
      generated.revenueRon,
      generated.profitLossRon,
      generated.debtRon,
      generated.subsidiesRon,
    ]) {
      expect(series).toHaveLength(attributes.siruta.length);
      for (const value of series) expect(Number.isFinite(value)).toBe(true);
    }
  });
});

describe('public-enterprise footprint totals', () => {
  it('sums selected unit members without loading company rows', () => {
    expect(publicEnterpriseFootprintTotals(payload, [0, 2])).toEqual({
      authorityCount: 3,
      companyCount: 5,
      activeCompanyCount: 4,
      companiesWithFinancials: 4,
      lossMakingCompanyCount: 2,
      employeeCount: 30,
      revenueRon: 400,
      profitLossRon: 40,
      debtRon: 200,
      subsidiesRon: 20,
    });
  });

  it('stays absent until the lazy payload is loaded', () => {
    expect(publicEnterpriseFootprintTotals(null, [0, 2])).toBeNull();
  });

  it('rejects shifted arrays', () => {
    expect(
      publicEnterpriseFootprintPayloadAligned({ ...payload, companyCount: [2, 0] }, [
        '10',
        '20',
        '30',
      ]),
    ).toBe(false);
  });
});

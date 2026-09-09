import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  localFinancePayloadAligned,
  localFinancePeriodLabel,
  localFinanceTotals,
  type LocalFinancePayload,
} from '../src/app/local-finance';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '../public/data');
const readJson = <T>(name: string): T => JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')) as T;

const payload: LocalFinancePayload = {
  id: 'administrativ-local-finance-2024',
  sourceMartId: 'local-finance-mart-2023-2025',
  sourceMartSha256: 'a'.repeat(64),
  period: '2024',
  sourceYears: [2023, 2024, 2025],
  siruta: ['10', '20', '30'],
  revenueRon: [100, 0, 300],
  ownRevenueRon: [25, 0, 150],
  ownRevenueShare: [0.25, null, 0.5],
  spendingRon2023: [100, null, 300],
  spendingRon2025: [120, null, 270],
  revenueRon2023: [200, null, 400],
  revenueRon2025: [300, null, 600],
  ownRevenueRon2023: [40, null, 200],
  ownRevenueRon2025: [75, null, 270],
  spendingGrowth2023To2025: [0.2, null, -0.1],
  ownRevenueShareChange2023To2025: [0.05, null, -0.05],
};

describe('the generated local finance payload', () => {
  const generated = readJson<LocalFinancePayload>('local-finance-2024.json');
  const attributes = readJson<{ siruta: string[] }>('attributes.json');

  it('is aligned to the same UAT index as attributes.json', () => {
    expect(localFinancePayloadAligned(generated, attributes.siruta)).toBe(true);
  });

  it('identifies the shared mart release asset it was built from', () => {
    expect(generated.period).toBe('2024');
    expect(generated.sourceMartId).toBe('local-finance-mart-2023-2025');
    expect(generated.sourceMartSha256).toMatch(/^[a-f0-9]{64}$/);
    if (generated.sourceYears) expect(generated.sourceYears).toEqual([2023, 2024, 2025]);
  });

  it('keeps finite values and recomputes own-revenue share from the denominators', () => {
    for (let i = 0; i < generated.siruta.length; i += 1) {
      expect(generated.revenueRon[i]!, generated.siruta[i]).toBeGreaterThan(0);
      expect(generated.ownRevenueRon[i]!, generated.siruta[i]).toBeGreaterThanOrEqual(0);
      expect(Number.isFinite(generated.revenueRon[i])).toBe(true);
      expect(Number.isFinite(generated.ownRevenueRon[i])).toBe(true);
      expect(generated.ownRevenueShare[i], generated.siruta[i]).toBeCloseTo(
        generated.ownRevenueRon[i]! / generated.revenueRon[i]!,
        4,
      );
    }
  });

  it('keeps optional multi-year trend arrays aligned when they are present', () => {
    for (const series of [
      generated.spendingRon2023,
      generated.spendingRon2025,
      generated.revenueRon2023,
      generated.revenueRon2025,
      generated.ownRevenueRon2023,
      generated.ownRevenueRon2025,
      generated.spendingGrowth2023To2025,
      generated.ownRevenueShareChange2023To2025,
    ]) {
      if (!series) continue;
      expect(series).toHaveLength(attributes.siruta.length);
      for (const value of series) {
        expect(value === null || Number.isFinite(value)).toBe(true);
      }
    }
  });
});

describe('local finance payload alignment', () => {
  it('accepts a payload with one value per UAT index', () => {
    expect(localFinancePayloadAligned(payload, ['10', '20', '30'])).toBe(true);
  });

  it('rejects a payload whose arrays would shift the UAT index', () => {
    expect(localFinancePayloadAligned({ ...payload, ownRevenueRon: [25, 0] }, ['10', '20', '30'])).toBe(
      false,
    );
  });

  it('rejects a payload whose optional trend arrays would shift the UAT index', () => {
    expect(
      localFinancePayloadAligned(
        { ...payload, spendingGrowth2023To2025: [0.2, null] },
        ['10', '20', '30'],
      ),
    ).toBe(false);
  });

  it('rejects a payload whose optional trend base arrays would shift the UAT index', () => {
    expect(
      localFinancePayloadAligned(
        { ...payload, spendingRon2023: [100, null] },
        ['10', '20', '30'],
      ),
    ).toBe(false);
  });

  it('accepts older payloads before the optional trend arrays existed', () => {
    const legacy: LocalFinancePayload = { ...payload };
    delete legacy.sourceYears;
    delete legacy.spendingRon2023;
    delete legacy.spendingRon2025;
    delete legacy.revenueRon2023;
    delete legacy.revenueRon2025;
    delete legacy.ownRevenueRon2023;
    delete legacy.ownRevenueRon2025;
    delete legacy.spendingGrowth2023To2025;
    delete legacy.ownRevenueShareChange2023To2025;
    expect(localFinancePayloadAligned(legacy, ['10', '20', '30'])).toBe(true);
  });

  it('rejects a payload in the wrong SIRUTA order', () => {
    expect(localFinancePayloadAligned(payload, ['20', '10', '30'])).toBe(false);
  });
});

describe('local finance totals', () => {
  it('sums own revenue in the selected unit order and recomputes merged trends from bases', () => {
    const totals = localFinanceTotals(payload, [0, 2]);
    expect(totals).toMatchObject({
      revenueRon: 400,
      ownRevenueRon: 175,
      ownRevenueShare: 0.4375,
      sourceYears: [2023, 2024, 2025],
    });
    expect(totals?.spendingGrowth2023To2025).toBeCloseTo(-0.025);
    expect(totals?.ownRevenueShareChange2023To2025).toBeCloseTo(-0.0166667);
  });

  it('averages member trends for legacy trend-only payloads', () => {
    const legacy: LocalFinancePayload = { ...payload };
    delete legacy.spendingRon2023;
    delete legacy.spendingRon2025;
    delete legacy.revenueRon2023;
    delete legacy.revenueRon2025;
    delete legacy.ownRevenueRon2023;
    delete legacy.ownRevenueRon2025;

    const totals = localFinanceTotals(legacy, [0, 2]);

    expect(totals?.spendingGrowth2023To2025).toBeCloseTo(0.05);
    expect(totals?.ownRevenueShareChange2023To2025).toBeCloseTo(0);
  });

  it('has no share when the selected unit has no revenue denominator', () => {
    expect(localFinanceTotals(payload, [1])).toEqual({
      revenueRon: 0,
      ownRevenueRon: 0,
      ownRevenueShare: null,
      sourceYears: [2023, 2024, 2025],
      spendingGrowth2023To2025: null,
      ownRevenueShareChange2023To2025: null,
    });
  });

  it('stays absent until the lazy payload is loaded', () => {
    expect(localFinanceTotals(null, [0, 2])).toBeNull();
  });
});

describe('local finance source period labels', () => {
  it('uses the source year span when the payload carries one', () => {
    expect(localFinancePeriodLabel(payload)).toBe('2023-2025');
  });

  it('falls back to the payload period for older payloads', () => {
    expect(localFinancePeriodLabel({ ...payload, sourceYears: undefined })).toBe('2024');
  });
});

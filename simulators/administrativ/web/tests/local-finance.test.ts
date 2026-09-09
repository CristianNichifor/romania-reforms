import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  localFinancePayloadAligned,
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
  siruta: ['10', '20', '30'],
  revenueRon: [100, 0, 300],
  ownRevenueRon: [25, 0, 150],
  ownRevenueShare: [0.25, null, 0.5],
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

  it('rejects a payload in the wrong SIRUTA order', () => {
    expect(localFinancePayloadAligned(payload, ['20', '10', '30'])).toBe(false);
  });
});

describe('local finance totals', () => {
  it('sums own revenue in the selected unit order and recomputes the share', () => {
    expect(localFinanceTotals(payload, [0, 2])).toEqual({
      revenueRon: 400,
      ownRevenueRon: 175,
      ownRevenueShare: 0.4375,
    });
  });

  it('has no share when the selected unit has no revenue denominator', () => {
    expect(localFinanceTotals(payload, [1])).toEqual({
      revenueRon: 0,
      ownRevenueRon: 0,
      ownRevenueShare: null,
    });
  });

  it('stays absent until the lazy payload is loaded', () => {
    expect(localFinanceTotals(null, [0, 2])).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';

import { readCap, readCapEntities } from './cap';
import type { CapSeries } from './cap';

const band = (
  scope: string,
  measure: string,
  index: number,
  label: string,
  overCap: boolean,
  count: number,
): CapSeries => ({
  id: `plafon-${scope}-${measure}-banda-${index}`,
  unit: 'COUNT',
  dims: { kind: 'band', scope, measure, band: label, bandIndex: String(index), overCap: String(overCap) },
  observations: [{ period: '2025', value: count }],
});

/** Shaped exactly like the importer's output, in deliberately shuffled order. */
const SERIES: CapSeries[] = [
  band('ordonator', 'narrow', 2, '10–20%', false, 300),
  band('ordonator', 'narrow', 0, 'fără sporuri raportate', false, 2000),
  band('ordonator', 'narrow', 4, '30–50%', true, 20),
  band('ordonator', 'narrow', 1, 'sub 10%', false, 900),
  band('ordonator', 'narrow', 3, '20–30%', true, 30),
  band('ordonator', 'narrow', 5, 'peste 50%', true, 6),
  band('ordonator', 'wide', 0, 'fără sporuri raportate', false, 500),
  band('ordonator', 'wide', 1, 'sub 10%', false, 1000),
  {
    id: 'plafon-ordonator-narrow-peste-plafon',
    unit: 'COUNT',
    dims: { kind: 'overCap', scope: 'ordonator', measure: 'narrow' },
    observations: [{ period: '2025', value: 56 }],
  },
  {
    id: 'plafon-ordonator-narrow-pondere-masa',
    unit: 'PC_TOT',
    dims: { kind: 'overCapWeight', scope: 'ordonator', measure: 'narrow' },
    observations: [{ period: '2025', value: 0.194 }],
  },
  {
    id: 'plafon-entitate-4266456-narrow',
    unit: 'RATE',
    dims: { kind: 'entity', cui: '4266456', name: 'MINISTERUL SANATATII', entityType: 'ministry', measure: 'narrow' },
    observations: [{ period: '2025', value: 0.282 }],
  },
  {
    id: 'plafon-entitate-4266456-wide',
    unit: 'RATE',
    dims: { kind: 'entity', cui: '4266456', name: 'MINISTERUL SANATATII', entityType: 'ministry', measure: 'wide' },
    observations: [{ period: '2025', value: 0.397 }],
  },
  {
    id: 'plafon-entitate-4266456-baza',
    unit: 'CP_MNAC',
    dims: { kind: 'entityBase', cui: '4266456', name: 'MINISTERUL SANATATII' },
    observations: [{ period: '2025', value: 8_031_000_000 }],
  },
  {
    id: 'plafon-entitate-13729380-narrow',
    unit: 'RATE',
    dims: { kind: 'entity', cui: '13729380', name: 'MINISTERUL EDUCATIEI', entityType: 'ministry', measure: 'narrow' },
    observations: [{ period: '2025', value: 0.04 }],
  },
  {
    id: 'plafon-entitate-13729380-baza',
    unit: 'CP_MNAC',
    dims: { kind: 'entityBase', cui: '13729380', name: 'MINISTERUL EDUCATIEI' },
    observations: [{ period: '2025', value: 36_513_000_000 }],
  },
];

describe('reading the ceiling', () => {
  it('orders bands by the index the importer wrote, not by their labels', () => {
    // Sorting on prose would put 'sub 10%' after 'peste 50%' and quietly draw a
    // distribution that runs backwards.
    const reading = readCap(SERIES, 'ordonator', 'narrow')!;
    expect(reading.bands.map((b) => b.label)).toEqual([
      'fără sporuri raportate',
      'sub 10%',
      '10–20%',
      '20–30%',
      '30–50%',
      'peste 50%',
    ]);
  });

  it('separates how many breach from how much of the wage bill they hold', () => {
    const reading = readCap(SERIES, 'ordonator', 'narrow')!;
    // 56 of 3 256 institutions is under 2% of them, but they carry 19,4% of the money.
    // Counting institutions treats a commune and a ministry alike; the weight does not.
    expect(reading.total).toBe(3256);
    expect(reading.overCapCount).toBe(56);
    expect(reading.overCapCount / reading.total).toBeLessThan(0.02);
    expect(reading.overCapWeight).toBeCloseTo(0.194, 3);
  });

  it('trusts the published breach count over re-summing the bands', () => {
    // The bands here total 56 over the cap and so does the series; if a band were ever
    // dropped the two would disagree, and the published figure is the one that is right.
    const summed = readCap(SERIES, 'ordonator', 'narrow')!
      .bands.filter((b) => b.overCap)
      .reduce((n, b) => n + b.count, 0);
    expect(summed).toBe(56);
  });

  it('gives each band a share of its own scope', () => {
    const reading = readCap(SERIES, 'ordonator', 'narrow')!;
    expect(reading.bands.reduce((sum, b) => sum + b.share, 0)).toBeCloseTo(1, 10);
  });

  it('returns null for a scope and measure the document does not carry', () => {
    expect(readCap(SERIES, 'pereche', 'narrow')).toBeNull();
  });

  it('falls back to zero weight rather than inventing one', () => {
    const reading = readCap(SERIES, 'ordonator', 'wide')!;
    expect(reading.total).toBe(1500);
    expect(reading.overCapWeight).toBe(0);
  });

  it('folds the three entity series into one record, largest wage bill first', () => {
    const entities = readCapEntities(SERIES);
    expect(entities.map((e) => e.name)).toEqual(['MINISTERUL EDUCATIEI', 'MINISTERUL SANATATII']);

    const health = entities.find((e) => e.cui === '4266456')!;
    expect(health.base).toBe(8_031_000_000);
    expect(health.narrow).toBeCloseTo(0.282, 3);
    expect(health.wide).toBeCloseTo(0.397, 3);
    expect(health.entityType).toBe('ministry');
  });

  it('leaves a missing measure at zero instead of undefined', () => {
    // Education has no 'wide' series in this fixture; a chart must draw nothing there,
    // not NaN.
    const education = readCapEntities(SERIES).find((e) => e.cui === '13729380')!;
    expect(education.wide).toBe(0);
    expect(education.narrow).toBeCloseTo(0.04, 3);
  });
});

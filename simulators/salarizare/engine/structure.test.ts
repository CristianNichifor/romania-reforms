import { describe, expect, it } from 'vitest';

import { decimalPlaces, resolveSeries, spanByPeriod, structure } from './structure';
import type { Position, Regime } from './types';

const provenance = { source: 'test', locator: 'test', confidence: 'verbatim' } as const;

function regime(positions: Position[], grades = defaultGrades()): Regime {
  return {
    id: 'test',
    name: 'test',
    jurisdiction: 'RO',
    status: 'draft',
    currency: 'RON',
    minorUnits: 2,
    provenance,
    reference: {
      amount: 4100,
      factor: 1,
      baseDate: '2026-12-01',
      unit: 'coefficient',
      period: 'month',
      rounding: { step: 100, mode: 'ceil' },
      provenance,
    },
    grades,
    ladders: {},
    positions,
    supplements: [],
    caps: [],
    levies: [],
    limitations: [],
  };
}

function defaultGrades() {
  return [
    { id: 'g1', label: 'Gradul 1', min: 1.0, max: 1.19, provenance },
    { id: 'g2', label: 'Gradul 2', min: 1.2, max: 1.34, provenance },
  ];
}

function position(code: string, values: number[], extra: Partial<Position> = {}): Position {
  return {
    code,
    name: code,
    family: 'test',
    kind: 'execution',
    variants: values.map((value) => ({ value, provenance })),
    provenance,
    ...extra,
  };
}

describe('decimalPlaces', () => {
  it('separates a designed coefficient from a back-solved one', () => {
    expect(decimalPlaces(2.4)).toBe(1);
    expect(decimalPlaces(3.29)).toBe(2);
    expect(decimalPlaces(5.189610389610378)).toBe(15);
    expect(decimalPlaces(1.1907527039036847)).toBe(16);
  });

  it('treats an integer coefficient as zero places, not one', () => {
    // The grid floor is stored as an integer. Reading it as 1.0 would put it in the
    // wrong histogram bucket and hide the bottom of the scale.
    expect(decimalPlaces(1)).toBe(0);
    expect(decimalPlaces(8)).toBe(0);
  });
});

describe('resolveSeries', () => {
  const series = [
    { from: '2026-12-01', value: 4100 },
    { from: '2028-01-01', value: 4300 },
  ];

  it('returns a constant unchanged', () => {
    expect(resolveSeries(1.265085)).toBe(1.265085);
  });

  it('takes the step in force at the date, not the newest', () => {
    expect(resolveSeries(series, '2027-06-01')).toBe(4100);
    expect(resolveSeries(series, '2029-01-01')).toBe(4300);
  });

  it('defaults to the earliest step rather than the latest', () => {
    // Defaulting to the newest would report a 2031 grid as though it were in force.
    expect(resolveSeries(series)).toBe(4100);
  });
});

describe('structure', () => {
  it('counts distinct values, not occurrences', () => {
    const result = structure(regime([position('a', [1.2, 1.2]), position('b', [1.2, 1.3])]));
    expect(result.variants).toBe(4);
    expect(result.distinctValues).toBe(2);
  });

  it('reports the back-solved share against distinct values', () => {
    const result = structure(
      regime([position('a', [1.2, 1.25, 1.1907527039036847, 1.3333333333333333])]),
    );
    expect(result.backSolvedShare).toBeCloseTo(0.5);
    expect(result.roundedShare).toBeCloseTo(0.5);
  });

  it('finds the coefficients that fall between grade bands', () => {
    // 1.195 is above grade 1's ceiling of 1.19 and below grade 2's floor of 1.20.
    const result = structure(regime([position('a', [1.1, 1.195, 1.25])]));
    expect(result.variantsInGaps).toBe(1);
    expect(result.bandGaps[0]).toMatchObject({
      belowGradeId: 'g1',
      aboveGradeId: 'g2',
      from: 1.19,
      to: 1.2,
      variants: 1,
    });
    expect(result.gradeOccupancy.map((g) => g.variants)).toEqual([1, 1]);
  });

  it('never reports money', () => {
    const result = structure(regime([position('a', [1.2])]));
    expect(JSON.stringify(result)).not.toContain('RON');
    expect(result).not.toHaveProperty('currency');
  });
});

describe('spanByPeriod', () => {
  const positions = [
    position('floor', [1.0]),
    position('president', [6.47, 6.85, 8.0], {
      kind: 'dignitary',
      variants: [
        { value: 6.47, dims: { an: '2026/2027' }, provenance },
        { value: 6.85, dims: { an: '2028' }, provenance },
        { value: 8.0, dims: { an: '2031' }, provenance },
      ],
    }),
  ];

  it('moves the ceiling per year while the floor stays put', () => {
    const span = spanByPeriod(positions);
    expect(span.map((s) => s.period)).toEqual(['2026/2027', '2028', '2031']);
    expect(span[0]).toMatchObject({ min: 1.0, max: 6.47 });
    expect(span[2]).toMatchObject({ min: 1.0, max: 8.0 });
  });

  it('reports the ratio in force, not the ratio at the end of the escalator', () => {
    const span = spanByPeriod(positions);
    expect(span[0].ratio).toBeCloseTo(6.47);
    expect(span[2].ratio).toBeCloseTo(8.0);
  });

  it('is empty when nothing carries a year', () => {
    expect(spanByPeriod([position('a', [1.2])])).toEqual([]);
  });
});

describe('assimilation', () => {
  it('counts merged positions and the titles they absorb', () => {
    const merged = position('m', [2.0], {
      titles: [{ name: 'Director', canonical: true }, { name: 'sef compartiment' }],
      assimilation: { rawTitleCell: 'Director; sef compartiment', parse: 'semicolon', fanIn: 2 },
    });
    const plain = position('p', [1.5], {
      assimilation: { rawTitleCell: 'Auditor', parse: 'single', fanIn: 1 },
    });
    const result = structure(regime([merged, plain])).assimilation;

    expect(result.codedPositions).toBe(2);
    expect(result.mergedPositions).toBe(1);
    expect(result.titlesAbsorbed).toBe(3);
    expect(result.bySeparator.semicolon).toBe(1);
    expect(result.bySeparator.single).toBe(1);
    expect(result.fanInHistogram).toEqual({ 1: 1, 2: 1 });
  });

  it('counts positions whose title split a human has not ruled on', () => {
    const unclear = position('u', [1.5], {
      assimilation: { rawTitleCell: 'a; b; c', parse: 'needsReview', fanIn: 1 },
    });
    expect(structure(regime([unclear])).assimilation.needsReview).toBe(1);
  });
});

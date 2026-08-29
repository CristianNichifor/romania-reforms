/**
 * View 2 — structural metrics.
 *
 * Everything here is dimensionless on purpose. Not one function returns money, so
 * there is no path by which a Romanian and a Danish figure can be placed beside each
 * other as levels. Shape only: how many distinct values, how precise they are, how far
 * apart the ends sit, how much occupational detail the grid collapses.
 *
 * Pure. No imports, no I/O, no dependencies.
 */

import type {
  Assimilation,
  IsoDate,
  Position,
  PositionVariant,
  Regime,
  ValueSeries,
} from './types';

// ------------------------------------------------------------------ primitives

/** Resolve a ValueSeries at a date. Undated series are constant. */
export function resolveSeries(series: ValueSeries, asOf?: IsoDate): number {
  if (typeof series === 'number') return series;
  const steps = [...series].sort((a, b) => a.from.localeCompare(b.from));
  if (!asOf) return steps[0].value;
  const applicable = steps.filter((s) => s.from <= asOf);
  return (applicable.length ? applicable[applicable.length - 1] : steps[0]).value;
}

/**
 * Decimal places in the shortest exact representation.
 *
 * This is the measurement the whole view exists for, so it must not lie. `repr`-style
 * shortest round-tripping is what distinguishes a designed 2,40 from a back-solved
 * 5,189610389610378 — formatting to fixed precision first would erase exactly the
 * signal being measured.
 */
export function decimalPlaces(value: number): number {
  const text = String(value);
  if (text.includes('e') || text.includes('E')) return 17;
  const dot = text.indexOf('.');
  if (dot === -1) return 0;
  return text.length - dot - 1;
}

function variantValue(variant: PositionVariant, asOf?: IsoDate): number | null {
  if (variant.value !== undefined) return resolveSeries(variant.value, asOf);
  if (variant.range) return resolveSeries(variant.range.min, asOf);
  return null;
}

// -------------------------------------------------------------------- results

export interface GradeOccupancy {
  gradeId: string;
  label: string;
  min: number;
  max: number;
  /** Variants whose value falls inside this band. */
  variants: number;
  /** Spread of values inside the band, as a share of the band's own width. */
  fill: number;
}

export interface BandGap {
  belowGradeId: string;
  aboveGradeId: string;
  from: number;
  to: number;
  variants: number;
}

export interface SpanPoint {
  period: string;
  min: number;
  max: number;
  ratio: number;
}

export interface AssimilationMetrics {
  codedPositions: number;
  mergedPositions: number;
  fanInHistogram: Record<number, number>;
  titlesAbsorbed: number;
  bySeparator: Record<Assimilation['parse'], number>;
  needsReview: number;
  byFamily: Array<{ family: string; positions: number; merged: number; titlesAbsorbed: number }>;
}

export interface StructureMetrics {
  regimeId: string;
  positions: number;
  variants: number;
  distinctValues: number;
  /** decimalPlaces -> count of distinct values carrying that precision. */
  precisionHistogram: Record<number, number>;
  /** Share of distinct values with 14 or more decimal places. */
  backSolvedShare: number;
  roundedShare: number;
  span: { min: number; max: number; ratio: number };
  /** What the regime says its own span is. Art. 5 says 8. */
  declaredRatio: number | null;
  spanByPeriod: SpanPoint[];
  gradeOccupancy: GradeOccupancy[];
  bandGaps: BandGap[];
  variantsInGaps: number;
  assimilation: AssimilationMetrics;
}

// ------------------------------------------------------------------ the metric

export function structure(
  regime: Regime,
  opts?: { asOf?: IsoDate; period?: string },
): StructureMetrics {
  const asOf = opts?.asOf;
  // Restricting to one phase makes every metric below describe the grid actually in
  // force that year, not the union of all six annual columns. Without it `span` reports
  // the 2031 ceiling against the day-one floor and calls the result the law's ratio.
  // Variants without a year of their own belong to every year.
  const positions = opts?.period
    ? regime.positions
        .map((p) => ({
          ...p,
          variants: p.variants.filter((v) => v.dims?.an === undefined || v.dims.an === opts.period),
        }))
        .filter((p) => p.variants.length > 0)
    : regime.positions;

  const values: number[] = [];
  for (const position of positions) {
    for (const variant of position.variants) {
      const value = variantValue(variant, asOf);
      if (value !== null) values.push(value);
    }
  }

  const distinct = [...new Set(values)];
  const precisionHistogram: Record<number, number> = {};
  for (const value of distinct) {
    const dp = decimalPlaces(value);
    precisionHistogram[dp] = (precisionHistogram[dp] ?? 0) + 1;
  }
  const backSolved = distinct.filter((v) => decimalPlaces(v) >= 14).length;
  const rounded = distinct.filter((v) => decimalPlaces(v) <= 2).length;

  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;

  // Grade bands, and the gaps between them. Art. 9(2) writes the bands to two
  // decimals while the annexes carry sixteen, so consecutive bands do not touch and
  // real coefficients fall into the space between.
  const bands = regime.grades.map((g) => ({
    gradeId: g.id,
    label: g.label ?? g.id,
    min: resolveSeries(g.min, asOf),
    max: resolveSeries(g.max, asOf),
  }));
  bands.sort((a, b) => a.min - b.min);

  const gradeOccupancy: GradeOccupancy[] = bands.map((band) => {
    const inside = values.filter((v) => v >= band.min && v <= band.max);
    const width = band.max - band.min;
    const spread = inside.length > 1 ? Math.max(...inside) - Math.min(...inside) : 0;
    return {
      ...band,
      variants: inside.length,
      fill: width > 0 ? spread / width : 0,
    };
  });

  const bandGaps: BandGap[] = [];
  for (let i = 0; i < bands.length - 1; i += 1) {
    const from = bands[i].max;
    const to = bands[i + 1].min;
    if (to <= from) continue;
    const inside = values.filter((v) => v > from && v < to);
    bandGaps.push({
      belowGradeId: bands[i].gradeId,
      aboveGradeId: bands[i + 1].gradeId,
      from,
      to,
      variants: inside.length,
    });
  }
  const variantsInGaps = bandGaps.reduce((sum, gap) => sum + gap.variants, 0);

  return {
    regimeId: regime.id,
    positions: positions.length,
    variants: values.length,
    distinctValues: distinct.length,
    precisionHistogram,
    backSolvedShare: distinct.length ? backSolved / distinct.length : 0,
    roundedShare: distinct.length ? rounded / distinct.length : 0,
    span: { min, max, ratio: min > 0 ? max / min : 0 },
    declaredRatio: declaredRatioOf(regime),
    spanByPeriod: spanByPeriod(positions, asOf),
    gradeOccupancy,
    bandGaps,
    variantsInGaps,
    assimilation: assimilation(regime),
  };
}

/**
 * The span in force in each calendar year.
 *
 * Annex IX phases the dignitary coefficients across year columns, so the top of the
 * grid moves while the floor stays put. A single min:max ratio would report the 2031
 * grid as though it took effect on day one. Variants carrying a year dimension count
 * only in that year; every other variant counts in all of them.
 */
export function spanByPeriod(positions: readonly Position[], asOf?: IsoDate): SpanPoint[] {
  const periods = new Set<string>();
  for (const position of positions) {
    for (const variant of position.variants) {
      const period = variant.dims?.an;
      if (period) periods.add(period);
    }
  }
  if (periods.size === 0) return [];

  const ordered = [...periods].sort((a, b) => a.localeCompare(b));
  return ordered.map((period) => {
    const values: number[] = [];
    for (const position of positions) {
      for (const variant of position.variants) {
        const own = variant.dims?.an;
        if (own !== undefined && own !== period) continue;
        const value = variantValue(variant, asOf);
        if (value !== null) values.push(value);
      }
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { period, min, max, ratio: min > 0 ? max / min : 0 };
  });
}

function declaredRatioOf(regime: Regime): number | null {
  // The regime states its intended span in a limitation rather than as a field: the
  // ratio is a claim the law makes about itself, not a parameter the engine consumes.
  const stated = regime.limitations.find((l) => l.id.startsWith('raportul-1-8'));
  return stated ? 8 : null;
}

export function assimilation(regime: Regime): AssimilationMetrics {
  const bySeparator = {
    single: 0,
    semicolon: 0,
    comma: 0,
    slash: 0,
    mixed: 0,
    needsReview: 0,
  } as Record<Assimilation['parse'], number>;

  const fanInHistogram: Record<number, number> = {};
  const families = new Map<string, { positions: number; merged: number; titlesAbsorbed: number }>();

  let merged = 0;
  let titlesAbsorbed = 0;
  let needsReview = 0;

  for (const position of regime.positions) {
    const parse = position.assimilation?.parse ?? 'single';
    bySeparator[parse] += 1;
    if (parse === 'needsReview') needsReview += 1;

    const fanIn = position.assimilation?.fanIn ?? position.titles?.length ?? 1;
    fanInHistogram[fanIn] = (fanInHistogram[fanIn] ?? 0) + 1;
    titlesAbsorbed += fanIn;
    if (fanIn > 1) merged += 1;

    const family = families.get(position.family) ?? { positions: 0, merged: 0, titlesAbsorbed: 0 };
    family.positions += 1;
    family.titlesAbsorbed += fanIn;
    if (fanIn > 1) family.merged += 1;
    families.set(position.family, family);
  }

  return {
    codedPositions: regime.positions.length,
    mergedPositions: merged,
    fanInHistogram,
    titlesAbsorbed,
    bySeparator,
    needsReview,
    byFamily: [...families.entries()]
      .map(([family, counts]) => ({ family, ...counts }))
      .sort((a, b) => b.merged - a.merged),
  };
}

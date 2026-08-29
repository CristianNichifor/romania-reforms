/**
 * The law's grid against what people are actually paid.
 *
 * Every Romanian figure in this project has come from a statute: a coefficient times a
 * reference value, which is what the law *says*, not what lands in an account. The Danish
 * side has had measured earnings from the start, and the asymmetry has been recorded as a
 * limitation on nearly every page.
 *
 * INS matrix FOM121A supplies the missing half for two sectors. It publishes the **base**
 * salary — the same quantity the grid holds, not total earnings — for public-sector
 * employees in education and health, by ISCO major group. So the grid can finally be
 * checked against a measurement.
 *
 * One difference between the two sides cannot be removed and must be carried into every
 * reading of the result:
 *
 *   **The grid is counted per position; the measurement is counted per person.** A median
 *   over the grid treats a post held by forty thousand teachers and one held by a single
 *   chief inspector as one vote each. The INS figure weights by headcount, because it is a
 *   survey of employees. Weighting the grid the same way would need per-position headcount,
 *   which Romania does not publish — that is precisely the gap this data does *not* close.
 *
 * So comparing the two medians is informative and is not an equality test. The range
 * comparison below is the safer reading: whether what people are paid falls inside what
 * the law provides for at all.
 */

import { resolveSeries } from './structure';
import type { Regime } from './types';

export interface MeasuredSeries {
  unit: string;
  dims?: Record<string, string>;
  observations: Array<{ period: string; value: number }>;
}

export interface OccupationPay {
  occupation: string;
  /** Measured monthly base salary, lei. */
  base: number;
  /** Employees behind that figure. */
  employees: number;
}

export interface SectorCheck {
  /** The importer's activity key: `invatamant` | `sanatate`. */
  activity: string;
  family: string;
  period: string;
  /** What INS measured, by ISCO major group, largest group first. */
  measured: OccupationPay[];
  /** The all-occupations figure, and the headcount behind it. */
  overall: OccupationPay | null;
  /** The grid, priced at its own reference value. */
  grid: { min: number; median: number; max: number; positions: number };
  /**
   * measured overall / grid median. Around 1 the law's middle matches the measured
   * middle; below 1 the law sits above what is paid, above 1 below it.
   */
  ratio: number | null;
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/** Base salaries the grid provides for one occupational family, in lei. */
export function gridPay(regime: Regime, family: string): SectorCheck['grid'] {
  const reference = resolveSeries(regime.reference.amount, regime.reference.baseDate);
  const positions = regime.positions.filter((p) => p.family === family);
  const values = positions
    .flatMap((p) => p.variants.map((v) => (typeof v.value === 'number' ? v.value : null)))
    .filter((n): n is number => n !== null)
    .map((coefficient) => coefficient * reference);

  return {
    min: values.length ? Math.min(...values) : 0,
    median: median(values),
    max: values.length ? Math.max(...values) : 0,
    positions: positions.length,
  };
}

export function checkAgainstMeasured(
  regime: Regime,
  series: MeasuredSeries[],
  activity: string,
  family: string,
): SectorCheck | null {
  const forActivity = (measure: string) =>
    series.filter((s) => s.dims?.kind === 'occupationGroup'
      && s.dims.measure === measure
      && s.dims.activity === activity);

  const pay = forActivity('base');
  const heads = forActivity('count');
  if (!pay.length) return null;

  // The most recent period both measures share, so a count is never paired with a salary
  // from a different year.
  const periodsOf = (list: MeasuredSeries[]) =>
    new Set(list.flatMap((s) => s.observations.map((o) => o.period)));
  const shared = [...periodsOf(pay)].filter((p) => periodsOf(heads).has(p)).sort();
  const period = shared[shared.length - 1];
  if (!period) return null;

  const at = (list: MeasuredSeries[], occupation: string) =>
    list
      .find((s) => s.dims?.occupation === occupation)
      ?.observations.find((o) => o.period === period)?.value ?? null;

  const occupations = [...new Set(pay.map((s) => s.dims?.occupation ?? ''))].filter(Boolean);
  const rows: OccupationPay[] = [];
  let overall: OccupationPay | null = null;

  for (const occupation of occupations) {
    const base = at(pay, occupation);
    const employees = at(heads, occupation);
    if (base === null || employees === null) continue;
    const row = { occupation, base, employees };
    // The total is a summary of the others, not another group beside them.
    if (occupation.startsWith('Toate')) overall = row;
    else rows.push(row);
  }

  rows.sort((a, b) => b.employees - a.employees);
  const grid = gridPay(regime, family);

  return {
    activity,
    family,
    period,
    measured: rows,
    overall,
    grid,
    ratio: overall && grid.median > 0 ? overall.base / grid.median : null,
  };
}

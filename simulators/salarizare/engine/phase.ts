/**
 * The years a regime phases itself over.
 *
 * The draft does not take effect at once. Annex IX publishes a column per year and walks
 * the dignitary coefficients from 2026/2027 up to 2031, so the declared 1:8 ratio is a
 * destination rather than a starting point — the grid in force on day one is 1:7,39. The
 * pages that quote the ratio have always been able to say this, because `spanByPeriod`
 * computes it, but a reader could only ever see the two endpoints.
 *
 * This module turns that phasing into something a control can move along. It reads the
 * periods out of the data rather than naming years in code: the moment an annex phases
 * something differently, the slider follows without an edit here.
 *
 * A period label is what the workbook prints — "2028", or "2026/2027" for a column that
 * covers two calendar years. Calendar years are what a reader thinks in, so the two are
 * mapped rather than conflated.
 */

import type { Regime } from './types';

export interface Phase {
  /** The label the source prints, e.g. "2026/2027". */
  period: string;
  /** Every calendar year that label covers. */
  years: number[];
}

const YEAR = /\d{4}/g;

/** The phases a regime declares, in order, or [] when it phases nothing. */
export function phases(regime: Regime): Phase[] {
  const labels = new Set<string>();
  for (const position of regime.positions) {
    for (const variant of position.variants) {
      if (variant.dims?.an) labels.add(variant.dims.an);
    }
  }
  return [...labels]
    .sort((a, b) => a.localeCompare(b))
    .map((period) => ({
      period,
      years: [...(period.match(YEAR) ?? [])].map(Number),
    }));
}

/** Every calendar year the regime distinguishes, ascending. */
export function phaseYears(regime: Regime): number[] {
  const years = new Set<number>();
  for (const phase of phases(regime)) {
    // A label like "2026/2027" names its endpoints; the years between them are covered
    // too, and a slider that skipped them would jump over a year the law does describe.
    if (phase.years.length > 1) {
      for (let y = Math.min(...phase.years); y <= Math.max(...phase.years); y += 1) years.add(y);
    } else {
      for (const y of phase.years) years.add(y);
    }
  }
  return [...years].sort((a, b) => a - b);
}

/** The period label in force in a calendar year, or null if the regime phases nothing. */
export function periodForYear(regime: Regime, year: number): string | null {
  const all = phases(regime);
  if (all.length === 0) return null;
  const hit = all.find(
    (p) =>
      p.years.includes(year) ||
      (p.years.length > 1 && year >= Math.min(...p.years) && year <= Math.max(...p.years)),
  );
  // Past the last published column the last column stays in force: the law does not
  // expire in 2032, it stops changing.
  if (hit) return hit.period;
  const last = all[all.length - 1];
  return year > Math.max(...last.years) ? last.period : all[0].period;
}

/**
 * An ISO date standing for a calendar year, for the dated-series resolver.
 *
 * December, not January: the reference value is dated 2026-12-01, so a year read at its
 * first day would resolve 2026 to the value in force *before* the law commences.
 */
export function asOfForYear(year: number): string {
  return `${year}-12-01`;
}

/** The calendar year an `asOf` date refers to, for putting a control back where it was. */
export function yearOfAsOf(asOf: string | undefined, fallback: number): number {
  const parsed = Number(asOf?.slice(0, 4));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

/**
 * One place that decides how an amount is written.
 *
 * The rule: a figure in a currency the reader does not think in is never shown alone.
 * "38 264 DKK" is unreadable to a Romanian audience — it could be a fortune or a
 * pittance, and the reader has to leave the page to find out. Every foreign amount
 * carries its conversion beside it, always in the same order, so the eye learns the
 * pattern once:
 *
 *     38 264 DKK · 26 917 RON · 5 118 EUR
 *
 * Amounts already in lei do not repeat themselves; they gain only the euro, which is the
 * unit most Romanian readers use for cross-border comparison.
 */

export interface Rates {
  /** Lei for one Danish krone. */
  dkkToRon: number;
  /** Lei for one euro. */
  eurToRon: number;
  /** The day the rates were taken. */
  date: string;
}

const NBSP = ' ';

function whole(value: number, currency: string): string {
  return `${Math.round(value).toLocaleString('ro-RO')}${NBSP}${currency}`;
}

/** Convert any supported currency into lei. */
export function toRon(amount: number, currency: string, rates: Rates): number {
  if (currency === 'RON') return amount;
  if (currency === 'DKK') return amount * rates.dkkToRon;
  if (currency === 'EUR') return amount * rates.eurToRon;
  return amount;
}

/**
 * The canonical rendering. Never returns a bare foreign figure.
 *
 * `emphasis` picks which unit is written first — the native amount when the point is
 * what the law says, the lei amount when the point is comparison.
 */
export function amounts(
  value: number,
  currency: string,
  rates: Rates,
  emphasis: 'native' | 'ron' = 'native',
): string[] {
  const ron = toRon(value, currency, rates);
  const eur = ron / rates.eurToRon;

  if (currency === 'RON') return [whole(value, 'RON'), whole(eur, 'EUR')];

  const native = whole(value, currency);
  const inRon = whole(ron, 'RON');
  const inEur = whole(eur, 'EUR');
  return emphasis === 'native' ? [native, inRon, inEur] : [inRon, native, inEur];
}

/** The same, joined for places that cannot take a list. */
export function amountLine(
  value: number,
  currency: string,
  rates: Rates,
  emphasis: 'native' | 'ron' = 'native',
): string {
  return amounts(value, currency, rates, emphasis).join(` ${NBSP}·${NBSP} `);
}

/**
 * A range, written once rather than as two full triples.
 *
 * `amountLine` on each endpoint produces six numbers for one bar, which is noise. A range
 * keeps the currency rule — no foreign figure without its conversion — while showing the
 * unit only where it changes.
 */
export function amountRange(
  from: number,
  to: number,
  currency: string,
  rates: Rates,
): string {
  const n = (v: number) => Math.round(v).toLocaleString('ro-RO');
  if (currency === 'RON') {
    return `${n(from)}–${n(to)} RON (${n(from / rates.eurToRon)}–${n(to / rates.eurToRon)} EUR)`;
  }
  const ronFrom = toRon(from, currency, rates);
  const ronTo = toRon(to, currency, rates);
  return `${n(from)}–${n(to)} ${currency} ≈ ${n(ronFrom)}–${n(ronTo)} RON (${n(
    ronFrom / rates.eurToRon,
  )}–${n(ronTo / rates.eurToRon)} EUR)`;
}

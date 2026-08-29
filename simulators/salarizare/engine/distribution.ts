/**
 * Who moves up and who moves down, across every post the crosswalk could match.
 *
 * The payslip answers this one person at a time. That is the right shape for an argument
 * about a particular job and the wrong shape for an argument about a reform: a reader can
 * always be shown the one post that makes the case. This module asks the question of the
 * whole matched grid at once.
 *
 * What is being compared is **standing, not pay**. A coefficient is a position in a
 * hierarchy, and the two laws divide by different numbers — 2 500 lei in 153/2017, 4 100
 * in the draft — so a ratio of coefficients says whether a post moved up or down relative
 * to everyone else, and says nothing about the size of anyone's salary. Every consumer of
 * this module has to repeat that, because the number looks exactly like a pay rise.
 *
 * Two further limits travel with the result rather than sitting in a footnote:
 *
 *   * It describes the **matched subset**. Roughly a third of the old grid could be
 *     matched by name; the rest is unresolved, not unchanged, and `coverage` says so.
 *   * A link with several posts on either side has no single before-and-after, so only
 *     one-to-one links carry a ratio. The many-to-many ones are counted and set aside.
 */

import { resolveSeries } from './structure';
import type { Crosswalk, Position, Regime } from './types';

/** Bands are fixed and symmetric, so a move down is as visible as a move up. */
export interface Band {
  id: string;
  label: string;
  /** Lower bound on the ratio, inclusive. */
  from: number;
  /** Upper bound, exclusive. Infinity on the last. */
  to: number;
  /** -1 loses standing, 0 holds it, +1 gains. Drives the diverging colour. */
  direction: -1 | 0 | 1;
}

export const BANDS: Band[] = [
  { id: 'down-hard', label: 'scade peste 20%', from: 0, to: 0.8, direction: -1 },
  { id: 'down', label: 'scade 10–20%', from: 0.8, to: 0.9, direction: -1 },
  { id: 'down-soft', label: 'scade 2–10%', from: 0.9, to: 0.98, direction: -1 },
  { id: 'flat', label: 'aproape neschimbat', from: 0.98, to: 1.02, direction: 0 },
  { id: 'up-soft', label: 'urcă 2–10%', from: 1.02, to: 1.1, direction: 1 },
  { id: 'up', label: 'urcă 10–20%', from: 1.1, to: 1.2, direction: 1 },
  { id: 'up-hard', label: 'urcă peste 20%', from: 1.2, to: Infinity, direction: 1 },
];

export interface Move {
  /** The draft's code, which is what the rest of the app addresses a post by. */
  code: string;
  title: string;
  family: string;
  before: number;
  after: number;
  /** after / before. Above 1 the post gained standing. */
  ratio: number;
  /** `assumed` links matched on a stripped title and are weaker evidence. */
  confidence: string;
}

export interface FamilySummary {
  family: string;
  moves: number;
  median: number;
  /** Share of the family's matched posts that lost standing. */
  losing: number;
}

export interface Distribution {
  moves: Move[];
  bands: Array<Band & { count: number; share: number }>;
  byFamily: FamilySummary[];
  median: number;
  /** Share of matched one-to-one posts that lost standing. */
  losing: number;
  /**
   * How far the Art. 33 transitional difference could reach, bounded from above.
   *
   * Art. 33 preserves November 2026 income where the new pay would be lower. Whether it
   * bites for a given person cannot be computed — Romania publishes no individual income
   * — but one half of the question can be settled. The reference value rises from 2 500 to
   * 4 100 lei, so a post only ends up with a smaller base if it falls further in standing
   * than that rise compensates. `breakeven` is that threshold and `below` counts the posts
   * past it.
   *
   * This bounds the *base salary* question against the *2022 grid*. It does not answer
   * Art. 33, which compares total income in November 2026 — supplements included, and
   * after every increase granted since 2022, none of which are in the annexes.
   */
  transition: {
    /** oldReference / newReference. Below this a post's base actually shrinks. */
    breakeven: number;
    /** Matched posts whose draft base is below their base in the old grid. */
    below: number;
    /** The largest fall in standing observed, for comparison with the threshold. */
    worstRatio: number;
    oldReference: number;
    newReference: number;
  };
  coverage: {
    /** One-to-one links, which are the only ones that can carry a ratio. */
    priced: number;
    /** Links the crosswalk holds in total. */
    links: number;
    /** Posts in the old regime, matched or not. */
    oldPositions: number;
    /** Links with several posts on a side, counted and set aside. */
    grouped: number;
  };
}

function entryValue(position: Position): number | null {
  const values = position.variants
    .map((v) => (typeof v.value === 'number' ? v.value : null))
    .filter((n): n is number => n !== null);
  return values.length ? Math.min(...values) : null;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function bandFor(ratio: number): Band {
  return BANDS.find((b) => ratio >= b.from && ratio < b.to) ?? BANDS[BANDS.length - 1];
}

export function distribution(
  inForce: Regime,
  draft: Regime,
  crosswalk: Crosswalk,
): Distribution {
  const oldByCode = new Map(inForce.positions.map((p) => [p.code, p]));
  const newByCode = new Map(draft.positions.map((p) => [p.code, p]));

  const moves: Move[] = [];
  let grouped = 0;

  for (const link of crosswalk.links) {
    if (link.from.length !== 1 || link.to.length !== 1) {
      // Several posts on a side have no single before-and-after. Averaging them would
      // invent a move nobody made.
      grouped += 1;
      continue;
    }
    const before = oldByCode.get(link.from[0].positionCode);
    const after = newByCode.get(link.to[0].positionCode);
    if (!before || !after) continue;
    const b = entryValue(before);
    const a = entryValue(after);
    if (b === null || a === null || b <= 0) continue;
    moves.push({
      code: after.code,
      title: after.name,
      family: after.family ?? before.family ?? 'necunoscut',
      before: b,
      after: a,
      ratio: a / b,
      confidence: link.confidence,
    });
  }

  const ratios = moves.map((m) => m.ratio);
  const bands = BANDS.map((band) => {
    const count = moves.filter((m) => bandFor(m.ratio).id === band.id).length;
    return { ...band, count, share: moves.length ? count / moves.length : 0 };
  });

  const families = new Map<string, number[]>();
  for (const move of moves) {
    const list = families.get(move.family) ?? [];
    list.push(move.ratio);
    families.set(move.family, list);
  }

  const byFamily = [...families.entries()]
    .map(([family, list]) => ({
      family,
      moves: list.length,
      median: median(list),
      losing: list.filter((r) => r < 0.98).length / list.length,
    }))
    // Most affected first, so the reader meets the families that move at all.
    .sort((a, b) => a.median - b.median);

  const oldReference = resolveSeries(inForce.reference.amount, inForce.reference.baseDate);
  const newReference = resolveSeries(draft.reference.amount, draft.reference.baseDate);
  const breakeven = newReference > 0 ? oldReference / newReference : 0;

  return {
    moves,
    bands,
    byFamily,
    transition: {
      breakeven,
      below: moves.filter((m) => m.after * newReference < m.before * oldReference).length,
      worstRatio: ratios.length ? Math.min(...ratios) : 0,
      oldReference,
      newReference,
    },
    median: median(ratios),
    losing: moves.length ? moves.filter((m) => m.ratio < 0.98).length / moves.length : 0,
    coverage: {
      priced: moves.length,
      links: crosswalk.links.length,
      oldPositions: inForce.positions.length,
      grouped,
    },
  };
}

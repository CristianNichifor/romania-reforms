/**
 * Envelope mode: fix total personnel spend, then make every increase name the reduction
 * that pays for it.
 *
 * The arithmetic here is deliberately simple, because the discipline is the product. A
 * more elaborate cost model would not make the trade-offs more honest; it would make them
 * harder to check. What matters is that an increase cannot exist without a matching
 * reduction, that the pairing is visible, and that an unfunded remainder is stated in
 * figures rather than absorbed.
 *
 * Moves act on the wage bill of a whole occupational family, or on all of it. That is the
 * finest split the published data supports: Eurostat reports general-government
 * compensation by COFOG function, and the Ministry of Finance reports filled posts per
 * ordonator, but nothing published maps either onto the 1176 positions of the grid.
 * Pretending otherwise would put a decimal point on a guess.
 *
 * Pure. No imports beyond the type contract.
 */

import type { Diagnostic, Money } from './types';

export interface FamilySlice {
  family: string;
  label: string;
  amount: Money;
}

export interface EnvelopeBaseline {
  currency: string;
  /** Everything here is annual: the published wage bill is an annual figure. */
  period: 'year';
  total: Money;
  byFamily: FamilySlice[];
  /** Filled posts behind the bill, for per-post readings. */
  posts: number;
  /** Nominal GDP, so the bill can be read as a share of the economy. */
  gdp: Money;
}

export type MoveTarget = { kind: 'all' } | { kind: 'family'; family: string };

export interface Move {
  id: string;
  label: string;
  target: MoveTarget;
  /** Proportional change to the targeted bill. +0.05 is five percent more. */
  pct: number;
  /**
   * Why. Envelope mode refuses to price an unnamed move: the whole point is that a
   * reduction has an author and a justification, not that the sums balance.
   */
  rationale: string;
}

export interface FundingLink {
  fromMoveId: string;
  fromLabel: string;
  amount: Money;
}

export interface LedgerEntry {
  move: Move;
  delta: Money;
  fundedBy: FundingLink[];
  unfunded: Money;
}

export interface ReductionEntry {
  move: Move;
  delta: Money;
  allocated: Money;
  spare: Money;
}

export interface EnvelopeResult {
  currency: string;
  baseline: Money;
  target: Money;
  proposed: Money;
  /** target − proposed. Zero or more means the plan fits. */
  headroom: Money;
  balanced: boolean;
  increases: LedgerEntry[];
  reductions: ReductionEntry[];
  byFamily: Array<{ family: string; label: string; before: Money; after: Money; delta: Money }>;
  /** The bill as a share of GDP, before and after, since Art. 36(3) is written that way. */
  shareOfGdp: { before: number; after: number };
  perPost: { before: Money; after: Money };
  unnamed: string[];
  diagnostics: Diagnostic[];
}

function note(code: string, severity: Diagnostic['severity'], message: string): Diagnostic {
  return { code, severity, message, affects: 'aggregate' };
}

export function envelope(
  baseline: EnvelopeBaseline,
  moves: Move[],
  target?: Money,
): EnvelopeResult {
  const diagnostics: Diagnostic[] = [
    note(
      'familie-nu-functie',
      'material',
      'Mutările lucrează pe familii ocupaționale, nu pe funcții. Este cel mai fin nivel pe care îl susțin datele publicate: execuția bugetară dă cheltuiala de personal pe capitole bugetare și pe ordonator principal, dar nimic publicat nu leagă vreun capitol de cele 1176 de funcții din grilă. Corespondența capitol → familie este de asemenea aproximativă: apărarea și ordinea publică sunt două capitole și o singură familie în anexe.',
    ),
  ];

  // Sequential within a family, so two moves on the same family compound the way money
  // actually does rather than each being priced against the untouched baseline.
  const running = new Map<string, Money>(baseline.byFamily.map((f) => [f.family, f.amount]));
  let runningTotal = baseline.total;

  const priced = moves.map((move) => {
    let base: Money;
    if (move.target.kind === 'all') {
      base = runningTotal;
    } else {
      base = running.get(move.target.family) ?? 0;
      if (!running.has(move.target.family)) {
        diagnostics.push(
          note('familie-necunoscuta', 'material', `Familia „${move.target.family}” nu există în baza de pornire; mutarea „${move.label}” a fost ignorată.`),
        );
      }
    }
    const delta = Math.round(base * move.pct);

    if (move.target.kind === 'all') {
      // Spread proportionally, so the family view stays consistent with the total.
      for (const [family, amount] of running) {
        running.set(family, Math.round(amount * (1 + move.pct)));
      }
    } else if (running.has(move.target.family)) {
      running.set(move.target.family, base + delta);
    }
    runningTotal += delta;

    return { move, delta };
  });

  const effectiveTarget = target ?? baseline.total;
  const proposed = runningTotal;
  const headroom = effectiveTarget - proposed;

  // Pair each increase with the reductions that pay for it, in the order they were made.
  const increases = priced.filter((p) => p.delta > 0);
  const cuts = priced
    .filter((p) => p.delta < 0)
    .map((p) => ({ move: p.move, delta: p.delta, remaining: -p.delta, allocated: 0 }));

  // Slack against the target counts as a source of funding: if the target is above the
  // baseline, that difference is money already available.
  let slack = Math.max(effectiveTarget - baseline.total, 0);

  const ledger: LedgerEntry[] = increases.map(({ move, delta }) => {
    let need = delta;
    const fundedBy: FundingLink[] = [];

    if (slack > 0) {
      const take = Math.min(slack, need);
      slack -= take;
      need -= take;
      fundedBy.push({ fromMoveId: '__target', fromLabel: 'spațiu față de ținta fixată', amount: take });
    }
    for (const cut of cuts) {
      if (need <= 0) break;
      if (cut.remaining <= 0) continue;
      const take = Math.min(cut.remaining, need);
      cut.remaining -= take;
      cut.allocated += take;
      need -= take;
      fundedBy.push({ fromMoveId: cut.move.id, fromLabel: cut.move.label, amount: take });
    }
    return { move, delta, fundedBy, unfunded: Math.max(need, 0) };
  });

  const unfundedTotal = ledger.reduce((sum, e) => sum + e.unfunded, 0);
  if (unfundedTotal > 0) {
    diagnostics.push(
      note('cresteri-nefinantate', 'blocking', `Creșteri nefinanțate: ${(unfundedTotal / 100).toLocaleString('ro-RO')} ${baseline.currency}. Fiecare creștere trebuie să numească reducerea care o plătește.`),
    );
  }

  const unnamed = moves.filter((m) => !m.rationale.trim()).map((m) => m.id);
  if (unnamed.length) {
    diagnostics.push(
      note('mutari-fara-motiv', 'material', `${unnamed.length} mutări nu au o justificare scrisă. O reducere fără autor și fără motiv nu e o propunere, e o cifră.`),
    );
  }

  return {
    currency: baseline.currency,
    baseline: baseline.total,
    target: effectiveTarget,
    proposed,
    headroom,
    balanced: headroom >= 0 && unfundedTotal === 0,
    increases: ledger,
    reductions: cuts.map((c) => ({
      move: c.move,
      delta: c.delta,
      allocated: c.allocated,
      spare: c.remaining,
    })),
    byFamily: baseline.byFamily.map((f) => {
      const after = running.get(f.family) ?? f.amount;
      return { family: f.family, label: f.label, before: f.amount, after, delta: after - f.amount };
    }),
    shareOfGdp: {
      before: baseline.gdp > 0 ? baseline.total / baseline.gdp : 0,
      after: baseline.gdp > 0 ? proposed / baseline.gdp : 0,
    },
    perPost: {
      before: baseline.posts > 0 ? Math.round(baseline.total / baseline.posts) : 0,
      after: baseline.posts > 0 ? Math.round(proposed / baseline.posts) : 0,
    },
    unnamed,
    diagnostics,
  };
}

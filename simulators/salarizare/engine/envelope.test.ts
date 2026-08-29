import { describe, expect, it } from 'vitest';

import { envelope } from './envelope';
import type { EnvelopeBaseline, Move } from './envelope';

const baseline: EnvelopeBaseline = {
  currency: 'RON',
  period: 'year',
  // Minor units throughout: 100 000 million lei expressed in bani.
  total: 100_000_00,
  byFamily: [
    { family: 'invatamant', label: 'Învățământ', amount: 40_000_00 },
    { family: 'sanatate', label: 'Sănătate', amount: 35_000_00 },
    { family: 'administratie', label: 'Administrație', amount: 25_000_00 },
  ],
  // 10 000 posts against a 100 000-lei bill: 10 lei each, which keeps the per-post
  // arithmetic checkable by eye.
  posts: 10_000,
  gdp: 1_000_000_00,
};

const move = (over: Partial<Move> & Pick<Move, 'id' | 'pct' | 'target'>): Move => ({
  label: over.id,
  rationale: 'motiv',
  ...over,
});

describe('pricing', () => {
  it('prices a family move against that family alone', () => {
    const result = envelope(baseline, [
      move({ id: 'a', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 }),
    ]);
    expect(result.increases[0].delta).toBe(4_000_00);
    expect(result.proposed).toBe(104_000_00);
  });

  it('compounds two moves on the same family instead of pricing both off the baseline', () => {
    const result = envelope(baseline, [
      move({ id: 'a', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 }),
      move({ id: 'b', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 }),
    ]);
    // 40 000 -> 44 000 -> 48 400, so the second move costs 4 400 rather than 4 000.
    expect(result.increases[1].delta).toBe(4_400_00);
    expect(result.byFamily.find((f) => f.family === 'invatamant')!.after).toBe(48_400_00);
  });

  it('spreads a whole-bill move across families so the parts still sum to the total', () => {
    const result = envelope(baseline, [move({ id: 'a', target: { kind: 'all' }, pct: 0.05 })]);
    expect(result.proposed).toBe(105_000_00);
    const sum = result.byFamily.reduce((s, f) => s + f.after, 0);
    expect(sum).toBe(result.proposed);
  });

  it('ignores a move against a family that does not exist, and says so', () => {
    const result = envelope(baseline, [
      move({ id: 'a', target: { kind: 'family', family: 'nope' }, pct: 0.5 }),
    ]);
    expect(result.proposed).toBe(baseline.total);
    expect(result.diagnostics.map((d) => d.code)).toContain('familie-necunoscuta');
  });
});

describe('the ledger', () => {
  it('pairs an increase with the reduction that pays for it', () => {
    const result = envelope(baseline, [
      move({ id: 'cut', label: 'minus administrație', target: { kind: 'family', family: 'administratie' }, pct: -0.2 }),
      move({ id: 'rise', label: 'plus învățământ', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 }),
    ]);
    const rise = result.increases[0];
    expect(rise.delta).toBe(4_000_00);
    expect(rise.fundedBy).toHaveLength(1);
    expect(rise.fundedBy[0].fromMoveId).toBe('cut');
    expect(rise.fundedBy[0].amount).toBe(4_000_00);
    expect(rise.unfunded).toBe(0);
    expect(result.balanced).toBe(true);
  });

  it('reports the unfunded remainder rather than absorbing it', () => {
    const result = envelope(baseline, [
      move({ id: 'cut', target: { kind: 'family', family: 'administratie' }, pct: -0.04 }),
      move({ id: 'rise', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 }),
    ]);
    // A 1 000 cut against a 4 000 rise leaves 3 000 unpaid for.
    expect(result.increases[0].unfunded).toBe(3_000_00);
    expect(result.balanced).toBe(false);
    expect(result.diagnostics.map((d) => d.code)).toContain('cresteri-nefinantate');
  });

  it('draws on several reductions in order until the increase is covered', () => {
    const result = envelope(baseline, [
      move({ id: 'cut1', target: { kind: 'family', family: 'administratie' }, pct: -0.04 }),
      move({ id: 'cut2', target: { kind: 'family', family: 'sanatate' }, pct: -0.1 }),
      move({ id: 'rise', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 }),
    ]);
    const rise = result.increases[0];
    expect(rise.fundedBy.map((f) => f.fromMoveId)).toEqual(['cut1', 'cut2']);
    expect(rise.fundedBy[0].amount).toBe(1_000_00);
    expect(rise.fundedBy[1].amount).toBe(3_000_00);
    expect(rise.unfunded).toBe(0);
  });

  it('leaves unspent reductions visible as spare rather than silently banking them', () => {
    const result = envelope(baseline, [
      move({ id: 'cut', target: { kind: 'family', family: 'administratie' }, pct: -0.2 }),
      move({ id: 'rise', target: { kind: 'family', family: 'invatamant' }, pct: 0.05 }),
    ]);
    const cut = result.reductions[0];
    expect(cut.delta).toBe(-5_000_00);
    expect(cut.allocated).toBe(2_000_00);
    expect(cut.spare).toBe(3_000_00);
  });

  it('treats headroom against a raised target as a source of funding', () => {
    const result = envelope(
      baseline,
      [move({ id: 'rise', target: { kind: 'family', family: 'invatamant' }, pct: 0.1 })],
      105_000_00,
    );
    expect(result.increases[0].fundedBy[0].fromMoveId).toBe('__target');
    expect(result.increases[0].unfunded).toBe(0);
    expect(result.balanced).toBe(true);
  });

  it('defaults to holding spend where it is', () => {
    const result = envelope(baseline, []);
    expect(result.target).toBe(baseline.total);
    expect(result.headroom).toBe(0);
    expect(result.balanced).toBe(true);
  });
});

describe('what the result has to say out loud', () => {
  it('names moves made without a reason', () => {
    const result = envelope(baseline, [
      { id: 'a', label: 'a', target: { kind: 'all' }, pct: -0.01, rationale: '  ' },
    ]);
    expect(result.unnamed).toEqual(['a']);
    expect(result.diagnostics.map((d) => d.code)).toContain('mutari-fara-motiv');
  });

  it('always states that moves work on families, not positions', () => {
    expect(envelope(baseline, []).diagnostics.map((d) => d.code)).toContain('familie-nu-functie');
  });

  it('reports the bill as a share of GDP, the way Art. 36(3) is written', () => {
    const result = envelope(baseline, [move({ id: 'a', target: { kind: 'all' }, pct: -0.1 })]);
    expect(result.shareOfGdp.before).toBeCloseTo(0.1, 6);
    expect(result.shareOfGdp.after).toBeCloseTo(0.09, 6);
  });

  it('reports spend per filled post, since that is the unit the headcount is in', () => {
    const result = envelope(baseline, [move({ id: 'a', target: { kind: 'all' }, pct: 0.1 })]);
    expect(result.perPost.before).toBe(1000);
    expect(result.perPost.after).toBe(1100);
  });
});

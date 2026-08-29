import { describe, expect, it } from 'vitest';

import { DEFAULT_SCENARIO, decodeScenario, encodeScenario, personFrom } from './scenario';
import type { Scenario } from './scenario';

describe('scenario codec', () => {
  const scenario: Scenario = {
    view: 'payslip',
    regimeIds: ['ro-draft-2026-07-16', 'dk-stat-2026'],
    positionCode: '81.10104001.01',
    seniorityYears: 12,
    dims: { institutionLevel: 'II' },
    claims: [
      { supplementId: 'cfp' },
      { supplementId: 'fonduri-externe', rate: 0.4, externallyFundedShare: 0.85 },
    ],
  };

  it('round-trips a full scenario', () => {
    expect(decodeScenario(encodeScenario(scenario))).toEqual(scenario);
  });

  it('stays legible in the address bar', () => {
    // A link used in a public argument has to be readable and hand-editable. An opaque
    // base64 blob would be shorter and useless for that.
    const hash = encodeScenario(scenario);
    expect(hash).toContain('#/payslip?');
    expect(hash).toContain('p=81.10104001.01');
    expect(hash).toContain('y=12');
    expect(decodeURIComponent(hash)).toContain('s=cfp,fonduri-externe:0.4:0.85');
  });

  it('falls back to a valid scenario rather than throwing on rubbish', () => {
    const result = decodeScenario('#/nonsense?r=&y=abc');
    // The default, whatever it is — a first visit should land somewhere sensible, and
    // pinning the literal here only records which view happened to be first that week.
    expect(result.view).toBe(DEFAULT_SCENARIO.view);
    expect(result.regimeIds).toEqual(['ro-draft-2026-07-16']);
    expect(result.seniorityYears).toBeUndefined();
  });

  it('handles an empty hash', () => {
    expect(decodeScenario('')).toEqual({
      view: DEFAULT_SCENARIO.view,
      regimeIds: ['ro-draft-2026-07-16'],
      positionCode: undefined,
      seniorityYears: undefined,
      dims: undefined,
      claims: undefined,
      asOf: undefined,
      extra: undefined,
    });
  });

  it('preserves parameters it does not understand', () => {
    // A link produced by a later version must not silently lose information when an
    // older build reads it and writes it back.
    const decoded = decodeScenario('#/payslip?r=ro-draft-2026-07-16&zz=future');
    expect(decoded.extra).toEqual({ zz: 'future' });
    expect(encodeScenario(decoded)).toContain('zz=future');
  });

  it('keeps seniority zero distinguishable from unset', () => {
    expect(decodeScenario('#/payslip?y=0').seniorityYears).toBe(0);
    expect(decodeScenario('#/payslip').seniorityYears).toBeUndefined();
  });

  it('builds a person, or nothing when no position is chosen', () => {
    expect(personFrom(scenario)).toMatchObject({
      positionCode: '81.10104001.01',
      seniorityYears: 12,
    });
    expect(personFrom({ view: 'payslip', regimeIds: [] })).toBeNull();
  });
});

describe('envelope scenarios survive a link', () => {
  it('carries the target and every move, reason included', () => {
    // Envelope mode refuses to price a move with no rationale. If the link dropped the
    // reason, a shared scenario would arrive as an unargued cut — the exact thing the
    // view exists to prevent.
    const scenario = {
      ...DEFAULT_SCENARIO,
      view: 'envelope' as const,
      envelopeTarget: -0.05,
      envelopeMoves: [
        { family: 'I-invatamant', pct: 0.08, why: 'Profesorii sunt sub media pieței' },
        { family: 'VIII-administratie', pct: -0.04, why: 'Comasare de funcții: 261 denumiri' },
      ],
    };
    const round = decodeScenario(encodeScenario(scenario));
    expect(round.envelopeTarget).toBeCloseTo(-0.05, 10);
    expect(round.envelopeMoves).toEqual(scenario.envelopeMoves);
  });

  it('keeps separators inside a reason from splitting it', () => {
    const scenario = {
      ...DEFAULT_SCENARIO,
      view: 'envelope' as const,
      envelopeMoves: [{ family: 'f', pct: 1, why: 'a, b: c' }],
    };
    expect(decodeScenario(encodeScenario(scenario)).envelopeMoves![0].why).toBe('a, b: c');
  });

  it('drops a malformed move rather than inventing a zero', () => {
    // A move read as 0% would look deliberate and would silently change the ledger.
    expect(decodeScenario('#/envelope?m=nu-e-un-numar').envelopeMoves).toBeUndefined();
  });
});

describe('the sector filter travels in the link', () => {
  it('round-trips, so a narrowed page can be sent to someone', () => {
    const round = decodeScenario(
      encodeScenario({ ...DEFAULT_SCENARIO, view: 'meserii', sector: 'Sănătate' }),
    );
    expect(round.sector).toBe('Sănătate');
    expect(round.view).toBe('meserii');
  });

  it('is absent rather than empty when nothing is selected', () => {
    expect(decodeScenario('#/meserii').sector).toBeUndefined();
  });
});

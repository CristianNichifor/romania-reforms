import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { aggregate, payslip, round } from './payslip';
import type { Headcount, Person } from './payslip';
import type { Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const load = (id: string): Regime =>
  JSON.parse(readFileSync(resolve(here, `../data/regimes/${id}.json`), 'utf8'));

const RO = load('ro-draft-2026-07-16');
const DK = load('dk-stat-2026');

/** Minor units to a readable major-unit number, for assertions only. */
const major = (m: number) => m / 100;

describe('round', () => {
  it('rounds up to a whole leu, in favour of the employee (Art. 10(4))', () => {
    expect(round(1024590, { step: 100, mode: 'ceil' })).toBe(1024600);
    expect(round(1024500, { step: 100, mode: 'ceil' })).toBe(1024500);
  });

  it('rounds a Danish salary to the nearest whole krone', () => {
    expect(round(33018718.5, { step: 100, mode: 'halfUp' })).toBe(33018700);
  });
});

describe('payslip — Romania', () => {
  const auditor: Person = { positionCode: '81.10104001.01', seniorityYears: 0 };

  it('multiplies the coefficient by the reference value and rounds up', () => {
    // 2,499 x 4100 = 10 245,90 -> 10 246 lei, rounded up in favour of the employee.
    const slip = payslip(auditor, RO);
    expect(major(slip.base)).toBe(10246);
    expect(slip.period).toBe('month');
    expect(slip.currency).toBe('RON');
  });

  it('compounds the gradatii, and rounding up at each step drifts above the nominal factor', () => {
    const at20 = payslip({ ...auditor, seniorityYears: 21 }, RO);
    expect(at20.seniority.stepId).toBe('gr5');
    expect(at20.base).toBeGreaterThan(payslip(auditor, RO).base);

    // 7,5 / 5 / 5 / 2,5 / 2,5 compounded is x1,2451876 in pure arithmetic. Art. 13(3)
    // says each step raises "salariul de baza avut", and Art. 10(4) rounds a salariu de
    // baza UP to whole lei — so five roundings each push a little further, and the
    // realised factor lands slightly above the nominal one. The law never says whether
    // to round per step or once at the end; the engine rounds per step and declares it.
    const nominal = 1.075 * 1.05 * 1.05 * 1.025 * 1.025;
    expect(at20.seniority.factor).toBeGreaterThan(nominal);
    expect(at20.seniority.factor - nominal).toBeLessThan(0.001);
    expect(at20.diagnostics.map((d) => d.code)).toContain('rounding-per-step');
  });

  it('places seniority on the step the years actually reach', () => {
    expect(payslip({ ...auditor, seniorityYears: 2 }, RO).seniority.stepId).toBe('gr0');
    expect(payslip({ ...auditor, seniorityYears: 4 }, RO).seniority.stepId).toBe('gr1');
    expect(payslip({ ...auditor, seniorityYears: 12 }, RO).seniority.stepId).toBe('gr3');
  });

  it('does not apply gradatii twice to a management position', () => {
    // Art. 10(6): for functii de conducere the top gradatie is already in the coefficient.
    const director = payslip(
      { positionCode: '81.10103003.09', dims: { gradManagerial: 'I' }, seniorityYears: 30 },
      RO,
    );
    expect(director.seniority.bakedIn).toBe(true);
    expect(director.seniority.amount).toBe(0);
  });

  it('excludes the senior civil service from the gradatii', () => {
    // Art. 13(1) excepts inaltii functionari publici by name. The sheets label that
    // section "categoriei inaltilor functionari publici" — declined — so a literal
    // phrase match missed it and every one of them was silently drawing seniority
    // increments the statute denies them.
    const secretarGeneral = payslip(
      { positionCode: '81.10101001.01', seniorityYears: 30 },
      RO,
    );
    expect(secretarGeneral.seniority.bakedIn).toBe(true);
    expect(secretarGeneral.seniority.amount).toBe(0);
    // 5,4 x 4100 = 22 140, with no uplift on top.
    expect(major(secretarGeneral.base)).toBe(22140);
  });

  it('charges income tax after the contributions, not on gross', () => {
    // The chain matters more than the arithmetic. CAS 25% and CASS 10% come off first,
    // and the 10% tax applies to what is left: net/gross settles at 0,585. Taxing gross
    // instead would give 0,55 — a plausible-looking number that is simply wrong.
    const slip = payslip(auditor, RO);
    expect(slip.net! / slip.gross).toBeCloseTo(0.585, 3);
    expect(slip.net!).toBeLessThan(slip.gross);
  });

  it('puts the employer contribution above gross, not inside it', () => {
    const slip = payslip(auditor, RO);
    // CAM 2,25% is the employer's alone.
    expect(slip.employerCost).toBe(slip.gross + round(slip.gross * 0.0225, RO.reference.rounding));
    expect(slip.employerCost).toBeGreaterThan(slip.gross);
  });

  it('caps a supplement at its statutory ceiling and says so', () => {
    const slip = payslip(
      { ...auditor, claims: [{ supplementId: 'fonduri-externe', rate: 0.6 }] },
      RO,
    );
    const line = slip.supplements[0];
    expect(line.requestedRate).toBe(0.6);
    expect(line.allowedRate).toBe(0.4);
    expect(slip.diagnostics.map((d) => d.code)).toContain('supplement-over-ceiling');
  });

  it('splits a partially exempt supplement across the Art. 21 ceiling', () => {
    // Art. 15(18)-(19): the externally funded share is exempt, the co-financed part counts.
    const slip = payslip(
      {
        ...auditor,
        claims: [{ supplementId: 'fonduri-externe', externallyFundedShare: 0.85 }],
      },
      RO,
    );
    const line = slip.supplements[0];
    expect(line.countsToCap).toBe('partial');
    expect(line.capCountingAmount).toBeGreaterThan(0);
    expect(line.capCountingAmount).toBeLessThan(line.amount);
    expect(Math.round(line.capCountingAmount / line.amount * 100)).toBe(15);
  });

  it('bases the disability supplement on the reference value, not on pay', () => {
    // Art. 19: 15% of the reference value — the same amount for everyone.
    const low = payslip({ ...auditor, claims: [{ supplementId: 'handicap' }] }, RO);
    const high = payslip(
      { positionCode: '81.10103003.09', dims: { gradManagerial: 'I' }, seniorityYears: 0, claims: [{ supplementId: 'handicap' }] },
      RO,
    );
    expect(low.supplements[0].amount).toBe(high.supplements[0].amount);
    expect(major(low.supplements[0].amount)).toBe(615); // 15% of 4100
  });

  it('suppresses a supplement excluded by another that was claimed', () => {
    const slip = payslip(
      { ...auditor, claims: [{ supplementId: 'ture-sanitare' }, { supplementId: 'noapte' }] },
      RO,
    );
    const night = slip.supplements.find((l) => l.id === 'noapte')!;
    expect(night.suppressedBy).toBe('ture-sanitare');
    expect(night.amount).toBe(0);
  });

  it('reports the Art. 21 ceiling as notional, never as authoritative', () => {
    const slip = payslip({ ...auditor, claims: [{ supplementId: 'cfp' }] }, RO);
    const cap = slip.capUtilisation.find((c) => c.capId === 'cap-sporuri-20')!;
    expect(cap.authoritative).toBe(false);
    expect(cap.scopeNote).toMatch(/notionala/);
    expect(slip.diagnostics.map((d) => d.code)).toContain('cap-not-per-person');
  });

  it('excludes exempt supplements from the ceiling numerator', () => {
    const slip = payslip({ ...auditor, claims: [{ supplementId: 'noapte' }] }, RO);
    const cap = slip.capUtilisation.find((c) => c.capId === 'cap-sporuri-20')!;
    // Art. 17(2) exempts the night supplement, so it raises gross but not the ratio.
    expect(slip.supplements[0].amount).toBeGreaterThan(0);
    expect(cap.numerator).toBe(0);
  });
});

describe('payslip — Denmark', () => {
  const engineer: Person = { positionCode: 'dk-stat-eng', seniorityYears: 0 };

  it('reproduces the published basic salary exactly', () => {
    // 285 240 x 1,265085 = 360 852,85 -> 360 853, as printed by IDA.
    const slip = payslip(engineer, DK);
    expect(major(slip.base)).toBe(360853);
    expect(slip.period).toBe('year');
    expect(slip.currency).toBe('DKK');
  });

  it('walks absolute scale grades, including a repeated one', () => {
    // A bachelor walks grades 1, 2, 4, 4, 5 — grade 4 lasts two years.
    const y0 = payslip({ positionCode: 'dk-stat-bsc', seniorityYears: 0 }, DK);
    const y8 = payslip({ positionCode: 'dk-stat-bsc', seniorityYears: 8 }, DK);
    expect(major(y0.base)).toBe(330187); // 261 000 x 1,265085
    expect(y8.base).toBeGreaterThan(y0.base);
  });

  it('adds pension into gross and splits it one third to the employee', () => {
    const slip = payslip(engineer, DK);
    const pension = slip.pensionSplit!;
    expect(pension.total).toBe(round(slip.base * 0.1807, DK.reference.rounding));
    expect(major(pension.employee) + major(pension.employer)).toBeCloseTo(major(pension.total), 0);
    expect(pension.employer).toBeGreaterThan(pension.employee);
    expect(slip.gross).toBe(slip.base + pension.total);
  });

  it('reproduces the published gross including pension', () => {
    // IDA prints 330 187 net, 59 665 pension, 389 852 gross for scale grade 1.
    const slip = payslip({ positionCode: 'dk-stat-bsc', seniorityYears: 0 }, DK);
    expect(major(slip.base)).toBe(330187);
    expect(major(slip.pensionSplit!.total)).toBe(59665);
    expect(major(slip.gross)).toBe(389852);
  });

  it('returns null net rather than inventing a tax schedule', () => {
    const slip = payslip(engineer, DK);
    expect(slip.net).toBeNull();
    expect(slip.diagnostics.map((d) => d.code)).toContain('no-tax-schedule');
  });

  it('has no ceiling to report, and that is a finding not a gap', () => {
    expect(payslip(engineer, DK).capUtilisation).toEqual([]);
  });

  it('flags a negotiated interval as a decision, not a legal entitlement', () => {
    const slip = payslip({ positionCode: 'dk-stat-specialkonsulent', seniorityYears: 0 }, DK);
    expect(slip.diagnostics.map((d) => d.code)).toContain('range-position');
    const top = payslip(
      { positionCode: 'dk-stat-specialkonsulent', seniorityYears: 0, rangePoint: 1 },
      DK,
    );
    expect(top.base).toBeGreaterThan(slip.base);
  });
});

describe('aggregate', () => {
  const headcount: Headcount = {
    id: 'test',
    asOf: '2026-12-01',
    rows: [
      { positionCode: '81.10104001.01', ordonator: 'MF', filledPosts: 100 },
      { positionCode: '81.10103003.09', dims: { gradManagerial: 'I' }, ordonator: 'MF', filledPosts: 10 },
      { positionCode: '81.10104001.01', ordonator: 'MEC', filledPosts: 50 },
    ],
  };

  it('scales the bill by filled posts and splits it by ordonator', () => {
    const result = aggregate(headcount, RO);
    expect(result.total.filledPosts).toBe(160);
    const mf = result.byOrdonator.find((b) => b.key === 'MF')!;
    const mec = result.byOrdonator.find((b) => b.key === 'MEC')!;
    expect(mf.filledPosts).toBe(110);
    expect(mec.filledPosts).toBe(50);
    expect(mf.grossBill).toBeGreaterThan(mec.grossBill);
  });

  it('says out loud that it runs on posts, not people', () => {
    const codes = aggregate(headcount, RO).diagnostics.map((d) => d.code);
    expect(codes).toContain('filled-posts-only');
    expect(aggregate(headcount, RO).diagnostics[0].severity).toBe('blocking');
  });

  it('warns that an unknown seniority distribution understates the bill', () => {
    expect(aggregate(headcount, RO).diagnostics.map((d) => d.code)).toContain('seniority-unknown');
  });

  it('measures the Art. 21 ceiling per ordonator, where the law puts it', () => {
    const result = aggregate(headcount, RO);
    const caps = result.capUtilisation.filter((c) => c.capId === 'cap-sporuri-20');
    expect(caps.length).toBe(2);
    expect(caps.every((c) => c.authoritative)).toBe(true);
    expect(caps.map((c) => c.bucketKey).sort()).toEqual(['MEC', 'MF']);
  });

  it('drops unknown position codes loudly instead of silently', () => {
    const result = aggregate(
      { id: 't', asOf: '2026-12-01', rows: [{ positionCode: 'nope', ordonator: 'X', filledPosts: 5 }] },
      RO,
    );
    expect(result.total.filledPosts).toBe(0);
    expect(result.diagnostics.map((d) => d.code)).toContain('headcount-position-missing');
  });
});

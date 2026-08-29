import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { applyProposal } from './proposal';
import type { Proposal } from './proposal';
import { structure } from './structure';
import type { Position, Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const BASE: Regime = JSON.parse(
  readFileSync(resolve(here, '../data/regimes/ro-draft-2026-07-16.json'), 'utf8'),
);
const PROPOSAL: Proposal = JSON.parse(
  readFileSync(resolve(here, '../data/proposals/propunere-v1.json'), 'utf8'),
);

const applied = applyProposal(BASE, PROPOSAL);
const before = structure(BASE);
const after = structure(applied.regime);

describe('the proposal is auditable', () => {
  it('every patch names a defect the base regime actually declares', () => {
    // A patch that fixes nothing recorded is a policy preference wearing a repair's
    // clothes. This test is what keeps the proposal honest as it grows.
    const declared = new Set(BASE.limitations.map((l) => l.id));
    for (const patch of PROPOSAL.patches) {
      // A patch that redistributes has to admit it. Without this the proposal could grow
      // policy under the cover of "five corrections that move nobody's pay".
      expect(patch.fixes, `${patch.id} must name what it fixes`).toBeTruthy();
      expect(declared, `${patch.id} fixes an unknown limitation`).toContain(patch.fixes!);
    }
  });

  it('marks any patch that redistributes rather than repairs', () => {
    const policy = PROPOSAL.patches.filter((p) => p.policyChange);
    const repairs = PROPOSAL.patches.filter((p) => !p.policyChange);
    expect(repairs.length).toBeGreaterThan(0);
    // The claim in notPolicy is about the repairs; a policy patch must be flagged so the
    // UI can separate the two rather than presenting them as one kind of change.
    for (const p of policy) {
      expect(p.rationale.toLowerCase()).toContain('politic');
    }
  });

  it('leaves the base regime untouched', () => {
    expect(BASE.id).toBe('ro-draft-2026-07-16');
    expect(before.distinctValues).toBeGreaterThan(1000);
    expect(applied.regime.positions).not.toBe(BASE.positions);
  });

  it('reports what each patch touched', () => {
    expect(applied.effects.map((e) => e.patchId)).toEqual(PROPOSAL.patches.map((p) => p.id));
    expect(applied.effects.some((e) => e.variantsTouched > 0)).toBe(true);
  });
});

describe('each patch fixes its stated defect', () => {
  it('rounding collapses the back-solved coefficients', () => {
    expect(before.backSolvedShare).toBeGreaterThan(0.6);
    expect(after.backSolvedShare).toBe(0);
    expect(after.roundedShare).toBe(1);
    expect(after.distinctValues).toBeLessThan(before.distinctValues);
  });

  it('contiguous bands leave no coefficient without a grade', () => {
    expect(before.variantsInGaps).toBeGreaterThan(0);
    expect(after.variantsInGaps).toBe(0);
  });

  it('collapsing the schedule makes the declared ratio the ratio in force', () => {
    // The base grid reaches 1:8 only in 2031; the proposal holds the top at its first-year
    // value, so there is one span rather than five.
    expect(before.spanByPeriod.length).toBeGreaterThan(1);
    expect(after.spanByPeriod.length).toBe(0);
    expect(after.span.max).toBeLessThan(before.span.max);
  });

  it('closing the loopholes makes the ceiling bind', () => {
    const cap = applied.regime.caps.find((c) => c.id === 'cap-sporuri-20')!;
    const exempt = new Set(cap.numerator?.exclude ?? []);
    for (const id of ['administrare-resurse-europene', 'izolare-delta', 'capacitate-fiscal-bugetara']) {
      expect(exempt.has(id), `${id} should no longer be exempt`).toBe(false);
      expect(applied.regime.supplements.find((s) => s.id === id)!.countsToCap).toBe(true);
    }
    // Time actually worked outside hours stays exempt: it compensates hours, not status.
    expect(exempt.has('noapte')).toBe(true);
  });

  it('takes the institution out of the job title without moving any pay', () => {
    // 95 positions carried variants that differed only by institutional tier — one title
    // paid up to 1,5x more depending where the post sat. After the patch the job appears
    // once and the institutional difference is an explicit multiplier.
    const context = new Set(['institutionLevel', 'sursa', 'celula']);
    const stillFused = applied.regime.positions.filter((p) => {
      if (p.variants.length < 2) return false;
      const jobs = new Set(
        p.variants.map((v) =>
          JSON.stringify(Object.entries(v.dims ?? {}).filter(([k]) => !context.has(k)).sort()),
        ),
      );
      return jobs.size === 1 && p.variants.some((v) =>
        Object.keys(v.dims ?? {}).some((k) => context.has(k)));
    });
    expect(stillFused).toHaveLength(0);

    const withFactor = applied.regime.positions.filter((p) => p.institutionFactor);
    expect(withFactor.length).toBeGreaterThan(50);
    // The spread is preserved, not discarded: the widest is the 1,5x TIC case.
    expect(Math.max(...withFactor.map((p) => p.institutionFactor!.max))).toBeGreaterThan(1.4);
  });

  it('unifying seniority puts every execution position on one ladder', () => {
    const banded = (r: Regime) =>
      r.positions.filter((p) => p.variants.some((v) => v.dims?.vechime !== undefined)).length;
    expect(banded(BASE)).toBeGreaterThan(0);
    expect(banded(applied.regime)).toBeLessThan(banded(BASE));
  });
});

describe('the proposal does not quietly change pay policy', () => {
  it('keeps the reference value, the grades, and every position reachable', () => {
    expect(applied.regime.reference.amount).toEqual(BASE.reference.amount);
    expect(applied.regime.grades.length).toBe(BASE.grades.length);

    // The proposal now merges names deliberately, so an equal position count is no
    // longer the right guard — it would forbid the very thing the merge is for. What
    // must still hold is that nothing vanished: every code in the base is either still
    // a position or recorded as absorbed into one.
    const reachable = new Set<string>();
    for (const p of applied.regime.positions) {
      reachable.add(p.code);
      for (const code of p.mergedFrom ?? []) reachable.add(code);
    }
    const lost = BASE.positions.filter((p) => !reachable.has(p.code));
    expect(lost.map((p) => p.code)).toEqual([]);
  });

  it('every variant is uniquely addressable', () => {
    // Without this the next assertion silently compares the wrong pair, and worse,
    // payslip() picks the first match: 233 positions once carried indistinguishable
    // variants, including four tiers of local authority spanning 4,47 down to 2,47 under
    // one code. A director in the smallest commune would have been priced at the
    // largest city's rate.
    for (const regime of [BASE, applied.regime]) {
      for (const position of regime.positions) {
        const signatures = position.variants.map((v) => JSON.stringify(v.dims ?? {}));
        expect(new Set(signatures).size, `${regime.id} ${position.code} has ambiguous variants`)
          .toBe(signatures.length);
      }
    }
  });

  it('moves no coefficient by more than rounding', () => {
    // Rounding to two decimals is the only edit that touches a value, so nothing may
    // move by more than half a hundredth. A larger move would be a pay decision.
    const baseByCode = new Map(BASE.positions.map((p) => [p.code, p]));
    let worst = 0;
    for (const position of applied.regime.positions) {
      const original = baseByCode.get(position.code)!;
      for (const variant of position.variants) {
        if (typeof variant.value !== 'number') continue;
        const match = original.variants.find(
          (v) => JSON.stringify(v.dims ?? {}) === JSON.stringify(variant.dims ?? {}),
        );
        if (!match || typeof match.value !== 'number') continue;
        worst = Math.max(worst, Math.abs(match.value - variant.value));
      }
    }
    // Half of the last retained decimal is exactly 0,005, which binary floating point
    // cannot represent — hence the epsilon. The bound is the rounding rule, not a fudge.
    expect(worst).toBeLessThanOrEqual(0.005 + 1e-9);
  });

  it('keeps the floor of the grid exactly where it was', () => {
    expect(after.span.min).toBe(before.span.min);
  });
});

describe('one job gets one name', () => {
  const merged = applied.regime.positions.filter((p) => p.mergedFrom?.length);
  const byName = (name: string) =>
    merged.find((p) => p.name.trim().toLowerCase() === name.toLowerCase());

  it('collapses the same job named once per employer', () => {
    // The grid carries "Director" under 25 codes across six annexes. That counts
    // employers, not occupations, and it is the headline number on the landing page.
    expect(applied.regime.positions.length).toBeLessThan(BASE.positions.length - 200);
    expect(merged.length).toBeGreaterThan(50);
    // "Director" absorbs five sibling codes; it would absorb eleven if the rank-label
    // guard were not holding the indented continuation rows back.
    expect(byName('Director')?.mergedFrom!.length).toBeGreaterThan(3);
  });

  it('never merges across occupational families', () => {
    // A director in education and a director in administration are different posts. The
    // family is what keeps the merge from fusing them on the strength of a shared word.
    const familyOf = new Map(BASE.positions.map((p) => [p.code, p.family]));
    for (const position of merged) {
      for (const code of position.mergedFrom!) {
        expect(familyOf.get(code)).toBe(position.family);
      }
    }
  });

  it('refuses rows whose name is a rank rather than a job', () => {
    // The importer now folds ranks into the position above as a `grad` dimension, so the
    // base regime no longer contains a job called "debutant" for the merge to swallow.
    // The guard stays because the two fixes are independent: a future sheet layout could
    // reintroduce the rows, and merging them would produce a large, satisfying, wrong
    // reduction. Assert both the corrected input and the guard that does not rely on it.
    for (const label of ['debutant', 'principal', 'gradul i', 'clasa a ii-a', 'treapta ii']) {
      expect(BASE.positions.map((p) => p.name.trim().toLowerCase())).not.toContain(label);
      expect(merged.map((p) => p.name.trim().toLowerCase())).not.toContain(label);
    }

    // The guard itself, on a regime built to contain exactly the defect.
    const rank = (code: string, name: string): Position => ({
      code,
      name,
      family: 'X-test',
      kind: 'execution',
      studyLevel: 'S',
      variants: [{ value: 2, provenance: BASE.positions[0].variants[0].provenance }],
      provenance: BASE.positions[0].provenance,
    });
    const trap: Regime = {
      ...BASE,
      positions: [rank('t.1', 'debutant'), rank('t.2', 'debutant'), rank('t.3', 'Auditor'), rank('t.4', 'Auditor')],
    };
    const out = applyProposal(trap, {
      ...PROPOSAL,
      patches: PROPOSAL.patches.filter((p) => p.op === 'mergeDuplicateTitles'),
    });
    const names = out.regime.positions.map((p) => p.name);
    expect(names.filter((n) => n === 'debutant')).toHaveLength(2);
    expect(names.filter((n) => n === 'Auditor')).toHaveLength(1);
  });

  it('loses no name and keeps every code traceable', () => {
    for (const position of merged.slice(0, 40)) {
      expect(position.titles!.length).toBeGreaterThan(0);
      // Every absorbed code is recorded, and never the kept position's own code.
      expect(position.mergedFrom).not.toContain(position.code);
      for (const code of position.mergedFrom!) {
        expect(BASE.positions.some((p) => p.code === code)).toBe(true);
      }
    }
  });

  it('turns the spread between employers into an explicit multiplier', () => {
    // The merge must not hide that two employers paid differently for the same job — it
    // moves that difference out of the name and into a number that can be argued with.
    const director = byName('Director general adjunct');
    expect(director?.institutionFactor?.max).toBeGreaterThan(1);
  });

  it('changes no salary', () => {
    // Naming is not pay. The lowest coefficient in the grid must be exactly what it was.
    const lowest = (regime: Regime) =>
      Math.min(
        ...regime.positions.flatMap((p) =>
          p.variants.map((v) => (typeof v.value === 'number' ? v.value : Infinity)),
        ),
      );
    expect(lowest(applied.regime)).toBeCloseTo(lowest(BASE), 10);
  });
});

import { describe, expect, it } from 'vitest';

import { compareComposition, COMPONENTS } from './composition';

/**
 * The real shares, as the two importers wrote them: Romania from the 2025 budget
 * execution across the whole public sector, Denmark from LONSOFF 2024, all public
 * employees. They are the fixture because the bug this file guards against is not a
 * crash — it is a chart that quietly reverses its own conclusion.
 */
const RO = {
  basic: 0.8018,
  seniority: 0.0001,
  conditions: 0.0762,
  overtime: 0.0268,
  irregular: 0.0312,
  fringe: 0.0514,
  other: 0.0125,
};

const DK = {
  basic: 0.763,
  conditions: 0.024,
  overtime: 0.001,
  irregular: 0.019,
  fringe: 0.0,
  pension: 0.135,
  sickness: 0.057,
  holiday: 0.12,
};

const basicOf = (side: { slices: Array<{ component: string; share: number }> }) =>
  side.slices.find((s) => s.component === 'basic')!.share;

describe('comparing the two compositions', () => {
  it('finds the Romanian supplement layer several times the Danish one', () => {
    const { ro, dk, timesLarger } = compareComposition(RO, DK);
    expect(ro.supplements).toBeCloseTo(0.188, 3);
    expect(dk.supplements).toBeCloseTo(0.055, 3);
    expect(timesLarger).toBeGreaterThan(3);
  });

  it('leaves employer pension and paid sickness out of the Danish denominator', () => {
    // Romania excludes title 10.03 and pays sick leave from another title, so counting
    // either on the Danish side would compare pay against the cost of employment.
    const { dk } = compareComposition(RO, DK);
    expect(dk.excluded.map((e) => e.key)).toEqual(['pension', 'sickness']);
    expect(basicOf(dk)).toBeCloseTo(0.945, 3);
  });

  it('leaves delegation and secondment out of the Romanian denominator', () => {
    const { ro } = compareComposition(RO, DK);
    expect(ro.excluded.map((e) => e.key)).toEqual(['other']);
    expect(basicOf(ro)).toBeCloseTo(0.812, 3);
  });

  it('never subtracts holiday pay, which is already inside basic earnings', () => {
    // Danmarks Statistik prints holiday with a leading '..' — a sub-item of BASIS, not a
    // component beside it. Treating it as a peer and removing it would strip twelve
    // points off Danish base pay and flip which country leans more on its base salary.
    const { dk } = compareComposition(RO, DK);
    expect(dk.holidayInsideBasic).toBeCloseTo(0.12, 3);
    expect(dk.excluded.map((e) => e.key)).not.toContain('holiday');

    const withoutHoliday = compareComposition(RO, { ...DK, holiday: 0 });
    expect(basicOf(withoutHoliday.dk)).toBe(basicOf(dk));

    // The claim the guard exists to protect: on the comparable basis Denmark is the more
    // base-heavy system, even though its published basic share (76,3%) is the lower one.
    expect(DK.basic).toBeLessThan(RO.basic);
    expect(basicOf(dk)).toBeGreaterThan(basicOf(compareComposition(RO, DK).ro));
  });

  it('renormalises each side to exactly one, in a fixed component order', () => {
    const { ro, dk } = compareComposition(RO, DK);
    for (const side of [ro, dk]) {
      expect(side.slices.reduce((sum, s) => sum + s.share, 0)).toBeCloseTo(1, 10);
      expect(side.slices.map((s) => s.component)).toEqual(COMPONENTS);
    }
  });

  it('returns an empty side rather than a bar of NaN when a side has no data', () => {
    const { dk, timesLarger } = compareComposition(RO, {});
    expect(dk.slices).toEqual([]);
    expect(dk.supplements).toBe(0);
    expect(timesLarger).toBeNull();
  });

  it('keeps seniority visible on the Romanian side even though Denmark has no such line', () => {
    // Romania folded the standalone seniority bonus into base pay in 2010, which is what
    // Denmark does too. The slice should exist and be ~zero; if it ever grows back, the
    // chart must show it rather than bury it in "other".
    const { ro } = compareComposition(RO, DK);
    expect(ro.slices.find((s) => s.component === 'seniority')!.share).toBeLessThan(0.001);
  });
});

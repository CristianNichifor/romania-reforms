/**
 * The map's five-step ramp stays readable with red-green colour blindness (UX review).
 *
 * The old ramp ran green to red, and its ends are close under protanopia and deuteranopia: the
 * two things the map exists to tell apart ("much below the grade average", "much above") were
 * the hardest pair to tell apart for about one man in twelve. Each step is simulated with the
 * Machado et al. (2009) matrices at full severity and must differ from its neighbours, and the
 * ends from each other, by more than a fixed distance in linear RGB.
 */
import { describe, expect, it } from 'vitest';

import { RAMP } from './ramp';

const OLD_RAMP = ['#2f7d4f', '#7fa86a', '#d9c05a', '#d98040', '#c2453a'];

const MACHADO: Record<string, number[][]> = {
  protanopia: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deuteranopia: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
};

const linear = (hex: string): number[] =>
  [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });

const simulate = (hex: string, matrix: number[][]): number[] => {
  const rgb = linear(hex);
  return matrix.map((row) => Math.min(1, Math.max(0, row[0]! * rgb[0]! + row[1]! * rgb[1]! + row[2]! * rgb[2]!)));
};

const distance = (a: number[], b: number[]) => Math.hypot(a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!);

/** The smallest gap, under either deficiency, between neighbours and between the two ends. */
const worstGap = (ramp: readonly string[]): number => {
  let worst = Infinity;
  for (const matrix of Object.values(MACHADO)) {
    const seen = ramp.map((hex) => simulate(hex, matrix));
    for (let i = 1; i < seen.length; i += 1) worst = Math.min(worst, distance(seen[i - 1]!, seen[i]!));
    worst = Math.min(worst, 2 * distance(seen[0]!, seen.at(-1)!) / (seen.length - 1));
  }
  return worst;
};

describe('the ramp under red-green colour blindness', () => {
  it('has five steps', () => {
    expect(RAMP).toHaveLength(5);
  });

  it('keeps every step apart', () => {
    expect(worstGap(RAMP)).toBeGreaterThan(0.08);
  });

  it('is a real test: the old green-to-red ramp fails it', () => {
    expect(worstGap(OLD_RAMP)).toBeLessThan(0.08);
  });
});

describe('the legend', () => {
  it('uses the same colours as the map', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8');
    const tokens = [1, 2, 3, 4, 5].map((i) => new RegExp(`--ramp-${i}: (#[0-9a-f]{6});`).exec(css)?.[1]);
    expect(tokens).toEqual([...RAMP]);
  });
});

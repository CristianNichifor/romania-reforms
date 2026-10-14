// Courts sharing a courthouse get their own circle each (UX review: București overlap).
import { describe, expect, it } from 'vitest';

import { SPREAD_DEGREES, spread } from './spread';

const at = (name: string, volume: number, point: [number, number] = [26.09326, 44.43234]) => ({
  name,
  volume,
  point,
});

describe('spread', () => {
  it('leaves a court alone at its own point', () => {
    const only = [at('Judecătoria Buftea', 71220, [25.94686, 44.55946])];
    expect(spread(only)).toEqual(only);
  });

  it('gives every coincident court a distinct point and keeps the largest in place', () => {
    const courts = [
      at('Înalta Curte', 18905),
      at('Curtea de Apel București', 65863),
      at('Tribunalul București', 172386),
      at('Tribunalul Militar Teritorial', 514),
    ];
    const out = spread(courts);
    expect(out.map((c) => c.name)).toEqual(courts.map((c) => c.name));
    expect(out[2]!.point).toEqual([26.09326, 44.43234]);
    const points = new Set(out.map((c) => c.point.join(',')));
    expect(points.size).toBe(4);
    for (const c of out) {
      expect(Math.abs(c.point[1] - 44.43234)).toBeLessThanOrEqual(SPREAD_DEGREES + 1e-9);
      expect(Math.abs(c.point[0] - 26.09326)).toBeLessThanOrEqual(SPREAD_DEGREES * 1.5);
    }
  });

  it('does not mutate the input', () => {
    const courts = [at('a', 1), at('b', 2)];
    spread(courts);
    expect(courts[0]!.point).toEqual([26.09326, 44.43234]);
  });
});

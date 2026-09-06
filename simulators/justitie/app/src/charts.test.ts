/**
 * The axis is the one part of a chart that can be wrong without looking wrong.
 *
 * A bar's length is checked by eye against its neighbours; a tick that reads 200.000 over a bar
 * of 240.000 is read as fact. So the scale gets tests and the markup does not.
 */

import { describe, expect, it } from 'vitest';
import { esc, niceScale } from './charts';

describe('niceScale', () => {
  it('never crops the longest bar', () => {
    for (const max of [1, 3, 7, 42, 99, 101, 1234, 4_655_217, 0.4, 2.5]) {
      expect(niceScale(max).max).toBeGreaterThanOrEqual(max);
    }
  });

  it('puts ticks on readable steps', () => {
    expect(niceScale(4_655_217).ticks).toEqual([0, 1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000]);
    expect(niceScale(42).ticks).toEqual([0, 10, 20, 30, 40, 50]);
    expect(niceScale(9).ticks).toEqual([0, 2, 4, 6, 8, 10]);
    expect(niceScale(1).ticks).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
  });

  it('starts at zero and ends at the top, exactly', () => {
    const { max, ticks } = niceScale(1234);
    expect(ticks.at(0)).toBe(0);
    expect(ticks.at(-1)).toBe(max);
  });

  it('does not drift on fractional steps', () => {
    // Three times 0,2 is 0,6000000000000001 in binary floating point, whether it is reached by
    // addition or by multiplication. A tick label with sixteen digits is a bug a reader can see.
    expect(niceScale(1).ticks.every((tick) => String(tick).length <= 3)).toBe(true);
  });

  it('survives a chart with nothing in it', () => {
    // An empty filter selection reaches here as a maximum of zero, and a division by zero in the
    // bar width would render every bar as `width:NaN%` — which draws nothing and reports nothing.
    expect(niceScale(0)).toEqual({ max: 1, ticks: [0, 1] });
    expect(niceScale(Number.NaN).max).toBe(1);
    expect(niceScale(-5).max).toBe(1);
  });
});

describe('esc', () => {
  it('closes off an attribute break', () => {
    // Court and party names come from a government dataset, not from a form, but they are still
    // interpolated into `data-tip="…"` and one ampersand is enough to lose the rest of the row.
    expect(esc('S.C. "X" & Co <b>')).toBe('S.C. &quot;X&quot; &amp; Co &lt;b&gt;');
  });
});

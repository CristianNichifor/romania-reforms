// On a touchscreen the map hint says "Atinge", not "Treci cu mouse-ul" (UX review).
import { afterEach, describe, expect, it } from 'vitest';

import { pointHint } from './touch';

const screen = (hoverNone: boolean) =>
  Object.defineProperty(globalThis, 'matchMedia', {
    value: (query: string) => ({ matches: query === '(hover: none)' && hoverNone }),
    configurable: true,
    writable: true,
  });

afterEach(() => {
  Reflect.deleteProperty(globalThis, 'matchMedia');
});

describe('pointHint', () => {
  it('asks a mouse to hover', () => {
    screen(false);
    expect(pointHint('o instanță')).toBe('Treci cu mouse-ul peste o instanță.');
  });

  it('asks a finger to tap', () => {
    screen(true);
    expect(pointHint('o comună')).toBe('Atinge o comună.');
  });

  it('assumes a mouse where media queries are unavailable', () => {
    expect(pointHint('o instanță')).toBe('Treci cu mouse-ul peste o instanță.');
  });
});

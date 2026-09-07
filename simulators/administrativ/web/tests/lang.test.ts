/**
 * Which language a visitor gets.
 *
 * The rule is short and worth pinning anyway, because getting it wrong is invisible to whoever
 * changed it: a developer with a Romanian browser and a Romanian default cannot tell the two
 * apart, and the bug only shows up for readers they never see.
 *
 * `detectLang` reads the global `location`, so these tests stub it rather than pull in a DOM.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { detectLang } from '../src/i18n';

const withHash = (hash: string): void => {
  Object.defineProperty(globalThis, 'location', {
    value: { hash },
    configurable: true,
    writable: true,
  });
};

afterEach(() => {
  Reflect.deleteProperty(globalThis, 'location');
});

describe('the language a bare URL gets', () => {
  it('is Romanian, matching the document and the subject', () => {
    withHash('');
    expect(detectLang()).toBe('ro');
  });

  it('is Romanian even where the scenario is spelled out but the language is not', () => {
    withHash('#x=8500&nmin=5');
    expect(detectLang()).toBe('ro');
  });

  it('does not consult the browser, which is a poor proxy here', () => {
    // Many Romanians run an English-locale system. If this ever reads navigator.language
    // again, this test is the thing that notices — the stub says English and the answer
    // must still be Romanian.
    Object.defineProperty(globalThis, 'navigator', {
      value: { language: 'en-US' },
      configurable: true,
      writable: true,
    });
    withHash('');
    expect(detectLang()).toBe('ro');
    Reflect.deleteProperty(globalThis, 'navigator');
  });
});

describe('what the URL can override', () => {
  it('honours an explicit English link, so a shared link keeps its meaning', () => {
    withHash('#x=8500&lang=en');
    expect(detectLang()).toBe('en');
  });

  it('honours an explicit Romanian link', () => {
    withHash('#lang=ro');
    expect(detectLang()).toBe('ro');
  });

  it('falls back rather than trusting an unknown language', () => {
    withHash('#lang=fr');
    expect(detectLang()).toBe('ro');
  });
});

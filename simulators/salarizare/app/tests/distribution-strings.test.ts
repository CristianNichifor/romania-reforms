// RR-10, third slice: the Distribuție view prints its own words in the page language. Both
// tables carry the same keys; the English strings and string formatters carry no Romanian
// letters; the Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { DISTRIBUTION_STRINGS } from '../src/DistributionView';

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1', 2, '3', '4', '5');
      if (typeof result === 'string') out.push(result);
    }
  }
  return out;
};

describe('the Distribuție strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(DISTRIBUTION_STRINGS.en).sort()).toEqual(Object.keys(DISTRIBUTION_STRINGS.ro).sort());
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(DISTRIBUTION_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(DISTRIBUTION_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build counts and the transition sentence from the caller\'s numbers', () => {
    expect(DISTRIBUTION_STRINGS.ro.matched(1)).toBe('1 post regăsit');
    expect(DISTRIBUTION_STRINGS.en.matched(3)).toBe('3 matched posts');
    expect(DISTRIBUTION_STRINGS.en.bandTitle('-5%', 12)).toBe('-5%: 12 posts');
    const hero = DISTRIBUTION_STRINGS.en.transitionHero('900', '2,500', '4,100', '61.0%', '72.3%');
    expect(hero).toContain('out of the 900 matched');
    expect(hero).toContain('from 2,500 to 4,100 lei');
    expect(hero).toContain('stops at 72.3%');
  });
});

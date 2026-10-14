// RR-10, first slice: the Domenii view prints its own words in the page language. Both tables
// carry the same keys, the English one has no Romanian letters left behind, and the Romanian
// one uses comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { DOMAINS_STRINGS } from '../src/DomainsView';

const flatten = (value: unknown): string[] => {
  if (typeof value === 'string') return [value];
  if (typeof value === 'function') {
    const fn = value as (...args: string[]) => string;
    return [fn('1', '2', '3', '4')];
  }
  if (Array.isArray(value)) return value.flatMap(flatten);
  if (value && typeof value === 'object') return Object.values(value).flatMap(flatten);
  return [];
};

describe('the Domenii strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(DOMAINS_STRINGS.en).sort()).toEqual(Object.keys(DOMAINS_STRINGS.ro).sort());
    expect(Object.keys(DOMAINS_STRINGS.en.sides)).toEqual(Object.keys(DOMAINS_STRINGS.ro.sides));
  });

  it('leave no Romanian letters in the English table', () => {
    for (const text of flatten(DOMAINS_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian table', () => {
    const texts = flatten(DOMAINS_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('format counts and movements with the caller\'s numbers', () => {
    expect(DOMAINS_STRINGS.en.postsInDraft('1,234')).toBe('1,234 posts in the draft');
    expect(DOMAINS_STRINGS.ro.rows(1)).toBe('1 rând');
    expect(DOMAINS_STRINGS.en.rows(2)).toBe('2 rows');
    expect(DOMAINS_STRINGS.en.disclaimerAverage('2024')).toContain('from 2024');
  });
});

// RR-10, ninth slice: the Funcție cu funcție view prints its own words in the page language.
// Both tables carry the same keys; the English strings and string formatters carry no Romanian
// letters (the search placeholder quotes grid titles, which are data); the Romanian ones use
// comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { MERGES_STRINGS } from '../src/MergesView';

const plainTexts = (table: Record<string, unknown>, skip: string[] = []): string[] => {
  const out: string[] = [];
  for (const [key, value] of Object.entries(table)) {
    if (skip.includes(key)) continue;
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1');
      if (typeof result === 'string') out.push(result);
    } else if (value && typeof value === 'object') {
      out.push(...Object.values(value as Record<string, string>).filter((v) => typeof v === 'string'));
    }
  }
  return out;
};

describe('the Funcție cu funcție strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(MERGES_STRINGS.en).sort()).toEqual(Object.keys(MERGES_STRINGS.ro).sort());
    expect(Object.keys(MERGES_STRINGS.en.rows)).toEqual(Object.keys(MERGES_STRINGS.ro.rows));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(MERGES_STRINGS.en, ['searchPlaceholder'])) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(MERGES_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the counts from the caller\'s figures', () => {
    expect(MERGES_STRINGS.en.found('1,031')).toBe('1,031 positions found');
    expect(MERGES_STRINGS.ro.found('1.031')).toBe('1.031 funcții găsite');
    expect(MERGES_STRINGS.en.showingFirst('60')).toBe(' — showing the first 60');
    expect(MERGES_STRINGS.en.more('60')).toBe('60 more positions');
    expect(MERGES_STRINGS.en.fanIn(11)).toBe('11 titles');
    expect(MERGES_STRINGS.ro.titlesSummary(11)).toBe('Denumirile strânse aici (11)');
    expect(MERGES_STRINGS.en.parseNote('a; b')).toContain('read as "a; b"');
  });
});

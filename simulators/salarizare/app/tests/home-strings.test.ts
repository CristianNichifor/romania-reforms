// RR-10, fifth slice: the Acasă view prints its own words in the page language. Both tables
// carry the same keys and the same number of questions and entries; the English strings and
// string formatters carry no Romanian letters; the Romanian ones use comma-below ș ț
// (ux-guidelines § 3). The search's empty state follows the same rule.
import { describe, expect, it } from 'vitest';

import { HOME_STRINGS } from '../src/HomeView';
import { NOHIT_STRINGS } from '../src/NoHit';

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1');
      if (typeof result === 'string') out.push(result);
    } else if (Array.isArray(value)) {
      for (const q of value as { ask: string; lead: string; entries: { title: string; body: string }[] }[]) {
        out.push(q.ask, q.lead);
        for (const e of q.entries) out.push(e.title, e.body);
      }
    }
  }
  return out;
};

describe('the Acasă strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(HOME_STRINGS.en).sort()).toEqual(Object.keys(HOME_STRINGS.ro).sort());
    expect(Object.keys(HOME_STRINGS.en.sources).sort()).toEqual(Object.keys(HOME_STRINGS.ro.sources).sort());
  });

  it('point the same questions at the same views', () => {
    const views = (lang: 'ro' | 'en') => HOME_STRINGS[lang].questions.map((q) => q.entries.map((e) => e.view));
    expect(views('en')).toEqual(views('ro'));
    expect(views('ro').flat()).toEqual([
      'compare', 'distributie', 'structure', 'domenii', 'meserii', 'payslip', 'echivalente', 'envelope',
    ]);
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(HOME_STRINGS.en)) {
      // The example titles to type into the search are grid titles, so they stay Romanian.
      expect(text).not.toMatch(/[ăâîșț]/i);
    }
    expect(NOHIT_STRINGS.en('x')).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(HOME_STRINGS.ro).join(' ') + NOHIT_STRINGS.ro('x');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the counts and the empty state from the caller\'s values', () => {
    expect(HOME_STRINGS.ro.positions('1.234')).toBe(' · 1.234 funcții');
    expect(HOME_STRINGS.en.positions('1,234')).toBe(' · 1,234 positions');
    expect(HOME_STRINGS.en.transcribed('98')).toBe(' · 98 posts transcribed');
    expect(HOME_STRINGS.en.otherTitles(3)).toBe('+3 titles · ');
    expect(NOHIT_STRINGS.en('farmacist primr')).toContain('No post for "farmacist primr"');
    expect(NOHIT_STRINGS.ro('farmacist primr')).toContain('„farmacist primr”');
  });
});

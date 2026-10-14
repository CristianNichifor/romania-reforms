// RR-10, seventh slice: the Echivalențe view prints its own words in the page language. Both
// tables carry the same keys; the English strings and string formatters carry no Romanian
// letters; the Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { EQUIVALENCE_STRINGS } from '../src/EquivalenceView';

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1', '2');
      if (typeof result === 'string') out.push(result);
    } else if (value && typeof value === 'object' && !('$$typeof' in (value as object))) {
      out.push(...Object.values(value as Record<string, string>).filter((v) => typeof v === 'string'));
    }
  }
  return out;
};

describe('the Echivalențe strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(EQUIVALENCE_STRINGS.en).sort()).toEqual(Object.keys(EQUIVALENCE_STRINGS.ro).sort());
    expect(Object.keys(EQUIVALENCE_STRINGS.en.anchorOptions)).toEqual(Object.keys(EQUIVALENCE_STRINGS.ro.anchorOptions));
    expect(Object.keys(EQUIVALENCE_STRINGS.en.anchorNames)).toEqual(Object.keys(EQUIVALENCE_STRINGS.ro.anchorNames));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(EQUIVALENCE_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(EQUIVALENCE_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('name the anchors the same way in the select and in the benchmark line', () => {
    for (const lang of ['ro', 'en'] as const) {
      const t = EQUIVALENCE_STRINGS[lang];
      expect(t.anchorNames.floor).toBe(t.anchorOptions.floor);
      // The benchmark line adds "gross"; the rest of the wording is the select's.
      for (const key of ['avg', 'gov'] as const) {
        const tail = t.anchorOptions[key].split(' ').slice(-3).join(' ');
        expect(t.anchorNames[key]).toContain(tail);
      }
    }
    expect(EQUIVALENCE_STRINGS.en.anchorOptions.avg).toBe('the average wage across the economy');
    expect(EQUIVALENCE_STRINGS.ro.badgeNone).toBe('fără corespondent danez');
  });
});

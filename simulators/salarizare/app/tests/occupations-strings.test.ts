// RR-10, eleventh and last slice: the Meserii view prints its own words in the page language.
// Both tables carry the same shape at every level; the English strings and string formatters
// carry no Romanian letters; the Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { OCCUPATIONS_STRINGS } from '../src/OccupationsView';
import { STRINGS } from '../src/i18n';

const isElement = (value: unknown) => !!value && typeof value === 'object' && '$$typeof' in (value as object);

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1', '2', '3', '4');
      if (typeof result === 'string') out.push(result);
    } else if (value && typeof value === 'object' && !isElement(value)) {
      out.push(...plainTexts(value as Record<string, unknown>));
    }
  }
  return out;
};

const shape = (table: Record<string, unknown>): unknown =>
  Object.fromEntries(
    Object.entries(table).map(([key, value]) => [
      key,
      value && typeof value === 'object' && !isElement(value) ? shape(value as Record<string, unknown>) : typeof value,
    ]),
  );

describe('the Meserii strings', () => {
  it('have the same shape in both languages', () => {
    expect(shape(OCCUPATIONS_STRINGS.en)).toEqual(shape(OCCUPATIONS_STRINGS.ro));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(OCCUPATIONS_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(OCCUPATIONS_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the sentences from the caller\'s figures', () => {
    expect(OCCUPATIONS_STRINGS.en.trendMoved(true, '1.3', '2021', '2025')).toBe(
      'Up by 1.3 percentage points between 2021 and 2025 — a change of share, not of percent.',
    );
    expect(OCCUPATIONS_STRINGS.ro.trendMoved(false, '1,3', '2021', '2025')).toContain('A scăzut cu 1,3 puncte');
    expect(OCCUPATIONS_STRINGS.en.positions('12')).toBe('12 positions');
    expect(OCCUPATIONS_STRINGS.en.andMore('3')).toBe('…and 3 more');
    expect(OCCUPATIONS_STRINGS.en.keyGridRange('40')).toBe("the grid's range (40 positions)");
    expect(OCCUPATIONS_STRINGS.en.oldGrid('3,000 RON', '28', '2024')).toContain('28% below what was paid in 2024');
  });
});

describe('the footer language note', () => {
  it('no longer claims the views are Romanian, only the documents they read', () => {
    expect(STRINGS.en.viewsInRomanian).not.toMatch(/views themselves are in Romanian/);
    expect(STRINGS.en.viewsInRomanian).toMatch(/remain in Romanian/);
    expect(STRINGS.ro.viewsInRomanian).toBeNull();
  });
});

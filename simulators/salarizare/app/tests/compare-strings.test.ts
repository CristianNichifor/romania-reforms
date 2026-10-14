// RR-10, tenth slice: the Ce se schimbă view prints its own words in the page language. Both
// tables carry the same keys at every level; the English strings and string formatters carry no
// Romanian letters; the Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { COMPARE_STRINGS } from '../src/CompareView';

const isElement = (value: unknown) => !!value && typeof value === 'object' && '$$typeof' in (value as object);

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1', '2', '3', '4', '5');
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

describe('the Ce se schimbă strings', () => {
  it('have the same shape in both languages', () => {
    expect(shape(COMPARE_STRINGS.en)).toEqual(shape(COMPARE_STRINGS.ro));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(COMPARE_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(COMPARE_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('count the proposal\'s own patches in the column subtitle', () => {
    expect(COMPARE_STRINGS.ro.oursSub(6, 1)).toBe('6 reparații + 1 schimbare');
    expect(COMPARE_STRINGS.ro.oursSub(1, 2)).toBe('1 reparație + 2 schimbări');
    expect(COMPARE_STRINGS.en.oursSub(6, 1)).toBe('6 repairs + 1 change');
    expect(COMPARE_STRINGS.en.oursSub(1, 2)).toBe('1 repair + 2 changes');
  });

  it('build the sentences from the caller\'s figures', () => {
    expect(COMPARE_STRINGS.en.purpose('7', '7')).toContain('with 7 corrections');
    expect(COMPARE_STRINGS.en.notes.fewer('12')).toBe('12 fewer');
    expect(COMPARE_STRINGS.ro.notes.fewer('12')).toBe('cu 12 mai puține');
    expect(COMPARE_STRINGS.en.notes.spanInPeriod('2027', '1:8.00', '2031')).toBe('in 2027; it reaches 1:8.00 in 2031');
    expect(COMPARE_STRINGS.en.heroWithLaw('300', '900', '3.0', '41%', '320')).toContain('3.0 times as many');
    expect(COMPARE_STRINGS.ro.referenceBody('4.050 RON', '10.125 RON')).toContain('(4.050 RON)');
  });
});

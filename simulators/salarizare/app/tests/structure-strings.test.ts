// RR-10, second slice: the Structură view prints its own words in the page language. Both
// tables carry the same keys; the English strings and formatters carry no Romanian letters
// (the legal file name and the quoted Romanian job titles are data, not copy, and are checked
// apart); the Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { STRUCTURE_STRINGS } from '../src/StructureView';

// Plain strings and string-returning formatters; React-node entries are exercised by rendering.
const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)(
        { ratio: '7,00', period: '2026' },
        { ratio: '8,00', period: '2030' },
      );
      if (typeof result === 'string') out.push(result);
    }
  }
  return out;
};

describe('the Structură strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(STRUCTURE_STRINGS.en).sort()).toEqual(Object.keys(STRUCTURE_STRINGS.ro).sort());
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(STRUCTURE_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(STRUCTURE_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the phase-in sentence from the caller\'s ratios and periods', () => {
    const en = STRUCTURE_STRINGS.en.spanLede({ ratio: '7.39', period: '2026' }, { ratio: '8.00', period: '2030' });
    expect(en).toContain('it is 1:7.39 in 2026 and reaches exactly 1:8.00 in 2030');
    const ro = STRUCTURE_STRINGS.ro.spanLede(null, null);
    expect(ro).toContain('raportul se mișcă: .');
    expect(STRUCTURE_STRINGS.en.gapRange(1.19, 1.2)).toBe('above 1.19 and below 1.2');
    expect(STRUCTURE_STRINGS.ro.mergedNames(3)).toBe('3 denumiri comasate');
  });
});

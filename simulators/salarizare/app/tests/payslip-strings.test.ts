// RR-10, fourth slice: the Fluturaș view prints its own words in the page language. Both tables
// carry the same keys; the English strings and string formatters carry no Romanian letters; the
// Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { PAYSLIP_STRINGS } from '../src/PayslipView';

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('x', 2);
      if (typeof result === 'string') out.push(result);
    } else if (value && typeof value === 'object' && !('$$typeof' in (value as object))) {
      out.push(...Object.values(value as Record<string, string>).filter((v) => typeof v === 'string'));
    }
  }
  return out;
};

describe('the Fluturaș strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(PAYSLIP_STRINGS.en).sort()).toEqual(Object.keys(PAYSLIP_STRINGS.ro).sort());
    expect(Object.keys(PAYSLIP_STRINGS.en.period)).toEqual(Object.keys(PAYSLIP_STRINGS.ro.period));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(PAYSLIP_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(PAYSLIP_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the labels from the caller\'s values', () => {
    expect(PAYSLIP_STRINGS.ro.otherTitles(3)).toBe(' (+3 denumiri)');
    expect(PAYSLIP_STRINGS.en.calcTable('Draft 2026')).toBe('Pay computation: Draft 2026');
    expect(PAYSLIP_STRINGS.en.excludedBy('spor X')).toBe(' — excluded by "spor X"');
    expect(PAYSLIP_STRINGS.en.diagnostics(2)).toBe('2 notes on this computation');
    expect(PAYSLIP_STRINGS.ro.period.month).toBe('pe lună');
    expect(PAYSLIP_STRINGS.en.period.year).toBe('per year');
  });
});

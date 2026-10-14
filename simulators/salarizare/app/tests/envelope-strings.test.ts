// RR-10, sixth slice: the Cât costă tot view and its cap section print their own words in the
// page language. Both tables carry the same keys; the English strings and string formatters carry
// no Romanian letters; the Romanian ones use comma-below ș ț (ux-guidelines § 3). Money follows
// the reader's locale too.
import { describe, expect, it } from 'vitest';

import { CAP_STRINGS } from '../src/CapSection';
import { ENVELOPE_STRINGS } from '../src/EnvelopeView';
import { amountLine } from '../src/money';

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1', '2', '3', '4');
      if (typeof result === 'string') out.push(result);
    } else if (value && typeof value === 'object' && !('$$typeof' in (value as object))) {
      out.push(...Object.values(value as Record<string, string>).filter((v) => typeof v === 'string'));
    }
  }
  return out;
};

describe('the Cât costă tot strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(ENVELOPE_STRINGS.en).sort()).toEqual(Object.keys(ENVELOPE_STRINGS.ro).sort());
    expect(Object.keys(ENVELOPE_STRINGS.en.severity)).toEqual(Object.keys(ENVELOPE_STRINGS.ro.severity));
    expect(Object.keys(CAP_STRINGS.en).sort()).toEqual(Object.keys(CAP_STRINGS.ro).sort());
    expect(Object.keys(CAP_STRINGS.en.columns)).toEqual(Object.keys(CAP_STRINGS.ro.columns));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of [...plainTexts(ENVELOPE_STRINGS.en), ...plainTexts(CAP_STRINGS.en)]) {
      expect(text).not.toMatch(/[ăâîșț]/i);
    }
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = [...plainTexts(ENVELOPE_STRINGS.ro), ...plainTexts(CAP_STRINGS.ro)].join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the sentences from the caller\'s figures', () => {
    expect(ENVELOPE_STRINGS.en.hero('120.3 bn', '24.1', '8.52', '8.60')).toBe(
      '120.3 bn lei a year ≈ 24.1 bn EUR — 8.52% of GDP, against 8.60% now.',
    );
    expect(ENVELOPE_STRINGS.ro.missing('1,2 mld.')).toBe('Lipsesc 1,2 mld. lei — sunt creșteri fără acoperire.');
    expect(ENVELOPE_STRINGS.en.targetNote('+2.5%', '120.3 bn')).toBe('+2.5% against 120.3 bn lei');
    expect(ENVELOPE_STRINGS.en.art38('8.6', '7.1', '-17.4%')).toContain('From 8.6% that would mean 7.1%');
    expect(CAP_STRINGS.en.heroText('37', '1,204')).toBe(
      'That much of the base wage bill sits in institutions already above 20%. They are 37 of 1,204 — few in number, but they carry the money.',
    );
    expect(CAP_STRINGS.ro.bnBase('2,35')).toBe('2,35 mld lei salarii de bază');
  });

  it('print money in the reader\'s locale', () => {
    const rates = { dkkToRon: 0.67, eurToRon: 5, date: '2026-01-01' };
    expect(amountLine(12345, 'RON', rates)).toContain('12.345');
    expect(amountLine(12345, 'RON', rates, 'native', 'en-GB')).toContain('12,345');
  });
});

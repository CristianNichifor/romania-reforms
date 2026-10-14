// RR-10, eighth slice: the Propunerea noastră view prints its own words in the page language.
// Both tables carry the same keys; the English strings and string formatters carry no Romanian
// letters; the Romanian ones use comma-below ș ț (ux-guidelines § 3).
import { describe, expect, it } from 'vitest';

import { PROPOSAL_STRINGS } from '../src/ProposalView';

const plainTexts = (table: Record<string, unknown>): string[] => {
  const out: string[] = [];
  for (const value of Object.values(table)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      const result = (value as (...args: unknown[]) => unknown)('1', '2', '3', '4');
      if (typeof result === 'string') out.push(result);
    } else if (value && typeof value === 'object' && !('$$typeof' in (value as object))) {
      for (const inner of Object.values(value as Record<string, unknown>)) {
        if (typeof inner === 'string') out.push(inner);
        else if (inner && typeof inner === 'object') out.push(...Object.values(inner as Record<string, string>));
      }
    }
  }
  return out;
};

describe('the Propunerea noastră strings', () => {
  it('have the same keys in both languages', () => {
    expect(Object.keys(PROPOSAL_STRINGS.en).sort()).toEqual(Object.keys(PROPOSAL_STRINGS.ro).sort());
    expect(Object.keys(PROPOSAL_STRINGS.en.kpis)).toEqual(Object.keys(PROPOSAL_STRINGS.ro.kpis));
    expect(Object.keys(PROPOSAL_STRINGS.en.touched)).toEqual(Object.keys(PROPOSAL_STRINGS.ro.touched));
    expect(Object.keys(PROPOSAL_STRINGS.en.next)).toEqual(Object.keys(PROPOSAL_STRINGS.ro.next));
  });

  it('leave no Romanian letters in the English copy', () => {
    for (const text of plainTexts(PROPOSAL_STRINGS.en)) expect(text).not.toMatch(/[ăâîșț]/i);
  });

  it('use comma-below ș and ț in the Romanian copy', () => {
    const texts = plainTexts(PROPOSAL_STRINGS.ro).join(' ');
    expect(texts).toMatch(/[șț]/);
    expect(texts).not.toMatch(/[şţ]/);
  });

  it('build the counts line from the caller\'s figures', () => {
    expect(PROPOSAL_STRINGS.en.counts('6', '3', '7', '9')).toBe('6 repairs · 3 distribution changes · on now: 7 of 9');
    expect(PROPOSAL_STRINGS.ro.counts('6', '3', '7', '9')).toBe(
      '6 reparații · 3 schimbări de distribuție · pornite acum: 7 din 9',
    );
    expect(PROPOSAL_STRINGS.en.from('1:12.50')).toBe('from 1:12.50');
    expect(PROPOSAL_STRINGS.ro.from('1:12,50')).toBe('de la 1:12,50');
  });
});

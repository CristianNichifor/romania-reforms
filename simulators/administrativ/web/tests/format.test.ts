/**
 * Decimals follow the reader's language (UX review): "92,2%" and "21,7 km" in Romanian, not the
 * "92.2%" and "21.7 km" that toFixed printed beside "8,73 mld RON" on the same screen.
 */
import { describe, expect, it } from 'vitest';

import { formatDecimal, formatKm, formatPercent } from '../src/i18n';

describe('decimals in the reader language', () => {
  it('uses a decimal comma in Romanian and a point in English', () => {
    expect(formatDecimal(0.25, 2, 'ro')).toBe('0,25');
    expect(formatDecimal(0.25, 2, 'en')).toBe('0.25');
  });

  it('prints distances in kilometres, dropping a trailing zero decimal', () => {
    expect(formatKm(21700, 'ro')).toBe('21,7 km');
    expect(formatKm(21700, 'en')).toBe('21.7 km');
    expect(formatKm(15000, 'ro')).toBe('15 km');
  });

  it('prints the reduction as a Romanian percentage', () => {
    expect(formatPercent(0.922, 'ro').replace(/\s/g, ' ')).toBe('92,2 %');
  });
});

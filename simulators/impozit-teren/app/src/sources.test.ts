/**
 * Each county says which year its notarial guide is from, and an estimated county says so (RR-8).
 *
 * Most chambers publish a 2026 guide; a few counties are still priced from a 2024 or 2025 one.
 * The year is read from the value files the build copies, so the page cannot claim a year the
 * data does not carry.
 */
import { readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { countySourceBadges, estimatedCounties, guideYearsFrom } from './sources';

const data = resolve(dirname(fileURLToPath(import.meta.url)), '../../data');

describe('guide years', () => {
  const years = guideYearsFrom(readdirSync(data));

  it('takes the newest value edition of every county', () => {
    expect(Object.keys(years)).toHaveLength(42);
    expect(years.ab).toBe('2026');
    expect(years.vl).toBe('2024');
  });

  it('finds the counties priced from an older guide', () => {
    const older = Object.entries(years)
      .filter(([, year]) => year !== '2026')
      .map(([county]) => county)
      .sort();
    expect(older).toEqual(['br', 'bz', 'db', 'ph', 'vl', 'vn']);
  });
});

describe('badges', () => {
  const years = { ab: '2026', vl: '2024' };

  it('shows the guide year of every county and marks an older one', () => {
    expect(countySourceBadges('ab', years, new Set())).toBe(
      '<span class="source-year" title="Anul grilei notariale">grila 2026</span>',
    );
    expect(countySourceBadges('vl', years, new Set())).toBe(
      '<span class="source-year older" title="Anul grilei notariale: mai vechi decât 2026">grila 2024</span>',
    );
  });

  it('badges an estimated county', () => {
    expect(countySourceBadges('vl', years, new Set(['vl']))).toContain(
      '<span class="badge-estimated" title="Valoare estimată, nu citită dintr-o grilă">estimat</span>',
    );
  });

  it('says nothing for a county without a known year', () => {
    expect(countySourceBadges('xx', years, new Set())).toBe('');
  });

  it('reads the estimated counties from the national estimate', () => {
    const national = {
      counties_valued: [
        { county: 'AB', basis: 'measured' },
        { county: 'VL', basis: 'predicted' },
        { county: 'B', basis: 'excluded' },
      ],
    };
    expect([...estimatedCounties(national)]).toEqual(['vl']);
    expect(estimatedCounties(null).size).toBe(0);
  });
});

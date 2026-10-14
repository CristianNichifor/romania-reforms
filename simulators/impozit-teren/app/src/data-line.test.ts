import { describe, expect, it } from 'vitest';

import { dataLineFor } from './data-line';

describe('the data line under the H1', () => {
  it('names the fiscal code year and the span of guide years', () => {
    expect(dataLineFor({ period: '2026' }, { ab: '2026', b: '2024', cj: '2026' })).toBe('Date: Codul fiscal (Legea 227/2015), 2026; grile notariale 2024–2026');
  });
  it('collapses a single guide year', () => {
    expect(dataLineFor({ period: '2026' }, { ab: '2026' })).toBe('Date: Codul fiscal (Legea 227/2015), 2026; grile notariale 2026');
  });
  it('omits the guides when no county has one', () => {
    expect(dataLineFor({ period: '2026' }, {})).toBe('Date: Codul fiscal (Legea 227/2015), 2026');
  });
});

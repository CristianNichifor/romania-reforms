import { describe, expect, it } from 'vitest';

import { dataLineFor } from './data-line';

describe('the data line under the H1', () => {
  it('names the road data and the period the summary carries', () => {
    expect(dataLineFor({ period: '2026' })).toBe('Date: OpenStreetMap (Geofabrik) și programele județene de transport, 2026');
  });
  it('says nothing rather than inventing a year when the summary has none', () => {
    expect(dataLineFor({})).toBeNull();
  });
});

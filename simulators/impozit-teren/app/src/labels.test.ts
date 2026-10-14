// Severities in Romanian on the page (UX review): the limits list printed "blocking".
import { describe, expect, it } from 'vitest';

import { severityLabel } from './sources';

describe('severityLabel', () => {
  it('names every severity in Romanian and passes an unknown one through', () => {
    expect(severityLabel('blocking')).toBe('blocant');
    expect(severityLabel('material')).toBe('important');
    expect(severityLabel('note')).toBe('de reținut');
    expect(severityLabel('other')).toBe('other');
  });
});

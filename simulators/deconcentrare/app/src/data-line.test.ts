import { describe, expect, it } from 'vitest';

import { dataLineFor } from './data-line';

describe('the data line under the H1', () => {
  it('names the ANFP register and the period of the document', () => {
    expect(dataLineFor({ period: '2025' })).toBe('Date: ANFP, registrul instituțiilor publice (data.gov.ro), 2025');
  });
});

import { describe, expect, it } from 'vitest';

import { dataLineFor } from './data-line';

describe('the data line under the H1', () => {
  it('prints the publisher and period the CSM document carries', () => {
    expect(dataLineFor({ publisher: 'Consiliul Superior al Magistraturii', period: '2025' })).toBe('Date: Consiliul Superior al Magistraturii, 2025');
  });
});

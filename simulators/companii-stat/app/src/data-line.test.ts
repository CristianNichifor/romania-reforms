import { describe, expect, it } from 'vitest';

import { dataLine, dataLineFor } from './data-line';

describe('the data line under the H1', () => {
  it('names the ministry and the period of the document', () => {
    expect(dataLineFor({ period: '2019-2024' })).toBe('Date: Ministerul Finanțelor, situațiile financiare ale companiilor de stat, 2019–2024');
  });
  it('keeps a single year as it is', () => {
    expect(dataLine('X', '2025')).toBe('Date: X, 2025');
  });
});

// Severities in Romanian on the page (UX review), not the data's English keys.
import { describe, expect, it } from 'vitest';

import { SEVERITY_LABELS } from './model';

describe('labels', () => {
  it('names every severity in Romanian', () => {
    expect(SEVERITY_LABELS).toEqual({ blocking: 'blocant', material: 'important', note: 'de reținut' });
  });
});

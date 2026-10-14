// Romanian on the page (UX review): no "alta" without its diacritic, severities in Romanian,
// and lei amounts in mil / mld rather than ten-digit integers.
import { describe, expect, it } from 'vitest';

import { SEVERITY_LABELS, TIER_LABELS, compactRon } from './model';

describe('labels', () => {
  it('spells the other tier with its diacritic', () => {
    expect(TIER_LABELS.other).toBe('altă');
  });

  it('names every severity in Romanian', () => {
    expect(SEVERITY_LABELS).toEqual({ blocking: 'blocant', material: 'important', note: 'de reținut' });
  });
});

describe('compactRon', () => {
  it('uses mld and mil with a decimal comma', () => {
    expect(compactRon(1_234_567_890)).toBe('1,23 mld');
    expect(compactRon(45_600_000)).toBe('45,6 mil');
    expect(compactRon(-2_500_000_000)).toBe('-2,5 mld');
  });

  it('keeps small amounts whole', () => {
    expect(compactRon(980_000)).toBe('980.000');
    expect(compactRon(0)).toBe('0');
  });
});

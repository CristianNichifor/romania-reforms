/**
 * "Deschide în Transport" carries the scenario (UX review). The transport map reads the same
 * hash this map writes, so the link is the transport page plus the current hash, untouched.
 */
import { describe, expect, it } from 'vitest';

import { transportUrlFor } from '../src/app/links';
import { STRINGS } from '../src/i18n';

describe('transportUrlFor', () => {
  it('keeps the scenario hash', () => {
    expect(transportUrlFor('#x=8500&nmin=5&lang=en')).toBe('../transport/#x=8500&nmin=5&lang=en');
  });

  it('opens the default scenario without a hash', () => {
    expect(transportUrlFor('')).toBe('../transport/');
  });
});

describe('the button label', () => {
  it('exists in both languages', () => {
    expect(STRINGS.ro.openTransport).toBe('Deschide în Transport →');
    expect(STRINGS.en.openTransport).toBe('Open in Transport →');
  });
});

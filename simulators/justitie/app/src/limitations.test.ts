import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { lead, SEVERITY } from './limitations';

const files = ['portal-stats.json', 'portal-instante.json'].map(
  (name) =>
    JSON.parse(readFileSync(new URL(`../../data/${name}`, import.meta.url), 'utf8')) as {
      limitations: { id: string; text: string; severity: keyof typeof SEVERITY }[];
    },
);
const limitations = files.flatMap((file) => file.limitations);

describe('the limitations list', () => {
  it('names every severity in Romanian, never by its data key', () => {
    expect(Object.values(SEVERITY)).toEqual(['blocant', 'important', 'de reținut']);
    for (const limitation of limitations) expect(SEVERITY[limitation.severity]).toBeTruthy();
  });

  it('summarises a caveat by its own first sentence without rewording it', () => {
    for (const { text } of limitations) {
      const { head, rest } = lead(text);
      expect(head.length).toBeGreaterThan(0);
      expect(rest ? `${head} ${rest}` : head).toBe(text.replace(/^(.+?[.!?])\s+/su, '$1 '));
    }
  });

  it('splits at the end of the first sentence', () => {
    expect(lead('A apărea des nu înseamnă abuz. La o judecătorie, altfel.')).toEqual({
      head: 'A apărea des nu înseamnă abuz.',
      rest: 'La o judecătorie, altfel.',
    });
    expect(lead('O singură propoziție')).toEqual({ head: 'O singură propoziție', rest: '' });
  });
});

// The "Date: <sursă>, <an>" line under the H1 (UX-5). The strings are static, so the test pins
// the one fact that can drift: the local-finance year names the file main.ts actually fetches.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { STRINGS } from '../src/i18n';

const main = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const financeYear = /local-finance-(\d{4})\.json/.exec(main)?.[1];

describe('the data line under the H1', () => {
  it('follows the H1 in the markup', () => {
    expect(html).toMatch(/<h1 data-i18n="title"><\/h1>\s*<p class="data-line" data-i18n="dataLine">/);
  });

  it('names the census and the local-finance year the app fetches, in both languages', () => {
    expect(financeYear).toBeDefined();
    expect(STRINGS.ro.dataLine).toMatch(/^Date: INS, Recensământ 2021; .*\b2024\b/);
    expect(STRINGS.en.dataLine).toMatch(/^Data: INS, 2021 census; .*\b2024\b/);
    for (const lang of ['ro', 'en'] as const) expect(STRINGS[lang].dataLine).toContain(financeYear!);
  });
});

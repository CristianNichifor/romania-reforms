/**
 * The map paints every proposed unit in its own colour, and the legend explained every colour
 * but those (UX review). It also hid itself on phones, and the summary bar scrolled sideways
 * there, clipping its last statistic off the edge.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { STRINGS } from '../src/i18n';

const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8');
const main = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8');
const mobile = css.slice(css.indexOf('@media (max-width: 900px)'), css.indexOf('@media print'));

describe('the unit colour legend', () => {
  it('explains the unit colours in both languages', () => {
    expect(STRINGS.ro.legendUnits).toMatch(/unitate propusă/);
    expect(STRINGS.en.legendUnits).toMatch(/proposed unit/);
  });

  it('draws the palette as one swatch in the legend', () => {
    expect(main).toMatch(/swatch units.*PALETTE\.map/);
    expect(css).toMatch(/\.legend \.swatch\.units \{/);
  });

  it('is not hidden on phones', () => {
    expect(mobile).not.toMatch(/\.legend\s*\{\s*display:\s*none/);
  });
});

describe('the summary bar on phones', () => {
  it('wraps instead of scrolling', () => {
    const rule = mobile.slice(mobile.indexOf('.summary {'), mobile.indexOf('}', mobile.indexOf('.summary {')));
    expect(rule).toMatch(/flex-wrap:\s*wrap/);
    expect(rule).toMatch(/white-space:\s*normal/);
    expect(rule).not.toMatch(/overflow-x:\s*auto/);
  });
});

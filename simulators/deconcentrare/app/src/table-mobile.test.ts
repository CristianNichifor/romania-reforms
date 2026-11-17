/**
 * The seven-column families table clipped on phones and the last columns were lost (UX review,
 * 390 px). The region scrolls sideways with the family's name pinned, as in companii-stat.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const narrow = css.slice(css.lastIndexOf('@media (max-width: 900px)'));

describe('the families table on phones', () => {
  it('scrolls sideways inside its region', () => {
    expect(html).toMatch(/<div class="table-scroll" role="region"[^>]*tabindex="0"/);
    expect(css).toMatch(/\.table-scroll \{[^}]*overflow-x: auto/);
    expect(narrow).toMatch(/#families \.table-scroll table \{\s*width: max-content;\s*min-width: 100%;/);
  });

  it('pins the family name while the numbers scroll', () => {
    expect(narrow).toMatch(/th\[scope='row'\][^{]*\{[^}]*position: sticky;[^}]*left: 0;/);
  });

  it('keeps a visible focus ring on rows and controls', () => {
    expect(css).toMatch(/:focus-visible \{[^}]*outline: 2px solid/);
  });
});

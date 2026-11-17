/**
 * The localities table is wider than a phone; its value columns sat off-screen with nothing to
 * say so (UX review, 390 px). The locality stays pinned while the figures scroll.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');

describe('the localities table on phones', () => {
  it('pins the first column while the figures scroll', () => {
    expect(css).toMatch(/\.table-wrap tr > :first-child \{[^}]*position: sticky;[^}]*left: 0;[^}]*background: var\(--bg\);/);
  });

  it('shades the edge while there is more to the right', () => {
    expect(css).toMatch(/\.table-wrap \.civic-table-scroll \{[^}]*no-repeat local/);
  });

  it('gives the back link a 24 px target', () => {
    expect(css).toMatch(/\.up \{[^}]*min-height: 24px;/);
  });
});

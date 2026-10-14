/**
 * The eleven-column table clipped on phones and the numbers were the part lost (UX review).
 * The scroll region already exists; on narrow screens the table must be allowed to be wider
 * than it and the row heading must stay pinned, so a figure is read against its activity.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('./style.css', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const narrow = css.slice(css.indexOf('@media (max-width: 900px)'), css.indexOf('#caveat-list'));

describe('the clusters table on phones', () => {
  it('scrolls sideways inside its region', () => {
    expect(html).toMatch(/<div class="table-scroll" role="region"[^>]*tabindex="0"/);
    expect(css).toMatch(/\.table-scroll \{[^}]*overflow-x: auto/);
    expect(narrow).toMatch(/\.table-scroll table \{\s*width: max-content;\s*min-width: 100%;/);
  });

  it('pins the activity name while the numbers scroll', () => {
    expect(narrow).toMatch(/th\[scope='row'\][^{]*\{[^}]*position: sticky;[^}]*left: 0;/);
  });
});

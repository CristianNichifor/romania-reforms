// UX-38 (ux-guidelines § 2.5, § 9 item 8): the data table ends with the page's data line,
// filled from the same loaded document as the line under the H1.
import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const main = readFileSync(new URL('./main.ts', import.meta.url), 'utf8');

it('index.html puts the source line right under the family-table and main.ts fills it (UX-38)', () => {
  expect(html).toMatch(/<table id="family-table">[\s\S]*?<\/table>\s*<\/div>\s*<p class="table-source" id="table-source" hidden><\/p>/);
  expect(main).toMatch(/\$\('#table-source'\)\.textContent = dataLineFor\(doc\)/);
  expect(main).toMatch(/\$\('#data-line'\)\.textContent = dataLineFor\(doc\)/);
});

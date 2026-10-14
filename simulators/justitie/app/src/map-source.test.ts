// UX-36 (design criterion 6; ux-guidelines § 9 item 8): a source line sits at the end of the map
// legend and reads the same data line as the head of the page, both from the loaded document.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, it } from 'vitest';

const root = join(import.meta.dirname, '..');
const html = readFileSync(join(root, 'index.html'), 'utf8');
const main = readFileSync(join(root, 'src/main.ts'), 'utf8');

it('index.html ends the legend with the source line and main.ts fills it with the data line (UX-36)', () => {
  expect(html).toMatch(/<p class="map-source" id="map-source"><\/p>\s*<\/section>/);
  expect(html.indexOf('id="map-source"')).toBeGreaterThan(html.indexOf('<section class="legend">'));
  expect(main).toMatch(/el\('#map-source'\)\.textContent = dataLineFor\(doc\)/);
  expect(main).toMatch(/el\('#data-line'\)\.textContent = dataLineFor\(doc\)/);
});

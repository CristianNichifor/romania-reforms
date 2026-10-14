// UX-20 (design criterion 6): a source line sits under the map legend and reads the same data
// line as the head of the page.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, it } from 'vitest';

const root = join(import.meta.dirname, '..');
const html = readFileSync(join(root, 'index.html'), 'utf8');
const main = readFileSync(join(root, 'src/main.ts'), 'utf8');

it('index.html has the source line under the legend and main.ts fills it with the data line (UX-20)', () => {
  expect(html).toMatch(/<div id="map-legend" class="legend"><\/div>\s*<p class="map-source" id="map-source"><\/p>/);
  expect(html).toContain('href="/src/map-source.css"');
  expect(main).toMatch(/getElementById\('map-source'\)/);
  expect(main).toMatch(/mapSource\.textContent = dataLineFor\(code, guideYears\)/);
});

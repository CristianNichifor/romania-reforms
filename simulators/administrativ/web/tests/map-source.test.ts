// UX-20 (design criterion 6): a source line sits under the map legend and reads the same data
// line as the head of the page, in the reader's language.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, it } from 'vitest';

const root = join(import.meta.dirname, '..');
const html = readFileSync(join(root, 'index.html'), 'utf8');

it('index.html prints the data line under the legend (UX-20)', () => {
  expect(html).toMatch(/<div class="legend" id="legend"><\/div>\s*<p class="map-source"><span data-i18n="dataLine"><\/span><\/p>/);
  expect(html.match(/data-i18n="dataLine"/g)).toHaveLength(2);
});

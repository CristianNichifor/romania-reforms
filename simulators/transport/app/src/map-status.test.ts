/**
 * The map says it is loading, and says when it failed (UX review). The geometry is several
 * MB; until it lands the map is a dark rectangle, and the only sign of life was a small grey
 * line in the panel. Now a status sits over the map, is removed when the data is in, and
 * becomes the error when loading fails — so a blank map is never the whole message.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(import.meta.dirname, '..');
const html = readFileSync(join(root, 'index.html'), 'utf8');
const css = readFileSync(join(root, 'src/style.css'), 'utf8');
const main = readFileSync(join(root, 'src/main.ts'), 'utf8');

describe('the map status', () => {
  it('is announced over the map while loading', () => {
    expect(html).toMatch(/<div id="map-status" class="map-status" role="status">Se încarcă harta…<\/div>/);
    expect(css).toMatch(/\.map-status \{[^}]*grid-area: 1 \/ 1/);
  });

  it('is removed when the data has landed', () => {
    expect(main).toMatch(/getElementById\('map-status'\)\?\.remove\(\)/);
  });

  it('becomes the error when loading fails', () => {
    const fail = main.slice(main.indexOf('function fail('), main.indexOf('if (!webglAvailable())'));
    expect(fail).toMatch(/status\.classList\.add\('error'\)/);
    expect(css).toMatch(/\.map-status\.error/);
  });
});

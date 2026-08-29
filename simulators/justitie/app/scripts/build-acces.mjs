/**
 * Flatten the access figures into something the map can paint directly.
 *
 * `acces-2025.json` is keyed by SIRUTA and carries names and court labels — 580 KB of it. The
 * map needs one number per polygon, and the polygons are keyed by their index in the
 * administrative payload. So this joins the two once, at build time, and emits an array the
 * renderer can walk without a lookup table.
 *
 * Lazy on purpose: the commune outlines are 2,9 MB and only the access view needs them, so
 * neither this nor uats.geojson is fetched unless the reader asks for that view.
 */
import { readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, '../public/data');
mkdirSync(out, { recursive: true });

const acces = JSON.parse(
  readFileSync(resolve(here, '../../data/acces-2025.json'), 'utf8'),
);
const attributes = JSON.parse(
  readFileSync(
    resolve(here, '../../../administrativ/web/public/data/attributes.json'),
    'utf8',
  ),
);

const indexOf = new Map(attributes.siruta.map((code, i) => [code, i]));
const today = new Int32Array(attributes.siruta.length).fill(-1);
const byCounty = new Int32Array(attributes.siruta.length).fill(-1);
const nearest = new Int32Array(attributes.siruta.length).fill(-1);

let joined = 0;
for (const row of acces.communes) {
  const index = indexOf.get(row.siruta);
  if (index === undefined) continue;
  // -1 stays for the eleven communes with no road, so the map greys them rather than
  // painting them as if the distance were zero.
  today[index] = row.metresToday ?? -1;
  byCounty[index] = row.metresByCounty ?? -1;
  nearest[index] = row.metresNearest ?? -1;
  joined += 1;
}
if (joined !== acces.communes.length) {
  console.error(`only ${joined} of ${acces.communes.length} communes joined to a polygon`);
  process.exit(1);
}

writeFileSync(
  resolve(out, 'acces.json'),
  JSON.stringify({
    summary: acces.summary,
    limitations: acces.limitations,
    // -1 means no road, or a commune the arondare does not place.
    today: Array.from(today),
    byCounty: Array.from(byCounty),
    nearest: Array.from(nearest),
  }),
);
copyFileSync(
  resolve(here, '../../../administrativ/web/public/data/uats.geojson'),
  resolve(out, 'uats.geojson'),
);
console.log(`acces.json: ${joined.toLocaleString()} communes joined`);

// The page reads the pipeline's payload rather than importing it: the bundle stays small,
// and the numbers on screen are the same file the simulator's tests assert on, not a copy
// that could drift. The copy step doubles as the payload's build-time gate — a missing or
// empty document fails here, before a page with nothing to say could ship.
import { copyFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, '..');
const source = join(app, '..', 'data', 'companii-stat.json');
const out = join(app, 'public', 'data');
mkdirSync(out, { recursive: true });

if (!existsSync(source)) {
  console.error('FATAL: data/companii-stat.json is missing — run scripts/build_companii_stat.py first');
  process.exit(1);
}
copyFileSync(source, join(out, 'companii-stat.json'));

const doc = JSON.parse(readFileSync(source, 'utf8'));
if (!Array.isArray(doc.clusters) || doc.clusters.length === 0 || !doc.summary) {
  console.error('FATAL: companii-stat.json has no clusters or summary — the page would render empty');
  process.exit(1);
}
console.log(`data ready: ${doc.clusters.length} clusters, ${doc.summary.companies} companies`);

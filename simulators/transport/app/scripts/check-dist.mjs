// MapLibre 6 loads its GeoJSON worker as a separate file. If the bundler does not emit it the
// worker 404s, dies silently, and no source ever loads: a blank map with no exception and no
// map error. That shipped, so the build now refuses to finish without the worker present.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const assets = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'assets');
const files = readdirSync(assets);

const worker = files.find((f) => /maplibre-gl-worker.*\.js$/.test(f));
if (!worker) {
  console.error('FATAL: no maplibre worker in dist/assets — the map will not draw.');
  console.error('       present:', files.join(', '));
  process.exit(1);
}

// And the bundle must point at the emitted file rather than at maplibre's own default name,
// which is what it fell back to when setWorkerUrl was missing.
const bundle = files.filter((f) => f.startsWith('index-') && f.endsWith('.js'));
const text = bundle.map((f) => readFileSync(join(assets, f), 'utf8')).join('');
if (!text.includes(worker)) {
  console.error(`FATAL: bundle does not reference ${worker}; the worker URL is wrong.`);
  process.exit(1);
}
console.log(`dist ok: worker ${worker} emitted and referenced`);

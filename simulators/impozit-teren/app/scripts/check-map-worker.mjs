/**
 * The map's worker has to be a file that exists.
 *
 * maplibre does its geometry work off the main thread and, left alone, looks for that worker
 * next to its own module — which after bundling is a path nobody ever wrote a file to. The
 * result is not an error the page shows: the canvas comes up, the legend comes up, and
 * nothing is ever painted on it, because no source is ever parsed. It shipped that way once.
 *
 * So the build asserts the thing the browser will actually do: the bundle names a worker, and
 * that name is a file in `dist/`. A check on the source — "does map.ts call setWorkerUrl" —
 * would have passed the whole time the map was blank, because the call is not the claim. The
 * emitted file is.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const assets = join(import.meta.dirname, '..', 'dist', 'assets');
const files = readdirSync(assets);
const bundles = files.filter((name) => name.startsWith('index-') && name.endsWith('.js'));

const named = new Set();
for (const bundle of bundles) {
  const source = readFileSync(join(assets, bundle), 'utf8');
  for (const match of source.matchAll(/[\w./-]*maplibre-gl-worker[\w.-]*\.m?js/g)) {
    named.add(match[0]);
  }
}

// The reference maplibre falls back to when nobody hands it a URL. Its presence is harmless —
// it is dead code once setWorkerUrl has been called — but it is not evidence of anything, so
// it does not count as the worker being named.
const fallbacks = new Set(['maplibre-gl-worker.mjs', 'maplibre-gl-worker-dev.mjs']);
const emitted = [...named].filter((name) => !fallbacks.has(name));

if (emitted.length === 0) {
  console.error(
    'The bundle names no built worker. maplibre would fall back to resolving\n' +
      "'./maplibre-gl-worker.mjs' next to the bundle, which is not a file that exists, and the\n" +
      'map would render an empty canvas. Check that map.ts still imports the worker with\n' +
      "'?worker&url' and hands it to setWorkerUrl.",
  );
  process.exit(1);
}

const missing = emitted.filter((name) => !files.includes(name.split('/').pop()));
if (missing.length > 0) {
  console.error(`The bundle asks for a worker that was not emitted: ${missing.join(', ')}`);
  process.exit(1);
}

console.log(`harta: worker ${emitted.join(', ')} emitted.`);

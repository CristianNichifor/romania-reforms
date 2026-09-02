// The app draws files the pipeline writes. They are copied rather than imported so the
// bundle stays small and the map can fetch the heavy geometry only when it is needed.
//
// uats.geojson is 3 MB — larger than everything else on the page combined — so the join to
// it is precomputed here into a compact array indexed by polygon, rather than shipping the
// 680 KB access file and a lookup table to the browser.
import { mkdirSync, readFileSync, writeFileSync, copyFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, '..');
const sim = join(app, '..');
const administrativ = join(sim, '..', 'administrativ');
const out = join(app, 'public', 'data');
mkdirSync(out, { recursive: true });

for (const [from, name] of [
  [join(administrativ, 'web/public/data/uats.geojson'), 'uats.geojson'],
  [join(administrativ, 'web/public/data/counties.geojson'), 'counties.geojson'],
  [join(administrativ, 'web/public/data/attributes.json'), 'attributes.json'],
  // The road network the travel-time model is measured over. Same two files the
  // administrative map draws, copied rather than re-derived so the two pages cannot disagree
  // about where a road is. Fetched only when the reader asks for them: 6,5 MB together.
  [join(administrativ, 'web/public/data/roads.geojson'), 'roads.geojson'],
  [join(administrativ, 'web/public/data/roads-county.geojson'), 'roads-county.geojson'],

  // The administrative model's own payload. The map re-runs that model in the browser so it
  // can follow whatever scenario the reader built next door, rather than a preset frozen here.
  // Copied rather than fetched across apps: a cross-app relative fetch breaks in preview and
  // in any single-simulator build.
  [join(administrativ, 'web/public/data/manifest.json'), 'admin-manifest.json'],
  [join(administrativ, 'web/public/data/attributes.json'), 'admin-attributes.json'],
  [join(administrativ, 'web/public/data/attributes.bin'), 'admin-attributes.bin'],
  [join(administrativ, 'web/public/data/adjacency.bin'), 'admin-adjacency.bin'],
  [join(administrativ, 'web/public/data/candidacy.bin'), 'admin-candidacy.bin'],
]) {
  copyFileSync(from, join(out, name));
}

// The signed speed limits are OPTIONAL, and deliberately not committed: 5,7 MB of derived
// geometry against a repository already at 54 of its 60 MB ceiling, whose own size gate says
// the fix for that is to stop committing derived payloads rather than raise the limit. Build
// it with `uv run python -m scripts.export_speed_limits` and it appears; without it the
// toggle disables itself and says why. A missing optional file must never fail the build,
// because CI has no OSM extract and never will.
const speeds = join(sim, 'data/road-speeds.geojson');
if (existsSync(speeds)) {
  copyFileSync(speeds, join(out, 'road-speeds.geojson'));
  console.log('  road-speeds.geojson copied');
} else {
  console.log('  road-speeds.geojson absent — the speed-limit toggle will be disabled');
}

const access = JSON.parse(readFileSync(join(sim, 'data/access.json'), 'utf8'));
const cost = JSON.parse(readFileSync(join(sim, 'data/cost.json'), 'utf8'));
const hubs = JSON.parse(readFileSync(join(sim, 'data/hubs.json'), 'utf8'));
const railnet = JSON.parse(readFileSync(join(sim, 'data/railnet.json'), 'utf8'));
const railCost = JSON.parse(readFileSync(join(sim, 'data/rail-cost.json'), 'utf8'));
const fares = JSON.parse(readFileSync(join(sim, 'data/fares.json'), 'utf8'));

// The track and its stations. Copied rather than joined to anything: rail is its own layer,
// and the whole point of the station geometry is that it does NOT line up with the settlements.
// The road-time graph: both endpoints and the seconds for each of the 9.281 edges. This is
// what lets the browser route a scenario nobody precomputed.
// cost-inputs travels with them: the browser now prices the reader's own network, and the
// prices must be the same file the pipeline argues from, not a copy of its numbers.
for (const name of ['rail-lines.geojson', 'rail-stations.geojson', 'road-time.bin', 'road-time.json', 'cost-inputs.json', 'rail-access.bin']) {
  copyFileSync(join(sim, 'data', name), join(out, name));
}

// Summary only — the panel needs the headline numbers, not every route.
writeFileSync(
  join(out, 'summary.json'),
  JSON.stringify({
    access: access.summary,
    cost: { annualRon: cost.annualRon, fleet: cost.fleet, perWeekday: cost.perWeekday },
    ledger: cost.ledgerRon,
    scenario: hubs.scenario,
    hubs: hubs.summary,
    rail: {
      network: railnet.network,
      seats: railnet.seats,
      pairs: railnet.pairs,
      conditions: railnet.conditions,
      rehabilitation: railCost.rehabilitation,
      againstPulsing: railCost.againstPulsing,
      reference: railCost.reference,
    },
    fares: {
      central: fares.central,
      band: fares.band,
      benchmark: fares.benchmark,
      // The browser reprices the reader's own network, so it needs the assumption itself and
      // not only the result the pipeline reached with it.
      assumedLoadFactor: fares.assumptions.loadFactor,
    },
    // The service standard the browser needs to turn road time into service time. Free-flow
    // road time is not a timetable: the pipeline divides by this factor and the map must too,
    // or every commune reads about a quarter closer to its centre than it is.
    serviceSpeedFactor: JSON.parse(readFileSync(join(sim, 'data/cost-inputs.json'), 'utf8'))
      .items.serviceSpeedFactor.value,
    limitations: [
      ...access.limitations,
      ...cost.limitations,
      ...railCost.limitations,
      ...fares.limitations,
    ],
  }),
);

// One row per polygon, in the geojson's own order: [uncoordinated, pulsed] minutes.
//
// uats.geojson carries no properties at all — it is geometry, and administrativ keys it by
// position against the parallel arrays in attributes.json. Joining on a `siruta` property
// silently matches nothing, which is why the guard below is fatal rather than a warning.
const attributes = JSON.parse(readFileSync(join(out, 'attributes.json'), 'utf8'));
const by = new Map(access.uats.map((u) => [String(u.siruta), u]));
const joined = attributes.siruta.map((siruta) => {
  const u = by.get(String(siruta));
  return u ? [u.uncoordinatedMin, u.pulsedMin] : null;
});
writeFileSync(join(out, 'journey.json'), JSON.stringify(joined));

// scenarios.json is gone. The page reads the reader's administrative scenario from the URL
// and recomputes the network, so five presets frozen at build time are not an alternative
// to that — they are a second answer to a question this app no longer asks.

const geo = JSON.parse(readFileSync(join(out, 'uats.geojson'), 'utf8'));
if (attributes.siruta.length !== geo.features.length) {
  console.error('FATAL: attributes and geometry are different lengths — the index join is invalid');
  process.exit(1);
}
const matched = joined.filter(Boolean).length;
console.log(`data ready: ${matched}/${geo.features.length} polygons joined to a journey time`);
if (matched < geo.features.length * 0.9) {
  console.error('FATAL: most polygons did not join — the siruta key is wrong');
  process.exit(1);
}

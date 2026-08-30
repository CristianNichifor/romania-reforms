// The app draws files the pipeline writes. They are copied rather than imported so the
// bundle stays small and the map can fetch the heavy geometry only when it is needed.
//
// uats.geojson is 3 MB — larger than everything else on the page combined — so the join to
// it is precomputed here into a compact array indexed by polygon, rather than shipping the
// 680 KB access file and a lookup table to the browser.
import { mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
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
]) {
  copyFileSync(from, join(out, name));
}

const access = JSON.parse(readFileSync(join(sim, 'data/access.json'), 'utf8'));
const sweep = JSON.parse(readFileSync(join(sim, 'data/scenarios.json'), 'utf8'));
const cost = JSON.parse(readFileSync(join(sim, 'data/cost.json'), 'utf8'));
const hubs = JSON.parse(readFileSync(join(sim, 'data/hubs.json'), 'utf8'));
const railnet = JSON.parse(readFileSync(join(sim, 'data/railnet.json'), 'utf8'));
const railCost = JSON.parse(readFileSync(join(sim, 'data/rail-cost.json'), 'utf8'));
const fares = JSON.parse(readFileSync(join(sim, 'data/fares.json'), 'utf8'));

// The track and its stations. Copied rather than joined to anything: rail is its own layer,
// and the whole point of the station geometry is that it does NOT line up with the settlements.
for (const name of ['rail-lines.geojson', 'rail-stations.geojson']) {
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
    fares: { central: fares.central, band: fares.band, benchmark: fares.benchmark },
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

// One array per consolidation scenario, aligned the same way. This is what lets the map show
// that consolidating harder makes the journey *shorter* — a result that reads as a mistake in
// a table and as an obvious fact on a map.
writeFileSync(
  join(out, 'scenarios.json'),
  JSON.stringify(
    sweep.scenarios.map((s) => {
      const { journeyByUat, ...stats } = s;
      return {
        ...stats,
        journey: attributes.siruta.map((siruta) => journeyByUat[String(siruta)] ?? null),
      };
    }),
  ),
);

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

/**
 * Copy what the page computes from into public/, at build time.
 *
 * The page does not read a finished answer. It reads the inputs — hectares by category, the
 * notaries' prices, the Fiscal Code's tables — and redoes the arithmetic as the reader moves
 * the assumptions. That is the point of the simulator: the assumptions move the answer more
 * than the data does, so a reader who cannot move them is being shown a conclusion.
 *
 * Copied at build time rather than committed, so there is one copy of each file in the
 * repository and it is the one the importers write.
 *
 * **Which counties, and which year, are discovered rather than listed.** A hand-kept list
 * meant a county could be built and still not reach the page, and a hard-coded 2026 meant a
 * county whose chamber published no 2026 study could not reach it at all — Prahova,
 * Dâmbovița and Vrancea are 2025 documents sitting beside nine that are not. So a county is
 * in the app if and only if `data/` holds both halves of it, and the year comes off the file
 * that is there. The app asks for a county; deciding which edition that is belongs here.
 *
 * The year is dropped from the copied name. `valoare-teren-ph-2025.json` is served as
 * `valoare-ph.json`, and the edition survives inside the file, in `period` and in its
 * provenance, which is where a reader looking for it will be.
 *
 * Stale copies are deleted rather than left. This directory is generated and ignored by git,
 * so anything in it that no longer has a dataset behind it is a file from an older build —
 * including, at one point, a county whose parse this repository had rejected.
 */
import { copyFileSync, mkdirSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const data = resolve(here, '../../data');
const out = resolve(here, '../public/data');
mkdirSync(out, { recursive: true });

/**
 * The newest file per county for one dataset family, keyed by county code.
 *
 * One-or-two letters, not two. București's code is a single "B", and a pattern that assumed
 * two silently left the country's most valuable county out of the app while every gate
 * upstream passed — the data was built, validated and tested, and simply never copied.
 */
const editions = (prefix) => {
  const found = new Map();
  for (const name of readdirSync(data).sort()) {
    const match = new RegExp(`^${prefix}-([a-z]{1,2})-\\d{4}\\.json$`).exec(name);
    if (match) found.set(match[1], name);
  }
  return found;
};

const values = editions('valoare-teren');
const taxes = editions('impozit');
// Both halves or neither: a county with a value dataset and no tax dataset would render as a
// blank comparison rather than as a county that is not ready.
const counties = [...values.keys()].filter((county) => taxes.has(county)).sort();

if (counties.length === 0) {
  console.error(
    'no county has both a value and a tax dataset\n' +
      'Run the importers and builders from the repository root:\n' +
      '  uv run python simulators/impozit-teren/scripts/import_fond_funciar.py --all\n' +
      '  uv run python simulators/impozit-teren/scripts/import_ghid.py --chamber bacau\n' +
      '  uv run python simulators/impozit-teren/scripts/import_cod_fiscal.py\n' +
      '  uv run python simulators/impozit-teren/scripts/build_valoare_teren.py --county BC\n' +
      '  uv run python simulators/impozit-teren/scripts/build_impozit.py --county BC',
  );
  process.exit(1);
}

// The map's shapes travel with the data. They are static — geometry and a SIRUTA — because
// the page colours them from the same arithmetic it prints, so a value baked in here would
// freeze at whatever the assumptions were when it was built.
const sources = [
  ['cod-fiscal-teren-2026.json', 'cod-fiscal.json'],
  ['harta-uat.geojson', 'harta-uat.geojson'],
  ['harta-judete.geojson', 'harta-judete.geojson'],
  // County polygons and the national estimate travel together: neither is any use without
  // the other. The polygons are the only geometry the nineteen unread counties have, and the
  // estimate is the only value they have.
  ['harta-judete-poligon.geojson', 'harta-judete-poligon.geojson'],
  ['valoare-nationala-2026.json', 'national.json'],
  // What each commune actually spends. The only file here that is not about land: it is the
  // denominator the third map metric divides by, and the one number that turns "this land is
  // worth X" into "that would pay for Y% of what this place does".
  ['buget-uat-2025.json', 'buget-uat-2025.json'],
];
for (const county of counties) {
  sources.push([values.get(county), `valoare-${county}.json`]);
  sources.push([taxes.get(county), `impozit-${county}.json`]);
}

const wanted = new Set(['manifest.json', ...sources.map(([, name]) => name)]);
for (const [from, name] of sources) {
  copyFileSync(resolve(data, from), resolve(out, name));
  console.log(`copied ${name}`);
}
for (const name of readdirSync(out)) {
  if (name.endsWith('.json') && !wanted.has(name)) {
    rmSync(resolve(out, name));
    console.log(`removed stale ${name}`);
  }
}

writeFileSync(resolve(out, 'manifest.json'), JSON.stringify({ counties }, null, 2));
console.log(`wrote manifest.json (${counties.length} counties: ${counties.join(' ')})`);

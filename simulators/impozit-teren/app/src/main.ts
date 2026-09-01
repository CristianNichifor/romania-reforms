/**
 * The page. Reads the inputs, recomputes both taxes, and renders the band.
 *
 * The scenario is the URL: every control writes to `location.hash`, so a reading of this
 * argument is a link somebody can paste into the argument. That is the whole point of these
 * simulators, and it is why the hash is restored on load rather than defaulted.
 */
import 'maplibre-gl/dist/maplibre-gl.css';

import { ValueMap, legend } from './map';
import { evaluate } from './model';
import type { BandKey, FiscalCode, Locality, Settings } from './model';

type ValueFile = {
  counties: string[];
  localities: Locality[];
  limitations: Array<{ id: string; text: string; severity: string }>;
  provenance: { locator: string };
};
type TaxFile = {
  assumptions: {
    ronPerEur: number;
    exchangeRateDate: string;
    agriculturalYieldPercent: { low: number; central: number; high: number } | null;
    agriculturalYieldSource: string | null;
    yieldByCategoryPercent: Record<string, { low: number; central: number; high: number }>;
    builtYieldPercent?: { low: number; central: number; high: number };
    builtYieldSource?: string;
  };
  limitations: Array<{ id: string; text: string; severity: string }>;
};

const base = import.meta.env.BASE_URL;
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const money = new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 });
const percent = new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Millions or billions, because a county's land is a ten-digit number of lei. */
function scaled(ron: number): string {
  if (Math.abs(ron) >= 1e9) return `${percent.format(ron / 1e9)} mld`;
  if (Math.abs(ron) >= 1e6) return `${percent.format(ron / 1e6)} mil`;
  return money.format(ron);
}

type State = {
  county: string;
  rate: number;
  share: number;
  value: BandKey;
  fiscal: BandKey;
  landYield: number;
  sort: 'delta' | 'value' | 'name';
};

const DEFAULTS: State = {
  county: 'bc',
  rate: 1,
  share: 1,
  value: 'central',
  fiscal: 'central',
  // The built-land yield the page opens on. Not 5% any more: that was an assumption anchored
  // on the residential market, and randament-teren-construit-2026.json derives 2,53% from an
  // identity whose other terms are published. This literal is only the value before the data
  // arrives — `adoptDerivedYield` replaces it with whatever the county's file actually carries,
  // so the browser cannot drift from the Python that produced the numbers beside it.
  landYield: 2.53,
  sort: 'delta',
};

/** Whether the URL pinned a yield. If it did, the file must not overrule the reader. */
let yieldFromUrl = false;

function readHash(): State {
  const params = new URLSearchParams(location.hash.slice(1));
  const number = (key: string, fallback: number) => {
    const value = Number(params.get(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  const band = (key: string, fallback: BandKey): BandKey => {
    const value = params.get(key);
    return value === 'low' || value === 'central' || value === 'high' ? value : fallback;
  };
  yieldFromUrl = Number(params.get('randament')) > 0;
  const sort = params.get('sort');
  return {
    county: params.get('j') ?? DEFAULTS.county,
    rate: number('cota', DEFAULTS.rate),
    share: number('intravilan', DEFAULTS.share),
    value: band('pret', DEFAULTS.value),
    fiscal: band('cod', DEFAULTS.fiscal),
    landYield: number('randament', DEFAULTS.landYield),
    sort: sort === 'value' || sort === 'name' ? sort : DEFAULTS.sort,
  };
}

function writeHash(state: State): void {
  const params = new URLSearchParams();
  params.set('j', state.county);
  params.set('cota', String(state.rate));
  params.set('intravilan', String(state.share));
  params.set('pret', state.value);
  params.set('cod', state.fiscal);
  params.set('randament', String(state.landYield));
  params.set('sort', state.sort);
  history.replaceState(null, '', `#${params}`);
}

// All forty-two, not only the built ones. The list used to hold eight and a county added to
// the data showed up in the selector as its own two-letter code.
const COUNTY_NAMES: Record<string, string> = {
  ab: 'Alba', ag: 'Argeș', ar: 'Arad', b: 'București', bc: 'Bacău', bh: 'Bihor',
  bn: 'Bistrița-Năsăud', br: 'Brăila', bt: 'Botoșani', bv: 'Brașov', bz: 'Buzău',
  cj: 'Cluj', cl: 'Călărași', cs: 'Caraș-Severin', ct: 'Constanța', cv: 'Covasna',
  db: 'Dâmbovița', dj: 'Dolj', gj: 'Gorj', gl: 'Galați', gr: 'Giurgiu', hd: 'Hunedoara',
  hr: 'Harghita', if: 'Ilfov', il: 'Ialomița', is: 'Iași', mh: 'Mehedinți', mm: 'Maramureș',
  ms: 'Mureș', nt: 'Neamț', ot: 'Olt', ph: 'Prahova', sb: 'Sibiu', sj: 'Sălaj',
  sm: 'Satu Mare', sv: 'Suceava', tl: 'Tulcea', tm: 'Timiș', tr: 'Teleorman',
  vl: 'Vâlcea', vn: 'Vrancea', vs: 'Vaslui',
};

async function load(county: string) {
  const [value, tax] = await Promise.all([
    fetch(`${base}data/valoare-${county}.json`).then((r) => r.json() as Promise<ValueFile>),
    fetch(`${base}data/impozit-${county}.json`).then((r) => r.json() as Promise<TaxFile>),
  ]);
  return { value, tax };
}

/**
 * The one figure on this page that is about the country rather than a county.
 *
 * Written once, on load, and never re-rendered by the controls. That is not laziness: the
 * estimate for the unread counties was fitted on the read ones at the
 * assumptions of the build, and letting a slider rescale it would imply a refit that has not
 * happened. What the reader moves is the measured half; the estimated half is a published
 * number with a published error, and it stays put.
 */
async function renderNational(): Promise<void> {
  const national = await fetch(`${base}data/national.json`)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  if (!national) return;
  const { summary, assumptions } = national;
  const excluded = national.counties_valued
    .filter((r: { basis: string }) => r.basis === 'excluded')
    .map((r: { county: string }) => r.county);
  const mld = (eur: number) => `${percent.format(eur / 1e9)} mld`;
  $('national').innerHTML = `
    <div class="card-head"><h2>Cât valorează tot pământul din România</h2></div>
    <div class="stat-row">
      <div class="stat">
        <div class="stat-label">Valoarea terenului, fără București și Ilfov</div>
        <div class="stat-value accent">${mld(summary.landValueEur.central)}<span class="unit">EUR</span></div>
        <p class="note">
          între ${mld(summary.landValueEur.low)} și ${mld(summary.landValueEur.high)} —
          o bandă care este eroarea măsurată a modelului, nu o presupunere
        </p>
      </div>
      <div class="stat">
        <div class="stat-label">Din care citit din grile notariale</div>
        <div class="stat-value">${percent.format(100 * summary.measuredShareOfValue)}<span class="unit">%</span></div>
        <p class="note">
          ${summary.measuredCounties} județe citite, ${summary.predictedCounties} estimate,
          ${summary.excludedCounties} lăsate în afară (${excluded.join(' și ')})
        </p>
      </div>
      <div class="stat">
        <div class="stat-label">Cât greșește modelul un județ pe care nu l-a văzut</div>
        <div class="stat-value">×${percent.format(assumptions.builtLeaveOneOutErrorFactor)}</div>
        <p class="note">
          teren construit prezis din populația celui mai mare oraș, R²
          ${percent.format(assumptions.builtR2)}. Cota construită a județului dă R² 0,04 și
          regiunea de dezvoltare e mai slabă decât nicio variabilă — de aceea nu sunt folosite.
        </p>
      </div>
    </div>
    <p class="limit blocking">
      Bucureștiul lipsește din total. Cel mai mare oraș din eșantionul pe care s-a estimat
      modelul are 390&nbsp;000 de locuitori, Bucureștiul are 2,14 milioane; o extrapolare de
      cinci ori peste interval nu ar fi o estimare. Cum acolo e cel mai scump teren din țară,
      cifra de mai sus este o subestimare a României întregi.
    </p>`;
}

async function main() {
  const code: FiscalCode = await fetch(`${base}data/cod-fiscal.json`).then((r) => r.json());
  const manifest: { counties: string[] } = await fetch(`${base}data/manifest.json`).then((r) =>
    r.json(),
  );

  let state = readHash();
  if (!manifest.counties.includes(state.county)) state.county = DEFAULTS.county;
  let loaded = await load(state.county);

  // The map covers every built county, not the selected one, so it needs all of them. Fetched
  // after the first paint rather than before it: the page is useful the moment the selected
  // county is in, and the other thirteen are a background cost the reader should not wait on.
  const valueMap = new ValueMap('map', base);
  $('map-legend').innerHTML = legend((v) => `${Math.round(v / 1000)}k`);
  void (async () => {
    for (const county of manifest.counties) {
      const data = county === state.county ? loaded : await load(county);
      valueMap.load(county, data as never);
    }
  })();

  $('counties').innerHTML = manifest.counties
    .map((c) => `<button data-county="${c}">${COUNTY_NAMES[c] ?? c.toUpperCase()}</button>`)
    .join('');

  /**
   * The measured farmland yield for the county on screen.
   *
   * Read from the tax file rather than held as a constant here, because it is county-specific
   * and because a constant in the browser is exactly what the parity test cannot check. Falls
   * back to the building-land control only if the survey was never imported, which leaves the
   * page doing what it did before the split rather than inventing a figure.
   */
  function agriculturalYield(): number {
    return loaded.tax.assumptions.agriculturalYieldPercent?.central ?? state.landYield;
  }

  /**
   * Take the built-land yield from the data rather than from a literal in this file.
   *
   * The figure is derived, not chosen, and the derivation lives in Python. Hard-coding it here
   * too would create the one bug the parity test cannot see: two copies of a number that are
   * equal today and silently unequal after the next rebuild. A reader who pinned `randament`
   * in the URL keeps their own value — the slider is the whole point of having one.
   */
  function adoptDerivedYield(): void {
    const derived = loaded.tax.assumptions.builtYieldPercent?.central;
    if (!yieldFromUrl && typeof derived === 'number' && derived > 0) {
      state.landYield = derived;
    }
  }

  function render() {
    const settings: Settings = {
      share: state.share,
      value: state.value,
      fiscal: state.fiscal,
      rate: state.rate,
      landYield: state.landYield,
      landYieldAgricultural: agriculturalYield(),
      landYieldByCategory: Object.fromEntries(
        Object.entries(loaded.tax.assumptions.yieldByCategoryPercent ?? {}).map(
          ([code, band]) => [code, band.central],
        ),
      ),
      ronPerEur: loaded.tax.assumptions.ronPerEur,
    };
    const { rows, totals } = evaluate(loaded.value.localities, code, settings);
    // Same settings object the totals came from, so the colours and the figures cannot
    // disagree; the map substitutes each county's own rate and yields on top of it.
    valueMap.paint(settings, code);

    for (const button of document.querySelectorAll<HTMLButtonElement>('#counties button')) {
      button.classList.toggle('on', button.dataset.county === state.county);
    }
    for (const [id, current] of [
      ['value-band', state.value],
      ['fiscal-band', state.fiscal],
    ] as const) {
      for (const button of document.querySelectorAll<HTMLButtonElement>(`#${id} button`)) {
        button.classList.toggle('on', button.dataset.band === current);
      }
    }
    for (const button of document.querySelectorAll<HTMLButtonElement>('#sort button')) {
      button.classList.toggle('on', button.dataset.sort === state.sort);
    }
    ($('rate') as HTMLInputElement).value = String(Math.round(state.rate * 100));
    ($('share') as HTMLInputElement).value = String(Math.round(state.share * 100));
    ($('yield') as HTMLInputElement).value = String(Math.round(state.landYield * 100));
    $('yield-value').textContent = `${percent.format(state.landYield)}%`;
    $('rate-value').textContent = `${percent.format(state.rate)}%`;
    $('share-value').textContent = `×${percent.format(state.share)}`;

    const neutral = totals.neutral;
    const direction = totals.lvt >= totals.fiscal ? 'more' : 'less';
    $('headline').innerHTML = `
      <div class="stat">
        <div class="stat-label">Impozitul de azi, Codul fiscal</div>
        <div class="stat-value">${scaled(totals.fiscal)} <span class="unit">lei</span></div>
      </div>
      <div class="stat">
        <div class="stat-label">Impozit pe valoare, la ${percent.format(state.rate)}%</div>
        <div class="stat-value ${direction}">${scaled(totals.lvt)} <span class="unit">lei</span></div>
      </div>
      <div class="stat">
        <div class="stat-label">Din renta funciară, ia azi</div>
        <div class="stat-value">${percent.format(totals.fiscalCapture)}<span class="unit">%</span></div>
        <p class="note">din ${scaled(totals.rent)} lei pe an pe care îi produce pământul</p>
      </div>
      <div class="stat">
        <div class="stat-label">Din renta funciară, ar lua impozitul pe valoare</div>
        <div class="stat-value ${direction}">${percent.format(totals.lvtCapture)}<span class="unit">%</span></div>
        <p class="note">
          un impozit care ia toată renta ar fi o cotă pe valoare de
          ${percent.format(totals.value ? (100 * totals.rent) / totals.value : 0)}% —
          amestecul dintre ${percent.format(state.landYield)}% pe terenul de sub clădiri și
          ${percent.format(agriculturalYield())}% măsurat pe terenul agricol
        </p>
      </div>
      <div class="stat wide">
        <div class="stat-label">Cota care ar aduce exact aceiași bani</div>
        <div class="stat-value accent">${percent.format(neutral)}<span class="unit">%</span></div>
        <p class="note">
          din valoarea terenului, ${scaled(totals.value)} lei. Sub această cotă impozitul pe
          valoare aduce mai puțin decât azi, peste ea mai mult.
        </p>
      </div>`;

    const sorted = [...rows].sort((a, b) => {
      if (state.sort === 'name') return a.name.localeCompare(b.name, 'ro');
      if (state.sort === 'value') return b.landValueRon - a.landValueRon;
      return b.deltaRon - a.deltaRon;
    });
    $('table-title').textContent = `${sorted.length} localități din județul ${
      COUNTY_NAMES[state.county] ?? state.county
    }`;
    $('rows').innerHTML = sorted
      .map(
        (row) => `<tr>
          <td>${row.name}<span class="rank">${
            row.rank === 'municipii' ? 'municipiu' : row.rank === 'orase' ? 'oraș' : 'comună'
          }</span></td>
          <td class="num">${money.format(Math.round(row.intravilanHa))} ha</td>
          <td class="num">${scaled(row.landValueRon)}</td>
          <td class="num">${scaled(row.fiscalCodeRon)}</td>
          <td class="num">${scaled(row.lvtRon)}</td>
          <td class="num ${row.deltaRon >= 0 ? 'more' : 'less'}">${
            row.deltaRon >= 0 ? '+' : '−'
          }${scaled(Math.abs(row.deltaRon))}</td>
        </tr>`,
      )
      .join('');

    // The caveats travel with the data rather than living in a footnote, so the page shows
    // exactly the ones its own numbers carry, blocking first.
    const limits = [...loaded.value.limitations, ...loaded.tax.limitations];
    const order = { blocking: 0, material: 1, note: 2 } as Record<string, number>;
    limits.sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
    $('limits-count').textContent = `${limits.length}`;
    $('limits').innerHTML = limits
      .map(
        (limit) =>
          `<p class="limit ${limit.severity}"><span class="sev">${limit.severity}</span>${limit.text}</p>`,
      )
      .join('');
    $('sources').textContent = `Sursele: ${loaded.value.provenance.locator}. Curs BCE din ${loaded.tax.assumptions.exchangeRateDate}.`;

    writeHash(state);
  }

  function update(next: Partial<State>) {
    state = { ...state, ...next };
    render();
  }

  $('rate').addEventListener('input', (event) =>
    update({ rate: Number((event.target as HTMLInputElement).value) / 100 }),
  );
  $('share').addEventListener('input', (event) =>
    update({ share: Number((event.target as HTMLInputElement).value) / 100 }),
  );
  $('yield').addEventListener('input', (event) =>
    update({ landYield: Number((event.target as HTMLInputElement).value) / 100 }),
  );
  for (const [id, key] of [
    ['value-band', 'value'],
    ['fiscal-band', 'fiscal'],
  ] as const) {
    $(id).addEventListener('click', (event) => {
      const band = (event.target as HTMLElement).dataset.band as BandKey | undefined;
      if (band) update({ [key]: band } as Partial<State>);
    });
  }
  $('sort').addEventListener('click', (event) => {
    const sort = (event.target as HTMLElement).dataset.sort as State['sort'] | undefined;
    if (sort) update({ sort });
  });
  $('counties').addEventListener('click', async (event) => {
    const county = (event.target as HTMLElement).dataset.county;
    if (!county || county === state.county) return;
    loaded = await load(county);
    adoptDerivedYield();
    update({ county });
  });

  adoptDerivedYield();
  render();
  void renderNational();
}

main().catch((error) => {
  $('headline').innerHTML = `<p class="limit blocking">Datele nu s-au încărcat: ${error}</p>`;
});

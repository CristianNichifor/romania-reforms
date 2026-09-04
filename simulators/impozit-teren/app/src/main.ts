/**
 * The page. Reads the inputs, recomputes both taxes, and renders the band.
 *
 * The scenario is the URL: every control writes to `location.hash`, so a reading of this
 * argument is a link somebody can paste into the argument. That is the whole point of these
 * simulators, and it is why the hash is restored on load rather than defaulted.
 */
import 'maplibre-gl/dist/maplibre-gl.css';

import { ValueMap, legend } from './map';
import type { Metric } from './map';
import { combine, evaluate } from './model';
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
  // The measured half. `collectedRon` is what the county actually banked under the revenue
  // classification, and it is null when the execution filings have not been imported — the
  // page has to render either way, so the type says so rather than the code assuming.
  summary: {
    collectedRon: number | null;
    collectedPeriod: string | null;
  };
  limitations: Array<{ id: string; text: string; severity: string }>;
};
/**
 * What the economy produced, so a levy in lei can be said as a share of it.
 *
 * Two series rather than one, because the page has two scopes and they need different
 * denominators: with every county selected the country's output is the right divisor, and with
 * one county selected the country's output would understate that county's tax by a factor of
 * thirty. Eurostat publishes both, and the county series is a year shorter than the national
 * one, which is why the year list is rebuilt per scope instead of being written once.
 */
type GdpYear = { year: number; gdpMron: number; gdpMeur: number };
type Gdp = {
  assumptions: { fromYear: number; nationalLatestYear: number; countyLatestYear: number };
  series: GdpYear[];
  regions: Array<{ county: string; name: string; series: GdpYear[] }>;
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
  /** Share of the tax on private land that is collected, 0 to 1. */
  collection: number;
  sort: 'delta' | 'value' | 'name';
  /** Which number the map colours by. */
  metric: Metric;
  /**
   * Which year's GDP the tax is compared against. Zero means "whichever is the most recent one
   * the data has", which is what a reader who never touched the control wants and what a link
   * written before the next annual release should keep meaning.
   */
  gdpYear: number;
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
  // Neutral, like the market multiple in build_renta.py. No collection rate is published per
  // locality, so the page opens on "all of it" and says so rather than opening on a guess.
  collection: 1,
  sort: 'delta',
  // Price, not size. The whole-commune total is mostly a map of how big communes are, which
  // is a thing an atlas already says; the price of a hectare is the thing this file measures.
  metric: 'perHa',
  gdpYear: 0,
};

/** Whether the URL pinned a yield. If it did, the file must not overrule the reader. */
let yieldFromUrl = false;

function readHash(): State {
  const params = new URLSearchParams(location.hash.slice(1));
  const number = (key: string, fallback: number) => {
    const value = Number(params.get(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  // Zero is a rate somebody may want to look at — it is the "what does the Fiscal Code raise
  // on its own" reading — and `number` above cannot express it, because for every other
  // control zero means "absent". So the rate gets its own reader rather than the shared one
  // silently turning a deliberate 0 back into 1%.
  const rateFrom = (key: string, fallback: number) => {
    const raw = params.get(key);
    const value = Number(raw);
    return raw !== null && Number.isFinite(value) && value >= 0 ? value : fallback;
  };
  const band = (key: string, fallback: BandKey): BandKey => {
    const value = params.get(key);
    return value === 'low' || value === 'central' || value === 'high' ? value : fallback;
  };
  yieldFromUrl = Number(params.get('randament')) > 0;
  const sort = params.get('sort');
  const metric = params.get('harta');
  return {
    metric:
      metric === 'total' || metric === 'autofinantare' ? metric : DEFAULTS.metric,
    county: params.get('j') ?? DEFAULTS.county,
    rate: rateFrom('cota', DEFAULTS.rate),
    gdpYear: Math.round(number('pib', DEFAULTS.gdpYear)),
    share: number('intravilan', DEFAULTS.share),
    value: band('pret', DEFAULTS.value),
    fiscal: band('cod', DEFAULTS.fiscal),
    landYield: number('randament', DEFAULTS.landYield),
    collection: Math.min(1, number('colectare', DEFAULTS.collection)),
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
  params.set('colectare', String(state.collection));
  params.set('sort', state.sort);
  params.set('harta', state.metric);
  if (state.gdpYear) params.set('pib', String(state.gdpYear));
  history.replaceState(null, '', `#${params}`);
}

// All forty-two, not only the built ones. The list used to hold eight and a county added to
// the data showed up in the selector as its own two-letter code.
/**
 * The whole country, as a selectable "county".
 *
 * A sentinel rather than a separate control, because it answers the same question the county
 * selector answers and belongs in the same place. It is `toate` in the URL, so a link to the
 * national reading is as shareable as a link to Bacău's.
 */
const ALL = 'toate';

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

type Loaded = { value: ValueFile; tax: TaxFile };

async function load(county: string): Promise<Loaded> {
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

  // Written against the file rather than against what was true when this was first written.
  // Every sentence here was once a statement about a gap — București missing, nineteen counties
  // estimated — and each stopped being true as a chamber's study was read. The page now says
  // what the numbers say, and goes back to saying the other thing if a chamber stops
  // publishing.
  // The outside check and the bias list. Both directions are rendered, because every one of
  // these was already a limitation somewhere and no page had ever added them up — a reader
  // could meet four separate caveats and never learn that two of them push the other way.
  // The second total: the headline plus the hectares no study priced, valued at the national
  // transfer price. Rendered under the headline rather than as its own stat, because it is the
  // same quantity measured a second way and putting it in a separate box invites reading it as
  // a separate finding.
  const filled = summary.filledGaps as {
    landValueEur: { low: number; central: number; high: number };
    addedEur: { central: number };
    addedSharePercent: number;
  } | null;

  const plausibility = summary.plausibility as {
    thisSimulatorLandOverGdp: number;
    groups: Record<string, { countries: number; medianLandOverGdp: number; impliedRomaniaEur: number }>;
    movesItUp: Array<{ id: string; text: string; measured: number | null }>;
    movesItDown: Array<{ id: string; text: string; measured: number | null }>;
  } | null;

  const predicted = summary.predictedCounties as number;
  const missing = summary.excludedCounties as number;
  const whole = predicted === 0 && missing === 0;

  // "Toată țara" is a claim, and the reader has no way to check it from a percentage. Naming
  // the capital is the difference between a total that is right and a total that reads right:
  // București is 16% of it, and a page that never says so invites exactly the suspicion that
  // it was left out.
  const coverage = [
    `${summary.measuredCounties} de județe citite, București și Ilfov incluse`,
    predicted ? `${predicted} estimate` : '',
    missing ? `${missing} lăsate în afară (${excluded.join(' și ')})` : '',
  ]
    .filter(Boolean)
    .join(', ');

  $('national').innerHTML = `
    <div class="card-head"><h2>Cât valorează tot pământul din România</h2></div>
    <div class="stat-row">
      <div class="stat">
        <div class="stat-label">Valoarea terenului${
          whole ? ', toată țara, București inclus' : ', fără județele lipsă'
        }</div>
        <div class="stat-value accent">${mld(summary.landValueEur.central)}<span class="unit">EUR</span></div>
        <p class="note">
          între ${mld(summary.landValueEur.low)} și ${mld(summary.landValueEur.high)} —
          ${
            whole
              ? 'capetele grilelor notariale, cel mai ieftin și cel mai scump preț publicat pe fiecare localitate'
              : 'o bandă care este eroarea măsurată a modelului, nu o presupunere'
          }
        </p>
        ${
          filled
            ? `<p class="note">Numără doar hectarele pe care un studiu chiar le-a prețuit.
                 Cu cele neprețuite evaluate la prețul de transfer național:
                 <strong>${mld(filled.landValueEur.central)} EUR</strong>, adică
                 +${percent.format(filled.addedSharePercent)}%.</p>`
            : ''
        }
      </div>
      <div class="stat">
        <div class="stat-label">Din care citit din grile notariale</div>
        <div class="stat-value">${percent.format(100 * summary.measuredShareOfValue)}<span class="unit">%</span></div>
        <p class="note">${coverage}</p>
      </div>
      <div class="stat">
        <div class="stat-label">Cât spun conturile naționale ale altor țări</div>
        ${
          plausibility
            ? `<div class="stat-value">${percent.format(
                plausibility.thisSimulatorLandOverGdp,
              )}<span class="unit">× PIB</span></div>
              <p class="note">
                Terenul e activ de bilanț în ESA 2010 și ${
                  plausibility.groups.toate?.countries ?? 0
                } state îl raportează; România nu. Raportat la PIB, cifra de aici stă
                ${
                  plausibility.groups.est
                    ? `lângă statele intrate în UE după 2004 (mediana ${percent.format(
                        plausibility.groups.est.medianLandOverGdp,
                      )}× — ar însemna ${mld(plausibility.groups.est.impliedRomaniaEur)})`
                    : ''
                }
                ${
                  plausibility.groups.vest
                    ? ` și mult sub Europa de Vest (${percent.format(
                        plausibility.groups.vest.medianLandOverGdp,
                      )}× — ar însemna ${mld(plausibility.groups.vest.impliedRomaniaEur)})`
                    : ''
                }. Grupul de comparație e jumătate din răspuns, deci sunt publicate amândouă.
              </p>`
            : '<p class="note">Reperul extern nu este importat.</p>'
        }
      </div>
      <div class="stat">
        <div class="stat-label">${
          whole
            ? 'Cât greșea modelul un județ pe care nu-l văzuse'
            : 'Cât greșește modelul un județ pe care nu l-a văzut'
        }</div>
        <div class="stat-value">×${percent.format(assumptions.builtLeaveOneOutErrorFactor)}</div>
        <p class="note">
          teren construit prezis din populația celui mai mare oraș, R²
          ${percent.format(assumptions.builtR2)}.
          ${
            whole
              ? 'Nu mai prezice niciun județ — toate sunt citite. Rămâne testul pe care fiecare l-a trecut când a fost citit: valoarea prezisă înainte, comparată cu grila după.'
              : 'Cota construită a județului dă R² 0,04 și regiunea de dezvoltare e mai slabă decât nicio variabilă — de aceea nu sunt folosite.'
          }
        </p>
      </div>
    </div>
    ${
      plausibility
        ? `<div class="bias">
            <div>
              <h3>Ce ar muta cifra în sus</h3>
              <ul>${plausibility.movesItUp
                .map(
                  (b) =>
                    `<li>${b.text}${
                      b.measured === null ? ' <em>(doar direcția e cunoscută)</em>' : ''
                    }</li>`,
                )
                .join('')}</ul>
            </div>
            <div>
              <h3>Ce ar muta-o în jos</h3>
              <ul>${plausibility.movesItDown
                .map(
                  (b) =>
                    `<li>${b.text}${
                      b.measured === null ? ' <em>(doar direcția e cunoscută)</em>' : ''
                    }</li>`,
                )
                .join('')}</ul>
            </div>
          </div>`
        : ''
    }
  `;
}

async function main() {
  const code: FiscalCode = await fetch(`${base}data/cod-fiscal.json`).then((r) => r.json());
  const manifest: { counties: string[] } = await fetch(`${base}data/manifest.json`).then((r) =>
    r.json(),
  );

  let state = readHash();
  if (state.county !== ALL && !manifest.counties.includes(state.county)) {
    state.county = DEFAULTS.county;
  }
  // Even with the whole country selected one county's file is loaded first, because the
  // assumptions the page prints beside the numbers — the exchange rate, the derived built-land
  // yield — are stamped per build and identical across the forty-two.
  let loaded = await load(state.county === ALL ? DEFAULTS.county : state.county);

  // The map covers every built county, not the selected one, so it needs all of them. Fetched
  // after the first paint rather than before it: the page is useful the moment the selected
  // county is in, and the other thirteen are a background cost the reader should not wait on.
  const valueMap = new ValueMap('map', base);
  // What every commune actually spent, so the map can ask whether a land tax would cover it.
  // Optional: a data directory built before the execution was imported still renders a map,
  // and the third metric simply has nothing to colour.
  const spending = await fetch(`${base}data/buget-uat-2025.json`)
    .then((r) => (r.ok ? r.json() : null))
    .then((doc: { uats: Array<{ siruta: string; spendingRon: number }> } | null) =>
      doc ? new Map(doc.uats.map((u) => [u.siruta, u.spendingRon])) : new Map<string, number>(),
    )
    .catch(() => new Map<string, number>());
  valueMap.setSpending(spending);

  // The denominator. Optional in the same way the budget file is: without it every figure on
  // this page still renders and the share-of-GDP box says what it is missing rather than
  // printing a ratio against a number nobody imported.
  const gdp: Gdp | null = await fetch(`${base}data/pib.json`)
    .then((r) => (r.ok ? (r.json() as Promise<Gdp>) : null))
    .catch(() => null);

  /**
   * The years the reader may pick from, which depend on which scope is on screen.
   *
   * Regional accounts are published a year behind the national ones, so the country has a 2025
   * and no county does. Offering that year on a county view and quietly falling back would
   * print last year's denominator under this year's label; the list is therefore rebuilt per
   * scope, and the year is clamped into it rather than substituted behind the reader's back.
   */
  function gdpSeries(county: string): GdpYear[] {
    if (!gdp) return [];
    if (county === ALL) return gdp.series;
    return gdp.regions.find((r) => r.county.toLowerCase() === county)?.series ?? [];
  }

  /** The chosen year's GDP for the scope on screen, in lei. */
  function gdpRon(): { year: number; ron: number; scope: string } | null {
    const rows = gdpSeries(state.county);
    if (!rows.length) return null;
    const row = rows.find((r) => r.year === state.gdpYear) ?? rows[rows.length - 1]!;
    return {
      year: row.year,
      ron: row.gdpMron * 1e6,
      scope:
        state.county === ALL
          ? 'României'
          : `județului ${COUNTY_NAMES[state.county] ?? state.county.toUpperCase()}`,
    };
  }

  /** Clamp the chosen year into what this scope actually publishes, latest by default. */
  function settleGdpYear(county: string): void {
    const rows = gdpSeries(county);
    if (!rows.length) return;
    if (!rows.some((r) => r.year === state.gdpYear)) {
      state.gdpYear = rows[rows.length - 1]!.year;
    }
  }

  // The hatch key only when something is hatched; the national file says whether anything is.
  const anyPredicted = await fetch(`${base}data/national.json`)
    .then((r) => (r.ok ? r.json() : null))
    .then((n) => (n?.summary?.predictedCounties ?? 0) > 0)
    .catch(() => false);
  /**
   * The legend, redrawn with the metric.
   *
   * It has to move with the toggle: the same seven colours mean thousands of lei a hectare in
   * one view and hundreds of millions of lei a commune in the other, and a legend left on the
   * first one while the map shows the second is a caption for a different map.
   */
  function renderLegend(): void {
    const format =
      state.metric === 'perHa'
        ? (v: number) => `${Math.round(v / 1000)}k`
        : state.metric === 'autofinantare'
          ? (v: number) => `${percent.format(100 * v)}%`
          : scaled;
    $('map-legend').innerHTML = legend(state.metric, format, anyPredicted);
  }
  // Kept as well as handed to the map: "toate județele" needs every county's own rates, and
  // fetching them twice for two views of the same numbers would be silly.
  const cache = new Map<string, Loaded>();
  if (state.county !== ALL) cache.set(state.county, loaded);
  const everything = (async () => {
    for (const county of manifest.counties) {
      const data = cache.get(county) ?? (await load(county));
      cache.set(county, data);
      valueMap.load(county, data as never);
    }
  })();

  const named = [...manifest.counties].sort((a, b) =>
    (COUNTY_NAMES[a] ?? a).localeCompare(COUNTY_NAMES[b] ?? b, 'ro'),
  );
  $('counties').innerHTML = `
    <label class="field" for="county">Județul</label>
    <select id="county">
      <option value="${ALL}">Toate județele (${manifest.counties.length})</option>
      ${named
        .map((c) => `<option value="${c}">${COUNTY_NAMES[c] ?? c.toUpperCase()}</option>`)
        .join('')}
    </select>`;

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

  /** The reader's controls, with one county's own measured rates substituted in. */
  function settingsFor(data: Loaded): Settings {
    return {
      share: state.share,
      value: state.value,
      fiscal: state.fiscal,
      rate: state.rate,
      collectionRate: state.collection,
      landYield: state.landYield,
      landYieldAgricultural:
        data.tax.assumptions.agriculturalYieldPercent?.central ?? state.landYield,
      landYieldByCategory: Object.fromEntries(
        Object.entries(data.tax.assumptions.yieldByCategoryPercent ?? {}).map(([code, band]) => [
          code,
          band.central,
        ]),
      ),
      ronPerEur: data.tax.assumptions.ronPerEur,
    };
  }

  function render() {
    const all = state.county === ALL;
    const settings = settingsFor(loaded);
    // Every county at its own rates, then the money added — never one county's yields applied
    // to another's hectares. Counties still arriving are simply not in the sum yet, which the
    // heading says out loud rather than quietly understating the country.
    const { rows, totals } = all
      ? combine([...cache.values()].map((d) => evaluate(d.value.localities, code, settingsFor(d))))
      : evaluate(loaded.value.localities, code, settings);
    // Same settings object the totals came from, so the colours and the figures cannot
    // disagree; the map substitutes each county's own rate and yields on top of it.
    valueMap.paint(settings, code);
    valueMap.setMetric(state.metric);
    renderLegend();

    ($('county') as HTMLSelectElement).value = state.county;
    for (const button of document.querySelectorAll<HTMLButtonElement>('#map-metric button')) {
      button.classList.toggle('on', button.dataset.metric === state.metric);
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
    // The slider runs to 5% and the box has no ceiling, so above 5% the slider sits at its end
    // and the box carries the answer. That is the honest arrangement: the slider is for the
    // range worth dragging through, and the ceiling is the reader's to decide, not this file's.
    const RATE_SLIDER_MAX = 500;
    ($('rate') as HTMLInputElement).value = String(
      Math.min(RATE_SLIDER_MAX, Math.round(state.rate * 100)),
    );
    ($('share') as HTMLInputElement).value = String(Math.round(state.share * 100));
    ($('yield') as HTMLInputElement).value = String(Math.round(state.landYield * 100));
    ($('collection') as HTMLInputElement).value = String(Math.round(state.collection * 100));
    $('yield-value').textContent = `${percent.format(state.landYield)}%`;
    $('collection-value').textContent = `${percent.format(100 * state.collection)}%`;
    // Written back only when it disagrees with the state, so a half-typed "1." is not rewritten
    // to "1" under the cursor. A number input carries a dot; `percent` carries a comma, and
    // putting a Romanian decimal into `value` empties the box.
    // An empty box is written back too, or a rate of 0 renders as a blank one: `Number('')`
    // is 0, so "already correct" and "nothing there" look the same to a bare comparison.
    const rateBox = $('rate-value') as HTMLInputElement;
    if (rateBox.value.trim() === '' || Number(rateBox.value) !== state.rate) {
      rateBox.value = String(state.rate);
    }
    $('share-value').textContent = `×${percent.format(state.share)}`;

    // What the chosen rate means against the flow the land produces. The full-rent rate is the
    // textbook ceiling for a land value tax — above it the tax is charging more than the land
    // earns in a year — and now that the control has no stop, the page has to say where that
    // line is instead of the slider's end implying one.
    const fullRent = totals.value ? (100 * totals.rent) / totals.value : 0;
    $('rate-context').innerHTML = !fullRent
      ? ''
      : state.rate > fullRent
        ? `La ${percent.format(state.rate)}% impozitul cere mai mult decât produce pământul
           într-un an: renta lui e ${percent.format(fullRent)}% din valoare, deci restul s-ar
           plăti din altceva sau prin vânzarea terenului.`
        : `Renta pământului e ${percent.format(fullRent)}% din valoarea lui pe an, deci cota
           aleasă ia ${percent.format(fullRent ? (100 * state.rate) / fullRent : 0)}% din ce
           produce.`;

    // The year list belongs to the scope, so it is rebuilt when the scope changes and left
    // alone when it does not — rewriting the options on every keystroke of the rate box would
    // close the dropdown under a reader who had it open.
    const years = gdpSeries(state.county);
    const yearSelect = $('gdp-year') as HTMLSelectElement;
    const offered = years.map((y) => y.year).join(',');
    if (yearSelect.dataset.years !== offered) {
      yearSelect.dataset.years = offered;
      yearSelect.innerHTML = [...years]
        .reverse()
        .map((y) => `<option value="${y.year}">${y.year}</option>`)
        .join('');
    }
    yearSelect.disabled = years.length === 0;
    yearSelect.value = String(state.gdpYear);

    const denominator = gdpRon();
    const overGdp = (amount: number) =>
      denominator && denominator.ron ? (100 * amount) / denominator.ron : null;
    const collectedOverGdp = overGdp(totals.collected);
    $('gdp-value').textContent =
      collectedOverGdp === null ? '—' : `${percent.format(collectedOverGdp)}% din PIB`;
    $('gdp-note').innerHTML = !denominator
      ? 'Seria PIB nu este importată, deci nu există numitor.'
      : `Numitorul e PIB-ul ${denominator.scope} în ${denominator.year}:
         <strong>${scaled(denominator.ron)} lei</strong>. Anul mută numitorul, nu și valoarea
         pământului — grila notarială e una singură, cea în vigoare${
           state.county === ALL
             ? '.'
             : `. PIB-ul județean spune unde e înregistrată firma, nu unde e terenul, așa că
                Bucureștiul iese mic și județele din jurul lui, mari.`
         }`;

    // Measured, not modelled: what the counties on screen actually banked under revenue codes
    // 07.02.01-03. Summed over the cache for the aggregate, so it covers exactly the counties
    // the figures beside it cover rather than the whole country.
    const receipts = (all ? [...cache.values()] : [loaded]).map(
      (d) => d.tax.summary.collectedRon as number | null,
    );
    const collectedActual = receipts.every((r) => typeof r === 'number')
      ? receipts.reduce((sum, r) => sum + (r as number), 0)
      : null;
    const collectedPeriod = loaded.tax.summary.collectedPeriod as string | null;

    const neutral = totals.neutral;
    const direction = totals.lvt >= totals.fiscal ? 'more' : 'less';
    $('headline').innerHTML = `
      <div class="stat">
        <div class="stat-label">Impozitul de azi, Codul fiscal</div>
        <div class="stat-value">${scaled(totals.fiscal)} <span class="unit">lei</span></div>
        ${
          collectedActual === null
            ? ''
            : `<p class="note">încasat efectiv în ${collectedPeriod}: <strong>${scaled(
                collectedActual,
              )} lei</strong> — ${percent.format(
                (100 * collectedActual) / totals.fiscal,
              )}% din impozitul calculat mai sus, care e pe <em>toate</em> hectarele. O parte din diferență e domeniul public, care nu se impozitează deloc; restul e cota aleasă de consilii, scutirile și restanțele.</p>`
        }
      </div>
      <div class="stat">
        <div class="stat-label">Impozit pe valoare, la ${percent.format(state.rate)}%</div>
        <div class="stat-value ${direction}">${scaled(totals.lvt)} <span class="unit">lei</span></div>
        <p class="note">pe tot pământul, ca și cifra de alături — așa se compară cele două reguli</p>
      </div>
      <div class="stat">
        <div class="stat-label">Din el, cât s-ar putea încasa</div>
        <div class="stat-value">${scaled(totals.collected)} <span class="unit">lei</span></div>
        <p class="note">
          doar pe cele ${percent.format(
            totals.value ? (100 * totals.taxable) / totals.value : 0,
          )}% din valoare aflate în proprietate privată${
            state.collection < 1
              ? `, la un grad de colectare de ${percent.format(100 * state.collection)}%`
              : '; restul e domeniu public, care nu se impozitează'
          }
        </p>
      </div>
      ${
        denominator === null
          ? ''
          : `<div class="stat">
              <div class="stat-label">Cât ar însemna din economie</div>
              <div class="stat-value ${direction}">${percent.format(
                collectedOverGdp ?? 0,
              )}<span class="unit">% din PIB</span></div>
              <p class="note">
                ${scaled(totals.collected)} lei din ${scaled(denominator.ron)} lei — PIB-ul
                ${denominator.scope} în ${denominator.year}. Impozitul de azi, calculat pe
                aceleași hectare, ar fi ${percent.format(
                  overGdp(totals.fiscal) ?? 0,
                )}%${
                  collectedActual === null
                    ? ''
                    : `, iar cât se încasează efectiv e ${percent.format(
                        overGdp(collectedActual) ?? 0,
                      )}%`
                }.
              </p>
            </div>`
      }
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
          ${
            all
              ? `amestecul dintre ${percent.format(
                  state.landYield,
                )}% pe terenul de sub clădiri și randamentul agricol al fiecărui județ, măsurat separat`
              : `amestecul dintre ${percent.format(
                  state.landYield,
                )}% pe terenul de sub clădiri și ${percent.format(
                  agriculturalYield(),
                )}% măsurat pe terenul agricol`
          }
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
    // The table is capped and the total is not. Three thousand rows is a slow page and a
    // worse answer than the first few hundred sorted the way the reader asked for; the count
    // says how many there are so the cap cannot be mistaken for the whole.
    const LIMIT = 400;
    const shown = sorted.slice(0, LIMIT);
    $('table-title').textContent = all
      ? `${money.format(sorted.length)} localități din ${cache.size} județe` +
        (sorted.length > LIMIT ? ` — primele ${LIMIT}` : '')
      : `${sorted.length} localități din județul ${COUNTY_NAMES[state.county] ?? state.county}`;
    $('rows').innerHTML = shown
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
    // With every county selected the same caveat arrives forty-two times, so they are folded
    // by id: the reader wants the list of things that are wrong, not one per county.
    const source = all ? [...cache.values()] : [loaded];
    const seen = new Map<string, { id: string; text: string; severity: string }>();
    for (const data of source) {
      for (const limit of [...data.value.limitations, ...data.tax.limitations]) {
        if (!seen.has(limit.id)) seen.set(limit.id, limit);
      }
    }
    // The GDP file's caveats join the rest, but only while its number is on screen. They are
    // about a denominator; folding them in when nothing is being divided would be four
    // warnings about a figure the page is not showing.
    if (denominator) {
      for (const limit of gdp?.limitations ?? []) {
        if (!seen.has(limit.id)) seen.set(limit.id, limit);
      }
    }
    const limits = [...seen.values()];
    const order = { blocking: 0, material: 1, note: 2 } as Record<string, number>;
    limits.sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
    $('limits-count').textContent = `${limits.length}`;
    $('limits').innerHTML = limits
      .map(
        (limit) =>
          `<p class="limit ${limit.severity}"><span class="sev">${limit.severity}</span>${limit.text}</p>`,
      )
      .join('');
    $('sources').textContent = all
      ? `Sursele: grilele notariale ale celor ${cache.size} județe. Curs BCE din ${loaded.tax.assumptions.exchangeRateDate}.`
      : `Sursele: ${loaded.value.provenance.locator}. Curs BCE din ${loaded.tax.assumptions.exchangeRateDate}.`;

    writeHash(state);
  }

  function update(next: Partial<State>) {
    state = { ...state, ...next };
    render();
  }

  $('collection').addEventListener('input', (event) =>
    update({ collection: Number((event.target as HTMLInputElement).value) / 100 }),
  );
  $('rate').addEventListener('input', (event) =>
    update({ rate: Number((event.target as HTMLInputElement).value) / 100 }),
  );
  // The typed box is the one control on the page with no ceiling. An empty box is left alone
  // rather than read as zero: clearing it to type a new number would otherwise repaint the
  // whole page at 0% between two keystrokes.
  $('rate-value').addEventListener('input', (event) => {
    const raw = (event.target as HTMLInputElement).value.trim();
    if (raw === '') return;
    const typed = Number(raw);
    if (Number.isFinite(typed) && typed >= 0) update({ rate: typed });
  });
  $('gdp-year').addEventListener('change', (event) =>
    update({ gdpYear: Number((event.target as HTMLSelectElement).value) }),
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
  $('map-metric').addEventListener('click', (event) => {
    const metric = (event.target as HTMLElement).dataset.metric as Metric | undefined;
    if (metric) update({ metric });
  });
  $('sort').addEventListener('click', (event) => {
    const sort = (event.target as HTMLElement).dataset.sort as State['sort'] | undefined;
    if (sort) update({ sort });
  });
  $('counties').addEventListener('change', async (event) => {
    const county = (event.target as HTMLSelectElement).value;
    if (!county || county === state.county) return;
    if (county === ALL) {
      // The total is only honest once every county is in it, so this waits for the background
      // fetch to finish rather than adding up whichever half happens to have arrived.
      $('table-title').textContent = 'se încarcă toate județele…';
      await everything;
    } else {
      loaded = cache.get(county) ?? (await load(county));
      cache.set(county, loaded);
    }
    adoptDerivedYield();
    // The county series is a year shorter than the national one, so arriving at a county from
    // "toate județele" on the newest year has to land on the newest year that county has.
    settleGdpYear(county);
    update({ county });
  });

  adoptDerivedYield();
  settleGdpYear(state.county);
  render();
  void renderNational();
  // Arriving *on* `#j=toate`, rather than switching to it. The dropdown's handler waits for
  // every county before adding them up; a page loaded straight from that URL used to render
  // once against an empty cache and never look again, so the scenario the whole hash design
  // exists to make shareable was the one that showed a confident set of zeros.
  if (state.county === ALL) {
    $('table-title').textContent = 'se încarcă toate județele…';
    await everything;
    render();
  }
}

main().catch((error) => {
  $('headline').innerHTML = `<p class="limit blocking">Datele nu s-au încărcat: ${error}</p>`;
});

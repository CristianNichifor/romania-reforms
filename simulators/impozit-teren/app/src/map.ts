/**
 * The choropleth. Same arithmetic as the numbers beside it, painted onto communes.
 *
 * The map is not a picture of a saved answer. It colours from `evaluate()` — the function that
 * produces the totals and the table — so moving the intravilan share or the price band repaints
 * every commune in the country at once. A pre-rendered choropleth would have frozen at whatever
 * assumptions were current when it was built and then disagreed, silently, with the figures
 * printed next to it.
 *
 * **It shows every county, not the selected one.** The rest of the page is about one
 * county at a time; a map that greyed out all but one would answer a narrower question
 * than "what is Romanian land worth". So every built county is fetched once, on the first paint,
 * and each is evaluated with **its own** exchange rate and its own measured yields — those are
 * county-specific, and using the selected county's for all of them would be wrong in a way
 * nobody would see.
 *
 * **Missing means missing.** Communes the county's own study does not price stay unpainted
 * inside a painted county — a gap that is honest and visible in a way it is not in a table.
 *
 * **Nothing is estimated at the moment.** All forty-two counties have a notary grid, so the
 * hatch below never draws and its legend key is not shown. The machinery stays because the set
 * is not permanently empty: a chamber that stops publishing puts its county back into it, and
 * the map would then have to say so again rather than quietly painting a gap as a measurement.
 *
 * **Estimated means estimated, and it is drawn differently.** The counties with no
 * grid are no longer empty outlines: the national estimate gives each a value, so each is
 * filled — but as one flat county-sized shape, on the same colour scale, at half opacity and
 * under a diagonal hatch. That is not decoration. A predicted county's value comes from a
 * two-parameter regression on the size of its largest town, so it is known at county
 * resolution and nowhere finer; painting it commune by commune would dress one coefficient up
 * as local knowledge. The mosaic and the flat shape are the difference in evidence, drawn.
 */
import { Map as MapLibre, setWorkerUrl, type ExpressionSpecification } from 'maplibre-gl';
// maplibre 6 does its geometry work off the main thread, and it finds that worker by resolving
// `./maplibre-gl-worker.mjs` against its own `import.meta.url`. After bundling that resolves to
// a file next to our own bundle, which nobody ever put there — so the worker 404s, no source
// is ever parsed, and the map paints its background and nothing else. Handing the URL over
// explicitly is the supported way out: `?worker&url` makes the bundler emit the worker (with
// the shared chunk it imports folded in) and hands back where it landed.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

import { evaluate } from './model';
import type { FiscalCode, Locality, Settings } from './model';

setWorkerUrl(workerUrl);

/** The national estimate, as much of it as the map needs. */
export type NationalFile = {
  counties_valued: Array<{
    county: string;
    basis: 'measured' | 'predicted' | 'excluded';
    totalHa: number;
    landValueEur: { low: number; central: number; high: number } | null;
  }>;
};

export type CountyData = {
  value: { localities: Locality[] };
  tax: {
    assumptions: {
      ronPerEur: number;
      agriculturalYieldPercent: { central: number } | null;
      yieldByCategoryPercent: Record<string, { low: number; central: number; high: number }>;
    };
  };
};

/**
 * Breaks in lei per hectare, not a smooth ramp.
 *
 * Land value per hectare spans four orders of magnitude between a hillside in Hunedoara and
 * the centre of Iași, so a linear gradient is one colour for the country and a bright dot on
 * Iași. The steps are round numbers a reader can hold, and the top one is open-ended because
 * the cities have no ceiling worth drawing.
 */
const COLOURS = ['#1b3a4b', '#255e6b', '#2f8f7a', '#7bb661', '#d9c05a', '#d9873f', '#c2453a'];

/**
 * Which number is painted.
 *
 * The first two are about the land. The third is about the place: what a land value tax at
 * the reader's own rate would raise here, against what this commune actually spent — the one
 * question that needs two of these simulators in the same sentence, and the reason the budget
 * execution is loaded at all.
 */
export type Metric = 'perHa' | 'total' | 'autofinantare';

const BREAKS: Record<Metric, number[]> = {
  perHa: [25_000, 60_000, 150_000, 400_000, 1_000_000, 3_000_000],
  // The commune's whole land value, so the steps are round lei rather than round lei per
  // hectare — and they are a different question, not the same map rescaled. A large poor
  // commune and a small rich one land in the same bucket here and in opposite ones above.
  // Placed where the communes actually are: a twentieth sit below the first break, a
  // twentieth above the last, and the top step is open because București is fifty times it.
  total: [50e6, 100e6, 250e6, 500e6, 1e9, 5e9],
  // A share of the commune's own spending, so the steps are proportions and the top one is
  // the only one that matters: at 1,00 the tax on land alone would pay for everything the
  // place does. Nothing published suggests many communes reach it, which is the finding
  // rather than a reason to stretch the scale until they appear to.
  autofinantare: [0.05, 0.1, 0.25, 0.5, 0.75, 1],
};

export function legend(
  metric: Metric,
  format: (value: number) => string,
  estimated = false,
): string {
  const breaks = BREAKS[metric];
  const cells = COLOURS.map((colour, index) => {
    const from = index === 0 ? 0 : breaks[index - 1]!;
    const to = breaks[index];
    const label = to === undefined ? `${format(from)}+` : `${format(from)}–${format(to)}`;
    return `<span class="key"><i style="background:${colour}"></i>${label}</span>`;
  });
  // What an unpainted commune means depends on the question being asked. In the two land
  // views it is a commune the county's own study never priced; in the third it is one whose
  // budget execution is not in the file. Saying "fără preț" over the third would name the
  // wrong missing document.
  const absent =
    metric === 'autofinantare' ? 'fără execuție bugetară' : 'fără preț';
  return (
    `${cells.join('')}` +
    `<span class="key"><i class="none"></i>${absent}</span>` +
    // The hatch has to be in the legend or it reads as a rendering artefact — but only while
    // something is actually hatched. Every county is read now, so a key for a mark that never
    // appears would be the legend explaining a thing the map does not do.
    (estimated ? '<span class="key"><i class="estimated"></i>estimat</span>' : '')
  );
}

export class ValueMap {
  private map: MapLibre;
  private ready = false;
  private counties = new Map<string, CountyData>();
  private metric: Metric = 'perHa';
  /** What each commune spent last year, by SIRUTA. Empty until the execution file lands. */
  private spending = new Map<string, number>();

  constructor(container: string, base: string) {
    this.map = new MapLibre({
      container,
      // No basemap tiles: this is a choropleth of administrative units, and a street map
      // underneath it would be decoration that costs a tile server.
      style: { version: 8, sources: {}, layers: [
        { id: 'bg', type: 'background', paint: { 'background-color': '#0f1418' } },
      ] },
      center: [25.0, 45.9],
      zoom: 5.6,
      attributionControl: false,
    });

    this.map.on('load', async () => {
      const [uats, counties, shapes, national] = await Promise.all([
        fetch(`${base}data/harta-uat.geojson`).then((r) => r.json()),
        fetch(`${base}data/harta-judete.geojson`).then((r) => r.json()),
        // Both optional: the page has to keep working against a data directory built before
        // the national estimate existed, rather than failing to render a map at all.
        fetch(`${base}data/harta-judete-poligon.geojson`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        fetch(`${base}data/national.json`)
          .then((r) => (r.ok ? (r.json() as Promise<NationalFile>) : null))
          .catch(() => null),
      ]);
      this.national = national;
      this.countyOrder = shapes
        ? new Map(
            (shapes.features as Array<{ id: number; properties: { county: string } }>).map(
              (f) => [f.properties.county, f.id],
            ),
          )
        : new Map();
      this.map.addSource('uats', { type: 'geojson', data: uats });
      this.map.addSource('counties', { type: 'geojson', data: counties });
      if (shapes) this.map.addSource('county-shapes', { type: 'geojson', data: shapes });
      if (shapes) this.map.addImage('hatch', hatch(), { pixelRatio: 2 });

      // Under the communes, so a measured county's mosaic always wins where both exist.
      if (shapes) {
        this.map.addLayer({
          id: 'county-fill',
          type: 'fill',
          source: 'county-shapes',
          paint: {
            'fill-color': fill(this.metric, 'rgba(0,0,0,0)'),
            // Half, so an estimate never reads as loud as a measurement.
            'fill-opacity': 0.5,
          },
        });
        // The hatch on top of the colour, not instead of it: the county still has to be
        // readable on the scale, it just has to be unmistakably a different kind of claim.
        this.map.addLayer({
          id: 'county-hatch',
          type: 'fill',
          source: 'county-shapes',
          paint: {
            'fill-pattern': 'hatch',
            'fill-opacity': [
              'case',
              ['==', ['coalesce', ['feature-state', 'estimated'], 0], 1],
              0.5,
              0,
            ] as unknown as ExpressionSpecification,
          },
        });
      }
      this.map.addLayer({
        id: 'uat-fill',
        type: 'fill',
        source: 'uats',
        paint: {
          // A commune with no feature state has no price. It is drawn as the background
          // rather than as the bottom of the scale, because "cheap" and "not published" are
          // different things and the second is common here.
          'fill-color': fill(this.metric, '#232a31'),
          'fill-opacity': 0.92,
        },
      });
      this.map.addLayer({
        id: 'uat-line',
        type: 'line',
        source: 'uats',
        paint: { 'line-color': '#0f1418', 'line-width': 0.3, 'line-opacity': 0.5 },
      });
      this.map.addLayer({
        id: 'county-line',
        type: 'line',
        source: 'counties',
        paint: { 'line-color': '#8a949e', 'line-width': 0.8 },
      });
      this.ready = true;
      this.paintEstimates();
      this.repaint();
    });
  }

  /**
   * The budget execution, keyed the same way the localities are.
   *
   * Optional on purpose: the map has to keep working against a data directory built before
   * this file existed, and a commune the execution does not cover stays unpainted in the
   * self-financing view rather than being drawn at the bottom of the scale. "Spends nothing"
   * and "did not file" are different facts.
   */
  setSpending(spending: Map<string, number>): void {
    this.spending = spending;
    if (this.ready) this.repaint();
  }

  /** Hand the map every county's data once; it keeps them and repaints on each settings change. */
  load(county: string, data: CountyData): void {
    const first = this.counties.size === 0;
    this.counties.set(county, data);
    // The estimated counties need an exchange rate and the first loaded county is where it
    // comes from, so they cannot be painted until one has arrived.
    if (this.ready && first) this.paintEstimates();
    if (this.ready) this.repaint();
  }

  private national: NationalFile | null = null;
  private countyOrder = new Map<string, number>();

  /**
   * Colour the predicted counties, once.
   *
   * Unlike the communes these do not repaint when the reader moves a control, and that is
   * deliberate rather than an omission. The estimate was fitted on the measured counties at
   * the assumptions the build used; re-scaling it by a slider the reader has since moved
   * would imply the regression had been refitted, which it has not. The measured half
   * responds to the controls and the estimated half does not — which is also, usefully, what
   * it looks like.
   */
  private paintEstimates(): void {
    if (!this.national) return;
    for (const row of this.national.counties_valued) {
      const id = this.countyOrder.get(row.county);
      if (id === undefined || row.basis !== 'predicted' || !row.landValueEur) continue;
      // Euro to lei at a fixed rate would be a second source of truth; the scale is in lei,
      // so the same conversion the tax files carry is used, read off any one of them.
      const value = row.landValueEur.central * this.ronPerEur;
      this.map.setFeatureState(
        { source: 'county-shapes', id },
        // Both metrics, or the toggle would blank the estimated counties instead of switching
        // them. A county's total is not on the same scale as a commune's, and it is not meant
        // to be: the flat shape is already saying this is a county, not a mosaic.
        { perHa: value / row.totalHa, total: value, estimated: true },
      );
    }
  }

  /** The exchange rate any loaded county carries; they are stamped from the same ECB day. */
  private get ronPerEur(): number {
    const first = this.counties.values().next().value;
    return first ? first.tax.assumptions.ronPerEur : 5;
  }

  /**
   * Switch which of the two numbers is coloured.
   *
   * Both are already on every commune — `repaint` sets them together — so this only swaps the
   * expression the fill reads and the scale it reads it against. Nothing is recomputed, which
   * is why the toggle is instant and why the two views can never disagree about a commune.
   */
  setMetric(metric: Metric): void {
    this.metric = metric;
    if (!this.ready) return;
    this.map.setPaintProperty('uat-fill', 'fill-color', fill(metric, '#232a31'));
    if (this.map.getLayer('county-fill')) {
      this.map.setPaintProperty('county-fill', 'fill-color', fill(metric, 'rgba(0,0,0,0)'));
    }
  }

  private current: { settings: Settings; code: FiscalCode } | null = null;

  paint(settings: Settings, code: FiscalCode): void {
    this.current = { settings, code };
    if (this.ready) this.repaint();
  }

  private repaint(): void {
    if (!this.current) return;
    const { settings, code } = this.current;
    for (const [, data] of this.counties) {
      // Each county at its own rate and its own measured yields. They differ — the farmland
      // yield is regional and the exchange rate is stamped per build — and borrowing the
      // selected county's would be an error invisible on a map.
      const own: Settings = {
        ...settings,
        ronPerEur: data.tax.assumptions.ronPerEur,
        landYieldAgricultural:
          data.tax.assumptions.agriculturalYieldPercent?.central ?? settings.landYield,
        landYieldByCategory: Object.fromEntries(
          Object.entries(data.tax.assumptions.yieldByCategoryPercent ?? {}).map(
            ([category, band]) => [category, band.central],
          ),
        ),
      };
      const { rows } = evaluate(data.value.localities, code, own);
      for (const row of rows) {
        const hectares = totalHa(data.value.localities, row.siruta);
        if (!hectares) continue;
        // The tax the reader's own rate would raise here, over what the place spent. Not
        // the land value over the spending: a commune does not collect its land, it
        // collects a percentage of it once a year, and the two differ by two orders of
        // magnitude. Left unset where nothing was filed, so the colour never implies a
        // ratio that was not computed.
        const spent = this.spending.get(row.siruta);
        const selfFunding = spent && spent > 0 ? row.lvtRon / spent : undefined;
        this.map.setFeatureState(
          { source: 'uats', id: Number(row.siruta) },
          {
            perHa: row.landValueRon / hectares,
            total: row.landValueRon,
            ...(selfFunding === undefined ? {} : { autofinantare: selfFunding }),
          },
        );
      }
    }
  }
}

function totalHa(localities: Locality[], siruta: string): number {
  const found = localities.find((l) => l.siruta === siruta);
  return found ? found.totalHa : 0;
}

/**
 * A diagonal hatch, drawn rather than fetched.
 *
 * Eight pixels with a light stripe across the diagonal, tiled by maplibre. Generated here
 * because the alternative is a PNG in the repository that nobody can see the source of, and
 * because a strict content policy on the published page blocks anything fetched from
 * elsewhere. The mark means one thing on this map — *this number was estimated* — so it is
 * worth the twelve lines.
 */
function hatch(): ImageData {
  const size = 8;
  const pixels = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const at = (y * size + x) * 4;
      const on = (x + y) % size < 2;
      pixels[at] = 255;
      pixels[at + 1] = 255;
      pixels[at + 2] = 255;
      pixels[at + 3] = on ? 90 : 0;
    }
  }
  return new ImageData(pixels, size, size);
}

/** The step expression wants value, colour, value, colour…, starting from the second colour. */
function interleave(metric: Metric): Array<string | number> {
  const out: Array<string | number> = [COLOURS[0]!];
  BREAKS[metric].forEach((breakpoint, index) => {
    out.push(breakpoint, COLOURS[index + 1]!);
  });
  return out;
}

/**
 * The fill colour for one metric, with a colour of its own for "no number here".
 *
 * Built rather than written twice because the communes and the estimated counties differ only
 * in what they show where the state is missing — a commune shows the background, a county
 * shows nothing at all — and two copies of a seven-step expression drift.
 */
function fill(metric: Metric, missing: string): ExpressionSpecification {
  return [
    'case',
    ['==', ['coalesce', ['feature-state', metric], -1], -1],
    missing,
    ['step', ['feature-state', metric], ...interleave(metric)],
  ] as unknown as ExpressionSpecification;
}

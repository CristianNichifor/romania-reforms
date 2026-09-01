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
 * **Estimated means estimated, and it is drawn differently.** The counties with no
 * grid are no longer empty outlines: the national estimate gives each a value, so each is
 * filled — but as one flat county-sized shape, on the same colour scale, at half opacity and
 * under a diagonal hatch. That is not decoration. A predicted county's value comes from a
 * two-parameter regression on the size of its largest town, so it is known at county
 * resolution and nowhere finer; painting it commune by commune would dress one coefficient up
 * as local knowledge. The mosaic and the flat shape are the difference in evidence, drawn.
 */
import { Map as MapLibre, type ExpressionSpecification } from 'maplibre-gl';

import { evaluate } from './model';
import type { FiscalCode, Locality, Settings } from './model';

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
const BREAKS = [25_000, 60_000, 150_000, 400_000, 1_000_000, 3_000_000];
const COLOURS = ['#1b3a4b', '#255e6b', '#2f8f7a', '#7bb661', '#d9c05a', '#d9873f', '#c2453a'];

export function legend(format: (value: number) => string): string {
  const cells = COLOURS.map((colour, index) => {
    const from = index === 0 ? 0 : BREAKS[index - 1]!;
    const to = BREAKS[index];
    const label = to === undefined ? `${format(from)}+` : `${format(from)}–${format(to)}`;
    return `<span class="key"><i style="background:${colour}"></i>${label}</span>`;
  });
  return (
    `${cells.join('')}` +
    '<span class="key"><i class="none"></i>fără preț</span>' +
    // The hatch has to be in the legend or it reads as a rendering artefact. It is the only
    // mark on the map that says something about evidence rather than about value.
    '<span class="key"><i class="estimated"></i>estimat</span>'
  );
}

export class ValueMap {
  private map: MapLibre;
  private ready = false;
  private counties = new Map<string, CountyData>();

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
            'fill-color': [
              'case',
              ['==', ['coalesce', ['feature-state', 'perHa'], -1], -1],
              'rgba(0,0,0,0)',
              ['step', ['feature-state', 'perHa'], ...interleave()],
            ] as unknown as ExpressionSpecification,
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
          'fill-color': [
            'case',
            ['==', ['coalesce', ['feature-state', 'perHa'], -1], -1],
            '#232a31',
            ['step', ['feature-state', 'perHa'], ...interleave()],
          ] as unknown as ExpressionSpecification,
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
      this.map.setFeatureState(
        { source: 'county-shapes', id },
        { perHa: (row.landValueEur.central * this.ronPerEur) / row.totalHa, estimated: true },
      );
    }
  }

  /** The exchange rate any loaded county carries; they are stamped from the same ECB day. */
  private get ronPerEur(): number {
    const first = this.counties.values().next().value;
    return first ? first.tax.assumptions.ronPerEur : 5;
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
        this.map.setFeatureState(
          { source: 'uats', id: Number(row.siruta) },
          { perHa: row.landValueRon / hectares, total: row.landValueRon },
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
function interleave(): Array<string | number> {
  const out: Array<string | number> = [COLOURS[0]!];
  BREAKS.forEach((breakpoint, index) => {
    out.push(breakpoint, COLOURS[index + 1]!);
  });
  return out;
}

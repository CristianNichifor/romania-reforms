/**
 * The court map.
 *
 * Two views of the same 241 courts. **Astăzi** is what the CSM report describes: every court
 * where it sits, sized by the dossiers it had to resolve, coloured by how its load per judge
 * compares with the national average for its grade. **Propunerea** is the reform paper's
 * proposal — 176 judecătorii and 42 tribunale collapsing into 42 consolidated tribunale —
 * modelled as each county's judecătorii merging into that county's tribunal.
 *
 * That last sentence is an assumption and the panel says so. The report contains no arondare:
 * which judecătorie answers to which tribunal is set by law, not by this document. County is
 * the reading the proposal implies — there are 42 tribunale and 41 counties plus Bucharest —
 * but it is a reading, and the access question underneath it stays unanswerable either way.
 */
import {
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type MapMouseEvent,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

// MapLibre 6 ships its worker as a separate file rather than inlining it, and a bundled app
// has to say where that file ended up. Without this every source fails to load silently —
// no error event, no failed request, just a map that renders its background and stays empty.
// `?worker&url` rather than `?url`: the worker imports a shared chunk, and plain `?url`
// copies the file without following its imports, so it dies in production while working in
// dev. Learned in the administrative map; repeated here rather than rediscovered.
setWorkerUrl(maplibreWorkerUrl);

interface Court {
  id: string;
  name: string;
  tier: 'iccj' | 'curte-de-apel' | 'tribunal' | 'judecatorie';
  volume: number;
  resolved: number;
  loadPerJudge?: number;
  loadPerPost?: number;
  judges?: number;
  posts?: number;
  county: string;
  siruta: string | null;
  placedBy: 'name' | 'county-seat' | 'city';
  point: [number, number];
}

interface Limitation {
  id: string;
  text: string;
  severity: string;
  affects: string[];
}

interface Document {
  period: string;
  courts: Court[];
  nationalAverages: { byTier: { tier: string; perJudge: number; perPost: number }[] };
  limitations: Limitation[];
}

const TIER_LABEL: Record<Court['tier'], string> = {
  iccj: 'Înalta Curte',
  'curte-de-apel': 'Curte de apel',
  tribunal: 'Tribunal',
  judecatorie: 'Judecătorie',
};

const ro = new Intl.NumberFormat('ro-RO');

const base = import.meta.env.BASE_URL;
const el = <T extends HTMLElement>(q: string): T => {
  const node = document.querySelector<T>(q);
  if (!node) throw new Error(`missing ${q}`);
  return node;
};

/**
 * A blank style: no tiles, no remote basemap, no third-party request.
 *
 * The same choice the administrative map makes, for the same reasons — the page stays free to
 * host, works offline, and asks nothing of anyone's browser that the reader did not choose.
 */
const BLANK = {
  version: 8 as const,
  // `glyphs` is omitted, not set to undefined. MapLibre validates the style and rejects a
  // key that is present with no value — "glyphs: string expected, undefined found" — and the
  // failure is quiet in the worst way: the style never loads, so `load` never fires, so no
  // layers are ever added and the page shows an empty canvas with a working panel beside it.
  // Nothing 404s and nothing throws where a reader would look.
  sources: {},
  layers: [{ id: 'bg', type: 'background' as const, paint: { 'background-color': '#0b0d10' } }],
};

async function main(): Promise<void> {
  const [doc, counties] = await Promise.all([
    fetch(`${base}data/instante.json`).then((r) => r.json() as Promise<Document>),
    fetch(`${base}data/counties.geojson`).then((r) => r.json()),
  ]);

  // The year comes from the document, not the markup. The CSM publishes annually and this
  // page had 2023 written into its subtitle while reading 2025 — a caption that disagrees
  // with its own figures is worse than none.
  el('#sub').textContent =
    `${ro.format(doc.courts.length)} de instanțe, dosarele pe care le-au avut de soluționat ` +
    `în ${doc.period} și încărcătura pe judecător.`;

  const averageFor = new Map(doc.nationalAverages.byTier.map((t) => [t.tier, t.perJudge]));

  /**
   * A court's load per judge, as a multiple of the yardstick it should be judged against.
   *
   * Today that is the national average for its own grade, which the report prints: a
   * judecatorie against 1.454,7 and a tribunal against 932,3, so a small court is not made
   * to look good by being compared with the Inalta Curte.
   *
   * Under the proposal it cannot be. A merged court carries the judecatorie work of its whole
   * county at tribunal grade, so measuring it against the *old* tribunal average paints every
   * one of the 42 red — which says nothing about the reform and everything about comparing a
   * court with a yardstick built before it existed. The proposal is therefore measured against
   * itself: the mean load per judge across the merged courts. That answers the question the
   * view can actually support — which of them would be worse off than the rest.
   */
  const ratioAgainst = (
    court: { tier: string; loadPerJudge?: number },
    yardstick: number | undefined,
  ): number | null => {
    if (!yardstick || !court.loadPerJudge) return null;
    return court.loadPerJudge / yardstick;
  };

  /**
   * The proposal: every judecătorie in a county folds into that county's tribunal.
   *
   * Curțile de apel and the Înalta Curte are left as they are — the paper keeps 15 courts of
   * appeal and there are already 15. Where a county has several tribunale, the specialised
   * ones fold in too, which is what "42 consolidated tribunale" means.
   */
  const proposed = (): Court[] => {
    const kept = doc.courts.filter((c) => c.tier === 'iccj' || c.tier === 'curte-de-apel');
    const byCounty = new Map<string, Court[]>();
    for (const court of doc.courts) {
      if (court.tier === 'iccj' || court.tier === 'curte-de-apel') continue;
      const list = byCounty.get(court.county) ?? [];
      list.push(court);
      byCounty.set(court.county, list);
    }
    const merged: Court[] = [];
    for (const [county, courts] of byCounty) {
      // The consolidated court is seated where that county's tribunal already is.
      const seat = courts.find((c) => c.tier === 'tribunal') ?? courts[0]!;
      const volume = courts.reduce((n, c) => n + c.volume, 0);
      const resolved = courts.reduce((n, c) => n + c.resolved, 0);
      const judges = courts.reduce((n, c) => n + (c.judges ?? 0), 0);
      merged.push({
        ...seat,
        id: `t-${county}`,
        name: `Tribunalul ${county} (comasat)`,
        tier: 'tribunal',
        volume,
        resolved,
        judges,
        loadPerJudge: judges > 0 ? volume / judges : undefined,
        posts: undefined,
        loadPerPost: undefined,
      });
    }
    return [...kept, ...merged];
  };

  const meanLoadOf = (courts: Court[]): number => {
    const loads = courts.map((c) => c.loadPerJudge ?? 0).filter((n) => n > 0);
    return loads.length ? loads.reduce((a, b) => a + b, 0) / loads.length : 0;
  };

  const asFeatures = (courts: Court[], ratioOf: (c: Court) => number | null) => ({
    type: 'FeatureCollection' as const,
    features: courts.map((c) => {
      const ratio = ratioOf(c);
      return {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: c.point },
        properties: {
          ...c,
          judges: c.judges ?? 0,
          loadPerJudge: c.loadPerJudge ?? 0,
          ratio: ratio ?? 1,
          hasRatio: ratio === null ? 0 : 1,
          tierLabel: TIER_LABEL[c.tier],
        },
      };
    }),
  });

  const map = new MapLibreMap({
    container: 'map',
    style: BLANK,
    center: [25.0, 45.9],
    zoom: 6.1,
    attributionControl: false,
    pitchWithRotate: false,
    dragRotate: false,
  });
  map.addControl(new NavigationControl({ showCompass: false }), 'top-right');

  let mode: 'today' | 'proposed' = 'today';
  const courtsFor = (m: typeof mode) => (m === 'today' ? doc.courts : proposed());

  /** The yardstick differs by view, so it is built with the courts rather than assumed. */
  const ratioFor = (m: typeof mode, courts: Court[]): ((c: Court) => number | null) => {
    if (m === 'today') return (c) => ratioAgainst(c, averageFor.get(c.tier));
    const merged = courts.filter((c) => c.id.startsWith('t-'));
    const mean = meanLoadOf(merged);
    // Courts the proposal leaves alone keep their own grade's yardstick.
    return (c) =>
      c.id.startsWith('t-') ? ratioAgainst(c, mean) : ratioAgainst(c, averageFor.get(c.tier));
  };

  map.on('load', () => {
    map.addSource('counties', { type: 'geojson', data: counties });
    map.addLayer({
      id: 'county-lines',
      type: 'line',
      source: 'counties',
      paint: { 'line-color': '#2b333c', 'line-width': 1 },
    });

    map.addSource('courts', {
      type: 'geojson',
      data: asFeatures(courtsFor(mode), ratioFor(mode, courtsFor(mode))),
    });

    // Radius by the square root of the volume: area reads as quantity, radius does not, and
    // the largest court carries a hundred times the smallest.
    const radius = [
      'interpolate',
      ['linear'],
      ['sqrt', ['get', 'volume']],
      0,
      3,
      300,
      22,
    ] as unknown as ExpressionSpecification;

    // Diverging on the ratio to the grade's own average, so a judecătorie is compared with
    // judecătorii and not with the Înalta Curte.
    const colour = [
      'case',
      ['==', ['get', 'hasRatio'], 0],
      '#6b7280',
      [
        'interpolate',
        ['linear'],
        ['get', 'ratio'],
        0.6,
        '#2f7d4f',
        0.85,
        '#7fa86a',
        1.0,
        '#d9c05a',
        1.2,
        '#d98040',
        1.6,
        '#c2453a',
      ],
    ] as unknown as ExpressionSpecification;

    map.addLayer({
      id: 'courts',
      type: 'circle',
      source: 'courts',
      paint: {
        'circle-radius': radius,
        'circle-color': colour,
        'circle-opacity': 0.85,
        'circle-stroke-color': '#0b0d10',
        'circle-stroke-width': 1,
      },
    });

    const detail = el('#detail');
    const show = (f: MapGeoJSONFeature | null): void => {
      if (!f) {
        detail.innerHTML = '<p class="hint">Treci cu mouse-ul peste o instanță.</p>';
        return;
      }
      const p = f.properties as unknown as Court & { tierLabel: string; ratio: number };
      const average = p.id.startsWith('t-') ? null : averageFor.get(p.tier);
      const load = p.loadPerJudge ? Math.round(p.loadPerJudge) : null;
      detail.innerHTML = `
        <div class="court">${p.name}</div>
        <div class="tier">${p.tierLabel}</div>
        <dl>
          <dt>Dosare de soluționat</dt><dd>${ro.format(p.volume)}</dd>
          <dt>Soluționate</dt><dd>${ro.format(p.resolved)}</dd>
          <dt>Judecători</dt><dd>${p.judges ? ro.format(Math.round(p.judges * 10) / 10) : '—'}</dd>
          <dt>Pe judecător</dt><dd>${load ? ro.format(load) : '—'}${
            load && average
              ? ` <span class="vs">(media gradului ${ro.format(Math.round(average))})</span>`
              : load
                ? ' <span class="vs">(comparat cu media instanțelor comasate)</span>'
                : ''
          }</dd>
        </dl>`;
    };

    map.on('mousemove', 'courts', (e: MapMouseEvent & { features?: MapGeoJSONFeature[] }) => {
      map.getCanvas().style.cursor = 'pointer';
      show(e.features?.[0] ?? null);
    });
    map.on('mouseleave', 'courts', () => {
      map.getCanvas().style.cursor = '';
      show(null);
    });

    const render = (): void => {
      const courts = courtsFor(mode);
      const ratioOf = ratioFor(mode, courts);
      (map.getSource('courts') as GeoJSONSource).setData(asFeatures(courts, ratioOf));
      const total = courts.reduce((n, c) => n + c.volume, 0);
      const over = courts.filter((c) => (ratioOf(c) ?? 0) > 1).length;
      // The legend has to name the yardstick, because it changes with the view and a reader
      // comparing colours across the two would otherwise be comparing different questions.
      el('#ramp-title').textContent =
        mode === 'today'
          ? 'Încărcătura față de media pe grad'
          : 'Încărcătura față de media instanțelor comasate';
      el('#summary').innerHTML = `
        <div class="figure"><strong>${ro.format(courts.length)}</strong> instanțe</div>
        <div class="figure"><strong>${ro.format(total)}</strong> dosare</div>
        <div class="figure"><strong>${ro.format(over)}</strong> peste media gradului</div>`;
    };

    for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
      button.addEventListener('click', () => {
        mode = button.dataset.mode as typeof mode;
        for (const other of document.querySelectorAll('[data-mode]')) other.classList.remove('on');
        button.classList.add('on');
        render();
      });
    }
    render();
  });

  // The limitations are part of the map, not a footnote to it. The blocking one is the reason
  // this shows where courts are and refuses to show what closing one would cost.
  el('#limits').innerHTML = doc.limitations
    .map(
      (l) =>
        `<p class="limit ${l.severity === 'blocking' ? 'blocking' : ''}">${
          l.severity === 'blocking' ? '<strong>Nu putem răspunde:</strong> ' : ''
        }${l.text}</p>`,
    )
    .join('');
}

main().catch((error: unknown) => {
  el('#detail').innerHTML = `<p class="hint">Harta nu s-a putut încărca: ${String(error)}</p>`;
});

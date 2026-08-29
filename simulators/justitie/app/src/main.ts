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
  /** Level-1 judges the county has today, carried on a merged court for comparison. */
  judgesToday?: number;
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

interface Proposal {
  publisher: string;
  published: boolean;
  provenance: { note?: string };
  tinta: { nivel1: { instante: number; motivInstante?: string } };
  limitations: Limitation[];
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
  const [doc, counties, proposal, manifest] = await Promise.all([
    fetch(`${base}data/instante.json`).then((r) => r.json() as Promise<Document>),
    fetch(`${base}data/counties.geojson`).then((r) => r.json()),
    fetch(`${base}data/propunere.json`).then((r) => r.json() as Promise<Proposal>),
    fetch(`${base}data/manifest.json`).then(
      (r) => r.json() as Promise<{ countyNames?: Record<string, string> }>,
    ),
  ]);
  const countyName = (code: string): string => manifest.countyNames?.[code] ?? code;

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
  /**
   * The proposal: one level-1 court per county, sized by the work it inherits.
   *
   * The count is fixed by territorial coverage — 41 counties and Bucharest, hence 42 — and a
   * county with more work gets a bigger court rather than another one. Judges follow from the
   * volume and the target rate; the number of courts does not move.
   *
   * The paper also says each court would serve 150.000-200.000 inhabitants. That cannot hold
   * at 42 — the average is 453.662 — and it is recorded in the proposal document as wording
   * to correct rather than modelled here. Curtile de apel and the Inalta Curte are untouched.
   */
  const proposed = (target: number): Court[] => {
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
      // Seated where the county's tribunal already is: it is the level-1 court that exists
      // at county scale, so it is the one with a building that plausibly takes the rest.
      const seat = courts.find((c) => c.tier === 'tribunal') ?? courts[0]!;
      const volume = courts.reduce((n, c) => n + c.volume, 0);
      const resolved = courts.reduce((n, c) => n + c.resolved, 0);
      merged.push({
        ...seat,
        id: `t-${county}`,
        name: `Instanța ${countyName(county)}`,
        tier: 'tribunal',
        volume,
        resolved,
        // Staffing is the output here, not an input carried over: this is what the court
        // would need to run at the chosen rate, which is the question consolidation raises.
        judges: volume / target,
        judgesToday: courts.reduce((n, c) => n + (c.judges ?? 0), 0),
        loadPerJudge: target,
        posts: undefined,
        loadPerPost: undefined,
      });
    }
    return [...kept, ...merged];
  };

  /** Judges at level 1 today, the figure the proposal's staffing is compared against. */
  const judgesToday = doc.courts
    .filter((c) => c.tier === 'judecatorie' || c.tier === 'tribunal')
    .reduce((n, c) => n + (c.judges ?? 0), 0);

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
  const targetInput = el<HTMLInputElement>('#target');
  const courtsFor = (m: typeof mode) =>
    m === 'today' ? doc.courts : proposed(Number(targetInput.value));

  /**
   * What the colour means differs by view, because the two views vary in different things.
   *
   * Today: load per judge against the national average for the court's own grade, so a
   * judecatorie is compared with judecatorii.
   *
   * Under the proposal every merged court runs at exactly the chosen rate — that is how its
   * staffing is derived — so colouring by load would paint all forty-two identically. What
   * actually varies is whether a county would need more judges than it has, which is the
   * question the merge raises and the one a reader can act on.
   */
  const ratioFor = (m: typeof mode, courts: Court[]): ((c: Court) => number | null) => {
    if (m === 'today') return (c) => ratioAgainst(c, averageFor.get(c.tier));
    return (c) => {
      if (!c.id.startsWith('t-')) return ratioAgainst(c, averageFor.get(c.tier));
      if (!c.judgesToday || !c.judges) return null;
      return c.judges / c.judgesToday;
    };
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

      el('#ramp-title').textContent =
        mode === 'today'
          ? 'Încărcătura față de media pe grad'
          : 'Judecători necesari față de câți sunt azi';
      el('#staffing').hidden = mode !== 'proposed';
      el('#authorship').hidden = mode !== 'proposed';
      el<HTMLOutputElement>('#target-value').textContent = ro.format(Number(targetInput.value));

      const total = courts.reduce((n, c) => n + c.volume, 0);
      if (mode === 'today') {
        const over = courts.filter((c) => (ratioOf(c) ?? 0) > 1).length;
        el('#summary').innerHTML = `
          <div class="figure"><strong>${ro.format(courts.length)}</strong> instanțe</div>
          <div class="figure"><strong>${ro.format(total)}</strong> dosare</div>
          <div class="figure"><strong>${ro.format(over)}</strong> peste media gradului</div>`;
        return;
      }

      const merged = courts.filter((c) => c.id.startsWith('t-'));
      const needed = merged.reduce((n, c) => n + (c.judges ?? 0), 0);
      // The dossiers the forty-two would actually carry. Printing the system-wide figure
      // beside "42 instante de nivel 1" reads as though they handle the appeals too.
      const levelOne = merged.reduce((n, c) => n + c.volume, 0);
      const delta = needed - judgesToday;
      const volumes = merged.map((c) => c.volume).sort((a, c) => a - c);
      const spread = volumes.length ? volumes[volumes.length - 1]! / volumes[0]! : 0;
      el('#summary').innerHTML = `
        <div class="figure"><strong>${ro.format(merged.length)}</strong> instanțe de nivel 1,
          câte una pe județ</div>
        <div class="figure"><strong>${ro.format(levelOne)}</strong> dosare de nivel 1
          <span class="vs">(din ${ro.format(total)} în tot sistemul)</span></div>
        <div class="figure"><strong>${ro.format(Math.round(needed))}</strong> judecători
          necesari, față de ${ro.format(Math.round(judgesToday))} azi
          <span class="vs">(${delta >= 0 ? '+' : ''}${ro.format(Math.round(delta))})</span></div>
        <div class="figure">cea mai mare instanță ar avea de
          <strong>${spread.toFixed(0)}×</strong> mai multe dosare decât cea mai mică</div>`;
    };

    for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
      button.addEventListener('click', () => {
        mode = button.dataset.mode as typeof mode;
        for (const other of document.querySelectorAll('[data-mode]')) other.classList.remove('on');
        button.classList.add('on');
        render();
      });
    }
    targetInput.addEventListener('input', render);
    render();
  });

  // Who wrote the proposal, stated on the view that shows it. The baseline is a CSM report
  // and the proposal is one person's paper; a reader seeing "Astăzi / Propunerea" has no way
  // to tell them apart unless the page says so. Read from the document, so it cannot drift
  // from what the data claims.
  el('#authorship').innerHTML = proposal.published
    ? `Propunere publicată de ${proposal.publisher}.`
    : `<strong>Propunere neinstituțională.</strong> Documentul este al lui ` +
      `${proposal.publisher}, autorul acestui simulator. Nu este act normativ și nu a trecut ` +
      `printr-un proces public. Baza de comparație — activitatea instanțelor — este raportul ` +
      `Consiliului Superior al Magistraturii.`;

  // The limitations are part of the map, not a footnote to it. The blocking one is the reason
  // this shows where courts are and refuses to show what closing one would cost.
  el('#limits').innerHTML = [...doc.limitations, ...proposal.limitations]
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

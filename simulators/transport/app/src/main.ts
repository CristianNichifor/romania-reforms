import * as maplibregl from 'maplibre-gl';
// MapLibre 6 parses GeoJSON in a web worker that it loads as a SEPARATE file, resolved next to
// the main script. Vite inlines the library into the app bundle and never emits that file, so
// the worker 404s, dies silently, and no source ever finishes loading: a blank map, no
// exception, no map error event. Pointing it at a worker Vite actually bundles is the fix.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';

maplibregl.setWorkerUrl(workerUrl);
import './style.css';
import { buildNetwork, changedParams, loadCoupling, readScenario } from './consolidare';
import {
  BANDS,
  NO_DATA,
  ROAD_CASING_COLOUR,
  ROAD_COLOUR,
  ROAD_COUNTY_COLOUR,
  countyRoadCasingOpacity,
  countyRoadOpacity,
  countyRoadWidth,
  journeyPaint,
  majorRoadWidth,
  railLinePaint,
  railLineWidth,
  stationRadius,
} from './paint';

/**
 * The map answers one question: how long would it take to reach your county seat by bus,
 * and how much of that is waiting rather than moving.
 *
 * The scenario toggle is the point. Both scenarios run the same buses over the same
 * kilometres — the only difference is whether the feeder is timed to meet the trunk. Nothing
 * else on this page changes when you switch, which is what makes the comparison honest.
 *
 * Banded, not a gradient. The question is which side of "an hour and a half" a commune falls
 * on, not a smooth ramp nobody can read off a legend.
 */

type Timetable = 'uncoordinated' | 'pulsed';

const base = import.meta.env.BASE_URL;
const asset = (name: string) => `${base}data/${name}`;

const fmt = new Intl.NumberFormat('ro-RO');
const min = (v: number) => `${fmt.format(Math.round(v))} min`;
const bn = (v: number) => `${(v / 1e9).toFixed(2).replace('.', ',')} mld lei`;

function hash() {
  return new URLSearchParams(location.hash.slice(1));
}

function writeHash(timetable: Timetable) {
  // Only the timetable belongs to this page. The consolidation parameters in the hash are the
  // administrative simulator's, and are preserved untouched so the link keeps working in both
  // directions — a reader can carry one URL between the two maps.
  const params = hash();
  params.set('s', timetable);
  history.replaceState(null, '', `#${params}`);
}

async function main() {
  // The consolidation is no longer chosen here. It is read from the URL — the same hash the
  // administrative simulator writes — and the whole network is recomputed from it. A reader
  // who moves those sliders is looking at a different country, and this map now follows.
  const [summary, coupled] = await Promise.all([
    fetch(asset('summary.json')).then((r) => r.json()),
    loadCoupling(base),
  ]);

  const { params, pins } = readScenario(location.hash);
  const moved = changedParams(params);
  const net = buildNetwork(coupled, params, pins);

  let scenario: Timetable = hash().get('s') === 'pulsed' ? 'pulsed' : 'uncoordinated';

  // Free-flow road time is not service time. The pipeline divides by this factor before
  // calling anything a journey, and so must this — otherwise every commune reads about a
  // quarter closer to its centre than a bus could ever bring it.
  const factor = summary.serviceSpeedFactor as number;
  const waits = {
    uncoordinated: summary.access.waitUncoordinatedMin as number,
    pulsed: summary.access.waitPulsedMin as number,
  };

  // [uncoordinated, pulsed] minutes per UAT index, in administrativ's order — which is the
  // order uats.geojson is drawn in, so no join is needed at all.
  const journeys: Array<[number, number] | null> = net.journeys.map((j) => {
    if (!j.reachable) return null;
    const moving = (j.feeder + j.trunk) / factor;
    const wait = j.feeder === 0 && j.trunk === 0 ? 0 : 1;
    return [moving + wait * waits.uncoordinated, moving + wait * waits.pulsed];
  });
  const journeyOf = () => journeys;

  const map = new maplibregl.Map({
    container: 'map',
    // No basemap. The geometry is the map, it needs no tile provider, and the whole thing
    // stays a static site with nothing to call at runtime.
    style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#12141a' } }] },
    center: [25.0, 45.9],
    zoom: 6.1,
    attributionControl: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
  map.addControl(
    new maplibregl.AttributionControl({
      customAttribution: 'Geometrie: ANCPI / OpenStreetMap · Model: romania-reforms',
    }),
  );

  // MapLibre reports source and worker failures through this event and never throws. Without
  // it a dead worker or an unreachable tile is completely silent — which is exactly how a blank
  // map went unnoticed through several deploys.
  map.on('error', (e: unknown) => {
    console.error('map error', (e as { error?: Error }).error ?? e);
  });
  await new Promise<void>((resolve) => map.on('load', () => resolve()));

  const uats = await fetch(asset('uats.geojson')).then((r) => r.json());
  const counties = await fetch(asset('counties.geojson')).then((r) => r.json());

  // The journey times are keyed by polygon position, not by a property: uats.geojson carries
  // no properties at all. Writing them onto the features here keeps the paint expression
  // simple and the join in one place.
  // Journey times are written onto the features rather than looked up in the paint
  // expression, and rewritten whenever the consolidation changes. Setting the source data
  // again is what makes the map redraw.
  const applyJourneys = () => {
    const rows = journeyOf();
    uats.features.forEach((f: { properties: Record<string, number> }, i: number) => {
      const row = rows[i];
      f.properties = { idx: i, u: row ? row[0] : -1, p: row ? row[1] : -1 };
    });
    const source = map.getSource('uats') as maplibregl.GeoJSONSource | undefined;
    source?.setData(uats);
  };
  applyJourneys();

  map.addSource('uats', { type: 'geojson', data: uats });
  map.addSource('counties', { type: 'geojson', data: counties });

  const paint = (s: Timetable): maplibregl.DataDrivenPropertyValueSpecification<string> => {
    // Built and tested in ./paint.ts, against the same parser MapLibre uses.
    return journeyPaint(s === 'pulsed' ? 'p' : 'u') as never;
  };

  map.addLayer({
    id: 'uat-fill',
    type: 'fill',
    source: 'uats',
    paint: { 'fill-color': paint(scenario), 'fill-opacity': 0.85 },
  });
  map.addLayer({
    id: 'uat-line',
    type: 'line',
    source: 'uats',
    paint: { 'line-color': '#12141a', 'line-width': 0.3 },
  });
  map.addLayer({
    id: 'county-line',
    type: 'line',
    source: 'counties',
    paint: { 'line-color': '#7a8399', 'line-width': 0.9 },
  });

  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
  map.on('mousemove', 'uat-fill', (e: maplibregl.MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (!f) return;
    map.getCanvas().style.cursor = 'pointer';
    const i = f.properties!.idx as number;
    const row = journeyOf()[i];
    popup
      .setLngLat(e.lngLat)
      .setHTML(
        row
          ? `<strong>${min(row[scenario === 'pulsed' ? 1 : 0])}</strong> până la reședință` +
            `<br><span style="opacity:.7">fără corespondență ${min(row[0])} · cu ${min(row[1])}</span>`
          : 'Fără traseu rutier până la centru',
      )
      .addTo(map);
  });
  map.on('mouseleave', 'uat-fill', () => {
    map.getCanvas().style.cursor = '';
    popup.remove();
  });

  const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

  /**
   * Median journey, weighted by the people who make it.
   *
   * Weighted rather than plain because the map is per commune and the country is not: small
   * remote communes are numerous, so an unweighted median describes the map rather than the
   * population. The note under the toggle says which is which.
   */
  function weightedMedian(column: 0 | 1): number {
    const rows: Array<[number, number]> = [];
    let total = 0;
    journeys.forEach((row, i) => {
      if (!row) return;
      const people = coupled.data.population[i];
      rows.push([row[column], people]);
      total += people;
    });
    rows.sort((a, b) => a[0] - b[0]);
    let seen = 0;
    for (const [value, people] of rows) {
      seen += people;
      if (seen >= total / 2) return value;
    }
    return 0;
  }

  el('legend').innerHTML = [
    ...BANDS.map((b) => `<li><i style="background:${b.colour}"></i>${b.label}</li>`),
    `<li><i style="background:${NO_DATA}"></i>fără traseu rutier</li>`,
  ].join('');

  const a = summary.access;

  function renderStats() {
    const median = weightedMedian(scenario === 'pulsed' ? 1 : 0);
    el('stats').innerHTML = `
      <dt>Mediană, ponderată cu populația</dt><dd class="big">${min(median)}</dd>
      <dt>Așteptare la schimb</dt><dd>${min(
        scenario === 'pulsed' ? a.waitPulsedMin : a.waitUncoordinatedMin,
      )}</dd>
      <dt>Centre</dt><dd>${fmt.format(net.centres.length)}</dd>
      <dt>Fără traseu</dt><dd>${fmt.format(net.unroutable)}</dd>`;
    // The map is per commune and the median is per person. Most communes are small and far,
    // so the typical polygon is redder than the median — saying so stops the map and the
    // number looking like they disagree.
    el('scenario-note').textContent =
      scenario === 'pulsed'
        ? `Rabaterile sunt cronometrate să prindă trunchiul: se așteaptă ${min(a.waitPulsedMin)}. Aceleași autobuze, aceiași kilometri. Mediana este pe om, harta este pe comună — comunele mici și îndepărtate sunt multe, deci harta arată mai roșu decât mediana.`
        : `Fiecare traseu are orarul lui, deci așteptarea medie este jumătate din interval, ${min(a.waitUncoordinatedMin)}. Mediana este pe om, harta este pe comună.`;

    // Cost is still the pipeline's, computed for the DEFAULT consolidation. Journeys follow
    // the reader's scenario; money does not yet, because costing needs routes — with stops and
    // kilometres — and the route generator is not ported. Saying so is the only honest option:
    // a live map beside a frozen price reads as one number when it is two.
    el('cost').innerHTML = `
      <dt>Funcționare</dt><dd>${bn(summary.cost.annualRon.operating)}</dd>
      <dt>Total pe an</dt><dd class="big">${bn(summary.cost.annualRon.total)}</dd>
      <dt>Autobuze</dt><dd>${fmt.format(summary.cost.fleet.total)}</dd>`;

    // What scenario the reader is actually on, and how to change it. The page used to offer
    // five presets; consolidation belongs to the administrative simulator, and this now says
    // so rather than re-deciding it.
    el('consolidation-note').innerHTML =
      moved.length === 0
        ? `Ești pe parametrii impliciți ai reformei administrative: ` +
          `${fmt.format(net.centres.length)} de centre. ` +
          `<a href="../administrativ/">Construiește altă hartă</a> și adu linkul înapoi aici — ` +
          `pagina îl citește și recalculează toate traseele.`
        : `Scenariu adus din reforma administrativă: ${fmt.format(net.centres.length)} de ` +
          `centre, ${moved.length} parametri mutați. Traseele și timpii de mai sus sunt ` +
          `recalculate pentru acest scenariu.`;
  }

  // Roads. The network the travel-time model is measured over, so a reader can see why a
  // commune two ridges from its centre takes ninety minutes. Same files and same styling as
  // the administrative map — a bright core over a dark casing, because every hue is already
  // spoken for by the journey bands.
  //
  // Inserted BENEATH the commune outline so roads read as terrain under the result rather than
  // as another result on top of it. Fetched on first tick: 6,5 MB that most visits never want.
  const roadsLoaded = new Set<string>();

  async function showRoads(kind: 'major' | 'county', on: boolean) {
    const ids = kind === 'major' ? ['roads-casing', 'roads-line'] : ['county-casing', 'county-line-r'];
    if (on && !roadsLoaded.has(kind)) {
      const file = kind === 'major' ? 'roads.geojson' : 'roads-county.geojson';
      const toggle = el<HTMLInputElement>(kind === 'major' ? 'roads-toggle' : 'county-roads-toggle');
      toggle.disabled = true;
      const data = await fetch(asset(file)).then((r) => r.json());
      map.addSource(`src-${kind}`, { type: 'geojson', data });
      const width = kind === 'major' ? majorRoadWidth() : countyRoadWidth();
      map.addLayer(
        {
          id: ids[0],
          type: 'line',
          source: `src-${kind}`,
          paint: {
            'line-color': ROAD_CASING_COLOUR,
            'line-opacity': (kind === 'major' ? 0.75 : countyRoadCasingOpacity()) as never,
            'line-width': ['+', width, kind === 'major' ? 2 : 1.6] as never,
          },
        },
        'uat-line',
      );
      map.addLayer(
        {
          id: ids[1],
          type: 'line',
          source: `src-${kind}`,
          paint: {
            'line-color': kind === 'major' ? ROAD_COLOUR : ROAD_COUNTY_COLOUR,
            'line-opacity': (kind === 'major' ? 0.95 : countyRoadOpacity()) as never,
            'line-width': width as never,
          },
        },
        'uat-line',
      );
      roadsLoaded.add(kind);
      toggle.disabled = false;
    }
    for (const id of ids) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    }
  }

  for (const [id, kind] of [['roads-toggle', 'major'], ['county-roads-toggle', 'county']] as const) {
    const box = el<HTMLInputElement>(id);
    box.addEventListener('change', () => {
      void showRoads(kind, box.checked);
      const params = hash();
      params.set(kind === 'major' ? 'dn' : 'dj', box.checked ? '1' : '0');
      history.replaceState(null, '', `#${params}`);
    });
    if (hash().get(kind === 'major' ? 'dn' : 'dj') === '1') {
      box.checked = true;
      void showRoads(kind, true);
    }
  }

  el('roads-note').textContent =
    'Aceleași drumuri peste care este măsurat modelul de timp, din OpenStreetMap. Se încarcă ' +
    'doar când le ceri — 6,5 MB împreună. Cele județene apar estompat la nivel de țară: ' +
    'la zoom mic sunt o pată, nu o informație.';

  // Rail. Its geometry is 2 MB and most readers never open it, so the layers are fetched the
  // first time the box is ticked rather than on load. `railLoaded` guards the second tick.
  let railLoaded = false;
  const railToggle = el<HTMLInputElement>('rail-toggle');

  async function showRail(on: boolean) {
    if (on && !railLoaded) {
      railToggle.disabled = true;
      const [lines, stations] = await Promise.all([
        fetch(asset('rail-lines.geojson')).then((r) => r.json()),
        fetch(asset('rail-stations.geojson')).then((r) => r.json()),
      ]);
      map.addSource('rail', { type: 'geojson', data: lines });
      map.addSource('stations', { type: 'geojson', data: stations });
      // Coloured by signed line speed, using CFR's own tariff bands. The slow network is the
      // story, so it is the one that shows: class D track is drawn in the alarm colour.
      map.addLayer({
        id: 'rail-line',
        type: 'line',
        source: 'rail',
        paint: {
          'line-color': railLinePaint() as never,
          'line-width': railLineWidth() as never,
        },
      });
      map.addLayer({
        id: 'station-dot',
        type: 'circle',
        source: 'stations',
        paint: {
          'circle-radius': stationRadius() as never,
          'circle-color': '#e8eaf0',
          'circle-stroke-color': '#12141a',
          'circle-stroke-width': 0.6,
        },
      });
      railLoaded = true;
      railToggle.disabled = false;
    }
    for (const id of ['rail-line', 'station-dot']) {
      if (map.getLayer(id)) {
        map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
      }
    }
  }

  function renderFares() {
    const f = summary.fares;
    if (!f) return;
    el('fares').innerHTML = `
      <dt>Venit din bilete</dt><dd>${bn(f.central.revenueRon)}</dd>
      <dt>Rămâne de acoperit</dt><dd class="big">${bn(f.central.subsidyRon)}</dd>
      <dt>Pe om, pe an</dt><dd>${fmt.format(
        Math.round(f.central.subsidyPerPersonYearRon),
      )} lei</dd>
      <dt>Acoperire din bilete</dt><dd>${(f.central.recovery * 100).toFixed(0)}%</dd>`;

    // The band, not just the central case. Occupancy is assumed and it is the only number that
    // moves this result, so quoting one recovery ratio alone would read as a measurement.
    const lo = f.band[0];
    const hi = f.band[f.band.length - 1];
    el('fares-note').textContent =
      `Cifra depinde de cât de plin merge autobuzul, iar asta este presupus. La ` +
      `${(lo.loadFactor * 100).toFixed(0)}% ocupare biletele acoperă ` +
      `${(lo.recovery * 100).toFixed(0)}% și rămân ${bn(lo.subsidyRon)}; la ` +
      `${(hi.loadFactor * 100).toFixed(0)}% acoperă ${(hi.recovery * 100).toFixed(0)}% și rămân ` +
      `${bn(hi.subsidyRon)}. Tariful este cel aprobat de consilii județene; ocuparea nu are ` +
      `cum să aibă sursă, pentru că serviciul nu există. Pentru comparație, Movia din Danemarca ` +
      `acoperă circa ${(f.benchmark.moviaRecovery * 100).toFixed(0)}% din bilete.`;
  }

  function renderRail() {
    const r = summary.rail;
    if (!r) return;
    const hours = (v: number) => `${fmt.format(Math.round(v / 1000))} mii ore`;
    el('rail').innerHTML = `
      <dt>Linie de călători</dt><dd>${fmt.format(Math.round(r.network.passengerLineKm))} km</dd>
      <dt>Gări și halte</dt><dd>${fmt.format(r.network.stationCount)}</dd>
      <dt>Viteză comercială azi</dt><dd>${fmt.format(r.conditions.as_is.commercialKmh)} km/h</dd>
      <dt>După reabilitare</dt><dd class="big">${fmt.format(
        r.conditions.rehabilitated.commercialKmh,
      )} km/h</dd>
      <dt>O oră de călător costă</dt><dd>${fmt.format(
        Math.round(r.rehabilitation.ronPerPassengerHour),
      )} lei</dd>
      <dt>UAT-uri mai rapide cu trenul</dt><dd>${fmt.format(
        a.rail.uatsFasterByRail,
      )} din ${fmt.format(a.rail.uatsWithOption)}</dd>`;

    const seatsOff = r.seats.considered - r.seats.withinWalkOfStation;
    el('rail-note').textContent =
      `Linia este colorată după viteza semnalizată: roșu sub 51 km/h, verde peste 121 — ` +
      `pragurile după care CFR își tarifează propria rețea. ${seatsOff} din ` +
      `${r.seats.considered} de reședințe au gara la peste ${r.seats.walkKm} km, deci au nevoie ` +
      `de autobuz ca să ajungă la propria cale ferată. ` +
      `Doar ${fmt.format(a.rail.uatsWithOption)} de UAT-uri au gară la mai puțin de ` +
      `${r.seats.walkKm} km la ambele capete ale drumului, iar pentru ` +
      `${fmt.format(a.rail.uatsFasterByRail)} dintre ele trenul este mai rapid decât autobuzul ` +
      `— ${fmt.format(a.rail.peopleFasterByRail)} de oameni. Mediana pe țară scade de la ` +
      `${min(a.medianPulsedMin)} la ${min(a.rail.medianBestPulsedMin)}: calea ferată ajunge la ` +
      `puține locuri și le schimbă mult.`;

    // The comparison the rail layer exists to make. Kept next to the number rather than in a
    // footnote, and stated as a unit price so nobody reads it as one mode replacing the other.
    el('rail-compare').innerHTML =
      `<strong>Ce cumperi cu un minut.</strong> Reabilitarea plătește ` +
      `${fmt.format(Math.round(r.rehabilitation.ronPerPassengerHour))} lei pentru o oră de ` +
      `călător. Corespondența dintre rabatere și trunchi scutește ` +
      `${fmt.format(r.againstPulsing.pulseSavingMin)} de minute de fiecare călătorie fără niciun ` +
      `leu de investiție — aceleași autobuze, aceiași kilometri. Aceleași ` +
      `${hours(r.againstPulsing.passengerHoursPerYear)} cumpărate prin reabilitare ar costa ` +
      `${bn(r.againstPulsing.equivalentRailSpendRon)} pe an, mai mult decât costă toată rețeaua ` +
      `de autobuze. Sunt prețuri unitare, nu doi moduri de a servi aceiași oameni: comparația ` +
      `spune în ce ordine se cheltuie, nu că reabilitarea ar fi inutilă.`;
  }

  railToggle.addEventListener('change', () => {
    void showRail(railToggle.checked);
    const params = hash();
    params.set('r', railToggle.checked ? '1' : '0');
    history.replaceState(null, '', `#${params}`);
  });
  if (hash().get('r') === '1') {
    railToggle.checked = true;
    void showRail(true);
  }
  renderRail();
  renderFares();

  el('caveats').innerHTML = summary.limitations
    .filter((l: { severity: string }) => l.severity === 'blocking' || l.severity === 'material')
    // Raised from five when rail landed: the page now carries three models' caveats, and a
    // short list would have silently dropped the bus ones to make room for the new arrivals.
    .slice(0, 8)
    .map((l: { text: string }) => `<li>${l.text}</li>`)
    .join('');

  document.querySelectorAll<HTMLButtonElement>('#toggle button').forEach((button) => {
    button.addEventListener('click', () => {
      scenario = button.dataset.scenario as Timetable;
      document
        .querySelectorAll('#toggle button')
        .forEach((b) => b.classList.toggle('on', b === button));
      map.setPaintProperty('uat-fill', 'fill-color', paint(scenario));
      writeHash(scenario);
      renderStats();
    });
    button.classList.toggle('on', button.dataset.scenario === scenario);
  });

  writeHash(scenario);
  renderStats();
  // The geometry is several MB and the map is blank until it lands. `role="status"` means a
  // screen reader announces it without stealing focus; removing the node is what tells a
  // sighted reader the blank map is finished rather than broken.
  el('loading').remove();
}

/** Is there a WebGL context at all? Without one MapLibre cannot draw and says so only in the
 *  console — which looks exactly like "the map is not visible" and nothing else. */
function webglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

function fail(title: string, detail: string) {
  // Keep the way out. Replacing the whole panel would delete the link back to the other
  // simulators at the one moment a reader is stuck on a page that shows nothing.
  //
  // And show the actual message. A generic "could not load the data" sent me hunting for a
  // missing file when the real fault was a malformed paint expression that MapLibre had
  // rejected by name — the map stayed blank and the page said nothing useful about why.
  document.getElementById('panel')!.innerHTML =
    '<a class="up" href="../">← Toate simulatoarele</a>' +
    `<h1>${title}</h1><p class="lede">${detail}</p>`;
}

if (!webglAvailable()) {
  fail(
    'Harta are nevoie de WebGL',
    'Browserul nu oferă un context WebGL, deci harta nu poate fi desenată. Cifrele din model ' +
      'sunt în data/, iar pagina rămâne inutilizabilă până când WebGL este activat.',
  );
} else {
  main().catch((error: unknown) => {
    console.error(error);
    const message = error instanceof Error ? error.message : String(error);
    fail(
      'Nu s-au putut încărca datele',
      `<code>${message.replace(/</g, '&lt;')}</code><br><br>Dacă rulezi local: ` +
        '<code>npm run build</code> în simulators/transport/app după ce ai generat datele.',
    );
  });
}

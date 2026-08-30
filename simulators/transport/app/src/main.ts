import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './style.css';

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

type Scenario = 'uncoordinated' | 'pulsed';

const BANDS: Array<{ upTo: number; colour: string; label: string }> = [
  { upTo: 45, colour: '#1a9850', label: 'sub 45 min' },
  { upTo: 60, colour: '#a6d96a', label: '45–60 min' },
  { upTo: 90, colour: '#fee08b', label: '60–90 min' },
  { upTo: 120, colour: '#fdae61', label: '90–120 min' },
  { upTo: Infinity, colour: '#d73027', label: 'peste 120 min' },
];
const NO_DATA = '#3a3f4d';

const base = import.meta.env.BASE_URL;
const asset = (name: string) => `${base}data/${name}`;

const fmt = new Intl.NumberFormat('ro-RO');
const min = (v: number) => `${fmt.format(Math.round(v))} min`;
const pct = (v: number) => `${v.toFixed(1).replace('.', ',')}%`;
const bn = (v: number) => `${(v / 1e9).toFixed(2).replace('.', ',')} mld lei`;

function scenarioFromHash(): Scenario {
  return new URLSearchParams(location.hash.slice(1)).get('s') === 'pulsed'
    ? 'pulsed'
    : 'uncoordinated';
}

function writeHash(scenario: Scenario) {
  // A scenario is a link you can paste into an argument — that is the whole point of the
  // repository, so the toggle lives in the URL rather than only in memory.
  const params = new URLSearchParams(location.hash.slice(1));
  params.set('s', scenario);
  history.replaceState(null, '', `#${params}`);
}

async function main() {
  const [summary, journey] = await Promise.all([
    fetch(asset('summary.json')).then((r) => r.json()),
    fetch(asset('journey.json')).then((r) => r.json() as Promise<Array<[number, number] | null>>),
  ]);

  let scenario = scenarioFromHash();

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

  await new Promise<void>((resolve) => map.on('load', () => resolve()));

  const uats = await fetch(asset('uats.geojson')).then((r) => r.json());
  const counties = await fetch(asset('counties.geojson')).then((r) => r.json());

  // The journey times are keyed by polygon position, not by a property: uats.geojson carries
  // no properties at all. Writing them onto the features here keeps the paint expression
  // simple and the join in one place.
  uats.features.forEach((f: { properties: Record<string, number> }, i: number) => {
    const row = journey[i];
    f.properties = {
      idx: i,
      u: row ? row[0] : -1,
      p: row ? row[1] : -1,
    };
  });

  map.addSource('uats', { type: 'geojson', data: uats });
  map.addSource('counties', { type: 'geojson', data: counties });

  const paint = (s: Scenario): maplibregl.DataDrivenPropertyValueSpecification<string> => {
    const key = s === 'pulsed' ? 'p' : 'u';
    const steps: unknown[] = ['step', ['get', key], NO_DATA];
    for (const band of BANDS) {
      if (band.upTo === Infinity) break;
      steps.push(band.upTo, band.colour);
    }
    steps.push(BANDS[BANDS.length - 1].colour);
    // Anything below zero is a UAT with no journey — the delta communes and Bucharest.
    return ['case', ['<', ['get', key], 0], NO_DATA, steps] as never;
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
    const row = journey[i];
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

  el('legend').innerHTML = [
    ...BANDS.map((b) => `<li><i style="background:${b.colour}"></i>${b.label}</li>`),
    `<li><i style="background:${NO_DATA}"></i>fără traseu rutier</li>`,
  ].join('');

  const a = summary.access;
  const c = summary.cost;

  function renderStats() {
    const median = scenario === 'pulsed' ? a.medianPulsedMin : a.medianUncoordinatedMin;
    const key = scenario === 'pulsed' ? 'pulsedPct' : 'uncoordinatedPct';
    const saved = a.medianUncoordinatedMin - a.medianPulsedMin;
    el('stats').innerHTML = `
      <dt>Călătorie mediană</dt><dd class="big">${min(median)}</dd>
      <dt>Așteptare la schimb</dt><dd>${min(
        scenario === 'pulsed' ? a.waitPulsedMin : a.waitUncoordinatedMin,
      )}</dd>
      <dt>Populație sub 60 min</dt><dd>${pct(a.within['60'][key])}</dd>
      <dt>Populație sub 90 min</dt><dd>${pct(a.within['90'][key])}</dd>
      <dt>Populație sub 120 min</dt><dd>${pct(a.within['120'][key])}</dd>`;
    el('scenario-note').textContent =
      scenario === 'pulsed'
        ? `Rabaterile sunt cronometrate să prindă trunchiul: se așteaptă ${min(a.waitPulsedMin)}. Aceleași autobuze, aceiași kilometri — se câștigă ${min(saved)} din orar.`
        : `Fiecare traseu are orarul lui, deci așteptarea medie este jumătate din interval, ${min(a.waitUncoordinatedMin)}.`;
  }

  el('cost').innerHTML = `
    <dt>Funcționare</dt><dd>${bn(c.annualRon.operating)}</dd>
    <dt>Investiție anualizată</dt><dd>${bn(c.annualRon.capital)}</dd>
    <dt>Total</dt><dd class="big">${bn(c.annualRon.total)}</dd>
    <dt>Autobuze</dt><dd>${fmt.format(c.fleet.total)}</dd>
    <dt>Economia administrativă revendicată</dt><dd>${bn(summary.ledger.administrativeSaving)}</dd>`;

  el('caveats').innerHTML = summary.limitations
    .filter((l: { severity: string }) => l.severity === 'blocking' || l.severity === 'material')
    .slice(0, 5)
    .map((l: { text: string }) => `<li>${l.text}</li>`)
    .join('');

  document.querySelectorAll<HTMLButtonElement>('#toggle button').forEach((button) => {
    button.addEventListener('click', () => {
      scenario = button.dataset.scenario as Scenario;
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
}

main().catch((error) => {
  console.error(error);
  document.getElementById('panel')!.innerHTML =
    '<h1>Nu s-au putut încărca datele</h1><p class="lede">Rulează <code>npm run build</code> în simulators/transport/app după ce ai generat datele.</p>';
});

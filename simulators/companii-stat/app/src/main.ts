import './style.css';
import {
  TIER_LABELS,
  absorbedRows,
  filtered,
  groupByCounty,
  groupRegistryByCluster,
  groupRegistryByCounty,
  operatorRows,
  reduction,
  registryCompanies,
  sortBy,
  type AbsorbedRow,
  type Cluster,
  type Document,
  type OperatorRow,
  type RegistryDocument,
  type Tier,
} from './model';

const DOC_URL = 'data/companii-stat.json';
const REGISTRY_URL = 'data/companii-registry.json';

/** Fetch JSON, but fail with a readable hint when the server answers with an HTML page —
 *  the usual symptom of starting vite without the predev data copy (npx vite) or serving a
 *  dist without its data/ folder. */
async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status} pentru ${url}`);
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('text/html')) {
    throw new Error(
      `Serverul a întors o pagină în loc de date (${url} lipsește). Pornește cu \`npm run dev\` din simulators/companii-stat/app — pasul predev copiază datele în public/data.`,
    );
  }
  return response.json() as Promise<T>;
}

const $ = <T extends HTMLElement>(selector: string): T => {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`missing element ${selector}`);
  return el;
};

let doc: Document;
let selectedTiers = new Set<Tier>(['regional', 'local', 'national', 'other']);
let sortKey: 'name' | 'companies' | 'employees' | 'revenue' | 'subsidy' | 'reduction' =
  'companies';
let sortDirection: 'asc' | 'desc' = 'desc';
let selectedRegion = 0;

type ListKey = 'all' | 'regional' | 'operators' | 'absorbed' | 'loss' | 'subsidised' | 'micro';
let registryDoc: RegistryDocument | null = null;
let registryPromise: Promise<RegistryDocument> | null = null;
let openList: ListKey | null = null;

const loadRegistry = (): Promise<RegistryDocument> => {
  registryPromise ??= fetchJSON<RegistryDocument>(REGISTRY_URL)
    .then((payload) => {
      registryDoc = payload;
      return payload;
    });
  return registryPromise;
};

function setText(id: string, value: string): void {
  $(`#${id}`).textContent = value;
}

function renderStats(): void {
  const s = doc.summary;
  setText('stat-total', s.companies.toLocaleString('ro-RO'));
  setText('stat-clusters', s.regionalClusters.toLocaleString('ro-RO'));
  setText('stat-merge', s.companiesInRegionalClusters.toLocaleString('ro-RO'));
  setText('stat-after', s.operatorsProposedOnEightRegions.toLocaleString('ro-RO'));
  setText('stat-cut', `−${s.reductionPercent.toLocaleString('ro-RO')}%`);
  setText('stat-micro', s.microUnder20.toLocaleString('ro-RO'));
  setText('stat-loss', s.lossMaking.toLocaleString('ro-RO'));
  setText('stat-subsidy', s.subsidisedCount.toLocaleString('ro-RO'));
  setText('stat-subsidy-ron', s.subsidyRon.toLocaleString('ro-RO'));
  for (const span of document.querySelectorAll('.micro-count')) {
    span.textContent = s.microUnder20.toLocaleString('ro-RO');
  }
  $('#stats').hidden = false;
  $('#stats-note').hidden = false;
}

function tierCell(cluster: Cluster): string {
  const label = TIER_LABELS[cluster.tier];
  return `<span class="tier-tag tier-tag--${cluster.tier}">${label}</span>`;
}

function microCell(cluster: Cluster): string {
  if (cluster.micro === 0) return '<span class="muted">—</span>';
  return cluster.micro.toLocaleString('ro-RO');
}

function buildRows(): void {
  const sorted = sortBy(filtered(doc, selectedTiers), sortKey, sortDirection);
  const tbody = $('#cluster-rows');
  tbody.replaceChildren();
  for (const cluster of sorted) {
    const tr = document.createElement('tr');
    tr.tabIndex = 0;
    tr.dataset.caen = cluster.caen;
    tr.innerHTML = `
      <td class="num">${cluster.caen}</td>
      <th scope="row">${cluster.name}</th>
      <td>${tierCell(cluster)}</td>
      <td class="num">${cluster.companies.toLocaleString('ro-RO')}</td>
      <td class="num">${cluster.proposed.toLocaleString('ro-RO')}</td>
      <td class="num">−${reduction(cluster).toLocaleString('ro-RO')}%</td>
      <td class="num">${cluster.employees.toLocaleString('ro-RO')}</td>
      <td class="num">${cluster.revenueRon.toLocaleString('ro-RO')}</td>
      <td class="num">${cluster.subsidyRon.toLocaleString('ro-RO')}</td>
      <td class="num">${cluster.lossCount.toLocaleString('ro-RO')}</td>
      <td class="num">${microCell(cluster)}</td>`;
    tr.addEventListener('click', () => selectCluster(cluster));
    tr.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectCluster(cluster);
      }
    });
    tbody.appendChild(tr);
  }
  for (const header of document.querySelectorAll<HTMLTableCellElement>('th.sortable')) {
    const key = header.dataset.key as typeof sortKey;
    header.setAttribute(
      'aria-sort',
      key === sortKey ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none',
    );
  }
}

function selectCluster(cluster: Cluster): void {
  for (const row of document.querySelectorAll<HTMLTableRowElement>('#cluster-rows tr')) {
    row.classList.toggle('on', row.dataset.caen === cluster.caen);
  }
  $('#detail-title').hidden = false;
  $('#detail-note').hidden = false;
  const detail = $('#operator-detail');
  if (cluster.tier === 'regional' && cluster.regions && cluster.regions.length > 0) {
    $('#detail-note').textContent =
      `${cluster.name} (${cluster.caen}): ${cluster.companies.toLocaleString('ro-RO')} de entități, propuse ${cluster.proposed.toLocaleString('ro-RO')} — comasarea pe regiuni, mai jos. Venituri agregate ${cluster.revenueRon.toLocaleString('ro-RO')} RON (MFin 2025), dintre care ${cluster.lossCount.toLocaleString('ro-RO')} companii în pierdere; ${cluster.subsidisedCount.toLocaleString('ro-RO')} sunt subvenționate, cu ${cluster.subsidyRon.toLocaleString('ro-RO')} RON raportați. ${cluster.distinctOwners.toLocaleString('ro-RO')} de proprietari distincți. Regula de sediu și de nucleu este scrisă ca presupunere în datele paginii, nu este din sursă.`;
    detail.hidden = false;
    selectedRegion = 0;
    const picker = $('#region-picker');
    picker.replaceChildren();
    cluster.regions.forEach((region, index) => {
      const button = document.createElement('button');
      button.className = 'region';
      button.dataset.index = String(index);
      button.textContent = `${region.region} (${region.absorbedCount.toLocaleString('ro-RO')})`;
      button.addEventListener('click', () => {
        selectedRegion = index;
        renderRegion(cluster);
      });
      picker.appendChild(button);
    });
    renderRegion(cluster);
  } else {
    detail.hidden = true;
    const headcount = cluster.headcountKnown > 0
      ? `; efectivul este raportat doar de ${cluster.headcountKnown.toLocaleString('ro-RO')} dintre ele, deci cei ${cluster.employees.toLocaleString('ro-RO')} de angajați sunt o limită inferioară`
      : '';
    $('#detail-note').textContent =
      `${cluster.name} (${cluster.caen}): ${cluster.companies.toLocaleString('ro-RO')} de entități, lăsate nemodificate — nivelul „${TIER_LABELS[cluster.tier]}”${headcount}.`;
  }
}

/** The before/after view for one region: absorbed companies grouped by county on the
 *  left, the single remaining operator on the right, one arrow per county. */
function renderRegion(cluster: Cluster): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>('#region-picker button')) {
    button.classList.toggle('on', button.dataset.index === String(selectedRegion));
  }
  const region = cluster.regions![selectedRegion];
  const groups = groupByCounty(region);
  const flux = $('#flux');
  flux.replaceChildren();

  const headLeft = document.createElement('h3');
  headLeft.className = 'flux-head';
  headLeft.textContent =
    `Astăzi — ${region.absorbedCount.toLocaleString('ro-RO')} ${region.absorbedCount === 1 ? 'entitate' : 'entități'}`;
  flux.appendChild(headLeft);
  const headRight = document.createElement('h3');
  headRight.className = 'flux-head flux-head--right';
  headRight.textContent = 'După — un operator pe regiune';
  flux.appendChild(headRight);

  let row = 2;
  for (const group of groups) {
    const cell = document.createElement('div');
    cell.className = 'county-group';
    cell.style.gridRow = String(row);
    const heading = document.createElement('div');
    heading.className = 'county-head';
    heading.textContent = `${group.county ?? 'fără județ'} (${group.companies.length.toLocaleString('ro-RO')})`;
    cell.appendChild(heading);
    for (const company of group.companies) {
      const chip = document.createElement('div');
      chip.className = 'company';
      chip.textContent = company.name;
      if (company.owner) {
        const owner = document.createElement('span');
        owner.className = 'owner';
        owner.textContent = ` — proprietar: ${company.owner}`;
        chip.appendChild(owner);
      }
      cell.appendChild(chip);
    }
    flux.appendChild(cell);

    const arrow = document.createElement('div');
    arrow.className = 'arrow';
    arrow.style.gridRow = String(row);
    arrow.textContent = `${group.companies.length.toLocaleString('ro-RO')} →`;
    flux.appendChild(arrow);
    row += 1;
  }

  const operator = document.createElement('div');
  operator.className = 'operator';
  operator.style.gridRow = `2 / span ${Math.max(1, groups.length)}`;
  if (region.absorber) {
    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = region.absorber.name;
    const seat = document.createElement('div');
    seat.className = 'small';
    seat.textContent = `județul ${region.seatCounty} — ${region.absorber.employees.toLocaleString('ro-RO')} angajați`;
    const one = document.createElement('div');
    one.className = 'big';
    one.textContent = '1';
    const what = document.createElement('div');
    what.className = 'small';
    what.textContent = `operator regional, în loc de ${region.absorbedCount.toLocaleString('ro-RO')}`;
    const points = document.createElement('div');
    points.className = 'small';
    points.textContent = 'punctele de lucru județene pot rămâne ca sucursale, fără aparat de conducere propriu';
    operator.append(name, seat, one, what, points);
  } else {
    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = 'Nucleul rămâne nenumit';
    const seat = document.createElement('div');
    seat.className = 'small';
    seat.textContent = `județul ${region.seatCounty} — niciun efectiv raportat`;
    operator.append(name, seat);
  }
  flux.appendChild(operator);
}

const ron = (value: number | null): string =>
  value === null ? '—' : Math.abs(value).toLocaleString('ro-RO');

function statRow(text: string, meta: string): HTMLElement {
  const row = document.createElement('div');
  row.className = 'stat-row';
  const name = document.createElement('span');
  name.className = 'stat-row-name';
  name.textContent = text;
  row.appendChild(name);
  if (meta) {
    const muted = document.createElement('span');
    muted.className = 'muted';
    muted.textContent = meta;
    row.appendChild(muted);
  }
  return row;
}

function statGroup(label: string, rows: HTMLElement[]): HTMLElement {
  const group = document.createElement('div');
  group.className = 'stat-group';
  const head = document.createElement('div');
  head.className = 'stat-group-head';
  head.textContent = label;
  group.appendChild(head);
  group.append(...rows);
  return group;
}

/** The list behind one summary card: operators and absorbed come from the payload, the
 *  registry-backed kinds (all / regional / loss / subsidised / micro) from the lazy file. */
async function renderStatList(key: ListKey): Promise<void> {
  const body = $('#stat-list-body');
  body.replaceChildren();
  const titleEl = $('#stat-list-title');
  const noteEl = $('#stat-list-note');

  if (key === 'operators' || key === 'absorbed') {
    if (key === 'operators') {
      const rows = operatorRows(doc);
      const named = rows.filter((row) => row.name !== null).length;
      titleEl.textContent = `Operatorii propuși: ${rows.length.toLocaleString('ro-RO')} — câte unul pe regiune de dezvoltare`;
      noteEl.textContent = named < rows.length
        ? `${named.toLocaleString('ro-RO')} au un operator numit; în celelalte ${rows.length - named} regiuni nu există azi nicio companie a activității, deci operatorul pornește de la zero.`
        : 'Fiecare regiune are un operator numit — regula de nucleu este scrisă în datele paginii, nu în sursă.';
      noteEl.hidden = false;
      const byCluster = new Map<string, OperatorRow[]>();
      for (const row of rows) {
        byCluster.set(row.cluster, [...(byCluster.get(row.cluster) ?? []), row]);
      }
      for (const [clusterName, list] of byCluster) {
        const rowsEl = list.map((row) =>
          statRow(
            row.name ?? 'nicio companie în activitate',
            ` — ${row.region}${row.employees !== null ? ` · ${row.employees.toLocaleString('ro-RO')} ang.` : ''}`,
          ),
        );
        body.appendChild(statGroup(clusterName, rowsEl));
      }
    } else {
      const rows = absorbedRows(doc);
      titleEl.textContent = `Companiile absorbite în operatorii regionali (${rows.length.toLocaleString('ro-RO')})`;
      noteEl.textContent =
        'Unele regiuni nu au nicio companie a activității; lista numără companiile care există azi și dispar în operatorul regional.';
      noteEl.hidden = false;
      const byCluster = new Map<string, AbsorbedRow[]>();
      for (const row of rows) {
        byCluster.set(row.cluster, [...(byCluster.get(row.cluster) ?? []), row]);
      }
      for (const [clusterName, list] of byCluster) {
        const rowsEl = list.map((row) =>
          statRow(row.name, ` — ${row.county ?? 'fără județ'}${row.owner ? ` · ${row.owner}` : ''}`),
        );
        body.appendChild(statGroup(clusterName, rowsEl));
      }
    }
  } else {
    await loadRegistry();
    const rows = registryCompanies(registryDoc!, key);
    titleEl.textContent = {
      all: `${rows.length.toLocaleString('ro-RO')} de companii în evidență`,
      regional: `${rows.length.toLocaleString('ro-RO')} de companii în activitățile de rețea`,
      loss: `${rows.length.toLocaleString('ro-RO')} de companii cu rând financiar în pierdere (MFin 2025)`,
      subsidised: `${rows.length.toLocaleString('ro-RO')} de companii subvenționate (2025)`,
      micro: `${rows.length.toLocaleString('ro-RO')} de companii cu sub 20 de angajați`,
    }[key];
    const note = {
      all: 'Întregul registru al companiilor de stat, grupate pe județul de înregistrare.',
      regional: 'Companiile din activitățile de rețea regionalizabile, grupate pe activitate.',
      loss: 'Doar companiile cu rând financiar în bilanțurile MFin 2025; cele fără rând nu apar — o limită inferioară.',
      subsidised: 'Subvenția raportată per firmă în Anexele SFA 2025; o companie poate primi subvenții care nu apar aici.',
      micro: 'Efectivul raportat: întâi bilanțurile MFin, apoi formularul. Companiile fără efectiv raportat nu apar.',
    }[key];
    noteEl.textContent = note;
    noteEl.hidden = false;
    if (key === 'regional') {
      for (const group of groupRegistryByCluster(rows)) {
        const rowsEl = group.companies.map((c) => statRow(c.name, c.county ? ` — ${c.county}` : ''));
        body.appendChild(statGroup(`${group.cluster} (${group.companies.length.toLocaleString('ro-RO')})`, rowsEl));
      }
    } else {
      for (const group of groupRegistryByCounty(rows)) {
        const label = `${group.county ?? 'fără județ'} (${group.companies.length.toLocaleString('ro-RO')})`;
        const rowsEl = group.companies.map((c) => {
          if (key === 'loss') {
            return statRow(c.name, ` — ${c.owner ?? 'fără proprietar raportat'} · −${ron(c.netResultRon)} RON`);
          }
          if (key === 'subsidised') {
            return statRow(c.name, ` — ${c.owner ?? 'fără proprietar raportat'} · ${ron(c.subsidyRon)} RON`);
          }
          if (key === 'micro') {
            return statRow(c.name, ` — ${c.county ?? 'fără județ'} · ${c.employees?.toLocaleString('ro-RO')} ang.`);
          }
          return statRow(
            c.name,
            ` — ${c.owner ?? 'fără proprietar raportat'}${c.employees !== null ? ` · ${c.employees.toLocaleString('ro-RO')} ang.` : ''}`,
          );
        });
        body.appendChild(statGroup(label, rowsEl));
      }
    }
  }
  $('#stat-list').hidden = false;
}

function closeStatList(): void {
  openList = null;
  $('#stat-list').hidden = true;
  for (const el of document.querySelectorAll<HTMLElement>('[data-list]')) {
    el.classList.remove('on');
  }
}

function toggleStatList(key: ListKey): void {
  if (openList === key) {
    closeStatList();
    return;
  }
  openList = key;
  for (const el of document.querySelectorAll<HTMLElement>('[data-list]')) {
    el.classList.toggle('on', el.dataset.list === key);
  }
  void renderStatList(key).catch((error: unknown) => {
    $('#stat-list-title').textContent = 'Lista nu s-a putut încărca';
    $('#stat-list-note').textContent = error instanceof Error ? error.message : String(error);
    $('#stat-list-note').hidden = false;
    $('#stat-list').hidden = false;
  });
}

function wireStatLists(): void {
  for (const el of document.querySelectorAll<HTMLElement>('[data-list]')) {
    const key = el.dataset.list as ListKey;
    el.addEventListener('click', () => toggleStatList(key));
    el.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleStatList(key);
      }
    });
  }
  $('#stat-list-close').addEventListener('click', closeStatList);
}

function renderFusions(): void {  if (doc.inFlightMergers.length === 0) return;
  $('#fusions-title').hidden = false;
  $('#fusions-note').hidden = false;
  $('#fusions-scroll').hidden = false;
  const tbody = $('#fusions-rows');
  tbody.replaceChildren();
  for (const merger of doc.inFlightMergers) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <th scope="row">${merger.name}</th>
      <td class="num">${merger.caen ?? '—'}</td>
      <td>${merger.status}</td>`;
    tbody.appendChild(tr);
  }
}

function renderCaveats(): void {
  const list = $('#caveat-list');
  list.replaceChildren();
  for (const limitation of doc.limitations) {
    const li = document.createElement('li');
    li.innerHTML = `<span class="severity severity--${limitation.severity}">${limitation.severity}</span> ${limitation.text}`;
    list.appendChild(li);
  }
  $('#caveats').hidden = false;
}

function wireControls(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>('button.tier')) {
    button.addEventListener('click', () => {
      const tier = button.dataset.tier as 'all' | Tier;
      for (const other of document.querySelectorAll<HTMLButtonElement>('button.tier')) {
        other.classList.toggle('on', other === button);
      }
      selectedTiers =
        tier === 'all'
          ? new Set<Tier>(['regional', 'local', 'national', 'other'])
          : new Set<Tier>([tier]);
      $('#detail-title').hidden = true;
      $('#detail-note').hidden = true;
      buildRows();
    });
  }
  for (const header of document.querySelectorAll<HTMLTableCellElement>('th.sortable')) {
    header.addEventListener('click', () => {
      const key = header.dataset.key as typeof sortKey;
      if (key === sortKey) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = key;
        sortDirection = key === 'name' ? 'asc' : 'desc';
      }
      buildRows();
    });
  }
}

async function main(): Promise<void> {
  try {
    doc = await fetchJSON<Document>(DOC_URL);
  } catch (error) {
    const loading = $('.loading');
    loading.textContent = `Nu s-au putut încărca datele: ${error instanceof Error ? error.message : String(error)}`;
    loading.classList.add('error');
    return;
  }
  $('.loading').hidden = true;
  $('#clusters').hidden = false;
  renderStats();
  wireControls();
  wireStatLists();
  buildRows();
  renderCaveats();
  renderFusions();
  $('#argument').hidden = false;
}

void main();

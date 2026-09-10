import './style.css';
import {
  TIER_LABELS,
  absorbedOffices,
  filtered,
  groupOfficesByFamily,
  officeList,
  proposedDirections,
  reduction,
  regionsOf,
  sortBy,
  type Document,
  type Family,
  type OfficeKind,
  type OfficeRegistryDocument,
  type OfficeRow,
  type ProposedDirection,
  type Tier,
} from './model';

const DOC_URL = 'data/deconcentrare.json';
const REGISTRY_URL = 'data/deconcentrare-registry.json';

const $ = <T extends HTMLElement>(selector: string): T => {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`missing element ${selector}`);
  return el;
};

/** Fetch JSON, but fail with a readable hint when the server answers with an HTML page —
 *  the usual symptom of starting vite without the predev data copy (npx vite) or serving a
 *  dist without its data/ folder. */
async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status} pentru ${url}`);
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('text/html')) {
    throw new Error(
      `Serverul a întors o pagină în loc de date (${url} lipsește). Pornește cu \`npm run dev\` din simulators/deconcentrare/app — pasul predev copiază datele în public/data.`,
    );
  }
  return response.json() as Promise<T>;
}

let doc: Document;
let selectedTiers = new Set<Tier>(['regional', 'regional-de-facto', 'special']);
let sortKey: 'name' | 'officesToday' | 'officesProposed' | 'reduction' = 'officesToday';
let sortDirection: 'asc' | 'desc' = 'desc';

type ListKey = 'all' | 'regional' | 'directions' | 'absorbed';
let registryDoc: OfficeRegistryDocument | null = null;
let registryPromise: Promise<OfficeRegistryDocument> | null = null;
let openList: ListKey | null = null;

const loadRegistry = (): Promise<OfficeRegistryDocument> => {
  registryPromise ??= fetchJSON<OfficeRegistryDocument>(REGISTRY_URL)
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
  setText('stat-total', s.deconcentratedOfficesTotal.toLocaleString('ro-RO'));
  setText('stat-families', s.regionalFamilies.toLocaleString('ro-RO'));
  setText('stat-merge', s.officesTodayInRegionalFamilies.toLocaleString('ro-RO'));
  setText('stat-after', s.officesProposedOnEightRegions.toLocaleString('ro-RO'));
  setText('stat-cut', `−${s.reductionPercent.toLocaleString('ro-RO')}%`);
  $('#stats').hidden = false;
  $('#stats-note').hidden = false;
}

function tierCell(family: Family): string {
  const label = TIER_LABELS[family.tier];
  return `<span class="tier-tag tier-tag--${family.tier}">${label}</span>`;
}

function buildRows(): void {
  const rows = filtered(doc, selectedTiers);
  const sorted = sortBy(rows, sortKey, sortDirection);
  const tbody = $('#family-rows');
  tbody.replaceChildren();
  for (const family of sorted) {
    const tr = document.createElement('tr');
    tr.tabIndex = 0;
    tr.dataset.code = family.code;
    tr.innerHTML = `
      <th scope="row">${family.name}</th>
      <td>${tierCell(family)}</td>
      <td class="num">${family.officesToday.toLocaleString('ro-RO')}</td>
      <td class="num">${family.officesProposed.toLocaleString('ro-RO')}</td>
      <td class="num">−${reduction(family).toLocaleString('ro-RO')}%</td>
      <td class="num">${family.regions.length}</td>`;
    tr.addEventListener('click', () => selectFamily(family));
    tr.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectFamily(family);
      }
    });
    tbody.appendChild(tr);
  }
  for (const header of document.querySelectorAll<HTMLTableCellElement>('th.sortable')) {
    const key = header.dataset.key as typeof sortKey;
    header.setAttribute('aria-sort', key === sortKey ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none');
  }
}

function selectFamily(family: Family): void {
  for (const row of document.querySelectorAll<HTMLTableRowElement>('#family-rows tr')) {
    row.classList.toggle('on', row.dataset.code === family.code);
  }
  renderRegionGrid(family);
}

function renderRegionGrid(family: Family): void {
  const grid = $('#region-grid');
  grid.replaceChildren();
  $('#detail-title').hidden = false;
  $('#detail-note').hidden = false;
  $('#detail-note').textContent = family.tier === 'regional'
    ? `${family.name}: ${family.officesToday.toLocaleString('ro-RO')} birouri în ${family.counties.length} județe, propuse ${family.officesProposed.toLocaleString('ro-RO')} — biroul din județul cel mai populat al fiecărei regiuni devine direcția regională, iar restul sunt absorbite. Birourile absorbite pot rămâne puncte de lucru, cu un șef de punct, nu un director cu aparat. Sediile nu sunt în sursă; regula este scrisă ca presupunere în datele paginii.`
    : `${family.name} nu se regionalizează prin această regulă; județele în care există:`;
  const groups = new Map(family.regions.map((g) => [g.region, g]));
  for (const region of regionsOf(doc)) {
    const group = groups.get(region);
    const card = document.createElement('div');
    card.className = 'region-card';
    if (!group || group.counties.length === 0) {
      card.classList.add('empty');
      card.textContent = region;
      card.title = `${region}: nicio unitate a acestei familii`;
      grid.appendChild(card);
      continue;
    }
    const title = document.createElement('div');
    title.className = 'region-name';
    title.textContent = region;
    const absorbed = group.counties.filter((county) => county !== group.seat);
    const seat = document.createElement('div');
    seat.className = 'region-seat';
    seat.textContent = `sediu: ${group.seat}`;
    const list = document.createElement('div');
    list.className = 'region-counties';
    list.textContent = absorbed.length > 0
      ? `absoarbe: ${absorbed.join(' · ')}`
      : 'singurul județ al regiunii';
    card.append(title, seat, list);
    grid.appendChild(card);
  }
  grid.hidden = false;
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

const officeMeta = (office: OfficeRow): string =>
  ` — ${office.county ?? 'fără județ'}${office.locality ? ` · ${office.locality}` : ''}`;

/** The list behind one summary card. Directions come from the payload; the office lists
 *  come from the lazy row-by-row registry. */
async function renderStatList(key: ListKey): Promise<void> {
  const body = $('#stat-list-body');
  body.replaceChildren();
  const titleEl = $('#stat-list-title');
  const noteEl = $('#stat-list-note');

  if (key === 'directions') {
    const rows = proposedDirections(doc);
    titleEl.textContent = `${rows.length.toLocaleString('ro-RO')} direcții propuse pe cele opt regiuni`;
    noteEl.textContent = 'Sediul este județul cel mai populat al fiecărei regiuni — o presupunere scrisă în datele paginii, nu un fapt din sursă.';
    noteEl.hidden = false;
    const byFamily = new Map<string, ProposedDirection[]>();
    for (const row of rows) {
      byFamily.set(row.family, [...(byFamily.get(row.family) ?? []), row]);
    }
    for (const [familyName, list] of byFamily) {
      const rowsEl = list.map((row) => statRow(row.region, ` — sediu: ${row.seat}`));
      body.appendChild(statGroup(familyName, rowsEl));
    }
  } else {
    await loadRegistry();
    const rows =
      key === 'absorbed'
        ? absorbedOffices(doc, registryDoc!)
        : officeList(registryDoc!, key as OfficeKind);
    titleEl.textContent = {
      all: `${rows.length.toLocaleString('ro-RO')} birouri deconcentrate în registrul ANFP 2025`,
      regional: `${rows.length.toLocaleString('ro-RO')} de birouri în familiile regionalizabile`,
      absorbed: `${rows.length.toLocaleString('ro-RO')} de birouri absorbite în direcțiile regionale`,
    }[key];
    noteEl.textContent = {
      all: 'Toate rândurile deconcentrate din registru, grupate pe familie. Serviciile municipale sunt raportate, nu comasate.',
      regional: 'Birourile familiilor regionalizabile, grupate pe familie — acestea sunt cele comasate.',
      absorbed: 'Birourile din afara județului-sediu. Punctele de lucru județene pot rămâne: comasarea taie structurile de comandă și costurile fixe, nu prezența locală.',
    }[key];
    noteEl.hidden = false;
    for (const group of groupOfficesByFamily(rows)) {
      const rowsEl = group.offices.map((office) => statRow(office.name, officeMeta(office)));
      body.appendChild(statGroup(`${group.label} (${group.offices.length.toLocaleString('ro-RO')})`, rowsEl));
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

function wireControls(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>('button.tier')) {
    button.addEventListener('click', () => {
      const tier = button.dataset.tier as 'all' | Tier;
      for (const other of document.querySelectorAll<HTMLButtonElement>('button.tier')) {
        other.classList.toggle('on', other === button);
      }
      selectedTiers =
        tier === 'all'
          ? new Set<Tier>(['regional', 'regional-de-facto', 'special'])
          : new Set<Tier>([tier]);
      $('#region-grid').hidden = true;
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
  $('#families').hidden = false;
  renderStats();
  wireControls();
  wireStatLists();
  buildRows();
  renderCaveats();
  $('#argument').hidden = false;
}

void main();

import './style.css';
import {
  TIER_LABELS,
  filtered,
  reduction,
  regionsOf,
  sortBy,
  type Document,
  type Family,
  type Tier,
} from './model';

const DOC_URL = 'data/deconcentrare.json';

const $ = <T extends HTMLElement>(selector: string): T => {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`missing element ${selector}`);
  return el;
};

let doc: Document;
let selectedTiers = new Set<Tier>(['regional', 'regional-de-facto', 'special']);
let sortKey: 'name' | 'officesToday' | 'officesProposed' | 'reduction' = 'officesToday';
let sortDirection: 'asc' | 'desc' = 'desc';

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
    ? `${family.name}: ${family.officesToday.toLocaleString('ro-RO')} birouri în ${family.counties.length} județe, propuse ${family.officesProposed.toLocaleString('ro-RO')} — biroul din județul cel mai populat al fiecărei regiuni devine direcția regională, iar restul sunt absorbite. Sediile nu sunt în sursă; regula este scrisă ca presupunere în datele paginii.`
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
    const response = await fetch(DOC_URL);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    doc = (await response.json()) as Document;
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
  buildRows();
  renderCaveats();
  $('#argument').hidden = false;
}

void main();

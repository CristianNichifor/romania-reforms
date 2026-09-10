import './style.css';
import {
  TIER_LABELS,
  filtered,
  reduction,
  sortBy,
  type Cluster,
  type Document,
  type Tier,
} from './model';

const DOC_URL = 'data/companii-stat.json';

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
  const grid = $('#operator-grid');
  grid.replaceChildren();
  if (cluster.tier === 'regional' && cluster.regions && cluster.regions.length > 0) {
    $('#detail-note').textContent =
      `${cluster.name} (${cluster.caen}): ${cluster.companies.toLocaleString('ro-RO')} de entități, propuse ${cluster.proposed.toLocaleString('ro-RO')} — operatorii de mai jos. Venituri agregate ${cluster.revenueRon.toLocaleString('ro-RO')} RON (MFin 2025), dintre care ${cluster.lossCount.toLocaleString('ro-RO')} companii în pierdere; ${cluster.subsidisedCount.toLocaleString('ro-RO')} sunt subvenționate, cu ${cluster.subsidyRon.toLocaleString('ro-RO')} RON raportați. ${cluster.distinctOwners.toLocaleString('ro-RO')} de proprietari distincți. Regula de sediu și de nucleu este scrisă ca presupunere în datele paginii, nu este din sursă.`;
    for (const group of cluster.regions) {
      const card = document.createElement('div');
      card.className = 'region-card';
      const title = document.createElement('div');
      title.className = 'region-name';
      title.textContent = group.region;
      const seat = document.createElement('div');
      seat.className = 'region-seat';
      seat.textContent = group.absorber
        ? `nucleu: ${group.absorber.name} (${group.absorber.employees.toLocaleString('ro-RO')} ang.) — județul ${group.seatCounty}`
        : `județul ${group.seatCounty} — niciun efectiv raportat, nucleul rămâne nenumit`;
      const count = document.createElement('div');
      count.className = 'region-count';
      count.textContent = `absoarbe ${group.absorbedCount.toLocaleString('ro-RO')} entități`;
      const details = document.createElement('details');
      details.className = 'absorbed-list';
      const summary = document.createElement('summary');
      summary.textContent = 'Lista celor absorbite';
      const list = document.createElement('ul');
      list.className = 'absorbed-names';
      for (const company of group.absorbed) {
        const li = document.createElement('li');
        const parts = [company.name];
        if (company.county) parts.push(company.county);
        if (company.owner) parts.push(`proprietar: ${company.owner}`);
        li.textContent = parts.join(' — ');
        list.appendChild(li);
      }
      details.append(summary, list);
      card.append(title, seat, count, details);
      grid.appendChild(card);
    }
    grid.hidden = false;
  } else {
    grid.hidden = true;
    const headcount = cluster.headcountKnown > 0
      ? `; efectivul este raportat doar de ${cluster.headcountKnown.toLocaleString('ro-RO')} dintre ele, deci cei ${cluster.employees.toLocaleString('ro-RO')} de angajați sunt o limită inferioară`
      : '';
    $('#detail-note').textContent =
      `${cluster.name} (${cluster.caen}): ${cluster.companies.toLocaleString('ro-RO')} de entități, lăsate nemodificate — nivelul „${TIER_LABELS[cluster.tier]}”${headcount}.`;
  }
}

function renderFusions(): void {
  if (doc.inFlightMergers.length === 0) return;
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
  $('#clusters').hidden = false;
  renderStats();
  wireControls();
  buildRows();
  renderCaveats();
  renderFusions();
  $('#argument').hidden = false;
}

void main();

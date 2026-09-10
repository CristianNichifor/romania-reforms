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
let sortKey: 'name' | 'companies' | 'employees' | 'reduction' = 'companies';
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
  setText('stat-headcount', s.headcountKnown.toLocaleString('ro-RO'));
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
  const headcount = cluster.headcountKnown > 0
    ? `; efectivul este raportat doar de ${cluster.headcountKnown.toLocaleString('ro-RO')} dintre ele, deci cei ${cluster.employees.toLocaleString('ro-RO')} de angajați sunt o limită inferioară`
    : '';
  $('#detail-note').textContent = cluster.tier === 'regional'
    ? `${cluster.name} (${cluster.caen}): ${cluster.companies.toLocaleString('ro-RO')} de entități, propuse ${cluster.proposed.toLocaleString('ro-RO')} — câte un operator pe fiecare regiune de dezvoltare${headcount}. Dintre ele, ${cluster.micro.toLocaleString('ro-RO')} au sub 20 de angajați și sunt candidate la absorbție sau lichidare indiferent de regulă.`
    : `${cluster.name} (${cluster.caen}): ${cluster.companies.toLocaleString('ro-RO')} de entități, lăsate nemodificate — nivelul „${TIER_LABELS[cluster.tier]}”${headcount}.`;
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
  $('#argument').hidden = false;
}

void main();

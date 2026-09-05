/**
 * What the case files say about how the courts work.
 *
 * Every number here comes from `portal-stats.json`, built by `build_portal_stats.py` out of the
 * dossiers the courts publish. The page's job is not to compute anything — it is to render the
 * figures beside the reason they can be trusted, because most of them are only true within a
 * stated cohort and a chart that drops that condition is worse than no chart.
 *
 * Three of those conditions do real work and are surfaced rather than footnoted:
 *
 *   * Durations are Kaplan-Meier estimates over a recent registration cohort. Outside it the
 *     portal has archived the fast cases and any average measures slowness twice — which is the
 *     "gradient" section, printed as a finding rather than hidden as a caveat.
 *   * A resolution share past the follow-up is null, not extrapolated, so the bars stop where
 *     the observation stops instead of running to a confident 100%.
 *   * Adjournments are three different acts and are never summed into one headline.
 *
 * No chart library, and no SVG either: every bar is a div with a width, every quartile strip is
 * three absolutely positioned spans. The page builds to about 7 kB of script over a 130 kB
 * document, and a plotting dependency to draw horizontal rectangles would cost more than it
 * explains.
 */

const BASE = import.meta.env.BASE_URL;

interface Limitation {
  id: string;
  text: string;
  severity: 'blocking' | 'material' | 'note';
  affects: string[];
}

interface Survival {
  level?: string;
  categorie?: string;
  dosare: number;
  solutionate: number;
  inCurs: number;
  urmarireZile: number;
  medianaZile: number | null;
  rezolvatePana: Record<string, number | null>;
}

interface Charge {
  cod: string;
  articol: number | null;
  dosare: number;
  denumire: string;
}

interface Stats {
  title: string;
  period: string;
  publisher: string;
  provenance: { locator: string };
  snapshot: {
    crawledAt: string;
    instante: number;
    dosare: number;
    sedinte: number;
    registeredFrom: string;
    registeredTo: string;
    coverageComplete: boolean | null;
    institutieDinFisier: boolean;
  };
  levels: { level: string; instante: number; dosare: number; dosarePerComplet: number | null }[];
  caseTypes: { categorie: string; dosare: number; share: number }[];
  termene: {
    cohortFrom: string;
    cohortMonths: number;
    intervalZileByLevel: { level: string; intervale: number; p25?: number; p50?: number; p75?: number }[];
    termenePerDosar: Record<string, number>;
  };
  durata: { cohortFrom: string; byLevel: Survival[]; byCategorie: Survival[] };
  primulTermen: { level: string; dosare: number; p25?: number; p50?: number; p75?: number }[];
  amanari: {
    termeneCuSolutie: number;
    amanareCauza: number;
    amanarePronuntare: number;
    termenPreschimbat: number;
    cotaAmanareCauza: number | null;
    cotaFaraProgres: number | null;
  };
  penal: {
    dosarePenale: number;
    cuArticol: number;
    cotaProcedurala: number | null;
    infractiuni: Charge[];
    proceduri: Charge[];
    legiSpeciale: Charge[];
    legiCunoscute: Record<string, string>;
  };
  concentrare: {
    identitati: number;
    dosareAncilare: number;
    distributie: { disputeDeLaPanaLa: string; identitati: number; cota: number }[];
    peGrupDeCalitate: Record<string, number>;
    cotaTopFilerilor: { top1la_suta: number | null; top5la_suta: number | null };
    comportamentInstitutional: {
      identitati: number;
      dispute: number;
      cotaDinCereri: number | null;
      pragDisputa: number;
      pragRecuperare: number;
    };
  };
  vechimeDosarePeRol: { from: number; to: number | null; dosare: number; share: number | null }[];
  gradientArhivare: { anInregistrare: number; dosareVizibileSolutionate: number; medianaNaivaZile: number }[];
  limitations: Limitation[];
}

interface Edition {
  period: string;
  courts: { id: string; tier: string; volume: number; resolved: number }[];
}

const el = (id: string) => document.getElementById(id) as HTMLElement;
const ro = new Intl.NumberFormat('ro-RO');
const pct = (value: number) => `${(value * 100).toFixed(1).replace('.', ',')}%`;

/** Days as a reader says them, because "547 de zile" is a number and "un an și jumătate" is a fact. */
function days(value: number | null): string {
  if (value === null) return '—';
  if (value < 60) return `${value} zile`;
  const months = value / 30.4;
  if (months < 24) return `${months.toFixed(months < 10 ? 1 : 0).replace('.', ',')} luni`;
  return `${(value / 365).toFixed(1).replace('.', ',')} ani`;
}

function bars(
  into: HTMLElement,
  rows: { label: string; value: number; note?: string; muted?: boolean }[],
  format: (value: number) => string = (value) => ro.format(value),
): void {
  const top = Math.max(...rows.map((row) => row.value), 1);
  into.innerHTML = rows
    .map(
      (row) => `
      <div class="bar${row.muted ? ' muted' : ''}">
        <span class="bar-label" title="${row.label}">${row.label}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${(row.value / top) * 100}%"></span></span>
        <span class="bar-value">${format(row.value)}</span>
        ${row.note ? `<span class="bar-note">${row.note}</span>` : ''}
      </div>`,
    )
    .join('');
}

/**
 * A resolution curve, drawn only as far as it was observed.
 *
 * The marks are the shares resolved by 90, 180 and 365 days. A null mark means the cohort has
 * not been followed that long, and the bar is drawn as an open outline rather than as zero —
 * "not yet known" and "none resolved" are opposite claims and must not look alike.
 */
function survivalRow(row: Survival): string {
  const name = row.level ?? row.categorie ?? '';
  const marks = [90, 180, 365]
    .map((day) => {
      const share = row.rezolvatePana[`zi${day}`];
      if (share === null || share === undefined) {
        return `<span class="mark unknown" title="Cohorta nu a fost urmărită ${day} de zile">
          <span class="mark-day">${day}z</span><span class="mark-value">?</span></span>`;
      }
      return `<span class="mark" title="${pct(share)} soluționate în ${day} de zile">
        <span class="mark-day">${day}z</span>
        <span class="mark-bar"><span style="height:${Math.max(share * 100, 2)}%"></span></span>
        <span class="mark-value">${Math.round(share * 100)}%</span></span>`;
    })
    .join('');
  return `
    <div class="survival">
      <div class="survival-head">
        <strong>${name}</strong>
        <span class="survival-n">${ro.format(row.dosare)} dosare · ${ro.format(row.solutionate)} soluționate · ${ro.format(row.inCurs)} în curs</span>
      </div>
      <div class="survival-body">
        <div class="median">
          <span class="median-value">${days(row.medianaZile)}</span>
          <span class="median-label">mediana</span>
        </div>
        <div class="marks">${marks}</div>
        <div class="followup">urmărire ${days(row.urmarireZile)}</div>
      </div>
    </div>`;
}

function quartiles(
  into: HTMLElement,
  rows: { level: string; dosare?: number; intervale?: number; p25?: number; p50?: number; p75?: number }[],
): void {
  const top = Math.max(...rows.map((row) => row.p75 ?? 0), 1);
  into.innerHTML = rows
    .map((row) => {
      const n = row.dosare ?? row.intervale ?? 0;
      if (row.p50 === undefined) {
        return `<div class="quart"><span class="bar-label">${row.level}</span>
          <span class="quart-none">prea puține observații</span></div>`;
      }
      const left = ((row.p25 ?? 0) / top) * 100;
      const width = Math.max((((row.p75 ?? 0) - (row.p25 ?? 0)) / top) * 100, 0.6);
      const mid = ((row.p50 ?? 0) / top) * 100;
      return `
        <div class="quart">
          <span class="bar-label" title="${row.level}">${row.level}</span>
          <span class="quart-track">
            <span class="quart-box" style="left:${left}%;width:${width}%"></span>
            <span class="quart-mid" style="left:${mid}%"></span>
          </span>
          <span class="bar-value">${days(row.p50 ?? null)}</span>
          <span class="bar-note">${ro.format(n)} obs.</span>
        </div>`;
    })
    .join('');
}

async function load<T>(name: string): Promise<T> {
  const response = await fetch(`${BASE}data/${name}`);
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  return (await response.json()) as T;
}

async function main(): Promise<void> {
  const [stats, ...editions] = await Promise.all([
    load<Stats>('portal-stats.json'),
    load<Edition>('instante-2022.json'),
    load<Edition>('instante-2023.json'),
    load<Edition>('instante-2024.json'),
    load<Edition>('instante-2025.json'),
  ]);

  const snap = stats.snapshot;
  el('cohort-note').textContent =
    `Cifrele de durată și de termene privesc dosarele înregistrate după ${stats.durata.cohortFrom}. ` +
    'Mai vechi de atât, portalul a arhivat deja cauzele rapide, iar orice medie ar măsura de două ' +
    'ori încetineala — vezi ultima secțiune.';

  // Coverage first, because a reader is entitled to know what the numbers were counted over
  // before being shown any of them.
  const incomplete = snap.coverageComplete === false;
  el('acoperire').innerHTML = `
    <h2>Ce s-a măsurat</h2>
    <div class="facts">
      <div><b>${ro.format(snap.dosare)}</b><span>dosare</span></div>
      <div><b>${ro.format(snap.instante)}</b><span>instanțe</span></div>
      <div><b>${ro.format(snap.sedinte)}</b><span>termene</span></div>
      <div><b>${snap.registeredFrom} — ${snap.registeredTo}</b><span>înregistrate</span></div>
    </div>
    ${
      incomplete
        ? '<p class="warn">Colectarea a raportat lipsuri: unele instanțe au ferestre eșuate sau trunchiate. Cifrele pe instanță sunt praguri de jos.</p>'
        : ''
    }
    ${
      snap.institutieDinFisier
        ? ''
        : '<p class="warn">Termenele sunt legate de instanță prin numărul dosarului, care se păstrează când cauza urcă. Pentru cauzele aflate la două instanțe deodată, împărțirea pe grade este aproximativă.</p>'
    }`;

  // The trend, from the CSM editions rather than from the portal.
  const trend = editions
    .map((edition) => ({
      label: edition.period,
      value: edition.courts
        .filter((court) => court.tier === 'judecatorie')
        .reduce((sum, court) => sum + court.volume, 0),
    }))
    .sort((a, b) => Number(a.label) - Number(b.label));
  // The oldest and newest editions, named rather than indexed: tsconfig sets
  // noUncheckedIndexedAccess, and an empty editions list should render nothing rather than throw.
  const oldest = trend.at(0);
  const newest = trend.at(-1);
  bars(
    el('trend'),
    trend.map((row) => ({
      label: row.label,
      value: row.value,
      note:
        oldest && newest && row.label === newest.label && oldest.value > 0
          ? `+${pct(newest.value / oldest.value - 1)} față de ${oldest.label}`
          : '',
    })),
  );

  bars(
    el('tipuri'),
    stats.caseTypes.slice(0, 10).map((row) => ({
      label: row.categorie,
      value: row.dosare,
      note: pct(row.share),
    })),
  );

  el('durata-note').textContent =
    `Estimare Kaplan-Meier peste dosarele înregistrate după ${stats.durata.cohortFrom}: cauzele ` +
    'încă nesoluționate contribuie cu „cel puțin atât", nu sunt aruncate. Un prag fără cifră ' +
    'înseamnă că nu s-a urmărit destul timp ca să se poată spune.';
  el('durata').innerHTML =
    stats.durata.byLevel.map(survivalRow).join('') +
    (stats.durata.byCategorie.length
      ? `<h3>Pe categorie</h3>${stats.durata.byCategorie.slice(0, 6).map(survivalRow).join('')}`
      : '');

  quartiles(el('primul'), stats.primulTermen);
  quartiles(el('intervale'), stats.termene.intervalZileByLevel);

  const a = stats.amanari;
  bars(
    el('amanari'),
    [
      { label: 'Amână cauza', value: a.amanareCauza, note: pct(a.amanareCauza / a.termeneCuSolutie) },
      { label: 'Amână pronunțarea', value: a.amanarePronuntare, note: pct(a.amanarePronuntare / a.termeneCuSolutie) },
      { label: 'Termen preschimbat', value: a.termenPreschimbat, note: pct(a.termenPreschimbat / a.termeneCuSolutie) },
    ],
  );

  const p = stats.penal;
  el('penal-note').textContent =
    `Din ${ro.format(p.dosarePenale)} dosare penale, ${ro.format(p.cuArticol)} poartă o trimitere ` +
    `la un text de lege. ${p.cotaProcedurala === null ? '' : pct(p.cotaProcedurala)} din ele sunt pași ` +
    'de procedură — confirmarea unei renunțări la urmărire, verificarea măsurilor preventive, ' +
    'liberarea condiționată — nu acuzații. O listă a „celor mai frecvente infracțiuni" care le ' +
    'amestecă spune că instanțele judecă mai ales confirmări de renunțare.';
  const chargeRow = (row: Charge) => ({
    label: row.denumire.replace(/\s*\([^)]*\)\s*$/, '') || row.cod,
    value: row.dosare,
    note: row.articol ? `art. ${row.articol}` : row.cod,
  });
  bars(el('infractiuni'), p.infractiuni.slice(0, 10).map(chargeRow));
  bars(el('proceduri'), p.proceduri.slice(0, 8).map(chargeRow));
  bars(
    el('legi'),
    p.legiSpeciale.slice(0, 8).map((row) => ({
      label: row.denumire.replace(/\s*\([^)]*\)\s*$/, '') || row.cod,
      value: row.dosare,
      note: p.legiCunoscute[row.cod.slice(1)] ?? row.cod,
      // Statutes whose character has not been checked are drawn muted: the file does not claim
      // to know whether they carry offences or procedure.
      muted: !(row.cod.slice(1) in p.legiCunoscute),
    })),
  );

  const c = stats.concentrare;
  const inst = c.comportamentInstitutional;
  const GROUPS: Record<string, string> = {
    initiaza: 'inițiază (reclamant, petent, creditor)',
    raspunde: 'răspunde (pârât, intimat, debitor)',
    vatamat: 'parte vătămată sau civilă',
    acuzat: 'inculpat sau suspect',
    altul: 'altă calitate',
  };
  el('concentrare').innerHTML = `
    <div class="facts">
      <div><b>${ro.format(c.identitati)}</b><span>identități distincte</span></div>
      <div><b>${c.cotaTopFilerilor.top1la_suta === null ? '—' : pct(c.cotaTopFilerilor.top1la_suta)}</b><span>din cereri, de la primul 1% dintre depunători</span></div>
      <div><b>${inst.cotaDinCereri === null ? '—' : pct(inst.cotaDinCereri)}</b><span>de la ${ro.format(inst.identitati)} identități cu tipar instituțional</span></div>
    </div>
    <p class="note">
      Tipar instituțional înseamnă cel puțin ${inst.pragDisputa} de dispute, dintre care peste
      ${pct(inst.pragRecuperare)} recuperare de creanțe — cereri de valoare redusă, validări de
      poprire, ordonanțe de plată. Este un tipar de comportament, nu un nume: nu se publică
      nicio identitate, doar câte sunt și cât duc.
    </p>`;

  bars(
    el('distributie'),
    c.distributie.map((row) => ({
      label: `${row.disputeDeLaPanaLa} ${row.disputeDeLaPanaLa === '1' ? 'dispută' : 'dispute'}`,
      value: row.identitati,
      note: pct(row.cota),
    })),
  );

  bars(
    el('calitati'),
    Object.entries(c.peGrupDeCalitate)
      .sort((a, b) => b[1] - a[1])
      .map(([group, count]) => ({ label: GROUPS[group] ?? group, value: count })),
  );

  bars(
    el('vechime'),
    stats.vechimeDosarePeRol.map((row) => ({
      label: row.to === null ? `peste ${row.from} de zile` : `${row.from}–${row.to} de zile`,
      value: row.dosare,
      note: row.share === null ? '' : pct(row.share),
    })),
  );

  bars(
    el('gradient'),
    stats.gradientArhivare.map((row) => ({
      label: String(row.anInregistrare),
      value: row.medianaNaivaZile,
      note: `${ro.format(row.dosareVizibileSolutionate)} dosare vizibile`,
    })),
    (value) => days(Math.round(value)),
  );

  el('limitari').innerHTML = stats.limitations
    .map(
      (limitation) => `
      <details class="lim ${limitation.severity}">
        <summary><span class="sev">${limitation.severity}</span> ${limitation.id.replace(/-/g, ' ')}</summary>
        <p>${limitation.text}</p>
      </details>`,
    )
    .join('');

  el('sursa').textContent = `${stats.publisher} · ${stats.provenance.locator}`;
}

main().catch((error) => {
  el('app').insertAdjacentHTML(
    'afterbegin',
    `<p class="warn">Datele nu au putut fi încărcate: ${String(error)}. Rulează
     <code>node scripts/copy-data.mjs</code> și
     <code>uv run python scripts/build_portal_stats.py</code>.</p>`,
  );
});

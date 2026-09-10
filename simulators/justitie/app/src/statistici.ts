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
 * three absolutely positioned spans. The drawing itself lives in `charts.ts`, which is where the
 * axis, the hover states and the tooltip are; this file decides what to plot and what to say
 * about it. A plotting dependency to draw horizontal rectangles would cost more than it explains.
 */

import { bars, count, esc, quartiles, share, wireTooltips, type QuartileRow } from './charts';
import {
  pool,
  strip,
  survival,
  type Court,
  type CourtsFile,
  type Edges,
  type Pooled,
} from './aggregate';
import { assign, changedParams, loadCoupling, readScenario } from './arondare';
import { proposedCourts, type ArondareInstante, type Proposal } from './propuse';

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
const pct = share;

/**
 * The ECRIS case-type enum, spelled the way a reader says it.
 *
 * The values arrive as `Contenciosadministrativsifiscal` — the enum member with its spaces
 * dropped — and the data files keep them exactly so, because they are the join key between the
 * portal and everything downstream. Expanding them is a presentation decision and lives here.
 * An unknown value falls through unchanged rather than being guessed at: a new ECRIS category
 * should look raw and unhandled, not plausibly renamed.
 */
const CATEGORIES: Record<string, string> = {
  Litigiicuprofesionistii: 'Litigii cu profesioniștii',
  Contenciosadministrativsifiscal: 'Contencios administrativ și fiscal',
  Minorisifamilie: 'Minori și familie',
  Asigurarisociale: 'Asigurări sociale',
  Litigiidemunca: 'Litigii de muncă',
  Insolventapersoaneifizice: 'Insolvența persoanei fizice',
  ProprietateIntelectuala: 'Proprietate intelectuală',
  Dreptmaritimsifluvial: 'Drept maritim și fluvial',
};

const categoryName = (raw: string): string => CATEGORIES[raw] ?? raw;

/** Days as a reader says them, because "547 de zile" is a number and "un an și jumătate" is a fact. */
function days(value: number | null): string {
  if (value === null) return '—';
  if (value < 60) return `${value} zile`;
  const months = value / 30.4;
  if (months < 24) return `${months.toFixed(months < 10 ? 1 : 0).replace('.', ',')} luni`;
  return `${(value / 365).toFixed(1).replace('.', ',')} ani`;
}

/** A tooltip payload: the attribute the delegated listener in `charts.ts` reads. */
function tip(title: string, lines: [string, string][]): string {
  const body = lines
    .filter(([, value]) => value !== '')
    .map(([term, value]) => `<dt>${esc(term)}</dt><dd>${esc(value)}</dd>`)
    .join('');
  return `tabindex="0" data-tip="${esc(`<strong>${esc(title)}</strong><dl>${body}</dl>`)}"`;
}

/**
 * A resolution curve, drawn only as far as it was observed.
 *
 * The marks are the shares resolved by 90, 180 and 365 days. A null mark means the cohort has
 * not been followed that long, and the bar is drawn as an open outline rather than as zero —
 * "not yet known" and "none resolved" are opposite claims and must not look alike. The tooltip
 * says which of the two it is in words, because an outline is a convention a reader has to be
 * taught and a sentence is not.
 */
function survivalRow(row: Survival): string {
  const name = row.level ?? (row.categorie ? categoryName(row.categorie) : '');
  const marks = [90, 180, 365]
    .map((day) => {
      const resolved = row.rezolvatePana[`zi${day}`];
      if (resolved === null || resolved === undefined) {
        const why: [string, string][] = [
          ['', `Cohorta a fost urmărită ${days(row.urmarireZile)}, mai puțin de ${day} de zile.`],
          ['', 'Nu se poate spune ce parte s-a soluționat până aici, iar o cifră ar fi o extrapolare.'],
        ];
        // Same three elements in the same order as an observed mark, so the day labels of all
        // three marks sit on one line. An `::before` box would push this one's label down and
        // the row would read as a different kind of thing rather than as a missing value.
        return `<span class="mark unknown" ${tip(`${name} — la ${day} de zile`, why)}>
          <span class="mark-day">${day}z</span>
          <span class="mark-bar unobserved"></span>
          <span class="mark-value">?</span></span>`;
      }
      const lines: [string, string][] = [
        ['soluționate', pct(resolved)],
        ['din', `${count(row.dosare)} dosare`],
        ['încă în curs sau ulterior', pct(1 - resolved)],
      ];
      return `<span class="mark" ${tip(`${name} — la ${day} de zile`, lines)}>
        <span class="mark-day">${day}z</span>
        <span class="mark-bar"><span style="height:${Math.max(resolved * 100, 2)}%"></span></span>
        <span class="mark-value">${Math.round(resolved * 100)}%</span></span>`;
    })
    .join('');
  const summary: [string, string][] = [
    ['dosare în cohortă', count(row.dosare)],
    ['soluționate', count(row.solutionate)],
    ['încă în curs', count(row.inCurs)],
    ['mediana', days(row.medianaZile)],
    ['urmărire', days(row.urmarireZile)],
    [
      '',
      'Mediana este estimată Kaplan-Meier: dosarele încă nesoluționate contribuie cu „cel puțin atât”.',
    ],
  ];
  return `
    <div class="survival" ${tip(name, summary)}>
      <div class="survival-head">
        <strong>${esc(name)}</strong>
        <span class="survival-n">${count(row.dosare)} dosare · ${count(row.solutionate)} soluționate · ${count(row.inCurs)} în curs</span>
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

/** Percentile rows as `charts.ts` wants them: a label, a denominator, three days. */
function strips(
  rows: { level: string; dosare?: number; intervale?: number; p25?: number; p50?: number; p75?: number }[],
): { label: string; n: number; p25?: number | undefined; p50?: number | undefined; p75?: number | undefined }[] {
  return rows.map((row) => ({
    label: row.level,
    n: row.dosare ?? row.intervale ?? 0,
    p25: row.p25,
    p50: row.p50,
    p75: row.p75,
  }));
}

async function load<T>(name: string): Promise<T> {
  const response = await fetch(`${BASE}data/${name}`);
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  return (await response.json()) as T;
}

/**
 * One shape for the figures a selection can produce, however the selection was made.
 *
 * The page has two sources for the same statistics: the national file, which is authoritative
 * and needs no arithmetic, and the per-court file, which has to be pooled. Rendering them
 * through two code paths would mean two chances to disagree, and a disagreement between the
 * national view and the "all courts" view would be invisible — both are plausible numbers.
 *
 * So both are adapted into this, and there is one renderer.
 */
interface View {
  dosare: number;
  instante: number | null;
  termene: number;
  caseTypes: { categorie: string; dosare: number }[];
  durataByLevel: Survival[];
  durataByCategorie: Survival[];
  primul: QuartileRow[];
  intervale: QuartileRow[];
  amanari: Stats['amanari'];
  vechime: { from: number; to: number | null; dosare: number }[];
  /** Courts left out for being unmeasured, and the note that says so. */
  trunchiate: number;
}

const LEVEL_ORDER = ['judecătorie', 'tribunal', 'curte de apel', 'tribunal specializat'];

function viewFromStats(stats: Stats): View {
  return {
    dosare: stats.snapshot.dosare,
    instante: stats.snapshot.instante,
    termene: stats.amanari.termeneCuSolutie,
    caseTypes: stats.caseTypes,
    durataByLevel: stats.durata.byLevel,
    durataByCategorie: stats.durata.byCategorie,
    primul: strips(stats.primulTermen),
    intervale: strips(stats.termene.intervalZileByLevel),
    amanari: stats.amanari,
    vechime: stats.vechimeDosarePeRol,
    trunchiate: 0,
  };
}

/**
 * The same view, pooled from a selection of courts.
 *
 * Durations and percentiles are computed per level rather than over the whole selection, because
 * a county's judecătorie and its tribunal are not the same kind of court and one median across
 * both would describe neither. Case categories are not available per court beyond their counts,
 * so `durataByCategorie` is empty here and the section says so rather than showing the national
 * figures under a county heading.
 */
function viewFromCourts(courts: Court[], edges: Edges): View {
  const all = pool(courts, edges);
  const levels = LEVEL_ORDER.filter((level) => courts.some((court) => court.level === level));

  const byLevel = levels.map((level) => {
    const summed = pool(courts.filter((court) => court.level === level), edges);
    return { level, ...survival(summed.durata, edges.durata) };
  });

  const stripsFor = (pick: (summed: ReturnType<typeof pool>) => number[]) =>
    levels.map((level) => {
      const summed = pool(courts.filter((court) => court.level === level), edges);
      return { label: level, ...strip(pick(summed), edges.termene) };
    });

  return {
    dosare: all.dosare,
    instante: all.instante,
    termene: all.amanari.termeneCuSolutie,
    caseTypes: Object.entries(all.peCategorie)
      .map(([categorie, dosare]) => ({ categorie, dosare }))
      .sort((a, b) => b.dosare - a.dosare),
    durataByLevel: byLevel.filter((row) => row.dosare > 0),
    durataByCategorie: [],
    primul: stripsFor((summed) => summed.primulTermen),
    intervale: stripsFor((summed) => summed.intervalTermene),
    amanari: {
      ...all.amanari,
      cotaAmanareCauza: all.amanari.termeneCuSolutie
        ? all.amanari.amanareCauza / all.amanari.termeneCuSolutie
        : null,
      cotaFaraProgres: null,
    },
    vechime: AGE_EDGES.map((from, index) => ({
      from,
      to: AGE_EDGES[index + 1] ?? null,
      dosare: all.peRol[index] ?? 0,
    })),
    trunchiate: all.trunchiate,
  };
}

let AGE_EDGES: number[] = [];

/**
 * A view over figures that are already pooled.
 *
 * Used for the proposed courts, which is why there is no split by level: a merged court holds
 * first-instance and tribunal work in one building, and splitting it back apart would describe
 * the thing the reform proposes to stop doing.
 */
function viewFromPooled(summed: Pooled, edges: Edges, label: string): View {
  return {
    dosare: Math.round(summed.dosare),
    instante: null,
    termene: Math.round(summed.amanari.termeneCuSolutie),
    caseTypes: Object.entries(summed.peCategorie)
      .map(([categorie, dosare]) => ({ categorie, dosare: Math.round(dosare) }))
      .sort((a, b) => b.dosare - a.dosare),
    durataByLevel: summed.durata.dosare
      ? [{ level: label, ...survival(summed.durata, edges.durata) }]
      : [],
    durataByCategorie: [],
    primul: [{ label, ...strip(summed.primulTermen, edges.termene) }],
    intervale: [{ label, ...strip(summed.intervalTermene, edges.termene) }],
    amanari: {
      termeneCuSolutie: Math.round(summed.amanari.termeneCuSolutie),
      amanareCauza: Math.round(summed.amanari.amanareCauza),
      amanarePronuntare: Math.round(summed.amanari.amanarePronuntare),
      termenPreschimbat: Math.round(summed.amanari.termenPreschimbat),
      cotaAmanareCauza: null,
      cotaFaraProgres: null,
    },
    vechime: AGE_EDGES.map((from, index) => ({
      from,
      to: AGE_EDGES[index + 1] ?? null,
      dosare: Math.round(summed.peRol[index] ?? 0),
    })),
    trunchiate: 0,
  };
}

/**
 * Caveats about the snapshot as a whole, not about the selection.
 *
 * They belong under "Ce s-a măsurat", which is rebuilt on every filter change, so they are held
 * here rather than written into the DOM once and lost on the first redraw.
 */
let snapshotNotes = '';

/** Every section whose numbers follow the filter. */
function renderScope(view: View, scopeLabel: string, extra = ''): void {
  const total = view.dosare || 1;
  el('acoperire').innerHTML = `
    <h2>Ce s-a măsurat${scopeLabel ? ` — ${esc(scopeLabel)}` : ''}</h2>
    <div class="facts">
      <div><b>${count(view.dosare)}</b><span>dosare</span></div>
      ${view.instante === null ? '' : `<div><b>${count(view.instante)}</b><span>instanțe</span></div>`}
      <div><b>${count(view.termene)}</b><span>termene cu soluție</span></div>
      ${extra}
    </div>
    ${snapshotNotes}
    ${
      view.trunchiate
        ? `<p class="warn">${
            view.trunchiate === 1
              ? 'O instanță a rămas necolectată și este scoasă'
              : `${count(view.trunchiate)} instanțe au rămas necolectate și sunt scoase`
          } din toate cifrele de aici, fiindcă a colecta câteva zeci de dosare dintr-o instanță nu este a o măsura. Vezi limitarea „instantele trunchiate sunt marcate nu sterse”.</p>`
        : ''
    }`;

  bars(
    el('tipuri'),
    view.caseTypes.slice(0, 10).map((row) => ({
      label: categoryName(row.categorie),
      value: row.dosare,
      note: pct(row.dosare / total),
      detail: [['din dosarele selecției', pct(row.dosare / total)]] as [string, string][],
    })),
    { unit: 'dosare' },
  );

  el('durata').innerHTML =
    (view.durataByLevel.length
      ? view.durataByLevel.map(survivalRow).join('')
      : '<p class="empty">Nicio cauză din cohortă pentru această selecție.</p>') +
    (view.durataByCategorie.length
      ? `<h3>Pe categorie</h3>${view.durataByCategorie.slice(0, 6).map(survivalRow).join('')}`
      : '');

  const inDays = (value: number) => days(Math.round(value));
  quartiles(el('primul'), view.primul, { format: inDays, unit: 'dosare', targetTicks: 2 });
  quartiles(el('intervale'), view.intervale, {
    format: inDays,
    unit: 'intervale',
    targetTicks: 2,
  });

  const a = view.amanari;
  const ofTerms: [string, string][] = [['din', `${count(a.termeneCuSolutie)} termene cu soluție`]];
  const shareOf = (value: number) => (a.termeneCuSolutie ? pct(value / a.termeneCuSolutie) : '—');
  bars(
    el('amanari'),
    [
      {
        label: 'Amână cauza',
        value: a.amanareCauza,
        note: shareOf(a.amanareCauza),
        detail: [...ofTerms, ['', 'Nu s-a ajuns la cauză: se fixează alt termen.']],
      },
      {
        label: 'Amână pronunțarea',
        value: a.amanarePronuntare,
        note: shareOf(a.amanarePronuntare),
        detail: [...ofTerms, ['', 'Instanța a judecat și își scrie hotărârea. Este progres, nu întârziere.']],
      },
      {
        label: 'Termen preschimbat',
        value: a.termenPreschimbat,
        note: shareOf(a.termenPreschimbat),
        detail: [...ofTerms, ['', 'Data a fost mutată, adesea înainte ca ședința să înceapă.']],
      },
    ],
    { unit: 'termene' },
  );

  const onRoll = view.vechime.reduce((sum, row) => sum + row.dosare, 0) || 1;
  bars(
    el('vechime'),
    view.vechime.map((row) => ({
      label: row.to === null ? `peste ${row.from} de zile` : `${row.from}–${row.to} de zile`,
      value: row.dosare,
      note: pct(row.dosare / onRoll),
      detail: [
        ['din dosarele pe rol', pct(row.dosare / onRoll)],
        ['dosare pe rol, total', count(onRoll)],
      ] as [string, string][],
    })),
    { unit: 'dosare' },
  );
}

/**
 * Say plainly which sections did not follow the filter.
 *
 * This is the part that makes the filter honest. Charges, litigants and the archiving gradient
 * exist only nationally, and leaving them silent under a heading that reads "Timiș" would
 * present national figures as county ones — which is exactly the misreading a filter invites and
 * the reader has no way to detect.
 */
function markNationalSections(active: boolean, scopeLabel: string): void {
  for (const node of document.querySelectorAll<HTMLElement>('[data-national]')) {
    node.hidden = !active;
    node.textContent = active
      ? `Această secțiune rămâne pe toată țara: cifrele ei nu se pot descompune pe ${scopeLabel}.`
      : '';
  }
}

async function main(): Promise<void> {
  const [stats, ...editions] = await Promise.all([
    load<Stats>('portal-stats.json'),
    load<Edition>('instante-2022.json'),
    load<Edition>('instante-2023.json'),
    load<Edition>('instante-2024.json'),
    load<Edition>('instante-2025.json'),
  ]);

  // Optional, like the rest of the portal payload: a checkout that has not run the builder still
  // gets the national page rather than an error, and simply has no filter.
  const courts = await load<CourtsFile>('portal-instante.json').catch(() => null);

  const snap = stats.snapshot;
  snapshotNotes =
    (snap.coverageComplete === false
      ? '<p class="warn">Colectarea a raportat lipsuri: unele instanțe au ferestre eșuate sau trunchiate. Cifrele pe instanță sunt praguri de jos.</p>'
      : '') +
    (snap.institutieDinFisier
      ? ''
      : '<p class="warn">Termenele sunt legate de instanță prin instanța care avea dosarul în ziua ședinței, nu prin numărul dosarului. Pentru cele 11,2% dintre cauze care stau la două instanțe deodată, împărțirea este dedusă din datele de înregistrare.</p>');
  el('cohort-note').textContent =
    `Cifrele de durată și de termene privesc dosarele înregistrate după ${stats.durata.cohortFrom}. ` +
    'Mai vechi de atât, portalul a arhivat deja cauzele rapide, iar orice medie ar măsura de două ' +
    'ori încetineala — vezi ultima secțiune.';

  renderNational(stats, editions);

  if (!courts) {
    renderScope(viewFromStats(stats), '');
    markNationalSections(false, '');
    finish(stats, null);
    return;
  }

  AGE_EDGES = courts.praguriZile.peRol;
  wireFilter(stats, courts);
  finish(stats, courts);
}

/** The sections that exist only nationally, and always show the whole country. */
function renderNational(stats: Stats, editions: Edition[]): void {
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
      detail: [['sursa', `Starea justiției ${row.label}, Anexa 1`]] as [string, string][],
    })),
    { unit: 'volum de activitate, judecătorii' },
  );

  const p = stats.penal;
  el('penal-note').textContent =
    `Din ${count(p.dosarePenale)} dosare penale, ${count(p.cuArticol)} poartă o trimitere ` +
    `la un text de lege. ${p.cotaProcedurala === null ? '' : pct(p.cotaProcedurala)} din ele sunt pași ` +
    'de procedură — confirmarea unei renunțări la urmărire, verificarea măsurilor preventive, ' +
    'liberarea condiționată — nu acuzații. O listă a „celor mai frecvente infracțiuni" care le ' +
    'amestecă spune că instanțele judecă mai ales confirmări de renunțare.';
  const chargeRow = (row: Charge) => ({
    label: row.denumire.replace(/\s*\([^)]*\)\s*$/, '') || row.cod,
    value: row.dosare,
    note: row.articol ? `art. ${row.articol}` : row.cod,
    detail: [
      ['text de lege', row.articol ? `art. ${row.articol} ${row.cod.replace(/^L?/, '')}` : row.cod],
      ['din dosarele penale', pct(row.dosare / p.dosarePenale)],
    ] as [string, string][],
  });
  bars(el('infractiuni'), p.infractiuni.slice(0, 10).map(chargeRow), { unit: 'dosare' });
  bars(el('proceduri'), p.proceduri.slice(0, 8).map(chargeRow), { unit: 'dosare' });
  bars(
    el('legi'),
    p.legiSpeciale.slice(0, 8).map((row) => {
      const known = row.cod.slice(1) in p.legiCunoscute;
      return {
        label: row.denumire.replace(/\s*\([^)]*\)\s*$/, '') || row.cod,
        value: row.dosare,
        note: p.legiCunoscute[row.cod.slice(1)] ?? row.cod,
        detail: [
          ['lege', row.cod.slice(1)],
          ['din dosarele penale', pct(row.dosare / p.dosarePenale)],
          ...(known
            ? []
            : ([['', 'Nu s-a verificat dacă legea poartă infracțiuni sau doar procedură, deci rândul este desenat estompat.']] as [string, string][])),
        ] as [string, string][],
        // Statutes whose character has not been checked are drawn muted: the file does not claim
        // to know whether they carry offences or procedure.
        muted: !known,
      };
    }),
    { unit: 'dosare' },
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
      <div><b>${count(c.identitati)}</b><span>identități distincte</span></div>
      <div><b>${c.cotaTopFilerilor.top1la_suta === null ? '—' : pct(c.cotaTopFilerilor.top1la_suta)}</b><span>din cereri, de la primul 1% dintre depunători</span></div>
      <div><b>${inst.cotaDinCereri === null ? '—' : pct(inst.cotaDinCereri)}</b><span>de la ${count(inst.identitati)} identități cu tipar instituțional</span></div>
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
      detail: [['din toate identitățile', pct(row.cota)]] as [string, string][],
    })),
    { unit: 'identități' },
  );

  const roles = Object.entries(c.peGrupDeCalitate).sort((a, b) => b[1] - a[1]);
  const roleTotal = roles.reduce((sum, [, n]) => sum + n, 0) || 1;
  bars(
    el('calitati'),
    roles.map(([group, n]) => ({
      label: GROUPS[group] ?? group,
      value: n,
      note: pct(n / roleTotal),
      detail: [['din toate calitățile', pct(n / roleTotal)]] as [string, string][],
    })),
    { unit: 'identități' },
  );

  bars(
    el('gradient'),
    stats.gradientArhivare.map((row) => ({
      label: String(row.anInregistrare),
      value: row.medianaNaivaZile,
      note: `${count(row.dosareVizibileSolutionate)} dosare vizibile`,
      detail: [
        ['dosare încă vizibile', count(row.dosareVizibileSolutionate)],
        [
          '',
          'Nu este durata reală a anului: este durata celor care se mai văd. Cu cât anul e mai vechi, cu atât ce a rămas e mai lent.',
        ],
      ] as [string, string][],
    })),
    { format: (value) => days(Math.round(value)), unit: 'mediana naivă' },
  );
}

/**
 * Build the two selects and re-render on every change.
 *
 * A native `<select>` rather than a list of buttons because there are 240 courts, and a select is
 * the one control every platform makes searchable by typing without a line of script.
 */
function wireFilter(stats: Stats, file: CourtsFile): void {
  const form = el('filtre') as HTMLFormElement;
  const scope = el('scope') as HTMLSelectElement;
  const tier = el('tier') as HTMLSelectElement;
  const state = el('filter-state');
  form.hidden = false;

  const counties = new Map<string, Court[]>();
  for (const court of file.instante) {
    if (!court.judet) continue;
    const list = counties.get(court.judet);
    if (list) list.push(court);
    else counties.set(court.judet, [court]);
  }
  const countyName = (code: string) => file.judete[code] ?? code;

  const option = (value: string, label: string) =>
    `<option value="${esc(value)}">${esc(label)}</option>`;

  scope.innerHTML =
    option('tara', 'Toată țara') +
    `<optgroup label="Județe">${[...counties.keys()]
      .sort((a, b) => countyName(a).localeCompare(countyName(b), 'ro'))
      .map((code) =>
        option(`j:${code}`, `${countyName(code)} — ${counties.get(code)!.length} instanțe`),
      )
      .join('')}</optgroup>` +
    `<optgroup label="Instanțe">${[...file.instante]
      .sort((a, b) => (a.nume ?? a.institutie).localeCompare(b.nume ?? b.institutie, 'ro'))
      .map((court) => option(`i:${court.institutie}`, court.nume ?? court.institutie))
      .join('')}</optgroup>`;

  const levels = LEVEL_ORDER.filter((level) =>
    file.instante.some((court) => court.level === level),
  );
  tier.innerHTML = option('toate', 'Toate gradele') + levels.map((l) => option(l, l)).join('');

  // The proposed courts are added only once the administrative model has been fetched, which
  // happens the first time a reader asks for one. It is 1,6 MB and every other view on this page
  // works without it; making the default load pay for a section most readers will not open is
  // the wrong trade on a page whose whole point is that it is a document.
  let proposal: Proposal | null = null;
  async function ensureProposal(): Promise<Proposal | null> {
    if (proposal) return proposal;
    state.textContent = 'Se încarcă modelul administrativ (1,6 MB) și se rulează comasarea…';
    try {
      const [coupled, communes] = await Promise.all([
        loadCoupling(BASE),
        load<ArondareInstante>('arondare-instante.json'),
      ]);
      const scenario = readScenario(location.hash);
      const arondare = assign(coupled, scenario.params, scenario.pins);
      proposal = proposedCourts(arondare, coupled, communes, file, file.praguriZile);
      scope.insertAdjacentHTML(
        'beforeend',
        `<optgroup label="Instanțe propuse — ${
          changedParams(scenario.params).length ? 'la parametrii din link' : 'la parametrii impliciți'
        }">${proposal.courts
          .map((court) => option(`p:${court.seat}`, `${court.nume} (${court.judet})`))
          .join('')}</optgroup>`,
      );
      return proposal;
    } catch (error) {
      state.textContent = `Comasarea nu a putut fi calculată: ${String(error)}`;
      return null;
    }
  }

  async function apply(): Promise<void> {
    const value = scope.value;

    // A proposed court is a set of fractions of existing ones, so it does not go through the
    // court-list path at all.
    if (value.startsWith('p:')) {
      const ready = await ensureProposal();
      const found = ready?.courts.find((court) => `p:${court.seat}` === value);
      if (!found) {
        state.textContent = 'Instanța propusă nu a putut fi calculată.';
        return;
      }
      tier.disabled = true;
      const perThousand = found.populatie
        ? Math.round((found.pooled.dosare / found.populatie) * 1000)
        : null;
      renderScope(
        viewFromPooled(found.pooled, file.praguriZile, found.nume),
        `${found.nume} (propusă)`,
        `<div><b>${count(found.populatie)}</b><span>locuitori</span></div>` +
          (perThousand === null
            ? ''
            : `<div><b>${count(perThousand)}</b><span>dosare la mia de locuitori</span></div>`),
      );
      markNationalSections(true, 'o instanță propusă');
      state.textContent =
        `${count(found.unitati)} unități consolidate · ${pct(found.cotaInvarianta)} din dosarele ` +
        'acestui sediu vin de la instanțe pe care harta nu le împarte, deci nu depind de ' +
        `repartiția pe populație (${pct(ready!.cotaInvariantaNationala)} pe toată țara).`;
      return;
    }

    const single = value.startsWith('i:');
    tier.disabled = single;

    let selected = file.instante;
    let label = '';
    if (value.startsWith('j:')) {
      const code = value.slice(2);
      selected = counties.get(code) ?? [];
      label = countyName(code);
    } else if (single) {
      const wanted = value.slice(2);
      selected = file.instante.filter((court) => court.institutie === wanted);
      label = selected[0]?.nume ?? wanted;
    }
    if (!single && tier.value !== 'toate') {
      selected = selected.filter((court) => court.level === tier.value);
      label = label ? `${label}, ${tier.value}` : tier.value;
    }

    const national = value === 'tara' && tier.value === 'toate';
    // At national scope the authoritative file is used rather than the sum of the courts. They
    // agree — the per-court file is built to sum to it — but if they ever stop agreeing, the
    // page should show the figure the national document states and the tests should catch the
    // divergence, rather than the page quietly preferring its own arithmetic.
    renderScope(national ? viewFromStats(stats) : viewFromCourts(selected, file.praguriZile), label);
    markNationalSections(!national, label || 'această selecție');

    state.textContent = national
      ? `Toate cele ${count(file.instante.length)} de instanțe colectate.`
      : `${count(selected.length)} ${selected.length === 1 ? 'instanță' : 'instanțe'} · ` +
        'durata și termenele se calculează pe cohortă, din histogramele însumate.';
  }

  // The selection lives in the URL, for the reason the map next door already puts its scenario
  // there: a figure nobody can link to is a figure nobody can dispute. Someone who finds that
  // their county's median interval is three weeks needs to be able to send that, not a
  // description of which two dropdowns to move.
  //
  // The hash is `URLSearchParams`, which is the administrative app's format rather than a
  // second one invented here. That matters for what comes next: the reform's proposed courts
  // are a function of the sliders on that map, so a link has to be able to carry a scenario and
  // a selection at once. Sharing the format means the two sets of keys sit side by side, and
  // each side ignores what it does not recognise.
  const LOCATION = 'loc';
  const TIER = 'grad';

  function readHash(): void {
    const params = new URLSearchParams(location.hash.replace(/^#/, ''));
    const wanted = params.get(LOCATION);
    const level = params.get(TIER);
    if (wanted && [...scope.options].some((o) => o.value === wanted)) scope.value = wanted;
    if (level && [...tier.options].some((o) => o.value === level)) tier.value = level;
  }

  function writeHash(): void {
    // Preserve every key this page did not write. A reader who arrived from the map carries a
    // scenario in the hash, and dropping it on the first dropdown change would silently return
    // them to the default country.
    const params = new URLSearchParams(location.hash.replace(/^#/, ''));
    params.delete(LOCATION);
    params.delete(TIER);
    if (scope.value !== 'tara') params.set(LOCATION, scope.value);
    if (tier.value !== 'toate' && !scope.value.startsWith('i:')) params.set(TIER, tier.value);
    const query = params.toString();
    // replaceState, not a hash assignment: moving the filter is a change of view rather than a
    // navigation, and stacking a history entry per dropdown change makes Back unusable.
    history.replaceState(null, '', query ? `#${query}` : location.pathname);
  }

  const onChange = () => {
    writeHash();
    void apply();
  };
  scope.addEventListener('change', onChange);
  tier.addEventListener('change', onChange);
  window.addEventListener('hashchange', () => {
    readHash();
    void apply();
  });

  // A link straight to a proposed court has to load the model before the option it names
  // exists, so the hash is read twice: once to see what was asked for, and again after the
  // options it may refer to have been added.
  // Reaching the proposed courts costs 1,6 MB, so it is a button rather than something the page
  // does on the reader's behalf. It disappears once the option group exists.
  const addProposal = el('load-proposal') as HTMLButtonElement;
  addProposal.addEventListener('click', () => {
    addProposal.disabled = true;
    void ensureProposal().then((ready) => {
      addProposal.hidden = Boolean(ready);
      addProposal.disabled = false;
      if (ready) {
        // A failed direct-link load has not selected its missing option yet.
        // Read the current hash after retry so intervening filter changes win.
        const wanted = new URLSearchParams(location.hash.replace(/^#/, '')).get(LOCATION);
        if (wanted?.startsWith('p:')) {
          readHash();
          void apply();
          return;
        }
        state.textContent =
          `${count(ready.courts.length)} instanțe propuse, calculate din harta administrativă. ` +
          `${pct(ready.cotaInvariantaNationala)} din dosare ajung întregi la un sediu. ` +
          (ready.trunchiate
            ? `${count(ready.trunchiate)} instanțe necolectate au fost scoase din rutare.`
            : '');
      }
    });
  });

  const wanted = new URLSearchParams(location.hash.replace(/^#/, '')).get(LOCATION);
  const start = wanted?.startsWith('p:')
    ? ensureProposal().then((ready) => {
        addProposal.hidden = Boolean(ready);
      })
    : Promise.resolve();
  void start.then(() => {
    readHash();
    return apply();
  });
}

/** The caveats and the source line, from both files, once. */
function finish(stats: Stats, courts: CourtsFile | null): void {
  const limitations = [...stats.limitations, ...(courts?.limitations ?? [])];
  el('limitari').innerHTML = limitations
    .map(
      (limitation) => `
      <details class="lim ${limitation.severity}">
        <summary><span class="sev">${limitation.severity}</span> ${esc(limitation.id.replace(/-/g, ' '))}</summary>
        <p>${esc(limitation.text)}</p>
      </details>`,
    )
    .join('');

  el('sursa').textContent = `${stats.publisher} · ${stats.provenance.locator}`;
  wireTooltips();
}

main().catch((error) => {
  el('app').insertAdjacentHTML(
    'afterbegin',
    `<p class="warn">Datele nu au putut fi încărcate: ${String(error)}. Rulează
     <code>node scripts/copy-data.mjs</code> și
     <code>uv run python scripts/build_portal_stats.py</code>.</p>`,
  );
});

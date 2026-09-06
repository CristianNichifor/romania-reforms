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

import { bars, count, esc, quartiles, share, wireTooltips } from './charts';

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
      <div><b>${count(snap.dosare)}</b><span>dosare</span></div>
      <div><b>${count(snap.instante)}</b><span>instanțe</span></div>
      <div><b>${count(snap.sedinte)}</b><span>termene</span></div>
      <div><b class="span">${snap.registeredFrom} — ${snap.registeredTo}</b><span>înregistrate</span></div>
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
      detail: [['sursa', `Starea justiției ${row.label}, Anexa 1`]],
    })),
    { unit: 'volum de activitate, judecătorii' },
  );

  bars(
    el('tipuri'),
    stats.caseTypes.slice(0, 10).map((row) => ({
      label: categoryName(row.categorie),
      value: row.dosare,
      note: pct(row.share),
      detail: [['din toate dosarele', pct(row.share)]],
    })),
    { unit: 'dosare' },
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

  const inDays = (value: number) => days(Math.round(value));
  // Two ticks, not four: these two charts sit side by side, so each track is half as wide and
  // five labels reading "3,3 luni" run into one another.
  quartiles(el('primul'), strips(stats.primulTermen), {
    format: inDays,
    unit: 'dosare',
    targetTicks: 2,
  });
  quartiles(el('intervale'), strips(stats.termene.intervalZileByLevel), {
    format: inDays,
    unit: 'intervale',
    targetTicks: 2,
  });

  const a = stats.amanari;
  const ofTerms: [string, string][] = [['din', `${count(a.termeneCuSolutie)} termene cu soluție`]];
  bars(
    el('amanari'),
    [
      {
        label: 'Amână cauza',
        value: a.amanareCauza,
        note: pct(a.amanareCauza / a.termeneCuSolutie),
        detail: [...ofTerms, ['', 'Nu s-a ajuns la cauză: se fixează alt termen.']],
      },
      {
        label: 'Amână pronunțarea',
        value: a.amanarePronuntare,
        note: pct(a.amanarePronuntare / a.termeneCuSolutie),
        detail: [...ofTerms, ['', 'Instanța a judecat și își scrie hotărârea. Este progres, nu întârziere.']],
      },
      {
        label: 'Termen preschimbat',
        value: a.termenPreschimbat,
        note: pct(a.termenPreschimbat / a.termeneCuSolutie),
        detail: [...ofTerms, ['', 'Data a fost mutată, adesea înainte ca ședința să înceapă.']],
      },
    ],
    { unit: 'termene' },
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

  const onRoll = stats.vechimeDosarePeRol.reduce((sum, row) => sum + row.dosare, 0);
  bars(
    el('vechime'),
    stats.vechimeDosarePeRol.map((row) => ({
      label: row.to === null ? `peste ${row.from} de zile` : `${row.from}–${row.to} de zile`,
      value: row.dosare,
      note: row.share === null ? '' : pct(row.share),
      detail: [
        ['din dosarele pe rol', row.share === null ? '' : pct(row.share)],
        ['dosare pe rol, total', count(onRoll)],
      ] as [string, string][],
    })),
    { unit: 'dosare' },
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
    { format: inDays, unit: 'mediana naivă' },
  );

  el('limitari').innerHTML = stats.limitations
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

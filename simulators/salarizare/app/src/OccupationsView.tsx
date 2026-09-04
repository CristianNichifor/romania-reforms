import { useMemo, useState } from 'react';

import { COMPONENT_LABELS, COMPONENTS, compareComposition } from '../../engine/composition';
import type { Component, Shares, Side } from '../../engine/composition';
import { resolveGroups } from '../../engine/occupations';
import type { DkOccupation, GroupsDocument, ResolvedGroup } from '../../engine/occupations';
import type { Regime } from '../../engine/types';
import { amountLine, amountRange } from './money';
import type { Rates } from './money';
import type { Scenario } from '../../engine/scenario';
import { checkAgainstMeasured, gridPay } from '../../engine/measured';
import type { MeasuredSeries, SectorCheck } from '../../engine/measured';

const times = (n: number) =>
  `${n.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}×`;

export interface OccupationBenchmarks {
  /** Median base salary across the Romanian grid — the middle of its own system. */
  roMedianBase: number;
  /** Median earnings of all Danish public employees — the middle of its own system. */
  dkMedian: number;
}

export default function OccupationsView({
  regime,
  groups,
  danish,
  benchmarks,
  rates,
  roComposition,
  scenario,
  onScenario,
  measured,
  inForce,
}: {
  regime: Regime;
  groups: GroupsDocument;
  danish: DkOccupation[];
  benchmarks: OccupationBenchmarks;
  rates: Rates;
  /** What Romania paid, by budget chapter and then by year. */
  roComposition: Record<string, Record<string, Shares>> | null;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
  /** What INS measured public employees are paid, education and health only. */
  measured: MeasuredSeries[] | null;
  inForce: Regime | null;
}) {
  const [showLegal, setShowLegal] = useState(false);
  const [withCap, setWithCap] = useState(true);

  const resolved = useMemo(
    () =>
      resolveGroups(regime, groups, danish, {
        roPublicAverage: benchmarks.roMedianBase,
        dkPublicMedian: benchmarks.dkMedian,
      }),
    [regime, groups, danish, benchmarks],
  );

  const bySector = useMemo(() => {
    const map = new Map<string, ResolvedGroup[]>();
    for (const r of resolved) {
      const list = map.get(r.group.sector) ?? [];
      list.push(r);
      map.set(r.group.sector, list);
    }
    return [...map.entries()];
  }, [resolved]);

  // Four sectors' worth of paired range bars ran to five and a half thousand pixels, which
  // is a list dumped rather than a page. Narrowing to one sector is the fix, and the
  // choice goes in the hash so a narrowed page is still a link.
  const sector = scenario.sector ?? null;
  const shown = sector ? bySector.filter(([name]) => name === sector) : bySector;

  // One axis for the whole page, so a bar in health is directly comparable with one in
  // administration. Per-row scaling would make every occupation look the same width.
  const axisMax = useMemo(() => {
    const all = resolved.flatMap((r) => [
      showLegal && r.roMax !== null ? r.roMax / 100 / benchmarks.roMedianBase : 0,
      withCap && r.roCapped ? r.roCapped.q3 / 100 / benchmarks.roMedianBase : 0,
      r.roQ3 !== null ? r.roQ3 / 100 / benchmarks.roMedianBase : 0,
      r.dkRatio?.q3 ?? 0,
    ]);
    return Math.max(...all, 2.5) * 1.04;
  }, [resolved, benchmarks.roMedianBase, showLegal, withCap]);

  return (
    <>
      <header className="masthead">
        <h1>Aceeași meserie, două sisteme</h1>
        <p>
          Funcțiile din proiect, regrupate după meserie și nu după anexă, apoi puse lângă ce
          câștigă aceeași meserie în sectorul public danez. Fiecare bară e raportată la mijlocul
          propriului sistem, deci se pot compara direct.
        </p>
      </header>

      <div className="disclaimer">
        <strong>Cifra daneză include sporurile. Cea românească, doar dacă bifezi.</strong> Pentru
        medici, asistenți sau profesori Danemarca nu are grilă — salariul se negociază peste un
        minim din contractul colectiv, iar ce se publică sunt câștiguri efective. Ca să fie o
        comparație corectă, partea românească trebuie să primească și ea sporurile.
        <details>
          <summary>Ce spune de fapt plafonul de 20%</summary>
          <p>
            Art. 21 alin. (2) plafonează suma sporurilor la 20% din suma salariilor de bază —{' '}
            <strong>pe ordonator principal de credite și pe sursă de finanțare, nu pe persoană</strong>.
            Este o medie a instituției: un om poate trece binișor peste 20%, dacă altul stă sub.
          </p>
          <p>
            În plus, legea scoate din plafon o listă lungă: munca de noapte (25%), orele
            suplimentare (75–100%), sporul pentru handicap (15% din valoarea de referință), turele
            din sănătate (15%), izolarea în Delta Dunării (15%), administrarea fondurilor europene
            (până la 40%) și premiul de performanță (10–20%, cu plafonul lui separat de 4%). Sporul
            pentru proiecte europene intră doar cu partea cofinanțată din buget. Practic, în plafon
            rămân trei: controlul financiar preventiv, condițiile periculoase și capacitatea
            fiscal-bugetară locală.
          </p>
          <p>
            Bara „cu sporuri în plafon” de mai jos adaugă exact 20% peste bază. Este o ilustrare a
            ce implică plafonul, nu un drept al nimănui — iar sporurile exceptate pot urca peste ea.
          </p>
        </details>
      </div>

      <section>
        <div className="card controls occ-controls">
          <label className="claim">
            <input type="checkbox" checked={withCap} onChange={() => setWithCap((v) => !v)} />
            <span>
              Adaugă sporurile în plafon la partea românească (+20%) — altfel se compară baza
              românească cu câștigul danez cu tot cu sporuri
            </span>
          </label>
          <label className="claim">
            <input type="checkbox" checked={showLegal} onChange={() => setShowLegal((v) => !v)} />
            <span>Arată și intervalul legal complet al bazei (bara palidă)</span>
          </label>
          <div className="occ-key">
            <span><i className="k-ro-solid" /> România, salariul de bază</span>
            {withCap && <span><i className="k-ro-cap" /> + sporuri în plafon (20%)</span>}
            {showLegal && <span><i className="k-ro-faint" /> tot ce permite legea, la bază</span>}
            <span><i className="k-dk" /> Danemarca, cuartilele angajaților</span>
            <span><i className="k-mid" /> mijlocul fiecărui sistem</span>
          </div>
        </div>
      </section>

      <section>
        <div className="sector-filter">
          <span className="sector-label">Arată</span>
          <button
            className={sector === null ? 'on' : ''}
            onClick={() => onScenario({ ...scenario, sector: undefined })}
          >
            toate ({resolved.length})
          </button>
          {bySector.map(([name, rows]) => (
            <button
              key={name}
              className={sector === name ? 'on' : ''}
              onClick={() => onScenario({ ...scenario, sector: name })}
            >
              {name} ({rows.length})
            </button>
          ))}
        </div>
      </section>

      {shown.map(([sector, rows]) => (
        <section key={sector}>
          <h2>{sector}</h2>
          <div className="occ-list">
            {rows.map((r) => (
              <OccupationRow key={r.group.id} row={r} axisMax={axisMax} showLegal={showLegal}
                             withCap={withCap} benchmarks={benchmarks} rates={rates} />
            ))}
          </div>
        </section>
      ))}

      <MeasuredSection regime={regime} inForce={inForce} measured={measured} rates={rates} />

      <CompositionSection roComposition={roComposition} resolved={resolved} danish={danish} />

      <section>
        <h2>Cum au fost făcute grupele</h2>
        <div className="card readme-grid">
          <p>
            Proiectul împarte funcțiile pe anexe, care urmează angajatorul și statutul juridic.
            Statistica daneză le împarte pe meserii, ca piața muncii. Grupele de aici urmează
            meseria, iar fiecare spune ce regulă a folosit și câte funcții a prins — ca să poată fi
            contestată gruparea, nu doar cifra.
          </p>
          <p>
            Reperul românesc este mediana salariului de bază din toată grila,{' '}
            {amountLine(benchmarks.roMedianBase, 'RON', rates)}. Cel danez este mediana câștigului
            tuturor angajaților publici, {amountLine(benchmarks.dkMedian, 'DKK', rates)}. Fiecare
            sistem e măsurat cu propria lui unitate, iar raportul e ce se compară.
          </p>
        </div>
      </section>
    </>
  );
}

function OccupationRow({
  row,
  axisMax,
  showLegal,
  withCap,
  benchmarks,
  rates,
}: {
  row: ResolvedGroup;
  axisMax: number;
  showLegal: boolean;
  withCap: boolean;
  benchmarks: OccupationBenchmarks;
  rates: Rates;
}) {
  const pos = (v: number) => `${Math.min((v / axisMax) * 100, 100)}%`;
  const span = (a: number, b: number) => ({ left: pos(a), width: `${Math.max(((b - a) / axisMax) * 100, 0.6)}%` });

  const roQ1 = row.roQ1 !== null ? row.roQ1 / 100 / benchmarks.roMedianBase : null;
  const roQ3 = row.roQ3 !== null ? row.roQ3 / 100 / benchmarks.roMedianBase : null;
  const roMed = row.roMedian !== null ? row.roMedian / 100 / benchmarks.roMedianBase : null;
  const roCapQ1 = row.roCapped ? row.roCapped.q1 / 100 / benchmarks.roMedianBase : null;
  const roCapQ3 = row.roCapped ? row.roCapped.q3 / 100 / benchmarks.roMedianBase : null;
  const roLo = row.roMin !== null ? row.roMin / 100 / benchmarks.roMedianBase : null;
  const roHi = row.roMax !== null ? row.roMax / 100 / benchmarks.roMedianBase : null;

  const weak = row.group.confidence === 'assumed' || row.group.disputed;

  return (
    <article className="card occ-row">
      <header className="occ-head">
        <div>
          <h3>{row.group.label}</h3>
          <p className="occ-proposed">{row.group.proposedName}</p>
        </div>
        <div className="badges">
          <span className="badge">{row.matched.length} funcții</span>
          {row.bandedPositions > 0 && (
            <span className="badge">±15% pe categoria unității</span>
          )}
          {weak && <span className="badge weak">echivalare slabă</span>}
        </div>
      </header>

      <div className="occ-bars">
        <div className="occ-line">
          <span className="occ-label">România</span>
          <div className="occ-track">
            <span className="occ-mid" style={{ left: pos(1) }} />
            {showLegal && roLo !== null && roHi !== null && (
              <div className="occ-faint" style={span(roLo, roHi)} />
            )}
            {withCap && roCapQ1 !== null && roCapQ3 !== null && (
              <div className="occ-cap" style={span(roCapQ1, roCapQ3)} />
            )}
            {roQ1 !== null && roQ3 !== null && <div className="occ-solid ro" style={span(roQ1, roQ3)} />}
            {roMed !== null && <span className="occ-tick" style={{ left: pos(roMed) }} />}
          </div>
          <span className="occ-value">
            {withCap && roCapQ1 !== null && roCapQ3 !== null
              ? `${times(roCapQ1)}–${times(roCapQ3)}`
              : roQ1 !== null && roQ3 !== null
                ? `${times(roQ1)}–${times(roQ3)}`
                : '—'}
          </span>
        </div>

        <div className="occ-line">
          <span className="occ-label">Danemarca</span>
          <div className="occ-track">
            <span className="occ-mid" style={{ left: pos(1) }} />
            {row.dkRatio && <div className="occ-solid dk" style={span(row.dkRatio.q1, row.dkRatio.q3)} />}
            {row.dkRatio && <span className="occ-tick" style={{ left: pos(row.dkRatio.median) }} />}
          </div>
          <span className="occ-value">
            {row.dkRatio ? `${times(row.dkRatio.q1)}–${times(row.dkRatio.q3)}` : '—'}
          </span>
        </div>
        {/*
          An empty Danish bar has two very different meanings, and a bare dash gives the
          wrong one. For most groups the comparator exists and the number simply did not
          load; for the trades it does not exist at all, and borrowing another occupation's
          figure to fill the row would be the easiest invented comparison on the page.
        */}
        {row.group.dkOccupations.length === 0 && (
          <p className="occ-nocomp">
            Statistica daneză nu publică această ocupație separat, deci nu există cu ce fi
            comparată. Rândul rămâne gol intenționat.
          </p>
        )}
      </div>

      <div className="occ-money">
        <span>
          <b>RO</b>{' '}
          {row.roQ1 !== null && row.roQ3 !== null
            ? amountRange(
                (withCap && row.roCapped ? row.roCapped.q1 : row.roQ1) / 100,
                (withCap && row.roCapped ? row.roCapped.q3 : row.roQ3) / 100,
                'RON',
                rates,
              )
            : '—'}
          {withCap && <em className="occ-caphint"> cu sporuri în plafon</em>}
        </span>
        <span>
          <b>DK</b> {row.dk ? amountRange(row.dk.q1, row.dk.q3, 'DKK', rates) : '—'}
        </span>
      </div>

      <details className="why">
        <summary>Ce intră în grupă și de ce</summary>
        <p className="equiv-note">{row.group.basis}</p>
        {row.bandedPositions > 0 && (
          <p className="equiv-note">
            <strong>Coeficientul publicat e un mijloc, nu o sumă.</strong> Pentru{' '}
            {row.bandedPositions} dintre funcțiile din grupă, Anexa II Cap. II Art. 10 stabilește
            nivelul între −15% și +15% față de cifra din anexă, în funcție de categoria unității —
            diminuat la unitățile medico-sociale și ambulatorii, majorat la medicina legală.
            Categoriile se stabilesc prin hotărâre de Guvern, care încă nu există, deci salariul nu
            se poate calcula din lege: doar intervalul. Barele de mai sus includ banda.
          </p>
        )}
        <p className="equiv-note">
          <strong>În afara plafonului de 20%:</strong>{' '}
          {row.exemptSupplements
            .map((e) => `${e.name}${e.rate !== null ? ` (${Math.round(e.rate * 100)}%)` : ''}`)
            .join('; ')}
          . Acestea se adaugă peste bara de mai sus, dacă persoana le îndeplinește condițiile.
        </p>
        <ul className="matched">
          {row.matched.slice(0, 14).map((m) => (
            <li key={m.code}>
              {m.name} <code>{m.code}</code>
            </li>
          ))}
          {row.matched.length > 14 && <li className="more">…și încă {row.matched.length - 14}</li>}
        </ul>
      </details>
    </article>
  );
}

/** Budget chapters are the finest cut Romania publishes; these are the page's sectors. */
const SECTOR_SCOPE: Record<string, string> = {
  'Sănătate': 'sanatate',
  'Educație': 'invatamant',
  'Administrație': 'administratie',
  'Ordine publică': 'ordine-publica',
};

const pctOf = (n: number, digits = 1) =>
  `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: digits })}%`;

/** One stacked bar. Segments under a hairline are dropped so they cannot look like a mark. */
function Bar({ side, label, sub }: { side: Side; label: string; sub?: string }) {
  return (
    <div className="comp-row">
      <div className="comp-name">
        {label}
        {sub && <small>{sub}</small>}
      </div>
      <div>
        <div className="comp-bar">
          {side.slices
            .filter((s) => s.share > 0.002)
            .map((s) => (
              <div
                key={s.component}
                className={`comp-seg ${s.component}`}
                style={{ width: `${s.share * 100}%` }}
                title={`${COMPONENT_LABELS[s.component]}: ${pctOf(s.share)}`}
              />
            ))}
        </div>
        <div className="comp-tail">
          <span>
            bază <b>{pctOf(side.slices.find((s) => s.component === 'basic')?.share ?? 0, 0)}</b>
          </span>
          <span>
            peste bază <b>{pctOf(side.supplements)}</b>
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * The Romanian and Danish pay compositions, both measured from what was paid.
 *
 * Until the budget execution was imported this section could only put a Danish fact next
 * to a Romanian legal ceiling. Both sides are now facts, which is why the comparison is
 * finally worth drawing — and why the caveats that remain are about *which* facts.
 */
function CompositionSection({
  roComposition,
  resolved,
  danish,
}: {
  roComposition: Record<string, Record<string, Shares>> | null;
  resolved: ResolvedGroup[];
  danish: DkOccupation[];
}) {
  /** The most recent year in a scope, which is what every bar on this page shows. */
  const latest = (scope: string): Shares | undefined => {
    const byYear = roComposition?.[scope];
    if (!byYear) return undefined;
    const years = Object.keys(byYear).sort();
    return byYear[years[years.length - 1]];
  };
  const national = useMemo(() => {
    // The all-employees row is not one of the occupation groups — it is the Danish
    // total, and it has to come from the raw table or the headline silently disappears.
    const dkTotal = danish.find((o) => o.occupation.startsWith('Public employees'))?.composition;
    const ro = latest('national');
    if (!ro) return null;
    return compareComposition(ro, (dkTotal ?? {}) as Shares);
  }, [roComposition, danish]);

  const bySector = useMemo(() => {
    const map = new Map<string, ResolvedGroup[]>();
    for (const r of resolved) {
      if (!r.dkComposition) continue;
      const list = map.get(r.group.sector) ?? [];
      list.push(r);
      map.set(r.group.sector, list);
    }
    return [...map.entries()];
  }, [resolved]);

  if (!roComposition) return null;

  return (
    <section>
      <h2>Din ce e făcut salariul</h2>
      <p className="lede">
        Amândouă părțile sunt acum ce s-a plătit efectiv, nu ce permite legea: Danemarca din
        statistica de câștiguri, România din execuția bugetară pe clasificația economică — acolo
        unde „Salarii de bază” stă la 10.01.01 și sporurile la 10.01.05 și 10.01.06.
      </p>

      {national && national.timesLarger !== null && (
        <>
          <div className="comp-hero">
            <span className="big">
              {national.timesLarger.toLocaleString('ro-RO', { maximumFractionDigits: 1 })}×
            </span>
            <p>
              Atât e de mare stratul de peste salariul de bază în România față de Danemarca:{' '}
              {pctOf(national.ro.supplements)} din plată, față de {pctOf(national.dk.supplements)}.
              Nu plafonul de 20% e neobișnuit — ci cât de mult atârnă deja plata de el.
            </p>
          </div>
          <div className="card">
            <Bar side={national.ro} label="România" sub="tot sectorul bugetar, execuție 2025" />
            <Bar side={national.dk} label="Danemarca" sub="toți angajații publici, 2024" />
          </div>
        </>
      )}

      {bySector.map(([sector, rows]) => {
        const scope = SECTOR_SCOPE[sector];
        const shares = scope ? latest(scope) : undefined;
        if (!shares) return null;
        return (
          <div className="card" key={sector} style={{ marginTop: 16 }}>
            <h3>{sector}</h3>
            <Bar
              side={compareComposition(shares, {}).ro}
              label="România"
              sub="tot capitolul bugetar — statul nu publică defalcarea pe meserii"
            />
            {rows.map((r) => (
              <Bar
                key={r.group.id}
                side={compareComposition({}, r.dkComposition as Shares).dk}
                label={r.group.label}
                sub="Danemarca"
              />
            ))}
          </div>
        );
      })}

      {(() => {
        // One series, so no legend and no palette: the question is simply whether the
        // layer above base pay is growing, and a single bar per year answers it. The
        // figures come from the same execution series the bars above use.
        const byYear = roComposition?.national ?? {};
        const years = Object.keys(byYear).sort();
        if (years.length < 2) return null;
        const points = years.map((y) => ({
          year: y,
          share: compareComposition(byYear[y], {}).ro.supplements,
        }));
        const max = Math.max(...points.map((p) => p.share)) * 1.15;
        const first = points[0];
        const last = points[points.length - 1];
        const change = last.share - first.share;
        return (
          <div className="card" style={{ marginTop: 16 }}>
            <h3>Crește stratul de peste salariul de bază?</h3>
            <p className="hint">
              Ponderea a tot ce se plătește peste salariul de bază, în fiecare an de execuție.{' '}
              {Math.abs(change) < 0.005
                ? 'Practic neschimbată de la un capăt la altul.'
                : `${change > 0 ? 'A urcat' : 'A scăzut'} cu ${(Math.abs(change) * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 })} puncte procentuale între ${first.year} și ${last.year} — o schimbare de pondere, nu de procent.`}
            </p>
            <div className="trend">
              {points.map((p) => (
                <div className="trend-col" key={p.year}>
                  <span className="trend-value">{pctOf(p.share)}</span>
                  <div className="trend-bar" style={{ height: `${(p.share / max) * 100}%` }} />
                  <span className="trend-year">{p.year}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {national && (
        <details className="table-view">
          <summary>Vezi compoziția ca tabel</summary>
          <table className="data">
            <thead>
              <tr>
                <th>Componentă</th>
                <th className="num">România</th>
                <th className="num">Danemarca</th>
              </tr>
            </thead>
            <tbody>
              {COMPONENTS.map((c: Component) => (
                <tr key={c}>
                  <td>{COMPONENT_LABELS[c]}</td>
                  <td className="num">
                    {pctOf(national.ro.slices.find((s) => s.component === c)?.share ?? 0)}
                  </td>
                  <td className="num">
                    {pctOf(national.dk.slices.find((s) => s.component === c)?.share ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      <div className="comp-key">
        {COMPONENTS.map((c: Component) => (
          <span key={c}>
            <i style={{ background: `var(--comp-${c})` }} />
            {COMPONENT_LABELS[c]}
          </span>
        ))}
      </div>

      {national && (
        <div className="comp-excl">
          <p>Ce s-a scos înainte de comparație, ca cele două să măsoare același lucru:</p>
          <ul>
            {[...national.dk.excluded, ...national.ro.excluded].map((e) => (
              <li key={e.key}>
                <b>{e.label}</b> ({pctOf(e.share)}) — {e.reason}
              </li>
            ))}
            <li>
              <b>Concediul de odihnă</b> nu se scade din nicio parte. Danemarca îl tipărește
              separat, {pctOf(national.dk.holidayInsideBasic)} din câștig, dar ca sub-poziție a
              salariului de bază — omul în concediu își primește salariul, exact ca în România.
              Scăzut ca și cum ar fi o componentă aparte, ar răsturna concluzia.
            </li>
          </ul>
          <p>
            Execuția arată regimul actual, nu proiectul: plafonul de 20% n-a funcționat încă
            niciun an. Iar clasificația economică e un vocabular contabil — ce intră la „Sporuri
            pentru condiții de muncă” nu e exact mulțimea pe care Art. 21 o plafonează.
          </p>
        </div>
      )}
    </section>
  );
}

const SECTORS: Array<{ activity: string; family: string; label: string }> = [
  { activity: 'invatamant', family: 'I-invatamant', label: 'Învățământ' },
  { activity: 'sanatate', family: 'II-sanatate-asistenta-sociala', label: 'Sănătate și asistență socială' },
];

/**
 * The grid against a measurement, for the two sectors where one exists.
 *
 * Every Romanian number on this page so far has been what a statute says. INS publishes
 * the *base* salary — the same quantity the grid holds — for public employees in education
 * and health, so for those two the law can be checked rather than only described.
 */
function MeasuredSection({
  regime,
  inForce,
  measured,
  rates,
}: {
  regime: Regime;
  inForce: Regime | null;
  measured: MeasuredSeries[] | null;
  rates: Rates;
}) {
  const checks = useMemo(
    () =>
      measured
        ? SECTORS.map((s) => ({
            ...s,
            draft: checkAgainstMeasured(regime, measured, s.activity, s.family),
            old: inForce ? checkAgainstMeasured(inForce, measured, s.activity, s.family) : null,
          })).filter((s) => s.draft)
        : [],
    [regime, inForce, measured],
  );

  if (!checks.length) return null;

  return (
    <section>
      <h2>Grila față de ce se plătește de fapt</h2>
      <p className="lede">
        Până aici, fiecare cifră românească a fost ce spune legea. Institutul Național de
        Statistică publică salariul brut <strong>de bază</strong> — exact mărimea pe care o dă și
        grila — pentru angajații publici din învățământ și sănătate. Atât cât ține de cele două
        sectoare, legea poate fi verificată, nu doar descrisă.
      </p>

      {checks.map((sector) => {
        const d = sector.draft!;
        const axis = Math.max(d.grid.max, ...d.measured.map((m) => m.base)) * 1.05;
        return (
          <div className="card" key={sector.activity} style={{ marginTop: 14 }}>
            <div className="meas-head">
              <h3>{sector.label}</h3>
              <span className="meas-verdict">
                Mediana grilei {amountLine(d.grid.median, 'RON', rates)} · măsurat{' '}
                {amountLine(d.overall!.base, 'RON', rates)}{' '}
                <b className={d.ratio! > 1.05 ? 'fall' : ''}>
                  ({d.ratio! >= 1 ? '+' : ''}
                  {((d.ratio! - 1) * 100).toLocaleString('ro-RO', { maximumFractionDigits: 0 })}%)
                </b>
              </span>
            </div>

            <div className="meas-rows">
              {d.measured.map((m) => (
                <div className="meas-row" key={m.occupation}>
                  <div className="meas-name">
                    {m.occupation}
                    <small>{m.employees.toLocaleString('ro-RO')} salariați</small>
                  </div>
                  <div className="meas-track">
                    {/* The grid's range sits behind, the measurement on top of it. */}
                    <div
                      className="meas-grid"
                      style={{
                        left: `${(d.grid.min / axis) * 100}%`,
                        width: `${((d.grid.max - d.grid.min) / axis) * 100}%`,
                      }}
                    />
                    <div className="meas-median" style={{ left: `${(d.grid.median / axis) * 100}%` }} />
                    <div
                      className="meas-dot"
                      style={{ left: `${(m.base / axis) * 100}%` }}
                      title={`${m.occupation}: ${Math.round(m.base).toLocaleString('ro-RO')} lei`}
                    />
                  </div>
                  <div className="meas-num">{Math.round(m.base).toLocaleString('ro-RO')}</div>
                </div>
              ))}
            </div>

            <div className="occ-key" style={{ marginTop: 10 }}>
              <span><i className="k-grid-range" /> intervalul grilei ({d.grid.positions} funcții)</span>
              <span><i className="k-grid-median" /> mediana grilei</span>
              <span><i className="k-measured" /> măsurat de INS, {d.period}</span>
            </div>

            {sector.old?.ratio && (
              <p className="cmp-foot">
                Grila din anexele legii în vigoare, tipărită pentru 2022, dă o mediană de{' '}
                {amountLine(sector.old.grid.median, 'RON', rates)} — cu{' '}
                {(((sector.old.ratio ?? 1) - 1) * 100).toLocaleString('ro-RO', {
                  maximumFractionDigits: 0,
                })}
                % sub ce se plătea în {d.period}. Peste ea s-au aplicat majorări an de an, care nu
                sunt în anexe.
              </p>
            )}
          </div>
        );
      })}

      <div className="limits" style={{ marginTop: 16 }}>
        <div className="limit blocking">
          <div className="sev">blocant</div>
          <p>
            <strong>Grila se numără pe funcții, măsurătoarea pe oameni.</strong> Mediana grilei
            tratează un post ocupat de patruzeci de mii de învățători și unul ocupat de un singur
            inspector-șef ca pe două voturi egale. Cifra INS e ponderată cu numărul de angajați,
            fiindcă e o anchetă pe salariați. Ca să fie ponderată și grila ar trebui numărul de
            posturi pe fiecare funcție, iar România nu îl publică — exact golul pe care datele
            astea <em>nu</em> îl acoperă. Comparația e informativă, nu un test de egalitate.
          </p>
        </div>
        <div className="limit material">
          <div className="sev">de reținut</div>
          <p>
            Ancheta acoperă secțiunile CAEN A–S și omite secțiunea O — administrație publică și
            apărare. Învățământul și sănătatea sunt înăuntru; ministerele, poliția și armata nu.
            Și numără doar salariații cu program complet plătiți întreaga lună octombrie, ceea ce
            împinge media în sus față de statul de plată real.
          </p>
        </div>
      </div>
    </section>
  );
}

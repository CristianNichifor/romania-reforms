import { useMemo } from 'react';

import { readCap } from '../../engine/cap';
import type { CapSeries } from '../../engine/cap';
import type { PatchEffect, Proposal } from '../../engine/proposal';
import { resolveSeries, structure } from '../../engine/structure';
import type { StructureMetrics } from '../../engine/structure';
import type { Regime } from '../../engine/types';
import { amountLine } from './money';
import type { Rates } from './money';

function ro(n: number): string {
  return n.toLocaleString('ro-RO');
}
function pct(n: number): string {
  return `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`;
}
function ratio(n: number): string {
  return `1:${n.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

type Col = 'inForce' | 'ministry' | 'ours' | 'dk';

interface Cell {
  /** What the bar is drawn from. null renders as an explained dash, never as zero. */
  n: number | null;
  text: string;
  note?: string;
  /**
   * The figure comes from a sample too thin to be scored against a full grid.
   *
   * The Danish regime is 16 hand-built positions against Romania's 1 049. For a share
   * that does not matter — 0% back-solved is 0% either way. For a *count*, and for a
   * span computed from the extremes of a count, it decides the answer: a 16-row table
   * will always look simpler than a 1 049-row one, partly because it is and partly
   * because it is 16 rows. Such a cell still shows its number, but never wins the row.
   */
  sampled?: boolean;
}
interface Row {
  label: string;
  hint: string;
  /** Which direction is an improvement, for the one mark of emphasis per row. */
  better: 'lower' | 'higher' | 'none';
  cells: Record<Col, Cell>;
}

/**
 * The proposal's subtitle counts its own patches. Written by hand it said "cinci
 * reparații + o schimbare" while the file held six repairs and one change, and the
 * masthead promised six questions against a table of seven rows. Counts that describe
 * data belong to the data.
 */
function columnsFor(proposal: Proposal): Array<{ key: Col; title: string; sub: string }> {
  const changes = proposal.patches.filter((p) => p.policyChange).length;
  const repairs = proposal.patches.length - changes;
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return [
    { key: 'inForce', title: 'Legea în vigoare', sub: '153/2017, grila pentru 2022' },
    { key: 'ministry', title: 'Proiectul MMFTSS', sub: '16.07.2026' },
    {
      key: 'ours',
      title: 'Propunerea alternativă',
      sub: `${plural(repairs, 'reparație', 'reparații')} + ${plural(changes, 'schimbare', 'schimbări')}`,
    },
    { key: 'dk', title: 'Danemarca', sub: 'sectorul de stat' },
  ];
}

/** Positions whose variants differ only by where the post sits, not by what the job is. */
function fusedCount(regime: Regime): number {
  const context = new Set(['institutionLevel', 'sursa', 'celula']);
  return regime.positions.filter((p) => {
    if (p.variants.length < 2) return false;
    const jobs = new Set(
      p.variants.map((v) =>
        JSON.stringify(Object.entries(v.dims ?? {}).filter(([k]) => !context.has(k)).sort()),
      ),
    );
    return (
      jobs.size === 1 &&
      p.variants.some((v) => Object.keys(v.dims ?? {}).some((k) => context.has(k)))
    );
  }).length;
}

export default function CompareView({
  ministry,
  inForce,
  ours,
  denmark,
  proposal,
  effects,
  onOpen,
  rates,
  capSeries,
  period,
}: {
  ministry: Regime;
  /** Law 153/2017 — what people are paid under today. */
  inForce: Regime | null;
  ours: Regime;
  denmark: Regime | null;
  proposal: Proposal;
  effects: PatchEffect[];
  onOpen: (view: 'structure' | 'payslip' | 'echivalente') => void;
  rates: Rates;
  capSeries: CapSeries[] | null;
  period: string | null;
}) {
  const COLUMNS = useMemo(() => columnsFor(proposal), [proposal]);
  const opts = period ? { period } : undefined;
  const m = useMemo(() => structure(ministry, opts), [ministry, period]);
  const o = useMemo(() => structure(ours, opts), [ours, period]);
  // The whole schedule, unfiltered: "how many annual columns are there" is a fact about
  // the law, not about the year being viewed, and filtering would always answer one.
  const schedule = useMemo(() => structure(ministry).spanByPeriod, [ministry]);
  const f: StructureMetrics | null = useMemo(
    () => (inForce ? structure(inForce) : null),
    [inForce],
  );

  // 153/2017 declares no salary grades and phases nothing, so two of the seven questions
  // have no answer for it. An explained dash, never a zero that reads as "none".
  const lawCell = (n: number | null, text: string, note?: string): Cell =>
    f ? { n, text, note } : { n: null, text: '—', note: 'legea în vigoare nu e încărcată' };
  // The first column where the ratio actually moves. It is not the second: the phased
  // dignitary coefficients stay below a post that is not phased at all, so the eșalonare
  // is invisible for its first years — which is only visible if you can step through them.
  const firstMove = useMemo(
    () => schedule.find((p) => p.ratio > (schedule[0]?.ratio ?? 0)) ?? null,
    [schedule],
  );
  const d: StructureMetrics | null = useMemo(
    () => (denmark ? structure(denmark) : null),
    [denmark],
  );

  // The reference value is a dated series, not a constant: read it at the date the draft
  // itself sets rather than assuming the first entry is the one in force.
  const referenceAmount = useMemo(
    () => resolveSeries(ministry.reference.amount, ministry.reference.baseDate),
    [ministry],
  );

  /** How much of the base wage bill already sits above the 20% ceiling, if measured. */
  const overCapWeight = useMemo(() => {
    const reading = capSeries && readCap(capSeries, 'pereche', 'wide');
    return reading ? reading.overCapWeight : null;
  }, [capSeries]);

  // Denmark's figures are computed from its own imported tables, not typed in by hand,
  // so they move if the import changes and cannot quietly go stale.
  const dkCell = (n: number | null, text: string, note?: string): Cell =>
    d ? { n, text, note } : { n: null, text: '—', note: 'regimul danez nu e încărcat' };

  /** The same, for rows where the count of Danish rows is what produces the number. */
  const dkSample = (n: number | null, text: string, note?: string): Cell =>
    d ? { n, text, note, sampled: true } : { n: null, text: '—', note: 'regimul danez nu e încărcat' };

  const rows: Row[] = [
    {
      label: 'Coeficienți retro-calculați',
      hint: 'valori cu 14 zecimale sau mai multe — reziduul unei împărțiri, nu o decizie',
      better: 'lower',
      cells: {
        inForce: lawCell(f?.backSolvedShare ?? 0, pct(f?.backSolvedShare ?? 0), 'coeficienții sunt tipăriți cu două zecimale'),
        ministry: { n: m.backSolvedShare, text: pct(m.backSolvedShare) },
        ours: { n: o.backSolvedShare, text: pct(o.backSolvedShare) },
        dk: dkCell(d?.backSolvedShare ?? 0, pct(d?.backSolvedShare ?? 0), 'treptele poartă direct suma'),
      },
    },
    {
      label: 'Câte numere trebuie decise',
      hint: 'valori distincte în toată grila',
      better: 'lower',
      cells: {
        inForce: lawCell(f?.distinctValues ?? null, ro(f?.distinctValues ?? 0)),
        ministry: { n: m.distinctValues, text: ro(m.distinctValues) },
        ours: {
          n: o.distinctValues,
          text: ro(o.distinctValues),
          note: `cu ${ro(m.distinctValues - o.distinctValues)} mai puține`,
        },
        dk: dkSample(d?.distinctValues ?? null, ro(d?.distinctValues ?? 0), `din ${ro(d?.positions ?? 0)} posturi transcrise, nu din toată grila daneză`),
      },
    },
    {
      label: 'Posturi numite în grilă',
      hint: 'câte denumiri distincte de post apar în documentul oficial',
      // Fewer is better here: the draft names a job once per employer, so a high count
      // measures how many institutions there are rather than how many occupations.
      better: 'lower',
      cells: {
        inForce: lawCell(f?.positions ?? null, ro(f?.positions ?? 0)),
        ministry: {
          n: m.positions,
          text: ro(m.positions),
          note: `${ro(m.assimilation.mergedPositions)} comasează mai multe denumiri`,
        },
        ours: {
          n: o.positions,
          text: ro(o.positions),
          note: `cu ${ro(m.positions - o.positions)} mai puține — aceeași meserie, un singur nume`,
        },
        dk: dkSample(d?.positions ?? null, ro(d?.positions ?? 0), 'atâtea am transcris din tabelele IDA — nu e numărul de posturi din Danemarca'),
      },
    },
    {
      label: 'Funcții al căror nume ascunde instituția',
      hint: 'aceeași denumire, coeficienți diferiți după categoria instituției — nu după meserie',
      better: 'lower',
      cells: {
        inForce: lawCell(inForce ? fusedCount(inForce) : null, inForce ? ro(fusedCount(inForce)) : '—'),
        ministry: {
          n: fusedCount(ministry),
          text: ro(fusedCount(ministry)),
          note: 'până la ×1,5 sub același nume',
        },
        ours: { n: fusedCount(ours), text: ro(fusedCount(ours)), note: 'diferența devine un multiplicator explicit' },
        dk: dkCell(0, '0', 'instituția se negociază local, nu intră în denumire'),
      },
    },
    {
      label: 'Coeficienți fără grad salarial',
      hint: 'cad în golurile dintre intervalele din Art. 9 alin. (2)',
      better: 'lower',
      cells: {
        inForce: lawCell(null, '—', 'legea în vigoare nu declară grade salariale'),
        ministry: { n: m.variantsInGaps, text: ro(m.variantsInGaps) },
        ours: { n: o.variantsInGaps, text: ro(o.variantsInGaps) },
        dk: dkCell(0, '0', 'fiecare treaptă e o sumă — deși scara sare peste treapta 3'),
      },
    },
    {
      label: 'Distanța dintre cel mai mic și cel mai mare',
      hint: 'Art. 5 o fixează la 1 la 8',
      better: 'none',
      cells: {
        inForce: lawCell(f?.span.ratio ?? null, ratio(f?.span.ratio ?? 0), 'nedeclarat în lege; rezultă din anexe'),
        ministry: {
          n: m.span.ratio,
          text: ratio(m.span.ratio),
          note: period
            ? `în ${period}; ajunge la ${ratio(schedule[schedule.length - 1]?.ratio ?? m.span.ratio)} în ${schedule[schedule.length - 1]?.period ?? ''}`
            : undefined,
        },
        ours: { n: o.span.ratio, text: ratio(o.span.ratio), note: 'fix, nu se mai schimbă' },
        dk: dkSample(d?.span.ratio ?? null, ratio(d?.span.ratio ?? 0), `nedeclarat în lege; între extremele celor ${ro(d?.positions ?? 0)} posturi transcrise`),
      },
    },
    {
      label: 'Ani până se aplică grila declarată',
      hint: 'câte coloane anuale trebuie parcurse',
      better: 'lower',
      cells: {
        inForce: lawCell(0, '0', 'eșalonarea din art. 38 s-a încheiat în 2022'),
        ministry: { n: schedule.length, text: ro(schedule.length) },
        ours: { n: 0, text: '0' },
        dk: dkCell(0, '0', 'treptele se renegociază, nu se eșalonează în lege'),
      },
    },
  ];

  return (
    <>
      <header className="masthead">
        <h1>Patru feluri de a plăti statul</h1>
        <p>
          Ce se plătește azi, ce propune ministerul, ce s-ar schimba cu{' '}
          {ro(proposal.patches.length)} corecturi, și cum arată sistemul danez. Aceleași{' '}
          {ro(rows.length)} întrebări puse tuturor.
        </p>
      </header>

      {/* Before any structural metric, the four facts a reader needs to hold the rest in
          their head: what a salary is made of, how many there are, how far apart, and how
          much can be added on top. Everything below is a detail of one of these. */}
      <section>
        <h2>Proiectul, pe scurt</h2>
        <div className="brief">
          <div className="brief-card">
            <span className="brief-num">{amountLine(referenceAmount, 'RON', rates)}</span>
            <strong>Valoarea de referință</strong>
            <p>
              Orice salariu de bază din sectorul public e această sumă înmulțită cu un coeficient.
              Un coeficient de 2,50 înseamnă {amountLine(referenceAmount * 2.5, 'RON', rates)} brut
              pe lună.
            </p>
          </div>
          <div className="brief-card">
            <span className="brief-num">{ro(m.positions)}</span>
            <strong>Funcții în grilă</strong>
            <p>
              Atâtea denumiri de post, cu {ro(m.distinctValues)} coeficienți distincți între ele.
              Din tabelul ăsta iese salariul fiecărui angajat la stat.
            </p>
          </div>
          <div className="brief-card">
            <span className="brief-num">{ratio(m.span.ratio)}</span>
            <strong>Între cel mai mic și cel mai mare</strong>
            <p>
              Art. 5 promite 1 la 8, dar grila urcă an de an: raportul de mai sus e cel din{' '}
              {period ?? 'grila întreagă'}, iar 1:8 se atinge abia în{' '}
              {schedule[schedule.length - 1]?.period ?? '2031'}. Mișcă anul de sus ca să vezi
              drumul — și observă că nu se schimbă nimic până în{' '}
              {firstMove?.period ?? 'ultimii ani'}: coeficienții eșalonați rămân sub o funcție
              care nu e eșalonată deloc.
            </p>
          </div>
          <div className="brief-card">
            <span className="brief-num">20%</span>
            <strong>Plafonul sporurilor</strong>
            <p>
              Atât pot adăuga sporurile peste salariile de bază — pe instituție și pe sursă de
              finanțare, nu pe om.
              {overCapWeight !== null && (
                <>
                  {' '}
                  Din execuția pe 2025, <strong>{pct(overCapWeight)}</strong> din masa salarială de
                  bază stă deja în instituții care trec de el.
                </>
              )}
            </p>
          </div>
        </div>
      </section>

      <section className="hero">
        <div className="hero-figure">
          {f && (
            <>
              <span className="from">{ro(f.distinctValues)}</span>
              <span className="arrow">→</span>
            </>
          )}
          <span className="to">{ro(m.distinctValues)}</span>
          <span className="arrow">→</span>
          <span className="from">{ro(o.distinctValues)}</span>
        </div>
        <p className="hero-text">
          {f ? (
            <>
              Legea în vigoare decide {ro(f.distinctValues)} numere, toate tipărite cu două
              zecimale. Proiectul cere {ro(m.distinctValues)} — de{' '}
              {(m.distinctValues / f.distinctValues).toLocaleString('ro-RO', {
                maximumFractionDigits: 1,
              })}{' '}
              ori mai multe — și {pct(m.backSolvedShare)} dintre ele au paisprezece zecimale sau
              mai multe. Nu e o grilă proiectată, ci una dedusă din salariile existente prin
              împărțire. Rotunjită la două zecimale, s-ar întoarce la {ro(o.distinctValues)}.
            </>
          ) : (
            <>
              Atâtea numere distincte are grila acum, și atâtea i-ar rămâne dacă ar fi rotunjită la
              două zecimale. Restul de {ro(m.distinctValues - o.distinctValues)} nu sunt decizii de
              politică salarială, ci resturi ale unei împărțiri.
            </>
          )}
        </p>
      </section>

      <section>
        <div className="cmp">
          <div className="cmp-head">
            <div />
            {COLUMNS.map((c) => (
              <div key={c.key} className={`cmp-col col-${c.key}`}>
                <span className="col-title">{c.title}</span>
                <span className="col-sub">{c.sub}</span>
              </div>
            ))}
          </div>

          {rows.map((row) => {
            const values = COLUMNS.map((c) => row.cells[c.key].n).filter(
              (n): n is number => n !== null,
            );
            // A sampled cell is drawn and labelled but kept out of the contest: it
            // cannot win a row whose metric is a function of how many rows there are.
            const contested = COLUMNS.map((c) => row.cells[c.key])
              .filter((cell) => !cell.sampled)
              .map((cell) => cell.n)
              .filter((n): n is number => n !== null);
            const max = Math.max(...values, 1e-9);
            const best =
              row.better === 'none' || contested.length === 0
                ? null
                : row.better === 'lower'
                  ? Math.min(...contested)
                  : Math.max(...contested);

            return (
              <div key={row.label} className="cmp-row">
                <div className="cmp-label">
                  <strong>{row.label}</strong>
                  <span className="hint">{row.hint}</span>
                </div>
                {COLUMNS.map((c) => {
                  const cell = row.cells[c.key];
                  const isBest =
                    best !== null && cell.n !== null && cell.n === best && !cell.sampled;
                  return (
                    <div key={c.key} className={`cmp-cell col-${c.key}`}>
                      <div className="cmp-track">
                        <div
                          className={`cmp-fill fill-${c.key}`}
                          style={{
                            width: cell.n === null ? 0 : `${Math.max((cell.n / max) * 100, 2)}%`,
                          }}
                        />
                      </div>
                      <span className={`cmp-value${isBest ? ' best' : ''}`}>
                        {cell.text}
                        {cell.sampled && <em className="sampled" title="eșantion, nu grilă întreagă">*</em>}
                      </span>
                      {cell.note && <span className="cmp-note">{cell.note}</span>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
        <p className="cmp-foot">
          Barele din fiecare rând sunt proporționale între ele, nu între rânduri. Unde nu există
          cifră, scrie de ce. Celulele cu <em className="sampled">*</em> vin dintr-un eșantion:
          regimul danez de aici are {ro(d?.positions ?? 0)} posturi transcrise din tabelele IDA,
          față de {ro(m.positions)} în grila românească. Pentru o pondere asta nu contează, dar
          pentru un <em>număr</em> de posturi și pentru distanța dintre extremele lui contează
          decisiv — un tabel cu {ro(d?.positions ?? 0)} rânduri va părea mereu mai simplu. De aceea
          acele celule nu câștigă rândul. Comparația daneză serioasă, pe câștiguri măsurate, e pe
          pagina „Meserii, RO vs DK”.
        </p>
      </section>

      <section>
        <h2>Corecturile propuse</h2>
        <p className="lede">{proposal.notPolicy}</p>
        <ol className="patches">
          {proposal.patches.map((patch) => {
            const effect = effects.find((e) => e.patchId === patch.id);
            const touched = effect
              ? [
                  effect.positionsTouched && `${ro(effect.positionsTouched)} funcții`,
                  effect.variantsTouched && `${ro(effect.variantsTouched)} variante`,
                  effect.gradesTouched && `${ro(effect.gradesTouched)} grade`,
                  effect.supplementsTouched && `${ro(effect.supplementsTouched)} sporuri`,
                ]
                  .filter(Boolean)
                  .join(' · ')
              : '';
            return (
              <li key={patch.id} className="card patch">
                <div className="patch-head">
                  <h3>{patch.title}</h3>
                  <span className="patch-tags">
                    {patch.policyChange ? (
                      <span className="badge weak">schimbă distribuția</span>
                    ) : (
                      <span className="badge">reparație</span>
                    )}
                    {touched && <span className="touched">{touched}</span>}
                  </span>
                </div>
                {patch.expectedEffect && <p className="effect">{patch.expectedEffect}</p>}
                <details>
                  <summary>De ce</summary>
                  <p>{patch.rationale}</p>
                </details>
              </li>
            );
          })}
        </ol>
      </section>

      <section>
        <h2>Mai departe</h2>
        <div className="next-grid">
          <button className="next" onClick={() => onOpen('structure')}>
            <strong>Cum e construită grila</strong>
            <span>Zecimalele, golurile dintre grade, funcțiile comasate</span>
          </button>
          <button className="next" onClick={() => onOpen('payslip')}>
            <strong>Un salariu, calculat</strong>
            <span>Un om anume, sub fiecare regim, cu linkul scenariului</span>
          </button>
          <button className="next" onClick={() => onOpen('echivalente')}>
            <strong>Echivalențe de post</strong>
            <span>Ce denumire daneză corespunde fiecărei funcții din grilă</span>
          </button>
        </div>
      </section>
    </>
  );
}

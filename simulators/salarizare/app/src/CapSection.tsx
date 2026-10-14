import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Checkbox, Table } from '@cristiannichifor/civic-ui';

import { readCap, readCapEntities } from '../../engine/cap';
import type { CapMeasure, CapScope, CapSeries } from '../../engine/cap';
import type { Lang } from './i18n';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

const CAP = 0.2;

/** Every word this section prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface CapStrings {
  title: string;
  lede: string;
  scopeLabel: ReactNode;
  measureLabel: ReactNode;
  heroText: (over: string, total: string) => string;
  underCap: (pct: string) => ReactNode;
  overCap: (pct: string) => ReactNode;
  overCapTag: string;
  topTitle: string;
  topHint: string;
  topHintPair: string;
  topHintOrdonator: string;
  bnBase: (bn: string) => string;
  tableToggle: string;
  tableLabel: string;
  columns: { ordonator: string; base: string; ratio: string; over: string };
  yes: string;
  no: string;
  exclusions: string;
}

export const CAP_STRINGS: Record<Lang, CapStrings> = {
  ro: {
    title: 'Pe cine prinde plafonul',
    lede:
      'Plafonul de 20% nu se măsoară pe om, ci pe ordonator principal de credite și pe sursă de finanțare. Până acum pagina putea doar să-l ilustreze. Execuția bugetară pe entitate raportoare îl face măsurabil: se poate spune pe cine ar prinde, dacă lucrurile rămân cum sunt.',
    scopeLabel: (
      <>
        Măsoară pe ordonator <em>și</em> pe sursă de finanțare, cum scrie în lege — altfel sursele se
        însumează și o depășire pe una singură dispare
      </>
    ),
    measureLabel: (
      <>
        Ia tot ce se plătește peste salariul de bază, nu doar paragrafele numite „sporuri“ — altfel o
        instituție pare în regulă doar fiindcă a trecut banii la alt paragraf
      </>
    ),
    heroText: (over, total) =>
      `Atâta parte din masa salarială de bază stă în instituții care depășesc deja 20%. Sunt ${over} din ${total} — puține la număr, dar ele duc banii.`,
    underCap: (pct) => (
      <>
        sub plafon <b>{pct}</b> din masa de bază
      </>
    ),
    overCap: (pct) => (
      <>
        peste plafon <b>{pct}</b>
      </>
    ),
    overCapTag: ' (peste plafon)',
    topTitle: 'Cei mai mari ordonatori',
    topHint: 'Ordonați după masa salarială de bază, fiindcă ei mișcă cifra națională. Linia portocalie e plafonul de 20%. ',
    topHintPair:
      'Lista de aici rămâne pe ordonator, cu sursele însumate — distribuția de mai sus e cea care se uită la fiecare sursă separat, iar acolo depășirile ies mai multe.',
    topHintOrdonator: 'Aceeași unitate ca distribuția de mai sus: ordonatorul, cu sursele însumate.',
    bnBase: (bn) => `${bn} mld lei salarii de bază`,
    tableToggle: 'Vezi cifrele ca tabel',
    tableLabel: 'Plafonul pe ordonatori',
    columns: { ordonator: 'Ordonator', base: 'Masa salarială de bază', ratio: 'Sporuri / bază', over: 'Peste plafon' },
    yes: 'da',
    no: 'nu',
    exclusions:
      'Două lucruri pe care cifra asta nu le spune. Paragrafele 10.01.05 și 10.01.06 sunt ce numește contabilitatea „sporuri“, nu mulțimea pe care Art. 21 o plafonează: legea scoate din plafon munca de noapte, orele suplimentare, handicapul, turele din sănătate, izolarea în Deltă, fondurile europene și premiul de performanță. Și execuția arată regimul actual — plafonul aparține proiectului și n-a funcționat încă niciun an.',
  },
  en: {
    title: 'Whom the cap catches',
    lede:
      'The 20% cap is not measured per person but per principal budget holder and per funding source. Until now the page could only illustrate it. Budget execution by reporting entity makes it measurable: one can say whom it would catch, if things stay as they are.',
    scopeLabel: (
      <>
        Measure per budget holder <em>and</em> per funding source, as the law says — otherwise the
        sources add up and a breach on a single one disappears
      </>
    ),
    measureLabel: (
      <>
        Take everything paid above base salary, not only the paragraphs called "supplements" —
        otherwise an institution looks fine only because it moved the money to another paragraph
      </>
    ),
    heroText: (over, total) =>
      `That much of the base wage bill sits in institutions already above 20%. They are ${over} of ${total} — few in number, but they carry the money.`,
    underCap: (pct) => (
      <>
        under the cap <b>{pct}</b> of the base wage bill
      </>
    ),
    overCap: (pct) => (
      <>
        over the cap <b>{pct}</b>
      </>
    ),
    overCapTag: ' (over the cap)',
    topTitle: 'The largest budget holders',
    topHint: 'Ordered by base wage bill, because they move the national figure. The orange line is the 20% cap. ',
    topHintPair:
      'This list stays per budget holder, with the sources added up — the distribution above is the one that looks at each source separately, and there the breaches come out more numerous.',
    topHintOrdonator: 'The same unit as the distribution above: the budget holder, with the sources added up.',
    bnBase: (bn) => `${bn} bn lei in base salaries`,
    tableToggle: 'See the figures as a table',
    tableLabel: 'The cap by budget holder',
    columns: { ordonator: 'Budget holder', base: 'Base wage bill', ratio: 'Supplements / base', over: 'Over the cap' },
    yes: 'yes',
    no: 'no',
    exclusions:
      'Two things this figure does not say. Paragraphs 10.01.05 and 10.01.06 are what the accounting calls "supplements", not the set that Art. 21 caps: the law takes night work, overtime, disability, health-sector shifts, isolation in the Delta, European funds and the performance bonus out of the cap. And the execution shows the current regime — the cap belongs to the draft and has not yet operated for a single year.',
  },
};

/**
 * Who the 20% ceiling actually binds.
 *
 * Everything else on this page describes pay design. This describes a rule, measured
 * where the rule measures itself: per ordonator principal de credite and per funding
 * source. Two controls stay visible because both choices change the answer, and hiding
 * either would be picking the argument for the reader.
 */
export default function CapSection({ series, lang = 'ro' }: { series: CapSeries[]; lang?: Lang }) {
  const t = CAP_STRINGS[lang];
  const locale = LOCALE[lang];
  const pctOf = (n: number, digits = 1) =>
    `${(n * 100).toLocaleString(locale, { maximumFractionDigits: digits })}%`;
  const n = (value: number) => value.toLocaleString(locale);
  const bn = (value: number) => (value / 1e9).toLocaleString(locale, { maximumFractionDigits: 2 });

  const [scope, setScope] = useState<CapScope>('pereche');
  const [measure, setMeasure] = useState<CapMeasure>('narrow');

  const reading = useMemo(() => readCap(series, scope, measure), [series, scope, measure]);
  const entities = useMemo(() => readCapEntities(series), [series]);

  if (!reading) return null;

  const top = entities.slice(0, 16);
  // One axis across the institutions, with headroom so the widest bar is not flush.
  const axis = Math.max(...top.map((e) => e[measure]), CAP * 1.5) * 1.06;

  return (
    <section>
      <h2>{t.title}</h2>
      <p className="lede">{t.lede}</p>

      <div className="card controls occ-controls civic-scope civic-pay">
        <Checkbox
          checked={scope === 'pereche'}
          onChange={() => setScope((s) => (s === 'pereche' ? 'ordonator' : 'pereche'))}
          label={t.scopeLabel}
        />
        <Checkbox
          checked={measure === 'wide'}
          onChange={() => setMeasure((m) => (m === 'wide' ? 'narrow' : 'wide'))}
          label={t.measureLabel}
        />
      </div>

      <div className="comp-hero">
        {/* A decimal, deliberately: rounded to "20%" the figure reads as the ceiling
            itself rather than as the share of the wage bill that has passed it. */}
        <span className="big">{pctOf(reading.overCapWeight)}</span>
        <p>{t.heroText(n(reading.overCapCount), n(reading.total))}</p>
      </div>

      <div className="card">
        <div className="cap-split">
          <div className="under" style={{ width: `${(1 - reading.overCapWeight) * 100}%` }} />
          <div className="breach" style={{ width: `${reading.overCapWeight * 100}%` }} />
        </div>
        <div className="comp-tail">
          <span>{t.underCap(pctOf(1 - reading.overCapWeight, 0))}</span>
          <span>{t.overCap(pctOf(reading.overCapWeight, 0))}</span>
        </div>

        <div className="cap-dist" style={{ marginTop: 18 }}>
          {reading.bands
            .filter((b) => b.share > 0)
            .map((b, i) => (
              <div
                key={b.label}
                className={b.overCap ? 'over' : undefined}
                style={{ width: `${b.share * 100}%`, background: `var(--band-${i})` }}
                title={`${b.label}: ${n(b.count)}`}
              />
            ))}
        </div>
        <div className="cap-key">
          {reading.bands.map((b, i) => (
            <span key={b.label}>
              <i style={{ background: `var(--band-${i})` }} />
              {b.label} — {n(b.count)}
              {b.overCap && t.overCapTag}
            </span>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>{t.topTitle}</h3>
        <p className="hint">
          {t.topHint}
          {scope === 'pereche' ? t.topHintPair : t.topHintOrdonator}
        </p>
        <div className="cap-list">
          {top.map((e) => {
            const value = e[measure];
            const over = value > CAP;
            return (
              <div className="cap-item" key={e.cui}>
                <div className="who">
                  {e.name.length > 44 ? `${e.name.slice(0, 43)}…` : e.name}
                  <small>{t.bnBase(bn(e.base))}</small>
                </div>
                <div className="cap-plot">
                  <div
                    className={`cap-bar${over ? ' over' : ''}`}
                    style={{ width: `${Math.min((value / axis) * 100, 100)}%` }}
                  />
                  <div className="cap-rule" style={{ left: `${(CAP / axis) * 100}%` }} />
                </div>
                <div className={`cap-num${over ? ' over' : ''}`}>
                  <b>{pctOf(value)}</b>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <details className="table-view">
        <summary>{t.tableToggle}</summary>
        <Table className="data" label={t.tableLabel}>
          <thead>
            <tr>
              <th>{t.columns.ordonator}</th>
              <th className="num">{t.columns.base}</th>
              <th className="num">{t.columns.ratio}</th>
              <th className="num">{t.columns.over}</th>
            </tr>
          </thead>
          <tbody>
            {top.map((e) => (
              <tr key={e.cui}>
                <td>{e.name}</td>
                <td className="num">{bn(e.base)} {lang === 'ro' ? 'mld lei' : 'bn lei'}</td>
                <td className="num">{pctOf(e[measure])}</td>
                <td className="num">{e[measure] > CAP ? t.yes : t.no}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </details>

      <div className="comp-excl">
        <p>{t.exclusions}</p>
      </div>
    </section>
  );
}

import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Field, NativeSelect, RangeSlider } from '@cristiannichifor/civic-ui';

import { payslip } from '../../engine/payslip';
import type { Lang } from './i18n';
import { amountLine } from './money';
import type { Crosswalk, CrosswalkLink, Regime } from '../../engine/types';

export interface Benchmarks {
  avgRo: number;
  avgDk: number;
  govRo: number;
  govDk: number;
  floorRo: number;
  floorDk: number;
  year: string;
}
export interface Fx {
  dkkToRon: number;
  eurToRon: number;
  date: string;
}

const MONTHS = 12;
const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

type Anchor = 'avg' | 'gov' | 'floor';

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface EquivalenceStrings {
  title: string;
  purpose: string;
  anchorLabel: string;
  anchorOptions: Record<Anchor, string>;
  anchorNames: Record<Anchor, string>;
  seniority: string;
  benchmarks: string;
  romania: string;
  denmark: string;
  noLegalMinimum: string;
  howToRead: string;
  bars: (date: string, rate: string) => ReactNode;
  equivalences: (year: string) => ReactNode;
  badgeRename: string;
  badgeWeak: string;
  badgeNone: string;
  noPublishedPost: string;
  noDanishMatch: string;
  renamedTag: string;
  whySummary: string;
}

export const EQUIVALENCE_STRINGS: Record<Lang, EquivalenceStrings> = {
  ro: {
    title: 'Cât valorează postul, față de salariul din țara lui',
    purpose:
      'Cursul de schimb spune cât de mare e un număr. Nu spune ce crede o societate despre un post. Raportul spune: o funcție plătită cu de trei ori salariul mediu e tratată ca importantă oriunde s-ar afla, iar una plătită cu 1,2 salarii medii nu e — indiferent de monedă și de prețuri.',
    anchorLabel: 'Raportat la',
    anchorOptions: {
      avg: 'salariul mediu din toată economia',
      gov: 'salariul mediu din sectorul public',
      floor: 'pragul de jos',
    },
    anchorNames: {
      avg: 'salariul mediu brut din toată economia',
      gov: 'salariul mediu brut din sectorul public',
      floor: 'pragul de jos',
    },
    seniority: 'Vechime presupusă (ani)',
    benchmarks: 'Reperele folosite',
    romania: 'România',
    denmark: 'Danemarca',
    noLegalMinimum: ' · nu e salariu minim legal, Danemarca nu are',
    howToRead: 'Cum se citește',
    bars: (date, rate) => (
      <>
        <strong>Barele</strong> sunt multipli ai reperului din <em>propria</em> țară a fiecărui sistem,
        deci se pot compara direct. Sumele de sub ele sunt în moneda proprie, iar cea daneză e
        convertită și în lei la cursul BCE din {date} (1 DKK = {rate} RON) doar ca ordin de mărime —
        prețurile daneze sunt mult mai mari, deci suma convertită nu înseamnă același trai.
      </>
    ),
    equivalences: (year) => (
      <>
        <strong>Echivalările</strong> sunt judecăți editoriale, nu drepturi. Cele nesigure sunt
        marcate. Media e din {year} iar grilele din 2026, deci rapoartele sunt ușor supraestimate în
        ambele coloane — dar în aceeași direcție, deci comparația ține.
      </>
    ),
    badgeRename: 'se poate numi altfel',
    badgeWeak: 'echivalare slabă',
    badgeNone: 'fără corespondent danez',
    noPublishedPost: 'niciun post publicat',
    noDanishMatch:
      'Tabelele IDA acoperă ingineri și academici; munca de îngrijire e plătită prin alt contract colectiv, care nu apare în această sursă.',
    renamedTag: 'denumire aliniată pieței muncii',
    whySummary: 'De ce sunt puse față în față',
  },
  en: {
    title: "What the post is worth, against its own country's wage",
    purpose:
      'The exchange rate says how big a number is. It does not say what a society thinks of a post. The ratio does: a position paid three times the average wage is treated as important wherever it is, and one paid 1.2 average wages is not — whatever the currency and the prices.',
    anchorLabel: 'Relative to',
    anchorOptions: {
      avg: 'the average wage across the economy',
      gov: 'the average wage in the public sector',
      floor: 'the floor',
    },
    anchorNames: {
      avg: 'the gross average wage across the economy',
      gov: 'the gross average wage in the public sector',
      floor: 'the floor',
    },
    seniority: 'Assumed seniority (years)',
    benchmarks: 'The benchmarks used',
    romania: 'Romania',
    denmark: 'Denmark',
    noLegalMinimum: ' · not a legal minimum wage, Denmark has none',
    howToRead: 'How to read it',
    bars: (date, rate) => (
      <>
        <strong>The bars</strong> are multiples of the benchmark in each system's <em>own</em> country,
        so they compare directly. The amounts under them are in the own currency, and the Danish one
        is also converted into lei at the ECB rate of {date} (1 DKK = {rate} RON) only as an order of
        magnitude — Danish prices are much higher, so the converted amount does not mean the same
        living.
      </>
    ),
    equivalences: (year) => (
      <>
        <strong>The equivalences</strong> are editorial judgements, not entitlements. The uncertain
        ones are marked. The average is from {year} and the grids from 2026, so the ratios are
        slightly overstated in both columns — but in the same direction, so the comparison holds.
      </>
    ),
    badgeRename: 'could be named differently',
    badgeWeak: 'weak equivalence',
    badgeNone: 'no Danish counterpart',
    noPublishedPost: 'no published post',
    noDanishMatch:
      'The IDA tables cover engineers and academics; care work is paid under another collective agreement, which does not appear in this source.',
    renamedTag: 'title aligned with the labour market',
    whySummary: 'Why they are set side by side',
  },
};

/** Monthly major units in the regime's own currency. */
function monthly(minor: number, regime: Regime): number {
  const value = minor / 100;
  return regime.reference.period === 'year' ? value / MONTHS : value;
}

interface Pair {
  link: CrosswalkLink;
  roName: string;
  dkName: string | null;
  roMonthly: number | null;
  dkMonthly: number | null;
  roRatio: number | null;
  dkRatio: number | null;
  gap: number;
}

export default function EquivalenceView({
  menu,
  ro,
  dk,
  crosswalk,
  fx,
  benchmarks,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  ro: Regime;
  dk: Regime;
  crosswalk: Crosswalk;
  fx: Fx;
  benchmarks: Benchmarks;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = EQUIVALENCE_STRINGS[lang];
  const locale = LOCALE[lang];
  const [seniority, setSeniority] = useState(10);
  const [anchor, setAnchor] = useState<Anchor>('avg');

  const base =
    anchor === 'avg'
      ? { ro: benchmarks.avgRo, dk: benchmarks.avgDk }
      : anchor === 'gov'
        ? { ro: benchmarks.govRo, dk: benchmarks.govDk }
        : { ro: benchmarks.floorRo, dk: benchmarks.floorDk };

  const anchorLabel = t.anchorNames[anchor];

  const pairs: Pair[] = useMemo(() => {
    const rows = crosswalk.links.map((link) => {
      const roPos = ro.positions.find((p) => p.code === link.from[0]?.positionCode) ?? null;
      const dkPos = dk.positions.find((p) => p.code === link.to[0]?.positionCode) ?? null;

      const roSlip = roPos ? payslip({ positionCode: roPos.code, seniorityYears: seniority }, ro) : null;
      const dkSlip = dkPos ? payslip({ positionCode: dkPos.code, seniorityYears: seniority }, dk) : null;

      const roMonthly = roSlip ? monthly(roSlip.base, ro) : null;
      const dkMonthly = dkSlip ? monthly(dkSlip.base, dk) : null;

      const roRatio = roMonthly !== null ? roMonthly / base.ro : null;
      const dkRatio = dkMonthly !== null ? dkMonthly / base.dk : null;

      return {
        link,
        roName: link.from.map((f) => f.title ?? f.positionCode).join(' · '),
        dkName: dkPos?.name ?? null,
        roMonthly,
        dkMonthly,
        roRatio,
        dkRatio,
        gap: roRatio !== null && dkRatio !== null ? Math.abs(roRatio - dkRatio) : -1,
      };
    });
    // Most divergent first: the rows where the two societies disagree most about what a
    // job is worth are the ones worth reading, and burying them alphabetically would
    // hide the entire point of the page.
    return rows.sort((a, b) => b.gap - a.gap);
  }, [crosswalk, ro, dk, seniority, base.ro, base.dk]);

  const scaleMax = Math.max(
    ...pairs.flatMap((p) => [p.roRatio ?? 0, p.dkRatio ?? 0]),
    1.2,
  );

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.purpose}</p>
      </header>
      {menu}

      <section>
        <div className="card controls anchor-controls civic-scope civic-pay">
          <Field id="equivalence-anchor" label={t.anchorLabel}>
            {(props) => <NativeSelect {...props} value={anchor} onChange={(e) => setAnchor(e.target.value as Anchor)}>
              <option value="avg">{t.anchorOptions.avg}</option>
              <option value="gov">{t.anchorOptions.gov}</option>
              <option value="floor">{t.anchorOptions.floor}</option>
            </NativeSelect>}
          </Field>
          <RangeSlider
            className="field"
            label={t.seniority}
            min={0}
            max={35}
            value={seniority}
            onValueChange={setSeniority}
          />
          <div className="field anchors">
            <span>{t.benchmarks}</span>
            <p>
              <span className="dot ro" /> {t.romania}: {amountLine(base.ro, 'RON', fx, 'native', locale)} — {anchorLabel}
            </p>
            <p>
              <span className="dot dk" /> {t.denmark}: {amountLine(base.dk, 'DKK', fx, 'native', locale)} — {anchorLabel}
              {anchor === 'floor' && <em>{t.noLegalMinimum}</em>}
            </p>
          </div>
        </div>
      </section>

      <section>
        <div className="ratio-list">
          {pairs.map((pair) => (
            <RatioRow key={pair.link.id} pair={pair} scaleMax={scaleMax} fx={fx} lang={lang} />
          ))}
        </div>
      </section>

      <section>
        <h2>{t.howToRead}</h2>
        <div className="card readme-grid">
          <p>{t.bars(fx.date, fx.dkkToRon.toLocaleString(locale, { maximumFractionDigits: 4 }))}</p>
          <p>{t.equivalences(benchmarks.year)}</p>
        </div>
      </section>
    </>
  );
}

function RatioRow({ pair, scaleMax, fx, lang }: { pair: Pair; scaleMax: number; fx: Fx; lang: Lang }) {
  const t = EQUIVALENCE_STRINGS[lang];
  const locale = LOCALE[lang];
  const times = (n: number) =>
    `${n.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}×`;
  const { link } = pair;
  const width = (r: number | null) => (r === null ? 0 : Math.max((r / scaleMax) * 100, 1.5));
  const weak = link.confidence === 'assumed' || link.disputed;

  return (
    <article className="card ratio-row">
      <header className="ratio-head">
        <h3>{pair.roName}</h3>
        <div className="badges">
          {link.proposedName && <span className="badge rename">{t.badgeRename}</span>}
          {weak && <span className="badge weak">{t.badgeWeak}</span>}
          {!pair.dkName && <span className="badge none">{t.badgeNone}</span>}
        </div>
      </header>

      <div className="bars">
        <div className="bar-line">
          <span className="bar-label">{t.romania}</span>
          <div className="track">
            <div className="fill ro" style={{ width: `${width(pair.roRatio)}%` }} />
            <span className="marker" style={{ left: `${(1 / scaleMax) * 100}%` }} />
          </div>
          <span className="bar-value">{pair.roRatio !== null ? times(pair.roRatio) : '—'}</span>
          <span className="bar-money">
            {pair.roMonthly !== null ? amountLine(pair.roMonthly, 'RON', fx, 'native', locale) : ''}
          </span>
        </div>

        <div className="bar-line">
          <span className="bar-label">{t.denmark}</span>
          <div className="track">
            <div className="fill dk" style={{ width: `${width(pair.dkRatio)}%` }} />
            <span className="marker" style={{ left: `${(1 / scaleMax) * 100}%` }} />
          </div>
          <span className="bar-value">{pair.dkRatio !== null ? times(pair.dkRatio) : '—'}</span>
          <span className="bar-money">
            {pair.dkMonthly !== null ? amountLine(pair.dkMonthly, 'DKK', fx, 'native', locale) : t.noPublishedPost}
          </span>
        </div>
      </div>

      <p className="dk-name">{pair.dkName ?? t.noDanishMatch}</p>

      {link.proposedName && (
        <p className="renamed">
          <span className="renamed-tag">{t.renamedTag}</span>
          {link.proposedName}
        </p>
      )}

      <details className="why">
        <summary>{t.whySummary}</summary>
        <ul className="evidence">
          {(link.evidence ?? []).map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
        {link.note && <p className="equiv-note">{link.note}</p>}
      </details>
    </article>
  );
}

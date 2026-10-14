import { useMemo } from 'react';
import type { ReactNode } from 'react';

import { resolveDomainShowcase } from '../../engine/domainShowcase';
import type { DomainBand, DomainSide } from '../../engine/domainShowcase';
import type { DkOccupation, GroupsDocument } from '../../engine/occupations';
import type { Scenario } from '../../engine/scenario';
import type { Regime } from '../../engine/types';
import type { Lang } from './i18n';
import { amountLine, amountRange } from './money';
import type { Rates } from './money';

const SIDE_KEYS = ['inForce', 'draft', 'proposal', 'denmark'] as const;
type SideKey = (typeof SIDE_KEYS)[number];

const SIDE_CLASS: Record<SideKey, string> = {
  inForce: 'current',
  draft: 'draft',
  proposal: 'proposal',
  denmark: 'dk',
};

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface DomainsStrings {
  title: string;
  lead: string;
  context: readonly [string, string][];
  disclaimerRank: string;
  disclaimerRankNote: string;
  disclaimerAverage: (year: string) => string;
  show: string;
  all: string;
  legendMedian: string;
  postsInDraft: (count: string) => string;
  weakMatch: string;
  draftVsToday: (move: string) => string;
  proposalVsToday: (move: string) => string;
  whatCompares: string;
  foundNote: (inForce: string, draft: string, proposal: string, dk: string) => string;
  sides: Record<SideKey, string>;
  basisLegal: string;
  basisMeasured: string;
  vsPublicMid: string;
  avgEconomyDk: string;
  floorDk: string;
  avgEconomyRo: string;
  floorRo: string;
  median: string;
  rows: (count: number) => string;
}

export const DOMAINS_STRINGS: Record<Lang, DomainsStrings> = {
  ro: {
    title: 'Poziții-cheie din sectorul public',
    lead:
      'Domenii din sănătate, educație, justiție, apărare, ordine publică, administrație, cercetare și cultură, puse pe aceeași scară: cât valorează față de mijlocul propriului sector public.',
    context: [
      ['Patru repere', 'legea de azi, proiectul ministerului, propunerea alternativă și Danemarca.'],
      ['Aceeași unitate', 'fiecare sumă este raportată la mijlocul sectorului public din propria țară.'],
      ['Reper social', 'fiecare grupă este pusă și lângă media economiei și pragul salarial de jos.'],
    ],
    disclaimerRank: 'Comparația este de rang economic, nu conversie brută RON-DKK.',
    disclaimerRankNote:
      'Pentru România afișăm baza legală din grile; pentru Danemarca afișăm câștiguri măsurate de Danmarks Statistik.',
    disclaimerAverage: (year) =>
      `Media economiei este din ${year}, nu mediană, fiindcă nu avem o mediană anuală comparabilă pentru ambele țări. Proiectul românesc încărcat aici este pachetul public MMFTSS din 20.08.2026; workbookul public nu conține Anexa III cap. V, deci domeniile legate de cultură poartă un avertisment de acoperire.`,
    show: 'Arată',
    all: 'toate',
    legendMedian: 'mediana sectorului public',
    postsInDraft: (count) => `${count} posturi în proiect`,
    weakMatch: 'echivalare slabă',
    draftVsToday: (move) => `proiect vs azi ${move}`,
    proposalVsToday: (move) => `propunere vs azi ${move}`,
    whatCompares: 'Ce intră în comparație',
    foundNote: (inForce, draft, proposal, dk) =>
      `În România regula a găsit ${inForce} posturi în legea în vigoare, ${draft} în proiect și ${proposal} în propunere. În Danemarca comparația folosește ${dk}.`,
    sides: { inForce: 'RO azi', draft: 'RO proiect', proposal: 'Propunere', denmark: 'Danemarca' },
    basisLegal: 'bază legală',
    basisMeasured: 'câștiguri măsurate',
    vsPublicMid: 'față de mijlocul public',
    avgEconomyDk: 'media economiei DK',
    floorDk: 'prag colectiv jos DK',
    avgEconomyRo: 'media economiei RO',
    floorRo: 'salariul minim RO',
    median: 'mediană',
    rows: (count) => `${count} ${count === 1 ? 'rând' : 'rânduri'}`,
  },
  en: {
    title: 'Key positions in the public sector',
    lead:
      'Fields from health, education, justice, defence, public order, administration, research and culture, placed on one scale: what they are worth against the middle of their own public sector.',
    context: [
      ['Four reference points', "today's law, the ministry's draft, the alternative proposal and Denmark."],
      ['One unit', 'every amount is set against the middle of the public sector in its own country.'],
      ['Social reference', 'every group is also set beside the economy average and the lowest pay floor.'],
    ],
    disclaimerRank: 'The comparison is one of economic rank, not a raw RON-DKK conversion.',
    disclaimerRankNote:
      'For Romania we show the legal base from the pay grids; for Denmark we show earnings measured by Danmarks Statistik.',
    disclaimerAverage: (year) =>
      `The economy average is from ${year}, not a median, because no comparable annual median exists for both countries. The Romanian draft loaded here is the public MMFTSS package of 20.08.2026; the public workbook lacks Annex III chapter V, so the culture-related fields carry a coverage warning.`,
    show: 'Show',
    all: 'all',
    legendMedian: 'public-sector median',
    postsInDraft: (count) => `${count} posts in the draft`,
    weakMatch: 'weak match',
    draftVsToday: (move) => `draft vs today ${move}`,
    proposalVsToday: (move) => `proposal vs today ${move}`,
    whatCompares: 'What enters the comparison',
    foundNote: (inForce, draft, proposal, dk) =>
      `In Romania the rule found ${inForce} posts in the law in force, ${draft} in the draft and ${proposal} in the proposal. In Denmark the comparison uses ${dk}.`,
    sides: { inForce: 'RO today', draft: 'RO draft', proposal: 'Proposal', denmark: 'Denmark' },
    basisLegal: 'legal base',
    basisMeasured: 'measured earnings',
    vsPublicMid: 'against the public middle',
    avgEconomyDk: 'DK economy average',
    floorDk: 'DK low collective floor',
    avgEconomyRo: 'RO economy average',
    floorRo: 'RO minimum wage',
    median: 'median',
    rows: (count) => `${count} ${count === 1 ? 'row' : 'rows'}`,
  },
};

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

const move = (from: DomainBand | null, to: DomainBand | null, locale: string) => {
  if (!from || !to) return null;
  const ratio = to.ratio.median / from.ratio.median - 1;
  return `${ratio >= 0 ? '+' : ''}${(ratio * 100).toLocaleString(locale, {
    maximumFractionDigits: 1,
  })}%`;
};

export interface SocietyBenchmarks {
  avgRo: number;
  avgDk: number;
  floorRo: number;
  floorDk: number;
  year: string;
}

export default function DomainsView({
  menu,
  inForce,
  draft,
  proposal,
  groups,
  danish,
  rates,
  benchmarks,
  scenario,
  onScenario,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  inForce: Regime | null;
  draft: Regime;
  proposal: Regime;
  groups: GroupsDocument;
  danish: DkOccupation[];
  rates: Rates;
  benchmarks: SocietyBenchmarks;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = DOMAINS_STRINGS[lang];
  const locale = LOCALE[lang];
  const n = (value: number) => value.toLocaleString(locale);
  const rows = useMemo(
    () => resolveDomainShowcase({ inForce, draft, proposal }, groups, danish),
    [inForce, draft, proposal, groups, danish],
  );

  const sectors = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of rows) map.set(row.group.sector, (map.get(row.group.sector) ?? 0) + 1);
    return [...map.entries()];
  }, [rows]);

  const sector = scenario.sector ?? null;
  const shown = sector ? rows.filter((row) => row.group.sector === sector) : rows;
  const axisMax = Math.max(
    2,
    ...rows.flatMap((row) =>
      SIDE_KEYS.map((key) => row.sides[key].band?.ratio.q3 ?? 0),
    ),
  ) * 1.08;

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.lead}</p>
      </header>
      {menu}

      <div className="domain-context">
        {t.context.map(([head, body]) => (
          <div key={head}>
            <strong>{head}</strong>
            <span>{body}</span>
          </div>
        ))}
      </div>

      <div className="disclaimer domain-disclaimer">
        <p>
          <strong>{t.disclaimerRank}</strong> {t.disclaimerRankNote}
        </p>
        <p>{t.disclaimerAverage(benchmarks.year)}</p>
      </div>

      <section className="filter-section">
        <div className="sector-filter">
          <span className="sector-label">{t.show}</span>
          <button
            className={sector === null ? 'on' : ''}
            onClick={() => onScenario({ ...scenario, sector: undefined })}
          >
            {t.all} ({rows.length})
          </button>
          {sectors.map(([name, count]) => (
            <button
              key={name}
              className={sector === name ? 'on' : ''}
              onClick={() => onScenario({ ...scenario, sector: name })}
            >
              {name} ({count})
            </button>
          ))}
        </div>
      </section>

      <section className="domain-results">
        <div className="domain-key">
          {SIDE_KEYS.map((key) => (
            <span key={key}>
              <i className={`domain-dot ${SIDE_CLASS[key]}`} />
              {t.sides[key]}
            </span>
          ))}
          <span>
            <i className="domain-midmark" />
            {t.legendMedian}
          </span>
        </div>
        <div className="domain-list">
          {shown.map((row) => {
            const toDraft = move(row.sides.inForce.band, row.sides.draft.band, locale);
            const toProposal = move(row.sides.inForce.band, row.sides.proposal.band, locale);
            return (
              <article className="card domain-row" key={row.group.id}>
                <header className="domain-head">
                  <div>
                    <span className="domain-sector">{row.group.sector}</span>
                    <h2>{row.group.label}</h2>
                    <p>{row.group.proposedName}</p>
                  </div>
                  <div className="badges">
                    <span className="badge">{t.postsInDraft(n(row.sides.draft.count))}</span>
                    {row.group.disputed && <span className="badge weak">{t.weakMatch}</span>}
                    {toDraft && <span className="badge">{t.draftVsToday(toDraft)}</span>}
                    {toProposal && <span className="badge">{t.proposalVsToday(toProposal)}</span>}
                  </div>
                </header>

                <div className="domain-sides">
                  {SIDE_KEYS.map((key) => (
                    <DomainSideCard
                      key={key}
                      sideKey={key}
                      side={row.sides[key]}
                      axisMax={axisMax}
                      rates={rates}
                      references={referencesFor(key, benchmarks, t)}
                      t={t}
                      locale={locale}
                    />
                  ))}
                </div>

                <details className="why">
                  <summary>{t.whatCompares}</summary>
                  <p className="equiv-note">{row.group.basis}</p>
                  <p className="equiv-note">
                    {t.foundNote(
                      n(row.sides.inForce.count),
                      n(row.sides.draft.count),
                      n(row.sides.proposal.count),
                      row.group.dkOccupations.join('; '),
                    )}
                  </p>
                </details>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}

function referencesFor(sideKey: SideKey, benchmarks: SocietyBenchmarks, t: DomainsStrings) {
  if (sideKey === 'denmark') {
    return {
      average: benchmarks.avgDk,
      floor: benchmarks.floorDk,
      averageLabel: t.avgEconomyDk,
      floorLabel: t.floorDk,
    };
  }
  return {
    average: benchmarks.avgRo,
    floor: benchmarks.floorRo,
    averageLabel: t.avgEconomyRo,
    floorLabel: t.floorRo,
  };
}

function DomainSideCard({
  sideKey,
  side,
  axisMax,
  rates,
  references,
  t,
  locale,
}: {
  sideKey: SideKey;
  side: DomainSide;
  axisMax: number;
  rates: Rates;
  references: {
    average: number;
    floor: number;
    averageLabel: string;
    floorLabel: string;
  };
  t: DomainsStrings;
  locale: string;
}) {
  const times = (value: number) =>
    `${value.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}x`;
  const rangeTimes = (from: number, to: number) => `${times(from)}-${times(to)}`;
  const pos = (value: number) => `${Math.min((value / axisMax) * 100, 100)}%`;
  const band = side.band;
  const width =
    band === null
      ? '0%'
      : `${Math.max(((band.ratio.q3 - band.ratio.q1) / axisMax) * 100, 0.8)}%`;

  return (
    <div className={`domain-side ${SIDE_CLASS[sideKey]}`}>
      <div className="domain-side-title">
        <strong>{t.sides[sideKey]}</strong>
        <span>{side.basis === 'legal-base' ? t.basisLegal : t.basisMeasured}</span>
      </div>
      <div className="domain-track">
        <span className="domain-mid" style={{ left: pos(1) }} />
        {band && (
          <>
            <div className="domain-fill" style={{ left: pos(band.ratio.q1), width }} />
            <span className="domain-tick" style={{ left: pos(band.ratio.median) }} />
          </>
        )}
      </div>
      {band ? (
        <>
          <div className="domain-ratio">
            {times(band.ratio.q1)}-{times(band.ratio.q3)}
            <span>{t.vsPublicMid}</span>
          </div>
          <div className="domain-bench">
            <span>
              <b>{rangeTimes(band.q1 / references.average, band.q3 / references.average)}</b>
              <em>{references.averageLabel}</em>
            </span>
            <span>
              <b>{rangeTimes(band.q1 / references.floor, band.q3 / references.floor)}</b>
              <em>{references.floorLabel}</em>
            </span>
          </div>
          <div className="domain-money">
            {amountRange(band.q1, band.q3, side.currency, rates)}
          </div>
          <div className="domain-median">
            {t.median} {amountLine(band.median, side.currency, rates)}
          </div>
        </>
      ) : (
        <p className="domain-missing">{side.missingReason}</p>
      )}
      <span className="domain-count">{t.rows(side.count)}</span>
    </div>
  );
}

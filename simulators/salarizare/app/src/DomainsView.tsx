import { useMemo } from 'react';

import { resolveDomainShowcase } from '../../engine/domainShowcase';
import type { DomainBand, DomainSide } from '../../engine/domainShowcase';
import type { DkOccupation, GroupsDocument } from '../../engine/occupations';
import type { Scenario } from '../../engine/scenario';
import type { Regime } from '../../engine/types';
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

const SIDE_SHORT: Record<SideKey, string> = {
  inForce: 'RO azi',
  draft: 'RO proiect',
  proposal: 'Propunere',
  denmark: 'Danemarca',
};

const ro = (n: number) => n.toLocaleString('ro-RO');
const times = (n: number) =>
  `${n.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}x`;
const rangeTimes = (from: number, to: number) => `${times(from)}-${times(to)}`;
const move = (from: DomainBand | null, to: DomainBand | null) => {
  if (!from || !to) return null;
  const ratio = to.ratio.median / from.ratio.median - 1;
  return `${ratio >= 0 ? '+' : ''}${(ratio * 100).toLocaleString('ro-RO', {
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
  inForce,
  draft,
  proposal,
  groups,
  danish,
  rates,
  benchmarks,
  scenario,
  onScenario,
}: {
  inForce: Regime | null;
  draft: Regime;
  proposal: Regime;
  groups: GroupsDocument;
  danish: DkOccupation[];
  rates: Rates;
  benchmarks: SocietyBenchmarks;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
}) {
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
        <h1>Poziții-cheie din sectorul public</h1>
        <p>
          Domenii din sănătate, educație, justiție, apărare, ordine publică, administrație,
          cercetare și cultură, puse pe aceeași scară: cât valorează față de mijlocul propriului
          sector public.
        </p>
      </header>

      <div className="domain-context">
        <div>
          <strong>Patru repere</strong>
          <span>legea de azi, proiectul ministerului, propunerea alternativă și Danemarca.</span>
        </div>
        <div>
          <strong>Aceeași unitate</strong>
          <span>fiecare sumă este raportată la mijlocul sectorului public din propria țară.</span>
        </div>
        <div>
          <strong>Reper social</strong>
          <span>fiecare grupă este pusă și lângă media economiei și pragul salarial de jos.</span>
        </div>
      </div>

      <div className="disclaimer domain-disclaimer">
        <p>
          <strong>Comparația este de rang economic, nu conversie brută RON-DKK.</strong> Pentru
          România afișăm baza legală din grile; pentru Danemarca afișăm câștiguri măsurate de
          Danmarks Statistik.
        </p>
        <p>
          Media economiei este din {benchmarks.year}, nu mediană, fiindcă nu avem o mediană anuală
          comparabilă pentru ambele țări. Proiectul românesc încărcat aici este pachetul public
          MMFTSS din 20.08.2026; workbookul public nu conține Anexa III cap. V, deci domeniile
          legate de cultură poartă un avertisment de acoperire.
        </p>
      </div>

      <section className="filter-section">
        <div className="sector-filter">
          <span className="sector-label">Arată</span>
          <button
            className={sector === null ? 'on' : ''}
            onClick={() => onScenario({ ...scenario, sector: undefined })}
          >
            toate ({rows.length})
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
              {SIDE_SHORT[key]}
            </span>
          ))}
          <span>
            <i className="domain-midmark" />
            mediana sectorului public
          </span>
        </div>
        <div className="domain-list">
          {shown.map((row) => {
            const toDraft = move(row.sides.inForce.band, row.sides.draft.band);
            const toProposal = move(row.sides.inForce.band, row.sides.proposal.band);
            return (
              <article className="card domain-row" key={row.group.id}>
                <header className="domain-head">
                  <div>
                    <span className="domain-sector">{row.group.sector}</span>
                    <h2>{row.group.label}</h2>
                    <p>{row.group.proposedName}</p>
                  </div>
                  <div className="badges">
                    <span className="badge">{ro(row.sides.draft.count)} posturi în proiect</span>
                    {row.group.disputed && <span className="badge weak">echivalare slabă</span>}
                    {toDraft && <span className="badge">proiect vs azi {toDraft}</span>}
                    {toProposal && <span className="badge">propunere vs azi {toProposal}</span>}
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
                      references={referencesFor(key, benchmarks)}
                    />
                  ))}
                </div>

                <details className="why">
                  <summary>Ce intră în comparație</summary>
                  <p className="equiv-note">{row.group.basis}</p>
                  <p className="equiv-note">
                    În România regula a găsit {ro(row.sides.inForce.count)} posturi în legea în
                    vigoare, {ro(row.sides.draft.count)} în proiect și{' '}
                    {ro(row.sides.proposal.count)} în propunere. În Danemarca comparația folosește{' '}
                    {row.group.dkOccupations.join('; ')}.
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

function referencesFor(sideKey: SideKey, benchmarks: SocietyBenchmarks) {
  if (sideKey === 'denmark') {
    return {
      average: benchmarks.avgDk,
      floor: benchmarks.floorDk,
      averageLabel: 'media economiei DK',
      floorLabel: 'prag colectiv jos DK',
    };
  }
  return {
    average: benchmarks.avgRo,
    floor: benchmarks.floorRo,
    averageLabel: 'media economiei RO',
    floorLabel: 'salariul minim RO',
  };
}

function DomainSideCard({
  sideKey,
  side,
  axisMax,
  rates,
  references,
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
}) {
  const pos = (value: number) => `${Math.min((value / axisMax) * 100, 100)}%`;
  const band = side.band;
  const width =
    band === null
      ? '0%'
      : `${Math.max(((band.ratio.q3 - band.ratio.q1) / axisMax) * 100, 0.8)}%`;

  return (
    <div className={`domain-side ${SIDE_CLASS[sideKey]}`}>
      <div className="domain-side-title">
        <strong>{SIDE_SHORT[sideKey]}</strong>
        <span>{side.basis === 'legal-base' ? 'bază legală' : 'câștiguri măsurate'}</span>
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
            <span>față de mijlocul public</span>
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
            mediană {amountLine(band.median, side.currency, rates)}
          </div>
        </>
      ) : (
        <p className="domain-missing">{side.missingReason}</p>
      )}
      <span className="domain-count">
        {side.count} {side.count === 1 ? 'rând' : 'rânduri'}
      </span>
    </div>
  );
}

import { useMemo, useState } from 'react';

import { payslip } from '../../engine/payslip';
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

const times = (n: number) => `${n.toLocaleString('ro-RO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}×`;

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
  ro,
  dk,
  crosswalk,
  fx,
  benchmarks,
}: {
  ro: Regime;
  dk: Regime;
  crosswalk: Crosswalk;
  fx: Fx;
  benchmarks: Benchmarks;
}) {
  const [seniority, setSeniority] = useState(10);
  const [anchor, setAnchor] = useState<'avg' | 'gov' | 'floor'>('avg');

  const base =
    anchor === 'avg'
      ? { ro: benchmarks.avgRo, dk: benchmarks.avgDk }
      : anchor === 'gov'
        ? { ro: benchmarks.govRo, dk: benchmarks.govDk }
        : { ro: benchmarks.floorRo, dk: benchmarks.floorDk };

  const anchorLabel =
    anchor === 'avg'
      ? 'salariul mediu brut din toată economia'
      : anchor === 'gov'
        ? 'salariul mediu brut din sectorul public'
        : 'pragul de jos';

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
        <h1>Cât valorează postul, față de salariul din țara lui</h1>
        <p>
          Cursul de schimb spune cât de mare e un număr. Nu spune ce crede o societate despre un
          post. Raportul spune: o funcție plătită cu de trei ori salariul mediu e tratată ca
          importantă oriunde s-ar afla, iar una plătită cu 1,2 salarii medii nu e — indiferent de
          monedă și de prețuri.
        </p>
      </header>

      <section>
        <div className="card controls anchor-controls">
          <label className="field">
            <span>Raportat la</span>
            <select value={anchor} onChange={(e) => setAnchor(e.target.value as 'avg' | 'gov' | 'floor')}>
              <option value="avg">salariul mediu din toată economia</option>
              <option value="gov">salariul mediu din sectorul public</option>
              <option value="floor">pragul de jos</option>
            </select>
          </label>
          <label className="field">
            <span>Vechime presupusă: {seniority} ani</span>
            <input
              type="range"
              min={0}
              max={35}
              value={seniority}
              onChange={(e) => setSeniority(Number(e.target.value))}
            />
          </label>
          <div className="field anchors">
            <span>Reperele folosite</span>
            <p>
              <span className="dot ro" /> România: {amountLine(base.ro, 'RON', fx)} — {anchorLabel}
            </p>
            <p>
              <span className="dot dk" /> Danemarca: {amountLine(base.dk, 'DKK', fx)} — {anchorLabel}
              {anchor === 'floor' && <em> · nu e salariu minim legal, Danemarca nu are</em>}
            </p>
          </div>
        </div>
      </section>

      <section>
        <div className="ratio-list">
          {pairs.map((pair) => (
            <RatioRow key={pair.link.id} pair={pair} scaleMax={scaleMax} fx={fx} />
          ))}
        </div>
      </section>

      <section>
        <h2>Cum se citește</h2>
        <div className="card readme-grid">
          <p>
            <strong>Barele</strong> sunt multipli ai reperului din <em>propria</em> țară a fiecărui
            sistem, deci se pot compara direct. Sumele de sub ele sunt în moneda proprie, iar cea
            daneză e convertită și în lei la cursul BCE din {fx.date} (1 DKK ={' '}
            {fx.dkkToRon.toLocaleString('ro-RO', { maximumFractionDigits: 4 })} RON) doar ca ordin de
            mărime — prețurile daneze sunt mult mai mari, deci suma convertită nu înseamnă același trai.
          </p>
          <p>
            <strong>Echivalările</strong> sunt judecăți editoriale, nu drepturi. Cele nesigure sunt
            marcate. Media e din {benchmarks.year} iar grilele din 2026, deci rapoartele sunt ușor
            supraestimate în ambele coloane — dar în aceeași direcție, deci comparația ține.
          </p>
        </div>
      </section>
    </>
  );
}

function RatioRow({ pair, scaleMax, fx }: { pair: Pair; scaleMax: number; fx: Fx }) {
  const { link } = pair;
  const width = (r: number | null) => (r === null ? 0 : Math.max((r / scaleMax) * 100, 1.5));
  const weak = link.confidence === 'assumed' || link.disputed;

  return (
    <article className="card ratio-row">
      <header className="ratio-head">
        <h3>{pair.roName}</h3>
        <div className="badges">
          {link.proposedName && <span className="badge rename">se poate numi altfel</span>}
          {weak && <span className="badge weak">echivalare slabă</span>}
          {!pair.dkName && <span className="badge none">fără corespondent danez</span>}
        </div>
      </header>

      <div className="bars">
        <div className="bar-line">
          <span className="bar-label">România</span>
          <div className="track">
            <div className="fill ro" style={{ width: `${width(pair.roRatio)}%` }} />
            <span className="marker" style={{ left: `${(1 / scaleMax) * 100}%` }} />
          </div>
          <span className="bar-value">{pair.roRatio !== null ? times(pair.roRatio) : '—'}</span>
          <span className="bar-money">
            {pair.roMonthly !== null ? amountLine(pair.roMonthly, 'RON', fx) : ''}
          </span>
        </div>

        <div className="bar-line">
          <span className="bar-label">{pair.dkName ? 'Danemarca' : 'Danemarca'}</span>
          <div className="track">
            <div className="fill dk" style={{ width: `${width(pair.dkRatio)}%` }} />
            <span className="marker" style={{ left: `${(1 / scaleMax) * 100}%` }} />
          </div>
          <span className="bar-value">{pair.dkRatio !== null ? times(pair.dkRatio) : '—'}</span>
          <span className="bar-money">
            {pair.dkMonthly !== null ? amountLine(pair.dkMonthly, 'DKK', fx) : 'niciun post publicat'}
          </span>
        </div>
      </div>

      <p className="dk-name">
        {pair.dkName ?? 'Tabelele IDA acoperă ingineri și academici; munca de îngrijire e plătită prin alt contract colectiv, care nu apare în această sursă.'}
      </p>

      {link.proposedName && (
        <p className="renamed">
          <span className="renamed-tag">denumire aliniată pieței muncii</span>
          {link.proposedName}
        </p>
      )}

      <details className="why">
        <summary>De ce sunt puse față în față</summary>
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

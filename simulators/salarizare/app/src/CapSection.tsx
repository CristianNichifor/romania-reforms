import { useMemo, useState } from 'react';

import { readCap, readCapEntities } from '../../engine/cap';
import type { CapMeasure, CapScope, CapSeries } from '../../engine/cap';

const pctOf = (n: number, digits = 1) =>
  `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: digits })}%`;

const CAP = 0.2;

/**
 * Who the 20% ceiling actually binds.
 *
 * Everything else on this page describes pay design. This describes a rule, measured
 * where the rule measures itself: per ordonator principal de credite and per funding
 * source. Two controls stay visible because both choices change the answer, and hiding
 * either would be picking the argument for the reader.
 */
export default function CapSection({ series }: { series: CapSeries[] }) {
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
      <h2>Pe cine prinde plafonul</h2>
      <p className="lede">
        Plafonul de 20% nu se măsoară pe om, ci pe ordonator principal de credite și pe sursă de
        finanțare. Până acum pagina putea doar să-l ilustreze. Execuția bugetară pe entitate
        raportoare îl face măsurabil: se poate spune pe cine ar prinde, dacă lucrurile rămân cum
        sunt.
      </p>

      <div className="card controls occ-controls">
        <label className="claim">
          <input
            type="checkbox"
            checked={scope === 'pereche'}
            onChange={() => setScope((s) => (s === 'pereche' ? 'ordonator' : 'pereche'))}
          />
          <span>
            Măsoară pe ordonator <em>și</em> pe sursă de finanțare, cum scrie în lege — altfel
            sursele se însumează și o depășire pe una singură dispare
          </span>
        </label>
        <label className="claim">
          <input
            type="checkbox"
            checked={measure === 'wide'}
            onChange={() => setMeasure((m) => (m === 'wide' ? 'narrow' : 'wide'))}
          />
          <span>
            Ia tot ce se plătește peste salariul de bază, nu doar paragrafele numite „sporuri“ —
            altfel o instituție pare în regulă doar fiindcă a trecut banii la alt paragraf
          </span>
        </label>
      </div>

      <div className="comp-hero">
        {/* A decimal, deliberately: rounded to "20%" the figure reads as the ceiling
            itself rather than as the share of the wage bill that has passed it. */}
        <span className="big">{pctOf(reading.overCapWeight)}</span>
        <p>
          Atâta parte din masa salarială de bază stă în instituții care depășesc deja 20%. Sunt{' '}
          {reading.overCapCount.toLocaleString('ro-RO')} din{' '}
          {reading.total.toLocaleString('ro-RO')} — puține la număr, dar ele duc banii.
        </p>
      </div>

      <div className="card">
        <div className="cap-split">
          <div className="under" style={{ width: `${(1 - reading.overCapWeight) * 100}%` }} />
          <div className="breach" style={{ width: `${reading.overCapWeight * 100}%` }} />
        </div>
        <div className="comp-tail">
          <span>
            sub plafon <b>{pctOf(1 - reading.overCapWeight, 0)}</b> din masa de bază
          </span>
          <span>
            peste plafon <b>{pctOf(reading.overCapWeight, 0)}</b>
          </span>
        </div>

        <div className="cap-dist" style={{ marginTop: 18 }}>
          {reading.bands
            .filter((b) => b.share > 0)
            .map((b, i) => (
              <div
                key={b.label}
                className={b.overCap ? 'over' : undefined}
                style={{ width: `${b.share * 100}%`, background: `var(--band-${i})` }}
                title={`${b.label}: ${b.count.toLocaleString('ro-RO')}`}
              />
            ))}
        </div>
        <div className="cap-key">
          {reading.bands.map((b, i) => (
            <span key={b.label}>
              <i style={{ background: `var(--band-${i})` }} />
              {b.label} — {b.count.toLocaleString('ro-RO')}
              {b.overCap && ' (peste plafon)'}
            </span>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Cei mai mari ordonatori</h3>
        <p className="hint">
          Ordonați după masa salarială de bază, fiindcă ei mișcă cifra națională. Linia portocalie
          e plafonul de 20%.{' '}
          {scope === 'pereche'
            ? 'Lista de aici rămâne pe ordonator, cu sursele însumate — distribuția de mai sus e cea care se uită la fiecare sursă separat, iar acolo depășirile ies mai multe.'
            : 'Aceeași unitate ca distribuția de mai sus: ordonatorul, cu sursele însumate.'}
        </p>
        <div className="cap-list">
          {top.map((e) => {
            const value = e[measure];
            const over = value > CAP;
            return (
              <div className="cap-item" key={e.cui}>
                <div className="who">
                  {e.name.length > 44 ? `${e.name.slice(0, 43)}…` : e.name}
                  <small>{(e.base / 1e9).toLocaleString('ro-RO', { maximumFractionDigits: 2 })} mld lei salarii de bază</small>
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
        <summary>Vezi cifrele ca tabel</summary>
        <table className="data">
          <thead>
            <tr>
              <th>Ordonator</th>
              <th className="num">Masa salarială de bază</th>
              <th className="num">Sporuri / bază</th>
              <th className="num">Peste plafon</th>
            </tr>
          </thead>
          <tbody>
            {top.map((e) => (
              <tr key={e.cui}>
                <td>{e.name}</td>
                <td className="num">
                  {(e.base / 1e9).toLocaleString('ro-RO', { maximumFractionDigits: 2 })} mld lei
                </td>
                <td className="num">{pctOf(e[measure])}</td>
                <td className="num">{e[measure] > CAP ? 'da' : 'nu'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <div className="comp-excl">
        <p>
          Două lucruri pe care cifra asta nu le spune. Paragrafele 10.01.05 și 10.01.06 sunt ce
          numește contabilitatea „sporuri“, nu mulțimea pe care Art. 21 o plafonează: legea scoate
          din plafon munca de noapte, orele suplimentare, handicapul, turele din sănătate, izolarea
          în Deltă, fondurile europene și premiul de performanță. Și execuția arată regimul actual —
          plafonul aparține proiectului și n-a funcționat încă niciun an.
        </p>
      </div>
    </section>
  );
}

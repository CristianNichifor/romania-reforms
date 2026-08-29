import { useMemo } from 'react';

import type { CapSeries } from '../../engine/cap';
import type { Scenario } from '../../engine/scenario';
import { envelope } from '../../engine/envelope';
import type { EnvelopeBaseline, Move } from '../../engine/envelope';
import CapSection from './CapSection';
import { amountLine } from './money';
import type { Rates } from './money';

const FAMILY_LABELS: Record<string, string> = {
  'I-invatamant': 'Învățământ',
  'II-sanatate-asistenta-sociala': 'Sănătate și asistență socială',
  'VI-aparare-ordine-securitate': 'Apărare, ordine publică, securitate',
  'VIII-administratie': 'Administrație',
};

/**
 * Billions of lei, one decimal. The wage bill is a twelve-digit number in minor units;
 * written out it is unreadable, and an earlier version of this labelled millions "mld.",
 * which was off by a factor of a thousand.
 */
function bn(minor: number): string {
  return `${(minor / 100 / 1e9).toLocaleString('ro-RO', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} mld.`;
}
/** One decimal, Romanian comma — the rest of the app reads that way. */
function dec(n: number): string {
  return n.toLocaleString('ro-RO', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
function pctText(n: number): string {
  const s = (n * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 });
  return `${n > 0 ? '+' : ''}${s}%`;
}

export default function EnvelopeView({
  baseline,
  rates,
  capSeries,
  scenario,
  onScenario,
}: {
  baseline: EnvelopeBaseline | null;
  rates: Rates;
  /** The ceiling, measured per ordonator and per funding source. */
  capSeries: CapSeries[] | null;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
}) {
  // Envelope state lives in the hash like every other view's. It was the one page whose
  // argument could not be sent to anyone: you could build a case for moving money
  // between families, and then had no way to link to it.
  const targetPct = scenario.envelopeTarget ?? 0;
  const moves: Record<string, { pct: number; why: string }> = useMemo(() => {
    const out: Record<string, { pct: number; why: string }> = {};
    for (const m of scenario.envelopeMoves ?? []) out[m.family] = { pct: m.pct, why: m.why };
    return out;
  }, [scenario.envelopeMoves]);

  const setTargetPct = (pct: number) => onScenario({ ...scenario, envelopeTarget: pct || undefined });
  const setMoves = (
    update: (prev: Record<string, { pct: number; why: string }>) => Record<string, { pct: number; why: string }>,
  ) => {
    const next = update(moves);
    const list = Object.entries(next)
      .filter(([, m]) => m.pct !== 0 || m.why)
      .map(([family, m]) => ({ family, pct: m.pct, why: m.why }));
    onScenario({ ...scenario, envelopeMoves: list.length ? list : undefined });
  };

  const moveList: Move[] = useMemo(
    () =>
      Object.entries(moves)
        .filter(([, m]) => m.pct !== 0)
        .map(([family, m]) => ({
          id: family,
          label: FAMILY_LABELS[family] ?? family,
          target: { kind: 'family' as const, family },
          pct: m.pct,
          rationale: m.why,
        })),
    [moves],
  );

  const result = useMemo(
    () =>
      baseline
        ? envelope(baseline, moveList, Math.round(baseline.total * (1 + targetPct)))
        : null,
    [baseline, moveList, targetPct],
  );

  if (!baseline || !result) {
    return (
      <p className="loading">
        Se încarcă baza de pornire — cheltuiala de personal pe funcții și posturile ocupate.
      </p>
    );
  }

  const set = (family: string, patch: Partial<{ pct: number; why: string }>) =>
    setMoves((prev) => ({
      ...prev,
      [family]: { ...{ pct: 0, why: '' }, ...prev[family], ...patch },
    }));

  const fits = result.balanced;

  return (
    <>
      <header className="masthead">
        <h1>Plicul: cât se cheltuie în total</h1>
        <p>
          Fixezi cât are voie să coste tot personalul bugetar, apoi orice creștere trebuie plătită
          dintr-o reducere numită. Nu din „eficientizare”, nu din creștere economică — dintr-o
          reducere pe care o scrii aici și care apare în dreptul creșterii.
        </p>
      </header>

      <section className="hero envelope-hero">
        <div className="hero-figure">
          <span className={fits ? 'to' : 'from'}>{bn(result.proposed)}</span>
        </div>
        <div>
          <p className="hero-text">
            {bn(result.proposed)} lei pe an ≈{' '}
            {(result.proposed / 100 / rates.eurToRon / 1e9).toLocaleString('ro-RO', {
              maximumFractionDigits: 1,
            })}{' '}
            mld. EUR —{' '}
            {(result.shareOfGdp.after * 100).toLocaleString('ro-RO', { maximumFractionDigits: 2 })}% din
            PIB, față de {(result.shareOfGdp.before * 100).toLocaleString('ro-RO', { maximumFractionDigits: 2 })}% acum.
          </p>
          <p className={`verdict ${fits ? 'ok' : 'bad'}`}>
            {fits
              ? 'Planul încape în plic.'
              : `Lipsesc ${bn(Math.abs(Math.min(result.headroom, 0)) || result.increases.reduce((s, i) => s + i.unfunded, 0))} lei — sunt creșteri fără acoperire.`}
          </p>
        </div>
      </section>

      <section>
        <h2>Ținta</h2>
        <div className="card controls">
          <label className="field">
            <span>
              Cheltuiala totală de personal: {pctText(targetPct)} față de {bn(baseline.total)} lei
              {targetPct === 0 && ' — plic închis, tot ce crește undeva scade altundeva'}
            </span>
            <input
              type="range"
              min={-15}
              max={15}
              step={0.5}
              value={targetPct * 100}
              onChange={(e) => setTargetPct(Number(e.target.value) / 100)}
            />
          </label>
          <p className="src">
            Art. 36 alin. (3) cere o reducere de cel puțin 1,5 puncte din PIB între 2024 și 2031.
            De la {dec(result.shareOfGdp.before * 100)}% asta ar însemna{' '}
            {dec(result.shareOfGdp.before * 100 - 1.5)}% — adică{' '}
            {pctText(((result.shareOfGdp.before - 0.015) / result.shareOfGdp.before) - 1)} din
            cheltuiala de azi, dacă PIB-ul ar sta pe loc.
          </p>
        </div>
      </section>

      <section>
        <h2>Mutările</h2>
        <p className="lede">
          Trage de fiecare familie. Ce crește trebuie plătit — motivul e obligatoriu, pentru că o
          reducere fără autor și fără justificare nu e o propunere.
        </p>
        <div className="moves">
          {result.byFamily.map((f) => {
            const state = moves[f.family] ?? { pct: 0, why: '' };
            return (
              <div key={f.family} className="card move-row">
                <div className="move-head">
                  <strong>{FAMILY_LABELS[f.family] ?? f.label}</strong>
                  <span className="move-base">
                    {bn(f.before)} lei
                    {f.delta !== 0 && (
                      <em className={f.delta > 0 ? 'up' : 'down'}>
                        {' '}
                        → {bn(f.after)} ({pctText(state.pct)})
                      </em>
                    )}
                  </span>
                </div>
                <input
                  type="range"
                  min={-25}
                  max={25}
                  step={0.5}
                  value={state.pct * 100}
                  onChange={(e) => set(f.family, { pct: Number(e.target.value) / 100 })}
                />
                {state.pct !== 0 && (
                  <input
                    type="text"
                    className={`why${state.why.trim() ? '' : ' missing'}`}
                    placeholder={
                      state.pct > 0 ? 'De ce merită această creștere?' : 'De unde vine reducerea?'
                    }
                    value={state.why}
                    onChange={(e) => set(f.family, { why: e.target.value })}
                  />
                )}
              </div>
            );
          })}
        </div>
      </section>

      {result.increases.length > 0 && (
        <section>
          <h2>Cine plătește ce</h2>
          <div className="ledger">
            {result.increases.map((entry) => (
              <div key={entry.move.id} className="card ledger-row">
                <div className="ledger-head">
                  <strong>{entry.move.label}</strong>
                  <span className="up">+{bn(entry.delta)} lei</span>
                </div>
                {entry.move.rationale.trim() && <p className="why-text">{entry.move.rationale}</p>}
                <ul className="funding">
                  {entry.fundedBy.map((f) => (
                    <li key={f.fromMoveId}>
                      <span className="down">−{bn(f.amount)}</span> din {f.fromLabel}
                    </li>
                  ))}
                  {entry.unfunded > 0 && (
                    <li className="unfunded">
                      <span>{bn(entry.unfunded)} lei fără acoperire</span> — trebuie numită o
                      reducere
                    </li>
                  )}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {capSeries && <CapSection series={capSeries} />}

      <section>
        <h2>Ce presupune calculul</h2>
        <div className="limits">
          {result.diagnostics.map((d, i) => (
            <div key={i} className={`limit ${d.severity}`}>
              <div className="sev">{d.severity === 'blocking' ? 'blocant' : 'de reținut'}</div>
              <p>{d.message}</p>
            </div>
          ))}
          <div className="limit note">
            <div className="sev">bază de pornire</div>
            <p>
              Execuția bugetară pe 2025, titlul I „cheltuieli de personal” în întregime — plata în
              bani și în natură plus contribuțiile angajatorului — raportată de ordonatorii
              principali de credite și împărțită pe capitole bugetare. E aceeași contabilitate în
              care e scrisă legea, nu o clasificare statistică suprapusă peste ea, și e și baza pe
              care Art. 36 își măsoară ținta. PIB-ul nominal rămâne de la Eurostat, fiindcă execuția
              nu-l conține.{' '}
              {baseline.posts.toLocaleString('ro-RO')} posturi ocupate din raportarea Ministerului
              Finanțelor, iunie 2026. Media pe post iese{' '}
              {amountLine(result.perPost.before / 100 / 12, baseline.currency, rates)} pe lună.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}

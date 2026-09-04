import { useMemo } from 'react';

import { applyProposal } from '../../engine/proposal';
import type { PatchEffect, Proposal } from '../../engine/proposal';
import { structure } from '../../engine/structure';
import type { Scenario } from '../../engine/scenario';
import type { Regime } from '../../engine/types';

function ro(n: number): string {
  return n.toLocaleString('ro-RO');
}
function pct(n: number): string {
  return `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`;
}
function ratio(n: number): string {
  return `1:${n.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * The proposal, one patch at a time.
 *
 * It used to exist only as a column on the comparison page and a folded list underneath
 * it: nine edits arrived as a single finished object, and a reader who doubted one of
 * them had no way to ask what the other eight would do without it. That is the wrong
 * shape for a document whose whole claim is that it can be audited edit by edit.
 *
 * So every patch has a switch. Turning one off re-applies the proposal without it and
 * recomputes the headline numbers, which is the only honest way to show what a single
 * edit is worth — the patches interact, and the difference a patch makes depends on which
 * others are already on. The switches live in the URL, so a disagreement is shareable:
 * "your proposal minus the two I don't accept" is a link.
 */
export default function ProposalView({
  ministry,
  proposal,
  scenario,
  onScenario,
  onOpen,
}: {
  ministry: Regime;
  proposal: Proposal;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
  onOpen: (view: 'compare' | 'distributie' | 'payslip') => void;
}) {
  const off = useMemo(() => new Set(scenario.offPatches ?? []), [scenario.offPatches]);

  const active = useMemo(
    () => ({ ...proposal, patches: proposal.patches.filter((p) => !off.has(p.id)) }),
    [proposal, off],
  );
  const applied = useMemo(() => applyProposal(ministry, active), [ministry, active]);
  const full = useMemo(() => applyProposal(ministry, proposal), [ministry, proposal]);

  const base = useMemo(() => structure(ministry), [ministry]);
  const now = useMemo(() => structure(applied.regime), [applied]);

  const effectOf = (id: string): PatchEffect | undefined =>
    applied.effects.find((e) => e.patchId === id) ??
    full.effects.find((e) => e.patchId === id);

  const toggle = (id: string) => {
    const next = new Set(off);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onScenario({ ...scenario, offPatches: [...next] });
  };

  const setAll = (on: boolean) =>
    onScenario({ ...scenario, offPatches: on ? [] : proposal.patches.map((p) => p.id) });

  const repairs = proposal.patches.filter((p) => !p.policyChange);
  const changes = proposal.patches.filter((p) => p.policyChange);
  const activeChanges = changes.filter((p) => !off.has(p.id)).length;

  const KPIS: Array<{ v: string; k: string; from?: string }> = [
    {
      v: ro(now.positions),
      k: 'funcții denumite',
      from: `de la ${ro(base.positions)}`,
    },
    {
      v: ro(now.distinctValues),
      k: 'coeficienți distincți de decis',
      from: `de la ${ro(base.distinctValues)}`,
    },
    {
      v: pct(now.backSolvedShare),
      k: 'retro-calculați, cu 14+ zecimale',
      from: `de la ${pct(base.backSolvedShare)}`,
    },
    {
      v: ro(now.variantsInGaps),
      k: 'variante fără grad salarial',
      from: `de la ${ro(base.variantsInGaps)}`,
    },
    {
      // span, not spanByPeriod: one of the patches removes the annual schedule outright,
      // so the proposal has no periods to take a last one from and the row read "1:0,00".
      v: ratio(now.span.ratio),
      k: 'raportul între capete',
      from: `de la ${ratio(base.span.ratio)}`,
    },
  ];

  return (
    <>
      <header className="masthead">
        <h1>Propunerea, corectură cu corectură</h1>
        <p>
          {proposal.summary} Fiecare corectură are un întrerupător: stinge-o și restul se
          recalculează fără ea. Linkul păstrează ce ai stins, deci un dezacord se poate trimite
          mai departe ca atare — „propunerea voastră, fără cele două pe care nu le accept”.
        </p>
        <p className="src">
          {ro(repairs.length)} reparații · {ro(changes.length)} schimbări de distribuție ·
          pornite acum: {ro(proposal.patches.length - off.size)} din {ro(proposal.patches.length)}
        </p>
      </header>

      <div className="disclaimer">
        <strong>Nu e un buget și nu e un proiect de lege.</strong> Este proiectul ministerului
        cu un număr de modificări numite, aplicate peste el. Cifrele de mai jos descriu forma
        grilei rezultate, nu suma pe care ar încasa-o cineva.
      </div>

      <section>
        <h2>Ce iese, cu ce e pornit acum</h2>
        <div className="kpis">
          {KPIS.map((kpi) => (
            <div className="kpi" key={kpi.k}>
              <div className="v accent">{kpi.v}</div>
              <div className="k">
                {kpi.k}
                {kpi.from && <em className="kpi-from"> {kpi.from}</em>}
              </div>
            </div>
          ))}
        </div>
        {activeChanges > 0 && (
          <p className="lede">
            <strong>Dintre corecturile pornite, {ro(activeChanges)} mută bani între oameni.</strong>{' '}
            Restul lasă distribuția exact cum a propus-o ministerul și schimbă doar dacă regulile
            scrise în lege pot fi aplicate. Stinge-le pe cele marcate „schimbă distribuția” ca să
            vezi propunerea strict ca reparație.
          </p>
        )}
        <div className="patch-actions">
          <button className="ghost" onClick={() => setAll(true)}>
            pornește tot
          </button>
          <button className="ghost" onClick={() => setAll(false)}>
            stinge tot
          </button>
          <button
            className="ghost"
            onClick={() =>
              onScenario({ ...scenario, offPatches: changes.map((p) => p.id) })
            }
          >
            doar reparațiile
          </button>
        </div>
      </section>

      <section>
        <h2>Corecturile</h2>
        <p className="lede">{proposal.notPolicy}</p>
        <ol className="patches">
          {proposal.patches.map((patch) => {
            const on = !off.has(patch.id);
            const effect = effectOf(patch.id);
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
              <li key={patch.id} className={`card patch ${on ? '' : 'patch-off'}`}>
                <div className="patch-head">
                  <h3>{patch.title}</h3>
                  <span className="patch-tags">
                    {patch.policyChange ? (
                      <span className="badge weak">schimbă distribuția</span>
                    ) : (
                      <span className="badge">reparație</span>
                    )}
                    {touched && <span className="touched">{touched}</span>}
                    <label className="patch-switch">
                      <input type="checkbox" checked={on} onChange={() => toggle(patch.id)} />
                      <span>{on ? 'pornită' : 'stinsă'}</span>
                    </label>
                  </span>
                </div>
                {patch.expectedEffect && <p className="effect">{patch.expectedEffect}</p>}
                <details>
                  <summary>De ce</summary>
                  <p>{patch.rationale}</p>
                  {patch.fixes && (
                    <p className="src">
                      Repară limita declarată <code>{patch.fixes}</code> din regimul de bază.
                    </p>
                  )}
                </details>
              </li>
            );
          })}
        </ol>
      </section>

      <section>
        <h2>Mai departe</h2>
        <div className="next-grid">
          <button className="next" onClick={() => onOpen('compare')}>
            <strong>Cele patru sisteme, față în față</strong>
            <span>Aceleași șapte întrebări puse fiecărui sistem</span>
          </button>
          <button className="next" onClick={() => onOpen('distributie')}>
            <strong>Cine urcă, cine coboară</strong>
            <span>Fiecare post comparat cu el însuși sub legea de azi</span>
          </button>
          <button className="next" onClick={() => onOpen('payslip')}>
            <strong>Un salariu, calculat</strong>
            <span>O funcție anume, sub fiecare regim</span>
          </button>
        </div>
      </section>
    </>
  );
}

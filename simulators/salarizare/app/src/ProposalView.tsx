import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Button, Checkbox } from '@cristiannichifor/civic-ui';

import { applyProposal } from '../../engine/proposal';
import type { PatchEffect, Proposal } from '../../engine/proposal';
import { structure } from '../../engine/structure';
import type { Scenario } from '../../engine/scenario';
import type { Regime } from '../../engine/types';
import type { Lang } from './i18n';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface ProposalStrings {
  title: string;
  /** Follows the proposal's own (data) summary sentence. */
  purpose: string;
  counts: (repairs: string, changes: string, on: string, total: string) => string;
  disclaimer: ReactNode;
  resultTitle: string;
  kpis: {
    positions: string;
    distinct: string;
    backSolved: string;
    gaps: string;
    span: string;
  };
  from: (value: string) => string;
  moveMoney: (n: string) => ReactNode;
  allOn: string;
  allOff: string;
  repairsOnly: string;
  patchesTitle: string;
  touched: { positions: string; variants: string; grades: string; supplements: string };
  badgeChange: string;
  badgeRepair: string;
  on: string;
  off: string;
  why: string;
  fixes: (limit: ReactNode) => ReactNode;
  nextTitle: string;
  next: Record<'compare' | 'distributie' | 'payslip', { title: string; body: string }>;
}

export const PROPOSAL_STRINGS: Record<Lang, ProposalStrings> = {
  ro: {
    title: 'Propunerea, corectură cu corectură',
    purpose:
      'Fiecare corectură are un întrerupător: stinge-o și restul se recalculează fără ea. Linkul păstrează ce ai stins, deci un dezacord se poate trimite mai departe ca atare — „propunerea voastră, fără cele două pe care nu le accept”.',
    counts: (repairs, changes, on, total) =>
      `${repairs} reparații · ${changes} schimbări de distribuție · pornite acum: ${on} din ${total}`,
    disclaimer: (
      <>
        <strong>Nu e un buget și nu e un proiect de lege.</strong> Este proiectul ministerului cu un
        număr de modificări numite, aplicate peste el. Cifrele de mai jos descriu forma grilei
        rezultate, nu suma pe care ar încasa-o cineva.
      </>
    ),
    resultTitle: 'Ce iese, cu ce e pornit acum',
    kpis: {
      positions: 'funcții denumite',
      distinct: 'coeficienți distincți de decis',
      backSolved: 'retro-calculați, cu 14+ zecimale',
      gaps: 'variante fără grad salarial',
      span: 'raportul între capete',
    },
    from: (value) => `de la ${value}`,
    moveMoney: (n) => (
      <>
        <strong>Dintre corecturile pornite, {n} mută bani între oameni.</strong> Restul lasă
        distribuția exact cum a propus-o ministerul și schimbă doar dacă regulile scrise în lege pot
        fi aplicate. Stinge-le pe cele marcate „schimbă distribuția” ca să vezi propunerea strict ca
        reparație.
      </>
    ),
    allOn: 'pornește tot',
    allOff: 'stinge tot',
    repairsOnly: 'doar reparațiile',
    patchesTitle: 'Corecturile',
    touched: { positions: 'funcții', variants: 'variante', grades: 'grade', supplements: 'sporuri' },
    badgeChange: 'schimbă distribuția',
    badgeRepair: 'reparație',
    on: 'pornită',
    off: 'stinsă',
    why: 'De ce',
    fixes: (limit) => <>Repară limita declarată {limit} din regimul de bază.</>,
    nextTitle: 'Mai departe',
    next: {
      compare: { title: 'Cele patru sisteme, față în față', body: 'Aceleași șapte întrebări puse fiecărui sistem' },
      distributie: { title: 'Cine urcă, cine coboară', body: 'Fiecare post comparat cu el însuși sub legea de azi' },
      payslip: { title: 'Un salariu, calculat', body: 'O funcție anume, sub fiecare regim' },
    },
  },
  en: {
    title: 'The proposal, one correction at a time',
    purpose:
      'Every correction has a switch: turn it off and the rest is recomputed without it. The link keeps what you turned off, so a disagreement can be passed on as such — "your proposal, without the two I do not accept".',
    counts: (repairs, changes, on, total) =>
      `${repairs} repairs · ${changes} distribution changes · on now: ${on} of ${total}`,
    disclaimer: (
      <>
        <strong>Not a budget and not a bill.</strong> It is the ministry's draft with a number of named
        changes applied on top of it. The figures below describe the shape of the resulting grid, not
        the sum anyone would receive.
      </>
    ),
    resultTitle: 'What comes out, with what is on now',
    kpis: {
      positions: 'named positions',
      distinct: 'distinct coefficients to decide',
      backSolved: 'back-solved, with 14+ decimals',
      gaps: 'variants without a pay grade',
      span: 'ratio between the ends',
    },
    from: (value) => `from ${value}`,
    moveMoney: (n) => (
      <>
        <strong>Of the corrections that are on, {n} move money between people.</strong> The rest
        leave the distribution exactly as the ministry proposed it and only change whether the rules
        written in the law can be applied. Turn off the ones marked "changes the distribution" to see
        the proposal strictly as a repair.
      </>
    ),
    allOn: 'turn all on',
    allOff: 'turn all off',
    repairsOnly: 'repairs only',
    patchesTitle: 'The corrections',
    touched: { positions: 'positions', variants: 'variants', grades: 'grades', supplements: 'supplements' },
    badgeChange: 'changes the distribution',
    badgeRepair: 'repair',
    on: 'on',
    off: 'off',
    why: 'Why',
    fixes: (limit) => <>Repairs the declared limit {limit} of the base regime.</>,
    nextTitle: 'Further',
    next: {
      compare: { title: 'The four systems, side by side', body: 'The same seven questions put to each system' },
      distributie: { title: 'Who rises, who falls', body: "Every post compared with itself under today's law" },
      payslip: { title: 'One salary, computed', body: 'One specific position, under each regime' },
    },
  },
};

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
  menu,
  ministry,
  proposal,
  scenario,
  onScenario,
  onOpen,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  ministry: Regime;
  proposal: Proposal;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
  onOpen: (view: 'compare' | 'distributie' | 'payslip') => void;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = PROPOSAL_STRINGS[lang];
  const locale = LOCALE[lang];
  const n = (value: number) => value.toLocaleString(locale);
  const pct = (value: number) => `${(value * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}%`;
  const ratio = (value: number) =>
    `1:${value.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

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
    { v: n(now.positions), k: t.kpis.positions, from: t.from(n(base.positions)) },
    { v: n(now.distinctValues), k: t.kpis.distinct, from: t.from(n(base.distinctValues)) },
    { v: pct(now.backSolvedShare), k: t.kpis.backSolved, from: t.from(pct(base.backSolvedShare)) },
    { v: n(now.variantsInGaps), k: t.kpis.gaps, from: t.from(n(base.variantsInGaps)) },
    {
      // span, not spanByPeriod: one of the patches removes the annual schedule outright,
      // so the proposal has no periods to take a last one from and the row read "1:0,00".
      v: ratio(now.span.ratio),
      k: t.kpis.span,
      from: t.from(ratio(base.span.ratio)),
    },
  ];

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>
          {proposal.summary} {t.purpose}
        </p>
        <p className="src">
          {t.counts(n(repairs.length), n(changes.length), n(proposal.patches.length - off.size), n(proposal.patches.length))}
        </p>
      </header>
      {menu}

      <div className="disclaimer">{t.disclaimer}</div>

      <section>
        <h2>{t.resultTitle}</h2>
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
        {activeChanges > 0 && <p className="lede">{t.moveMoney(n(activeChanges))}</p>}
        <div className="patch-actions civic-scope civic-pay">
          <Button onClick={() => setAll(true)}>{t.allOn}</Button>
          <Button onClick={() => setAll(false)}>{t.allOff}</Button>
          <Button onClick={() => onScenario({ ...scenario, offPatches: changes.map((p) => p.id) })}>
            {t.repairsOnly}
          </Button>
        </div>
      </section>

      <section>
        <h2>{t.patchesTitle}</h2>
        <p className="lede">{proposal.notPolicy}</p>
        <ol className="patches">
          {proposal.patches.map((patch) => {
            const on = !off.has(patch.id);
            const effect = effectOf(patch.id);
            const touched = effect
              ? [
                  effect.positionsTouched && `${n(effect.positionsTouched)} ${t.touched.positions}`,
                  effect.variantsTouched && `${n(effect.variantsTouched)} ${t.touched.variants}`,
                  effect.gradesTouched && `${n(effect.gradesTouched)} ${t.touched.grades}`,
                  effect.supplementsTouched && `${n(effect.supplementsTouched)} ${t.touched.supplements}`,
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
                      <span className="badge weak">{t.badgeChange}</span>
                    ) : (
                      <span className="badge">{t.badgeRepair}</span>
                    )}
                    {touched && <span className="touched">{touched}</span>}
                    <span className="patch-switch civic-scope civic-pay">
                      <Checkbox
                        checked={on}
                        onChange={() => toggle(patch.id)}
                        label={on ? t.on : t.off}
                        aria-label={`${patch.title}: ${on ? t.on : t.off}`}
                      />
                    </span>
                  </span>
                </div>
                {patch.expectedEffect && <p className="effect">{patch.expectedEffect}</p>}
                <details>
                  <summary>{t.why}</summary>
                  <p>{patch.rationale}</p>
                  {patch.fixes && <p className="src">{t.fixes(<code>{patch.fixes}</code>)}</p>}
                </details>
              </li>
            );
          })}
        </ol>
      </section>

      <section>
        <h2>{t.nextTitle}</h2>
        <div className="next-grid">
          {(['compare', 'distributie', 'payslip'] as const).map((view) => (
            <button key={view} className="next" onClick={() => onOpen(view)}>
              <strong>{t.next[view].title}</strong>
              <span>{t.next[view].body}</span>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Field, Input, RangeSlider } from '@cristiannichifor/civic-ui';

import type { CapSeries } from '../../engine/cap';
import type { Scenario } from '../../engine/scenario';
import { envelope } from '../../engine/envelope';
import type { EnvelopeBaseline, Move } from '../../engine/envelope';
import CapSection from './CapSection';
import type { Lang } from './i18n';
import { amountLine } from './money';
import type { Rates } from './money';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

const FAMILY_LABELS: Record<Lang, Record<string, string>> = {
  ro: {
    'I-invatamant': 'Învățământ',
    'II-sanatate-asistenta-sociala': 'Sănătate și asistență socială',
    'VI-aparare-ordine-securitate': 'Apărare, ordine publică, securitate',
    'VIII-administratie': 'Administrație',
  },
  en: {
    'I-invatamant': 'Education',
    'II-sanatate-asistenta-sociala': 'Health and social care',
    'VI-aparare-ordine-securitate': 'Defence, public order, security',
    'VIII-administratie': 'Administration',
  },
};

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface EnvelopeStrings {
  /** The "mld." / "bn" suffix after a figure in billions. */
  bn: string;
  loading: string;
  title: string;
  purpose: string;
  hero: (lei: string, eur: string, after: string, before: string) => string;
  fits: string;
  missing: (lei: string) => string;
  targetTitle: string;
  targetLabel: string;
  targetNote: (pct: string, base: string) => string;
  closedEnvelope: string;
  art38: (before: string, target: string, change: string) => string;
  movesTitle: string;
  movesLede: string;
  familyLabel: (family: string) => string;
  whyLabel: string;
  whyAria: (family: string) => string;
  whyUp: string;
  whyDown: string;
  ledgerTitle: string;
  plus: (lei: string) => string;
  from: (amount: string, label: string) => ReactNode;
  unfunded: (lei: string) => ReactNode;
  assumptionsTitle: string;
  severity: Record<'blocking' | 'material' | 'note', string>;
  baselineTag: string;
  baselineNote: (posts: string, perPost: string) => ReactNode;
}

export const ENVELOPE_STRINGS: Record<Lang, EnvelopeStrings> = {
  ro: {
    bn: 'mld.',
    loading: 'Se încarcă baza de pornire — cheltuiala de personal pe funcții și posturile ocupate.',
    title: 'Plicul: cât se cheltuie în total',
    purpose:
      'Fixezi cât are voie să coste tot personalul bugetar, apoi orice creștere trebuie plătită dintr-o reducere numită. Nu din „eficientizare”, nu din creștere economică — dintr-o reducere pe care o scrii aici și care apare în dreptul creșterii.',
    hero: (lei, eur, after, before) =>
      `${lei} lei pe an ≈ ${eur} mld. EUR — ${after}% din PIB, față de ${before}% acum.`,
    fits: 'Planul încape în plic.',
    missing: (lei) => `Lipsesc ${lei} lei — sunt creșteri fără acoperire.`,
    targetTitle: 'Ținta',
    targetLabel: 'Cheltuiala totală de personal (%)',
    targetNote: (pct, base) => `${pct} față de ${base} lei`,
    closedEnvelope: ' — plic închis, tot ce crește undeva scade altundeva',
    art38: (before, target, change) =>
      `Art. 38 alin. (5) cere o reducere de cel puțin 1,5 puncte din PIB între 2024 și 2031. De la ${before}% asta ar însemna ${target}% — adică ${change} din cheltuiala de azi, dacă PIB-ul ar sta pe loc.`,
    movesTitle: 'Mutările',
    movesLede:
      'Trage de fiecare familie. Ce crește trebuie plătit — motivul e obligatoriu, pentru că o reducere fără autor și fără justificare nu e o propunere.',
    familyLabel: (family) => `${family} (%)`,
    whyLabel: 'Motivul mutării',
    whyAria: (family) => `Motivul mutării: ${family}`,
    whyUp: 'De ce merită această creștere?',
    whyDown: 'De unde vine reducerea?',
    ledgerTitle: 'Cine plătește ce',
    plus: (lei) => `+${lei} lei`,
    from: (amount, label) => (
      <>
        <span className="down">−{amount}</span> din {label}
      </>
    ),
    unfunded: (lei) => (
      <>
        <span>{lei} lei fără acoperire</span> — trebuie numită o reducere
      </>
    ),
    assumptionsTitle: 'Ce presupune calculul',
    severity: { blocking: 'blocant', material: 'important', note: 'de reținut' },
    baselineTag: 'bază de pornire',
    baselineNote: (posts, perPost) => (
      <>
        Execuția bugetară pe 2025, titlul I „cheltuieli de personal” în întregime — plata în bani și
        în natură plus contribuțiile angajatorului — raportată de ordonatorii principali de credite
        și împărțită pe capitole bugetare. E aceeași contabilitate în care e scrisă legea, nu o
        clasificare statistică suprapusă peste ea, și e și baza pe care Art. 38 alin. (5) își
        măsoară ținta. PIB-ul nominal rămâne de la Eurostat, fiindcă execuția nu-l conține.{' '}
        {posts} posturi ocupate din raportarea Ministerului Finanțelor, iunie 2026. Media pe post
        iese {perPost} pe lună.
      </>
    ),
  },
  en: {
    bn: 'bn',
    loading: 'Loading the baseline — staff spending by position and the posts filled.',
    title: 'The envelope: what is spent in total',
    purpose:
      'You fix what all public staff may cost, and then any increase has to be paid for by a named cut. Not by "efficiency gains", not by economic growth — by a cut you write here, which appears next to the increase.',
    hero: (lei, eur, after, before) =>
      `${lei} lei a year ≈ ${eur} bn EUR — ${after}% of GDP, against ${before}% now.`,
    fits: 'The plan fits in the envelope.',
    missing: (lei) => `${lei} lei are missing — there are increases without cover.`,
    targetTitle: 'The target',
    targetLabel: 'Total staff spending (%)',
    targetNote: (pct, base) => `${pct} against ${base} lei`,
    closedEnvelope: ' — closed envelope, whatever grows somewhere shrinks elsewhere',
    art38: (before, target, change) =>
      `Art. 38 (5) requires a cut of at least 1.5 points of GDP between 2024 and 2031. From ${before}% that would mean ${target}% — that is ${change} of today's spending, if GDP stood still.`,
    movesTitle: 'The moves',
    movesLede:
      'Drag each family. Whatever grows has to be paid for — the reason is mandatory, because a cut without an author and without a justification is not a proposal.',
    familyLabel: (family) => `${family} (%)`,
    whyLabel: 'Reason for the move',
    whyAria: (family) => `Reason for the move: ${family}`,
    whyUp: 'Why does this increase deserve it?',
    whyDown: 'Where does the cut come from?',
    ledgerTitle: 'Who pays for what',
    plus: (lei) => `+${lei} lei`,
    from: (amount, label) => (
      <>
        <span className="down">−{amount}</span> from {label}
      </>
    ),
    unfunded: (lei) => (
      <>
        <span>{lei} lei without cover</span> — a cut has to be named
      </>
    ),
    assumptionsTitle: 'What the computation assumes',
    severity: { blocking: 'blocking', material: 'material', note: 'to note' },
    baselineTag: 'baseline',
    baselineNote: (posts, perPost) => (
      <>
        Budget execution for 2025, title I "staff costs" in full — pay in cash and in kind plus
        employer contributions — as reported by the principal budget holders and split by budget
        chapter. It is the same accounting the law is written in, not a statistical classification
        laid over it, and it is also the base on which Art. 38 (5) measures its target. Nominal GDP
        stays with Eurostat, since the execution does not contain it. {posts} posts filled from
        the Ministry of Finance's reporting, June 2026. The average per post comes to {perPost} a
        month.
      </>
    ),
  },
};

export default function EnvelopeView({
  menu,
  baseline,
  rates,
  capSeries,
  scenario,
  onScenario,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  baseline: EnvelopeBaseline | null;
  rates: Rates;
  /** The ceiling, measured per ordonator and per funding source. */
  capSeries: CapSeries[] | null;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = ENVELOPE_STRINGS[lang];
  const locale = LOCALE[lang];
  const families = FAMILY_LABELS[lang];

  /**
   * Billions of lei, one decimal. The wage bill is a twelve-digit number in minor units;
   * written out it is unreadable, and an earlier version of this labelled millions "mld.",
   * which was off by a factor of a thousand.
   */
  const bn = (minor: number) =>
    `${(minor / 100 / 1e9).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${t.bn}`;
  /** One decimal, in the reader's locale. */
  const dec = (n: number) => n.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const pctText = (n: number) => {
    const s = (n * 100).toLocaleString(locale, { maximumFractionDigits: 1 });
    return `${n > 0 ? '+' : ''}${s}%`;
  };

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
          label: families[family] ?? family,
          target: { kind: 'family' as const, family },
          pct: m.pct,
          rationale: m.why,
        })),
    [moves, families],
  );

  const result = useMemo(
    () =>
      baseline
        ? envelope(baseline, moveList, Math.round(baseline.total * (1 + targetPct)))
        : null,
    [baseline, moveList, targetPct],
  );

  if (!baseline || !result) {
    return <p className="loading">{t.loading}</p>;
  }

  const set = (family: string, patch: Partial<{ pct: number; why: string }>) =>
    setMoves((prev) => ({
      ...prev,
      [family]: { ...{ pct: 0, why: '' }, ...prev[family], ...patch },
    }));

  const fits = result.balanced;
  const missing = Math.abs(Math.min(result.headroom, 0)) || result.increases.reduce((s, i) => s + i.unfunded, 0);

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.purpose}</p>
      </header>
      {menu}

      <section className="hero envelope-hero">
        <div className="hero-figure">
          <span className={fits ? 'to' : 'from'}>{bn(result.proposed)}</span>
        </div>
        <div>
          <p className="hero-text">
            {t.hero(
              bn(result.proposed),
              (result.proposed / 100 / rates.eurToRon / 1e9).toLocaleString(locale, { maximumFractionDigits: 1 }),
              (result.shareOfGdp.after * 100).toLocaleString(locale, { maximumFractionDigits: 2 }),
              (result.shareOfGdp.before * 100).toLocaleString(locale, { maximumFractionDigits: 2 }),
            )}
          </p>
          <p className={`verdict ${fits ? 'ok' : 'bad'}`}>{fits ? t.fits : t.missing(bn(missing))}</p>
        </div>
      </section>

      <section>
        <h2>{t.targetTitle}</h2>
        <div className="card controls">
          <RangeSlider
            className="field"
            label={t.targetLabel}
            min={-15}
            max={15}
            step={0.5}
            value={targetPct * 100}
            onValueChange={(value) => setTargetPct(value / 100)}
          />
          <p className="field-note">
            {t.targetNote(pctText(targetPct), bn(baseline.total))}
            {targetPct === 0 && t.closedEnvelope}
          </p>
          <p className="src">
            {t.art38(
              dec(result.shareOfGdp.before * 100),
              dec(result.shareOfGdp.before * 100 - 1.5),
              pctText(((result.shareOfGdp.before - 0.015) / result.shareOfGdp.before) - 1),
            )}
          </p>
        </div>
      </section>

      <section>
        <h2>{t.movesTitle}</h2>
        <p className="lede">{t.movesLede}</p>
        <div className="moves">
          {result.byFamily.map((f) => {
            const state = moves[f.family] ?? { pct: 0, why: '' };
            const label = families[f.family] ?? f.label;
            return (
              <div key={f.family} className="card move-row">
                <div className="move-head">
                  <strong>{label}</strong>
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
                <RangeSlider
                  label={t.familyLabel(label)}
                  min={-25}
                  max={25}
                  step={0.5}
                  value={state.pct * 100}
                  onValueChange={(value) => set(f.family, { pct: value / 100 })}
                />
                {state.pct !== 0 && (
                  <Field id={`move-why-${f.family}`} label={t.whyLabel}>
                    {(attributes) => (
                      <Input
                        {...attributes}
                        type="text"
                        aria-label={t.whyAria(label)}
                        className={`why${state.why.trim() ? '' : ' missing'}`}
                        placeholder={state.pct > 0 ? t.whyUp : t.whyDown}
                        value={state.why}
                        onChange={(e) => set(f.family, { why: e.target.value })}
                      />
                    )}
                  </Field>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {result.increases.length > 0 && (
        <section>
          <h2>{t.ledgerTitle}</h2>
          <div className="ledger">
            {result.increases.map((entry) => (
              <div key={entry.move.id} className="card ledger-row">
                <div className="ledger-head">
                  <strong>{entry.move.label}</strong>
                  <span className="up">{t.plus(bn(entry.delta))}</span>
                </div>
                {entry.move.rationale.trim() && <p className="why-text">{entry.move.rationale}</p>}
                <ul className="funding">
                  {entry.fundedBy.map((f) => (
                    <li key={f.fromMoveId}>{t.from(bn(f.amount), f.fromLabel)}</li>
                  ))}
                  {entry.unfunded > 0 && <li className="unfunded">{t.unfunded(bn(entry.unfunded))}</li>}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {capSeries && <CapSection series={capSeries} lang={lang} />}

      <section>
        <h2>{t.assumptionsTitle}</h2>
        <div className="limits">
          {result.diagnostics.map((d, i) => (
            <div key={i} className={`limit ${d.severity}`}>
              <div className="sev">{t.severity[d.severity === 'blocking' ? 'blocking' : 'note']}</div>
              <p>{d.message}</p>
            </div>
          ))}
          <div className="limit note">
            <div className="sev">{t.baselineTag}</div>
            <p>
              {t.baselineNote(
                baseline.posts.toLocaleString(locale),
                amountLine(result.perPost.before / 100 / 12, baseline.currency, rates, 'native', locale),
              )}
            </p>
          </div>
        </div>
      </section>
    </>
  );
}

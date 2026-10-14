import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { PositionName } from './names';
import { Checkbox, Field, Input, NativeSelect, RangeSlider, Table } from '@cristiannichifor/civic-ui';

import { ineligibility, payslip } from '../../engine/payslip';
import type { Payslip, Person } from '../../engine/payslip';
import type { Scenario } from '../../engine/scenario';
import type { Crosswalk, Position, Regime } from '../../engine/types';
import { amountLine } from './money';
import type { Rates } from './money';
import { SEVERITY_LABELS } from './i18n';
import type { Lang } from './i18n';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

/**
 * Variant dimensions, named as a reader would name them.
 *
 * The picker used to print the field as the engine spells it — `gradProfesional: treaptă
 * III` — the one place in the app where reading the screen required knowing how the data
 * is stored. It matters most for the trades: for a *muncitor calificat* the step is the
 * only thing in the whole grid that says what the qualification being paid actually is,
 * so it must not arrive looking like a debugging aid.
 *
 * `sursa` and `celula` are deliberately labelled as what they are. They are not a
 * distinction the law draws — they are where the row came from, kept only because two
 * variants would otherwise be indistinguishable and unaddressable. Naming them honestly
 * is how a reader can tell a real difference from a gap in the source.
 */
const DIM_LABEL: Record<Lang, Record<string, string>> = {
  ro: {
    grad: 'grad',
    gradProfesional: 'grad/treaptă',
    gradManagerial: 'grad managerial',
    gradatie: 'gradație',
    treapta: 'treaptă',
    vechime: 'vechime',
    institutionLevel: 'nivelul instituției',
    an: 'anul',
    variant: 'varianta',
    sursa: 'din foaia',
    celula: 'din celula',
  },
  en: {
    grad: 'grade',
    gradProfesional: 'grade/step',
    gradManagerial: 'managerial grade',
    gradatie: 'seniority step',
    treapta: 'step',
    vechime: 'seniority',
    institutionLevel: 'institution level',
    an: 'year',
    variant: 'variant',
    sursa: 'from sheet',
    celula: 'from cell',
  },
};

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface PayslipStrings {
  title: string;
  lead: ReactNode;
  disclaimer: ReactNode;
  why: string;
  whyText: string;
  person: string;
  position: string;
  searchPlaceholder: string;
  selectedPosition: string;
  otherTitles: (n: number) => string;
  seniority: string;
  wasCalled: string;
  assumedMatch: string;
  derivedMatch: string;
  coefficient: (value: string) => string;
  wasMove: (share: string) => ReactNode;
  wasCaveat: string;
  gradeOrStep: string;
  variant: (i: number) => string;
  claimed: string;
  upTo: string;
  exemptFromCap: string;
  partialInCap: string;
  claimsNote: string;
  pickOne: string;
  perRegime: string;
  noCrossCurrency: (list: string) => ReactNode;
  unitless: string;
  unitlessLede: string;
  unitlessTable: string;
  colRatio: string;
  baseOfGross: string;
  supplementsOfGross: string;
  netOfGross: string;
  cannotCompute: string;
  employerOverGross: string;
  seniorityVsZero: string;
  bakedIn: string;
  period: Record<string, string>;
  missingCode: ReactNode;
  calcTable: (regime: string) => string;
  base: string;
  ofWhichSeniority: (step: string | null) => string;
  excludedBy: (name: string) => string;
  gross: string;
  net: string;
  notComputed: string;
  employerCost: string;
  pensionSplit: string;
  capOf: (limit: string) => string;
  usage: (share: string) => string;
  notional: string;
  diagnostics: (n: number) => string;
  composeLabel: string;
  composeBase: string;
  composeSupplements: string;
  composePension: string;
}

export const PAYSLIP_STRINGS: Record<Lang, PayslipStrings> = {
  ro: {
    title: 'Același om, sub mai multe regimuri',
    lead: (
      <>
        Alege o funcție și o vechime. Fiecare regim calculează din propriile lui reguli, iar tot
        scenariul stă în adresa paginii — linkul <em>este</em> scenariul.
      </>
    ),
    disclaimer: (
      <>
        <strong>Cifrele sunt ce spune legea, nu ce încasează cineva.</strong> Orice sumă de aici e un
        prag, nu o prognoză.
      </>
    ),
    why: 'De ce',
    whyText:
      'Diferența salarială tranzitorie de la Art. 33 menține venitul din noiembrie 2026 și, în primii ani, domină factura reală. Nu poate fi calculată fără date individuale de salarizare, pe care România nu le publică.',
    person: 'Persoana',
    position: 'Funcția',
    searchPlaceholder: 'caută după denumire sau cod — ex. auditor, director, 81.101',
    selectedPosition: 'Funcția selectată',
    otherTitles: (n) => ` (+${n} denumiri)`,
    seniority: 'Vechime în muncă (ani)',
    wasCalled: 'Sub legea în vigoare, postul ăsta se numea',
    assumedMatch: 'potrivire presupusă',
    derivedMatch: 'potrivire derivată',
    coefficient: (value) => ` — coeficient ${value}`,
    wasMove: (share) => (
      <>
        {' '}= {share} ca poziție în grilă. Nu e schimbarea salariului: valoarea de referință trece de
        la 2.500 lei la 4.100 lei, deci coeficienții măsoară locul în ierarhie, nu suma.
      </>
    ),
    wasCaveat:
      'Nicio lege nu publică asimilarea. Art. 32 cere reîncadrarea fiecărui angajat, dar lasă decizia la fiecare ordonator de credite — deci legătura de mai sus e o reconstrucție după denumire și familie ocupațională, nu un drept.',
    gradeOrStep: 'Gradul sau treapta',
    variant: (i) => `varianta ${i}`,
    claimed: 'Sporuri revendicate',
    upTo: ' (până la)',
    exemptFromCap: ' · exceptat de la plafon',
    partialInCap: ' · parțial în plafon',
    claimsNote:
      'Sporurile stinse nu se aplică acestei funcții. Regula este a propunerii, nu a paginii: fiecare spor își declară familia sau tipul de funcție pentru care se plătește, iar aici nu se poate bifa în afara ei. Un regim care nu declară nimic — cum e legea în vigoare, care nu publică niciun spor — rămâne la fel de permisiv cum era.',
    pickOne: 'Alege o funcție ca să vezi calculul.',
    perRegime: 'Calculul, regim cu regim',
    noCrossCurrency: (list) => (
      <>
        <strong>Nu se compară cuantumuri între monede.</strong> Regimurile alese sunt exprimate în
        monede sau perioade diferite ({list}). Coloanele stau una lângă alta, dar nu se scad.
        Comparația care rămâne validă este cea fără unități, de mai jos.
      </>
    ),
    unitless: 'Comparație fără unități',
    unitlessLede:
      'Singura comparație validă între regimuri exprimate în monede diferite: proporții, nu sume. Ce parte din brut e salariul de bază, cât adaugă sporurile, cât rămâne net, cât costă angajatorul peste brut.',
    unitlessTable: 'Comparație fără unități',
    colRatio: 'Raport',
    baseOfGross: 'Salariul de bază din brut',
    supplementsOfGross: 'Sporuri din brut',
    netOfGross: 'Net din brut',
    cannotCompute: 'nu se poate calcula',
    employerOverGross: 'Costul angajatorului peste brut',
    seniorityVsZero: 'Sporul de vechime față de gradația 0',
    bakedIn: 'inclus în coeficient',
    period: { month: 'pe lună', year: 'pe an' },
    missingCode: (
      <>
        Funcția nu are un cod în acest regim — cele două sisteme nu folosesc același nomenclator.
        Echivalările dintre ele, cu sumele convertite și cu denumirea pe care ar folosi-o piața
        muncii, sunt în <a href="#/echivalente">Echivalențe RO–DK</a>.
      </>
    ),
    calcTable: (regime) => `Calcul salarial: ${regime}`,
    base: 'Salariu de bază',
    ofWhichSeniority: (step) => (step ? `din care vechime (${step})` : 'din care vechime'),
    excludedBy: (name) => ` — exclus de „${name}”`,
    gross: 'Brut',
    net: 'Net',
    notComputed: 'nu se calculează',
    employerCost: 'Cost total angajator',
    pensionSplit: 'pensie: angajat / angajator',
    capOf: (limit) => `Plafonul de ${limit}`,
    usage: (share) => `utilizare ${share}`,
    notional: 'Cifră notională. ',
    diagnostics: (n) => `${n} observații despre acest calcul`,
    composeLabel: 'din ce e compus brutul',
    composeBase: 'bază',
    composeSupplements: 'sporuri',
    composePension: 'pensie',
  },
  en: {
    title: 'The same person, under several regimes',
    lead: (
      <>
        Pick a position and a seniority. Each regime computes from its own rules, and the whole
        scenario sits in the page address: the link <em>is</em> the scenario.
      </>
    ),
    disclaimer: (
      <>
        <strong>The figures are what the law says, not what anyone takes home.</strong> Every amount
        here is a threshold, not a forecast.
      </>
    ),
    why: 'Why',
    whyText:
      'The transitional pay difference of Art. 33 keeps the November 2026 income and, in the first years, dominates the real bill. It cannot be computed without individual pay data, which Romania does not publish.',
    person: 'The person',
    position: 'Position',
    searchPlaceholder: 'search by title or code, e.g. auditor, director, 81.101',
    selectedPosition: 'Selected position',
    otherTitles: (n) => ` (+${n} titles)`,
    seniority: 'Years of service',
    wasCalled: 'Under the law in force this post was called',
    assumedMatch: 'assumed match',
    derivedMatch: 'derived match',
    coefficient: (value) => ` — coefficient ${value}`,
    wasMove: (share) => (
      <>
        {' '}= {share} as a place in the grid. This is not the change in pay: the reference value
        moves from 2,500 lei to 4,100 lei, so the coefficients measure the place in the hierarchy,
        not the sum.
      </>
    ),
    wasCaveat:
      'No law publishes the assimilation. Art. 32 requires every employee to be regraded but leaves the decision to each budget holder, so the link above is a reconstruction by title and occupational family, not a right.',
    gradeOrStep: 'Grade or step',
    variant: (i) => `variant ${i}`,
    claimed: 'Supplements claimed',
    upTo: ' (up to)',
    exemptFromCap: ' · exempt from the cap',
    partialInCap: ' · partly within the cap',
    claimsNote:
      'Greyed-out supplements do not apply to this position. The rule is the proposal\'s, not the page\'s: each supplement declares the family or type of position it is paid for, and nothing outside it can be ticked here. A regime that declares nothing, like the law in force, which publishes no supplement, stays as permissive as it was.',
    pickOne: 'Pick a position to see the computation.',
    perRegime: 'The computation, regime by regime',
    noCrossCurrency: (list) => (
      <>
        <strong>Amounts are not compared across currencies.</strong> The chosen regimes are
        expressed in different currencies or periods ({list}). The columns stand side by side but
        are not subtracted. The comparison that stays valid is the unit-free one below.
      </>
    ),
    unitless: 'Unit-free comparison',
    unitlessLede:
      'The only valid comparison between regimes expressed in different currencies: proportions, not sums. What share of gross is base salary, how much the supplements add, how much stays net, how much the employer pays above gross.',
    unitlessTable: 'Unit-free comparison',
    colRatio: 'Ratio',
    baseOfGross: 'Base salary as a share of gross',
    supplementsOfGross: 'Supplements as a share of gross',
    netOfGross: 'Net as a share of gross',
    cannotCompute: 'cannot be computed',
    employerOverGross: 'Employer cost above gross',
    seniorityVsZero: 'Seniority supplement against step 0',
    bakedIn: 'built into the coefficient',
    period: { month: 'per month', year: 'per year' },
    missingCode: (
      <>
        The position has no code in this regime: the two systems do not share a nomenclature.
        The equivalences between them, with converted amounts and the title the labour market
        would use, are in <a href="#/echivalente">RO–DK equivalences</a>.
      </>
    ),
    calcTable: (regime) => `Pay computation: ${regime}`,
    base: 'Base salary',
    ofWhichSeniority: (step) => (step ? `of which seniority (${step})` : 'of which seniority'),
    excludedBy: (name) => ` — excluded by "${name}"`,
    gross: 'Gross',
    net: 'Net',
    notComputed: 'not computed',
    employerCost: 'Total employer cost',
    pensionSplit: 'pension: employee / employer',
    capOf: (limit) => `Cap of ${limit}`,
    usage: (share) => `usage ${share}`,
    notional: 'Notional figure. ',
    diagnostics: (n) => `${n} notes on this computation`,
    composeLabel: 'what the gross is made of',
    composeBase: 'base',
    composeSupplements: 'supplements',
    composePension: 'pension',
  },
};

function dimText(dims: Readonly<Record<string, string>> | undefined, labels: Record<string, string>): string {
  return Object.entries(dims ?? {})
    .map(([key, value]) => `${labels[key] ?? key}: ${value}`)
    .join(' · ');
}

export default function PayslipView({
  menu,
  regimes,
  scenario,
  onChange,
  rates,
  assimilation,
  inForce,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  regimes: Regime[];
  scenario: Scenario;
  onChange: (next: Scenario) => void;
  rates: Rates;
  /** 153/2017 -> draft. A reconstruction, never a statement of anyone's rights. */
  assimilation: Crosswalk | null;
  inForce: Regime | null;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = PAYSLIP_STRINGS[lang];
  const locale = LOCALE[lang];
  const dims = DIM_LABEL[lang];
  const n = (value: number) => value.toLocaleString(locale);
  const pct = (value: number, digits = 1): string =>
    `${(value * 100).toLocaleString(locale, { maximumFractionDigits: digits })}%`;
  const primary = regimes[0];
  const [query, setQuery] = useState('');

  const matches = useMemo(() => {
    if (!primary) return [];
    const q = query.trim().toLowerCase();
    if (!q) return primary.positions.slice(0, 40);
    return primary.positions
      .filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.code.toLowerCase().includes(q) ||
          p.titles?.some((title) => title.name.toLowerCase().includes(q)),
      )
      .slice(0, 40);
  }, [primary, query]);

  const options = useMemo(() => {
    if (!primary || !scenario.positionCode) return matches;
    if (matches.some((p) => p.code === scenario.positionCode)) return matches;
    const selected = primary.positions.find((p) => p.code === scenario.positionCode);
    return selected ? [selected, ...matches] : matches;
  }, [matches, primary, scenario.positionCode]);

  const person: Person | null = scenario.positionCode
    ? {
        positionCode: scenario.positionCode,
        seniorityYears: scenario.seniorityYears ?? 0,
        dims: scenario.dims,
        claims: scenario.claims,
      }
    : null;

  const slips = useMemo(
    () =>
      person
        ? regimes.map((regime) => ({
            regime,
            position: regime.positions.find((p) => p.code === person.positionCode) ?? null,
            slip: payslip(person, regime),
          }))
        : [],
    [person, regimes],
  );

  const chosen: Position | undefined = primary?.positions.find(
    (p) => p.code === scenario.positionCode,
  );

  // Absolute amounts are only ever compared inside one currency and one period. Two
  // regimes denominated differently get their own columns and no delta — the comparison
  // that remains is the dimensionless one below.
  const priced = slips.filter((s) => s.position !== null);
  const comparable =
    slips.length > 1 &&
    new Set(slips.map((s) => `${s.regime.currency}|${s.slip.period}`)).size === 1;

  // What this post was called before the draft abrogated the law that named it. Art. 32
  // requires everyone to be reassigned but publishes no mapping, so this is reconstructed
  // and says so — the link is evidence for an argument, not a claim about entitlement.
  const wasCalled = useMemo(() => {
    if (!assimilation || !chosen) return null;
    const link = assimilation.links.find((l) =>
      l.to.some((e) => e.positionCode === chosen.code),
    );
    if (!link) return null;
    const before = link.from
      .map((e) => {
        const position = inForce?.positions.find((p) => p.code === e.positionCode);
        const values = position?.variants
          .map((v) => (typeof v.value === 'number' ? v.value : null))
          .filter((value): value is number => value !== null);
        return {
          title: e.title ?? e.positionCode,
          coefficient: values && values.length ? Math.min(...values) : null,
        };
      })
      .filter((b) => b.title);
    const after = chosen.variants
      .map((v) => (typeof v.value === 'number' ? v.value : null))
      .filter((value): value is number => value !== null);
    return {
      link,
      before,
      after: after.length ? Math.min(...after) : null,
    };
  }, [assimilation, chosen, inForce]);

  const set = (patch: Partial<Scenario>) => onChange({ ...scenario, ...patch });

  const toggleClaim = (id: string) => {
    const claims = scenario.claims ?? [];
    const exists = claims.some((c) => c.supplementId === id);
    set({
      claims: exists
        ? claims.filter((c) => c.supplementId !== id)
        : [...claims, { supplementId: id }],
    });
  };

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.lead}</p>
      </header>
      {menu}

      <div className="disclaimer">
        {t.disclaimer}
        <details>
          <summary>{t.why}</summary>
          <p>{t.whyText}</p>
        </details>
      </div>

      <section>
        <h2>{t.person}</h2>
        <div className="card controls">
          <div className="field">
            <Field id="payslip-search" label={t.position}>
              {(attributes) => (
                <Input
                  {...attributes}
                  type="search"
                  value={query}
                  placeholder={t.searchPlaceholder}
                  onChange={(e) => setQuery(e.target.value)}
                />
              )}
            </Field>
            <select
              aria-label={t.selectedPosition}
              size={8}
              value={scenario.positionCode ?? ''}
              onChange={(e) => set({ positionCode: e.target.value, dims: undefined })}
            >
              {options.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                  {p.assimilation && p.assimilation.fanIn && p.assimilation.fanIn > 1
                    ? t.otherTitles(p.assimilation.fanIn - 1)
                    : ''}{' '}
                  — {p.code}
                </option>
              ))}
            </select>
          </div>

          <RangeSlider
            className="field"
            label={t.seniority}
            min={0}
            max={40}
            value={scenario.seniorityYears ?? 0}
            onValueChange={(value) => set({ seniorityYears: value })}
          />

          {wasCalled && (
            <div className="was-called">
              <div className="was-head">
                <strong>{t.wasCalled}</strong>
                <span className={`badge ${wasCalled.link.confidence === 'assumed' ? 'weak' : ''}`}>
                  {wasCalled.link.confidence === 'assumed' ? t.assumedMatch : t.derivedMatch}
                </span>
              </div>
              <ul>
                {wasCalled.before.map((b) => (
                  <li key={b.title}>
                    {b.title}
                    {b.coefficient !== null && <em>{t.coefficient(n(b.coefficient))}</em>}
                  </li>
                ))}
              </ul>
              {wasCalled.after !== null && wasCalled.before[0]?.coefficient != null && (
                <p className="was-move">
                  {n(wasCalled.before[0].coefficient)} → <b>{n(wasCalled.after)}</b>
                  {t.wasMove(pct(wasCalled.after / wasCalled.before[0].coefficient - 1, 1))}
                </p>
              )}
              <p className="was-caveat">{t.wasCaveat}</p>
            </div>
          )}

          {chosen && chosen.variants.length > 1 && chosen.variants[0].dims && (
            <Field id="payslip-variant" label={t.gradeOrStep}>
              {(attributes) => (
                <NativeSelect
                  {...attributes}
                  value={JSON.stringify(scenario.dims ?? chosen.variants[0].dims)}
                  onChange={(e) => set({ dims: JSON.parse(e.target.value) })}
                >
                  {chosen.variants.map((v, i) => (
                    <option key={i} value={JSON.stringify(v.dims ?? {})}>
                      {dimText(v.dims, dims) || t.variant(i + 1)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          )}

          {primary && (
            <fieldset className="field">
              <legend>{t.claimed}</legend>
              <div className="claims">
                {primary.supplements.map((s) => {
                  // Shown even when it cannot be claimed, greyed and with the reason. A
                  // checkbox that silently disappears teaches nobody why: the point of the
                  // proposal is that a supplement belongs to a job, and the reader only sees
                  // that rule exists if the refusal is on the page.
                  const barred = chosen ? ineligibility(s, chosen) : undefined;
                  return (
                    <Checkbox
                      key={s.id}
                      className={barred ? 'claim barred' : 'claim'}
                      title={barred?.reason}
                      disabled={Boolean(barred)}
                      checked={(scenario.claims ?? []).some((c) => c.supplementId === s.id)}
                      onChange={() => toggleClaim(s.id)}
                      label={
                        <>
                          {s.name}
                          {s.mode === 'upTo' && <em>{t.upTo}</em>}
                          {s.countsToCap === false && <em>{t.exemptFromCap}</em>}
                          {s.countsToCap === 'partial' && <em>{t.partialInCap}</em>}
                          {barred && <em className="why-not"> · {barred.reason}</em>}
                        </>
                      }
                    />
                  );
                })}
              </div>
              <p className="note">{t.claimsNote}</p>
            </fieldset>
          )}
        </div>
      </section>

      {!person && (
        <section>
          <p className="lede">{t.pickOne}</p>
        </section>
      )}

      {person && (
        <section>
          <h2>{t.perRegime}</h2>
          {!comparable && slips.length > 1 && (
            <div className="disclaimer">
              {t.noCrossCurrency(
                slips.map((s) => `${s.regime.currency} ${t.period[s.slip.period]}`).join(', '),
              )}
            </div>
          )}
          <div className="slips">
            {slips.map(({ regime, position, slip }) => (
              <PayslipCard
                key={regime.id}
                regime={regime}
                position={position}
                slip={slip}
                rates={rates}
                t={t}
                pct={pct}
              />
            ))}
          </div>
        </section>
      )}

      {person && priced.length > 1 && (
        <section>
          <h2>{t.unitless}</h2>
          <p className="lede">{t.unitlessLede}</p>
          <div className="card">
            <Table className="data" label={t.unitlessTable}>
              <thead>
                <tr>
                  <th>{t.colRatio}</th>
                  {priced.map((s) => (
                    <th key={s.regime.id}>{s.regime.name.split('(')[0].trim()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t.baseOfGross}</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.gross ? pct(s.slip.base / s.slip.gross) : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>{t.supplementsOfGross}</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.gross
                        ? pct(s.slip.supplements.reduce((a, l) => a + l.amount, 0) / s.slip.gross)
                        : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>{t.netOfGross}</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.net === null ? t.cannotCompute : pct(s.slip.net / s.slip.gross)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>{t.employerOverGross}</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.gross ? pct(s.slip.employerCost / s.slip.gross - 1) : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>{t.seniorityVsZero}</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.seniority.bakedIn ? t.bakedIn : pct(s.slip.seniority.factor - 1)}
                    </td>
                  ))}
                </tr>
              </tbody>
            </Table>
          </div>
        </section>
      )}
    </>
  );
}

function PayslipCard({
  regime,
  position,
  slip,
  rates,
  t,
  pct,
}: {
  regime: Regime;
  position: Position | null;
  slip: Payslip;
  rates: Rates;
  t: PayslipStrings;
  pct: (value: number, digits?: number) => string;
}) {
  const cur = (m: number) => amountLine(m / 100, slip.currency, rates);
  // A refused supplement is worth a row at zero: it is the only place the reader sees that
  // the proposal has a rule about who gets what.
  const supplements = slip.supplements.filter(
    (l) => l.amount > 0 || l.suppressedBy || l.ineligible,
  );

  if (!position) {
    return (
      <div className="card slip">
        <h3>{regime.name.split('(')[0].trim()}</h3>
        <p className="missing">{t.missingCode}</p>
      </div>
    );
  }

  return (
    <div className="card slip">
      <h3>{regime.name.split('(')[0].trim()}</h3>
      <p className="slip-meta">
        <PositionName name={position.name} /> · {slip.currency} {t.period[slip.period]}
      </p>

      <Composition slip={slip} t={t} />

      <Table className="data" label={t.calcTable(regime.name)}>
        <tbody>
          <tr>
            <td>{t.base}</td>
            <td className="num">{cur(slip.base)}</td>
          </tr>
          {!slip.seniority.bakedIn && slip.seniority.amount !== 0 && (
            <tr className="sub">
              <td>{t.ofWhichSeniority(slip.seniority.stepId)}</td>
              <td className="num">{cur(slip.seniority.amount)}</td>
            </tr>
          )}
          {supplements.map((line) => (
            <tr key={line.id} className={line.suppressedBy || line.ineligible ? 'struck' : undefined}>
              <td>
                {line.name}
                {line.allowedRate !== null && <> · {pct(line.allowedRate, 1)}</>}
                {line.suppressedBy && <em>{t.excludedBy(line.suppressedBy)}</em>}
                {line.ineligible && <em> — {line.ineligible.reason}</em>}
              </td>
              <td className="num">{cur(line.amount)}</td>
            </tr>
          ))}
          <tr className="total">
            <td>{t.gross}</td>
            <td className="num">{cur(slip.gross)}</td>
          </tr>
          <tr>
            <td>{t.net}</td>
            <td className="num">
              {slip.net === null ? <span className="missing-inline">{t.notComputed}</span> : cur(slip.net)}
            </td>
          </tr>
          <tr>
            <td>{t.employerCost}</td>
            <td className="num">{cur(slip.employerCost)}</td>
          </tr>
          {slip.pensionSplit && (
            <tr className="sub">
              <td>{t.pensionSplit}</td>
              <td className="num">
                {cur(slip.pensionSplit.employee)} / {cur(slip.pensionSplit.employer)}
              </td>
            </tr>
          )}
        </tbody>
      </Table>

      {slip.capUtilisation.map((cap) => (
        <div key={cap.capId} className="cap">
          <div className="cap-head">
            <span>{t.capOf(pct(cap.limit, 0))}</span>
            <strong>{pct(cap.ratio)}</strong>
          </div>
          <div className="meter" role="img" aria-label={t.usage(pct(cap.ratio))}>
            <div
              className="meter-fill"
              style={{ width: `${Math.min((cap.ratio / Math.max(cap.limit, 0.0001)) * 100, 100)}%` }}
            />
          </div>
          <p className="cap-note">
            {cap.authoritative ? '' : t.notional}
            {cap.scopeNote}
          </p>
        </div>
      ))}

      {slip.diagnostics.length > 0 && (
        <details className="diags">
          <summary>{t.diagnostics(slip.diagnostics.length)}</summary>
          <ul>
            {slip.diagnostics.map((d, i) => (
              <li key={i} className={d.severity}>
                <span className="sev">{SEVERITY_LABELS[d.severity]}</span> {d.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/**
 * What the gross is made of, before what it adds up to.
 *
 * A number cannot show that one system pays through the base and another through
 * supplements; a proportion can, at a glance, which is the whole argument about Article
 * 21 rendered in one bar.
 */
function Composition({ slip, t }: { slip: Payslip; t: PayslipStrings }) {
  const supplements = slip.supplements.reduce((sum, l) => sum + l.amount, 0);
  const pension = slip.pensionSplit?.total ?? 0;
  const total = slip.base + supplements + pension;
  if (total <= 0) return null;
  const w = (value: number) => `${(value / total) * 100}%`;
  const share = (value: number) => Math.round((value / total) * 100);

  return (
    <div className="slip-compose">
      <div className="compose-track" role="img" aria-label={t.composeLabel}>
        <div className="compose-seg seg-base" style={{ width: w(slip.base) }} />
        {supplements > 0 && <div className="compose-seg seg-sup" style={{ width: w(supplements) }} />}
        {pension > 0 && <div className="compose-seg seg-pension" style={{ width: w(pension) }} />}
      </div>
      <div className="compose-key">
        <span>
          <i className="seg-base" /> {t.composeBase} {share(slip.base)}%
        </span>
        {supplements > 0 && (
          <span>
            <i className="seg-sup" /> {t.composeSupplements} {share(supplements)}%
          </span>
        )}
        {pension > 0 && (
          <span>
            <i className="seg-pension" /> {t.composePension} {share(pension)}%
          </span>
        )}
      </div>
    </div>
  );
}

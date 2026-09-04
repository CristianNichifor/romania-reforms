import { useMemo, useState } from 'react';

import { payslip } from '../../engine/payslip';
import type { Payslip, Person } from '../../engine/payslip';
import type { Scenario } from '../../engine/scenario';
import type { Crosswalk, Position, Regime } from '../../engine/types';
import { amountLine } from './money';
import type { Rates } from './money';
function pct(n: number, digits = 1): string {
  return `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: digits })}%`;
}

const PERIOD_LABEL: Record<string, string> = { month: 'pe lună', year: 'pe an' };

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
const DIM_LABEL: Record<string, string> = {
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
};

function dimText(dims: Readonly<Record<string, string>> | undefined): string {
  return Object.entries(dims ?? {})
    .map(([key, value]) => `${DIM_LABEL[key] ?? key}: ${value}`)
    .join(' · ');
}

export default function PayslipView({
  regimes,
  scenario,
  onChange,
  rates,
  assimilation,
  inForce,
}: {
  regimes: Regime[];
  scenario: Scenario;
  onChange: (next: Scenario) => void;
  rates: Rates;
  /** 153/2017 -> draft. A reconstruction, never a statement of anyone's rights. */
  assimilation: Crosswalk | null;
  inForce: Regime | null;
}) {
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
          p.titles?.some((t) => t.name.toLowerCase().includes(q)),
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
          .filter((n): n is number => n !== null);
        return {
          title: e.title ?? e.positionCode,
          coefficient: values && values.length ? Math.min(...values) : null,
        };
      })
      .filter((b) => b.title);
    const after = chosen.variants
      .map((v) => (typeof v.value === 'number' ? v.value : null))
      .filter((n): n is number => n !== null);
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
        <h1>Același om, sub mai multe regimuri</h1>
        <p>
          Alege o funcție și o vechime. Fiecare regim calculează din propriile lui reguli, iar tot
          scenariul stă în adresa paginii — linkul <em>este</em> scenariul.
        </p>
      </header>

      <div className="disclaimer">
        <strong>Cifrele sunt ce spune legea, nu ce încasează cineva.</strong> Orice sumă de aici e
        un prag, nu o prognoză.
        <details>
          <summary>De ce</summary>
          <p>
            Diferența salarială tranzitorie de la Art. 33 menține venitul din noiembrie 2026 și, în
            primii ani, domină factura reală. Nu poate fi calculată fără date individuale de
            salarizare, pe care România nu le publică.
          </p>
        </details>
      </div>

      <section>
        <h2>Persoana</h2>
        <div className="card controls">
          <label className="field">
            <span>Funcția</span>
            <input
              type="search"
              value={query}
              placeholder="caută după denumire sau cod — ex. auditor, director, 81.101"
              onChange={(e) => setQuery(e.target.value)}
            />
            <select
              size={8}
              value={scenario.positionCode ?? ''}
              onChange={(e) => set({ positionCode: e.target.value, dims: undefined })}
            >
              {options.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                  {p.assimilation && p.assimilation.fanIn && p.assimilation.fanIn > 1
                    ? ` (+${p.assimilation.fanIn - 1} denumiri)`
                    : ''}{' '}
                  — {p.code}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Vechime în muncă: {scenario.seniorityYears ?? 0} ani</span>
            <input
              type="range"
              min={0}
              max={40}
              value={scenario.seniorityYears ?? 0}
              onChange={(e) => set({ seniorityYears: Number(e.target.value) })}
            />
          </label>

          {wasCalled && (
            <div className="was-called">
              <div className="was-head">
                <strong>Sub legea în vigoare, postul ăsta se numea</strong>
                <span className={`badge ${wasCalled.link.confidence === 'assumed' ? 'weak' : ''}`}>
                  {wasCalled.link.confidence === 'assumed'
                    ? 'potrivire presupusă'
                    : 'potrivire derivată'}
                </span>
              </div>
              <ul>
                {wasCalled.before.map((b) => (
                  <li key={b.title}>
                    {b.title}
                    {b.coefficient !== null && (
                      <em> — coeficient {b.coefficient.toLocaleString('ro-RO')}</em>
                    )}
                  </li>
                ))}
              </ul>
              {wasCalled.after !== null && wasCalled.before[0]?.coefficient != null && (
                <p className="was-move">
                  {wasCalled.before[0].coefficient.toLocaleString('ro-RO')} →{' '}
                  <b>{wasCalled.after.toLocaleString('ro-RO')}</b> ={' '}
                  {pct(wasCalled.after / wasCalled.before[0].coefficient - 1, 1)} ca poziție în
                  grilă. Nu e schimbarea salariului: valoarea de referință trece de la 2.500 lei la
                  4.100 lei, deci coeficienții măsoară locul în ierarhie, nu suma.
                </p>
              )}
              <p className="was-caveat">
                Nicio lege nu publică asimilarea. Art. 32 cere reîncadrarea fiecărui angajat, dar
                lasă decizia la fiecare ordonator de credite — deci legătura de mai sus e o
                reconstrucție după denumire și familie ocupațională, nu un drept.
              </p>
            </div>
          )}

          {chosen && chosen.variants.length > 1 && chosen.variants[0].dims && (
            <label className="field">
              <span>Gradul sau treapta</span>
              <select
                value={JSON.stringify(scenario.dims ?? chosen.variants[0].dims)}
                onChange={(e) => set({ dims: JSON.parse(e.target.value) })}
              >
                {chosen.variants.map((v, i) => (
                  <option key={i} value={JSON.stringify(v.dims ?? {})}>
                    {dimText(v.dims) || `varianta ${i + 1}`}
                  </option>
                ))}
              </select>
            </label>
          )}

          {primary && (
            <fieldset className="field">
              <legend>Sporuri revendicate</legend>
              <div className="claims">
                {primary.supplements.map((s) => (
                  <label key={s.id} className="claim">
                    <input
                      type="checkbox"
                      checked={(scenario.claims ?? []).some((c) => c.supplementId === s.id)}
                      onChange={() => toggleClaim(s.id)}
                    />
                    <span>
                      {s.name}
                      {s.mode === 'upTo' && <em> (până la)</em>}
                      {s.countsToCap === false && <em> · exceptat de la plafon</em>}
                      {s.countsToCap === 'partial' && <em> · parțial în plafon</em>}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
        </div>
      </section>

      {!person && (
        <section>
          <p className="lede">Alege o funcție ca să vezi calculul.</p>
        </section>
      )}

      {person && (
        <section>
          <h2>Calculul, regim cu regim</h2>
          {!comparable && slips.length > 1 && (
            <div className="disclaimer">
              <strong>Nu se compară cuantumuri între monede.</strong> Regimurile alese sunt
              exprimate în monede sau perioade diferite ({slips
                .map((s) => `${s.regime.currency} ${PERIOD_LABEL[s.slip.period]}`)
                .join(', ')}
              ). Coloanele stau una lângă alta, dar nu se scad. Comparația care rămâne validă este
              cea fără unități, de mai jos.
            </div>
          )}
          <div className="slips">
            {slips.map(({ regime, position, slip }) => (
              <PayslipCard key={regime.id} regime={regime} position={position} slip={slip} rates={rates} />
            ))}
          </div>
        </section>
      )}

      {person && priced.length > 1 && (
        <section>
          <h2>Comparație fără unități</h2>
          <p className="lede">
            Singura comparație validă între regimuri exprimate în monede diferite: proporții, nu
            sume. Ce parte din brut e salariul de bază, cât adaugă sporurile, cât rămâne net, cât
            costă angajatorul peste brut.
          </p>
          <div className="card chart-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Raport</th>
                  {priced.map((s) => (
                    <th key={s.regime.id}>{s.regime.name.split('(')[0].trim()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Salariul de bază din brut</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.gross ? pct(s.slip.base / s.slip.gross) : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Sporuri din brut</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.gross
                        ? pct(s.slip.supplements.reduce((a, l) => a + l.amount, 0) / s.slip.gross)
                        : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Net din brut</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.net === null ? 'nu se poate calcula' : pct(s.slip.net / s.slip.gross)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Costul angajatorului peste brut</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.gross ? pct(s.slip.employerCost / s.slip.gross - 1) : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Sporul de vechime față de gradația 0</td>
                  {priced.map((s) => (
                    <td key={s.regime.id} className="num">
                      {s.slip.seniority.bakedIn ? 'inclus în coeficient' : pct(s.slip.seniority.factor - 1)}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
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
}: {
  regime: Regime;
  position: Position | null;
  slip: Payslip;
  rates: Rates;
}) {
  const cur = (m: number) => amountLine(m / 100, slip.currency, rates);
  const supplements = slip.supplements.filter((l) => l.amount > 0 || l.suppressedBy);

  if (!position) {
    return (
      <div className="card slip">
        <h3>{regime.name.split('(')[0].trim()}</h3>
        <p className="missing">
          Funcția nu are un cod în acest regim — cele două sisteme nu folosesc același nomenclator.
          Echivalările dintre ele, cu sumele convertite și cu denumirea pe care ar folosi-o piața
          muncii, sunt în <a href="#/echivalente">Echivalențe RO–DK</a>.
        </p>
      </div>
    );
  }

  return (
    <div className="card slip">
      <h3>{regime.name.split('(')[0].trim()}</h3>
      <p className="slip-meta">
        {position.name} · {slip.currency} {PERIOD_LABEL[slip.period]}
      </p>

      <Composition slip={slip} />

      <table className="data">
        <tbody>
          <tr>
            <td>Salariu de bază</td>
            <td className="num">{cur(slip.base)}</td>
          </tr>
          {!slip.seniority.bakedIn && slip.seniority.amount !== 0 && (
            <tr className="sub">
              <td>din care vechime ({slip.seniority.stepId})</td>
              <td className="num">{cur(slip.seniority.amount)}</td>
            </tr>
          )}
          {supplements.map((line) => (
            <tr key={line.id} className={line.suppressedBy ? 'struck' : undefined}>
              <td>
                {line.name}
                {line.allowedRate !== null && <> · {pct(line.allowedRate, 1)}</>}
                {line.suppressedBy && <em> — exclus de „{line.suppressedBy}”</em>}
              </td>
              <td className="num">{cur(line.amount)}</td>
            </tr>
          ))}
          <tr className="total">
            <td>Brut</td>
            <td className="num">{cur(slip.gross)}</td>
          </tr>
          <tr>
            <td>Net</td>
            <td className="num">
              {slip.net === null ? <span className="missing-inline">nu se calculează</span> : cur(slip.net)}
            </td>
          </tr>
          <tr>
            <td>Cost total angajator</td>
            <td className="num">{cur(slip.employerCost)}</td>
          </tr>
          {slip.pensionSplit && (
            <tr className="sub">
              <td>pensie: angajat / angajator</td>
              <td className="num">
                {cur(slip.pensionSplit.employee)} / {cur(slip.pensionSplit.employer)}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {slip.capUtilisation.map((cap) => (
        <div key={cap.capId} className="cap">
          <div className="cap-head">
            <span>Plafonul de {pct(cap.limit, 0)}</span>
            <strong>{pct(cap.ratio)}</strong>
          </div>
          <div className="meter" role="img" aria-label={`utilizare ${pct(cap.ratio)}`}>
            <div
              className="meter-fill"
              style={{ width: `${Math.min((cap.ratio / Math.max(cap.limit, 0.0001)) * 100, 100)}%` }}
            />
          </div>
          <p className="cap-note">
            {cap.authoritative ? '' : 'Cifră notională. '}
            {cap.scopeNote}
          </p>
        </div>
      ))}

      {slip.diagnostics.length > 0 && (
        <details className="diags">
          <summary>{slip.diagnostics.length} observații despre acest calcul</summary>
          <ul>
            {slip.diagnostics.map((d, i) => (
              <li key={i} className={d.severity}>
                <span className="sev">{d.severity}</span> {d.message}
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
function Composition({ slip }: { slip: Payslip }) {
  const supplements = slip.supplements.reduce((sum, l) => sum + l.amount, 0);
  const pension = slip.pensionSplit?.total ?? 0;
  const total = slip.base + supplements + pension;
  if (total <= 0) return null;
  const w = (n: number) => `${(n / total) * 100}%`;
  const share = (n: number) => Math.round((n / total) * 100);

  return (
    <div className="slip-compose">
      <div className="compose-track" role="img" aria-label="din ce e compus brutul">
        <div className="compose-seg seg-base" style={{ width: w(slip.base) }} />
        {supplements > 0 && <div className="compose-seg seg-sup" style={{ width: w(supplements) }} />}
        {pension > 0 && <div className="compose-seg seg-pension" style={{ width: w(pension) }} />}
      </div>
      <div className="compose-key">
        <span>
          <i className="seg-base" /> bază {share(slip.base)}%
        </span>
        {supplements > 0 && (
          <span>
            <i className="seg-sup" /> sporuri {share(supplements)}%
          </span>
        )}
        {pension > 0 && (
          <span>
            <i className="seg-pension" /> pensie {share(pension)}%
          </span>
        )}
      </div>
    </div>
  );
}

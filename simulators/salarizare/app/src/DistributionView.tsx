import { useMemo } from 'react';

import { distribution } from '../../engine/distribution';
import type { Crosswalk, Regime } from '../../engine/types';

const FAMILY_LABELS: Record<string, string> = {
  'I-invatamant': 'Învățământ',
  'II-sanatate-asistenta-sociala': 'Sănătate și asistență socială',
  'III-cultura': 'Cultură',
  'IV-diplomatie': 'Diplomație',
  'V-justitie': 'Justiție',
  'VI-aparare-ordine-securitate': 'Apărare, ordine publică, securitate',
  'VII-administratie-culte': 'Culte',
  'VIII-administratie': 'Administrație',
  'IX-demnitati': 'Demnități publice',
};

/** Below this a family's median is one or two posts, which is an anecdote, not a finding. */
const MIN_FOR_A_CLAIM = 5;

const pct = (n: number, digits = 0) =>
  `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: digits })}%`;
const move = (ratio: number) =>
  `${ratio >= 1 ? '+' : ''}${((ratio - 1) * 100).toLocaleString('ro-RO', {
    maximumFractionDigits: 1,
  })}%`;

/**
 * The reform seen across every post that could be matched, rather than one at a time.
 *
 * The payslip can always be pointed at the job that makes someone's case. This page is
 * the answer to that: the same question asked of the whole matched grid, with the count
 * behind every claim visible so a family represented by one post cannot masquerade as a
 * trend.
 */
export default function DistributionView({
  inForce,
  draft,
  crosswalk,
}: {
  inForce: Regime | null;
  draft: Regime;
  crosswalk: Crosswalk;
}) {
  const d = useMemo(
    () => (inForce ? distribution(inForce, draft, crosswalk) : null),
    [inForce, draft, crosswalk],
  );

  if (!d) return <p className="loading">Se încarcă legea în vigoare…</p>;

  const flat = d.bands.find((b) => b.direction === 0)?.share ?? 0;
  const gaining = d.bands
    .filter((b) => b.direction === 1)
    .reduce((sum, b) => sum + b.share, 0);
  const widest = Math.max(...d.bands.map((b) => b.share), 0.01);
  const sorted = [...d.moves].sort((a, b) => a.ratio - b.ratio);
  const falls = sorted.slice(0, 6);
  const rises = sorted.slice(-6).reverse();

  return (
    <>
      <header className="masthead">
        <h1>Cine urcă și cine coboară</h1>
        <p>
          Fiecare post care a putut fi regăsit în ambele legi, comparat cu el însuși. Nu este
          schimbarea salariului, ci a locului în ierarhie: valoarea de referință trece de la 2.500
          lei la 4.100 lei, deci coeficienții spun cine urcă față de ceilalți, nu cât ia cineva.
        </p>
      </header>

      <div className="disclaimer">
        <strong>Media aproape nu se mișcă. Aproape toată lumea se mișcă.</strong> Postul din mijloc
        își păstrează locul ({move(d.median)}), dar numai {pct(flat)} dintre posturi rămân efectiv
        pe loc. {pct(d.losing)} coboară și {pct(gaining)} urcă. O reformă care ar lăsa ierarhia
        neatinsă ar arăta invers: o singură bară, în mijloc.
      </div>

      <section>
        <h2>Cât se mișcă posturile</h2>
        <div className="card">
          <div className="dist">
            {d.bands.map((band) => (
              <div className="dist-col" key={band.id}>
                <span className="dist-count">{band.count}</span>
                <div
                  className={`dist-bar dir${band.direction}`}
                  style={{ height: `${(band.share / widest) * 100}%` }}
                  title={`${band.label}: ${band.count} posturi`}
                />
                <span className="dist-label">{band.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <h2>Pe familii ocupaționale</h2>
        <p className="lede">
          Ordonate după cât de mult coboară. Numărul de posturi regăsite e scris lângă fiecare,
          fiindcă o familie cu două posturi nu susține nicio concluzie.
        </p>
        <div className="card">
          {d.byFamily.map((f) => {
            const thin = f.moves < MIN_FOR_A_CLAIM;
            return (
              <div className="fam-row" key={f.family}>
                <div className="fam-name">
                  {FAMILY_LABELS[f.family] ?? f.family}
                  <small>
                    {f.moves} {f.moves === 1 ? 'post regăsit' : 'posturi regăsite'}
                    {thin && ' — prea puține pentru o concluzie'}
                  </small>
                </div>
                <div className="fam-track">
                  {/* Zero sits in the middle, so a fall reads as a fall. */}
                  <div className="fam-zero" />
                  <div
                    className={`fam-bar ${f.median < 1 ? 'down' : 'up'}${thin ? ' thin' : ''}`}
                    style={{
                      left: f.median < 1 ? `${50 - Math.min((1 - f.median) * 250, 50)}%` : '50%',
                      width: `${Math.min(Math.abs(f.median - 1) * 250, 50)}%`,
                    }}
                  />
                </div>
                <div className={`fam-num ${f.median < 1 ? 'down' : 'up'}`}>
                  <b>{move(f.median)}</b>
                  <small>{pct(f.losing)} coboară</small>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h2>Cele mai mari mișcări</h2>
        <div className="card chart-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Postul</th>
                <th>Familia</th>
                <th className="num">Coeficient azi</th>
                <th className="num">În proiect</th>
                <th className="num">Mișcare</th>
              </tr>
            </thead>
            <tbody>
              {[...falls, ...rises].map((m) => (
                <tr key={m.code}>
                  <td>
                    {m.title.length > 52 ? `${m.title.slice(0, 51)}…` : m.title}
                    {m.confidence === 'assumed' && <em className="occ-caphint"> · potrivire presupusă</em>}
                  </td>
                  <td>{FAMILY_LABELS[m.family] ?? m.family}</td>
                  <td className="num">{m.before.toLocaleString('ro-RO')}</td>
                  <td className="num">{m.after.toLocaleString('ro-RO')}</td>
                  <td className={`num ${m.ratio < 1 ? 'fall' : 'rise'}`}>{move(m.ratio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Diferența salarială tranzitorie (Art. 33)</h2>
        <p className="lede">
          Art. 33 păstrează venitul din noiembrie 2026 acolo unde noua plată ar fi mai mică. Dacă
          prinde pe cineva nu se poate calcula — România nu publică venituri individuale — dar
          jumătate din întrebare se poate închide.
        </p>
        <div className="card">
          <div className="comp-hero">
            <span className="big">{d.transition.below}</span>
            <p>
              Atâtea posturi dintre cele {d.coverage.priced} regăsite ar avea salariul de bază mai
              mic în proiect decât în grila legii în vigoare. Valoarea de referință urcă de la{' '}
              {d.transition.oldReference.toLocaleString('ro-RO')} la{' '}
              {d.transition.newReference.toLocaleString('ro-RO')} lei, deci un post iese în pierdere
              doar dacă scade în ierarhie sub {pct(d.transition.breakeven, 1)} din locul lui de azi.
              Cea mai mare cădere observată se oprește la {pct(d.transition.worstRatio, 1)}.
            </p>
          </div>
        </div>
        <div className="limits" style={{ marginTop: 14 }}>
          <div className="limit blocking">
            <div className="sev">blocant</div>
            <p>
              Asta <strong>nu</strong> înseamnă că nu pierde nimeni. Comparația de mai sus e cu
              grila pentru 2022 tipărită în anexele legii în vigoare, nu cu ce se plătește în
              noiembrie 2026: peste acele sume s-au aplicat majorări an de an, iar Art. 33 se uită
              la venitul total, cu sporuri cu tot. Ce se poate spune este că, la nivel de salariu de
              bază și față de grila din 2022, creșterea referinței acoperă chiar și cea mai mare
              cădere în ierarhie. Întrebarea propriu-zisă rămâne deschisă și nu poate fi închisă cu
              date publice.
            </p>
          </div>
        </div>
      </section>

      <section>
        <h2>Ce nu spune pagina asta</h2>
        <div className="limits">
          <div className="limit material">
            <div className="sev">de reținut</div>
            <p>
              Sunt {d.coverage.priced} posturi din cele {d.coverage.oldPositions.toLocaleString('ro-RO')} ale
              legii în vigoare — {pct(d.coverage.priced / d.coverage.oldPositions)}. Restul nu au
              putut fi regăsite după denumire, ceea ce nu înseamnă că au fost desființate. Iar{' '}
              {d.coverage.grouped} legături unesc mai multe posturi pe o parte și nu au un „înainte“
              și un „după“ unic, deci nu apar aici.
            </p>
          </div>
          <div className="limit material">
            <div className="sev">de reținut</div>
            <p>
              Coeficientul e poziția în ierarhie, nu suma. Cu referința urcând de la 2.500 la 4.100
              lei, un post care coboară cu 10% în coeficient poate primi mai mulți lei decât acum.
              Pagina spune cine urcă <em>față de ceilalți</em>.
            </p>
          </div>
          <div className="limit note">
            <div className="sev">de reținut</div>
            <p>
              Asimilarea nu e publicată de nicio lege: Art. 32 cere reîncadrarea, dar lasă decizia
              fiecărui ordonator de credite. Legăturile sunt reconstruite după denumire și familie,
              iar cele marcate „potrivire presupusă“ au fost făcute după eliminarea gradului și a
              nivelului de studii.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}

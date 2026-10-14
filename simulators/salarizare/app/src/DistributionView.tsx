import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Table } from '@cristiannichifor/civic-ui';

import { distribution } from '../../engine/distribution';
import type { Crosswalk, Regime } from '../../engine/types';
import type { Lang } from './i18n';

const FAMILY_LABELS: Record<Lang, Record<string, string>> = {
  ro: {
    'I-invatamant': 'Învățământ',
    'II-sanatate-asistenta-sociala': 'Sănătate și asistență socială',
    'III-cultura': 'Cultură',
    'IV-diplomatie': 'Diplomație',
    'V-justitie': 'Justiție',
    'VI-aparare-ordine-securitate': 'Apărare, ordine publică, securitate',
    'VII-administratie-culte': 'Culte',
    'VIII-administratie': 'Administrație',
    'IX-demnitati': 'Demnități publice',
  },
  en: {
    'I-invatamant': 'Education',
    'II-sanatate-asistenta-sociala': 'Health and social care',
    'III-cultura': 'Culture',
    'IV-diplomatie': 'Diplomacy',
    'V-justitie': 'Justice',
    'VI-aparare-ordine-securitate': 'Defence, public order, security',
    'VII-administratie-culte': 'Religious affairs',
    'VIII-administratie': 'Administration',
    'IX-demnitati': 'Public office',
  },
};

/** Below this a family's median is one or two posts, which is an anecdote, not a finding. */
const MIN_FOR_A_CLAIM = 5;

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface DistributionStrings {
  loading: string;
  title: string;
  lead: string;
  summary: (median: string, flat: string, losing: string, gaining: string) => ReactNode;
  howMuch: string;
  bandTitle: (label: string, count: number) => string;
  byFamily: string;
  byFamilyLede: string;
  matched: (count: number) => string;
  tooFew: string;
  fall: (share: string) => string;
  biggestMoves: string;
  movesTable: string;
  colPost: string;
  colFamily: string;
  colToday: string;
  colDraft: string;
  colMove: string;
  assumedMatch: string;
  transitionTitle: string;
  transitionLede: string;
  transitionHero: (priced: string, oldRef: string, newRef: string, breakeven: string, worst: string) => string;
  blocking: string;
  transitionCaveat: ReactNode;
  notSaid: string;
  keepInMind: string;
  coverage: (priced: string, oldPositions: string, share: string, grouped: string) => ReactNode;
  rankNotSum: ReactNode;
  assimilation: ReactNode;
}

export const DISTRIBUTION_STRINGS: Record<Lang, DistributionStrings> = {
  ro: {
    loading: 'Se încarcă legea în vigoare…',
    title: 'Cine urcă și cine coboară',
    lead:
      'Fiecare post care a putut fi regăsit în ambele legi, comparat cu el însuși. Nu este schimbarea salariului, ci a locului în ierarhie: valoarea de referință trece de la 2.500 lei la 4.100 lei, deci coeficienții spun cine urcă față de ceilalți, nu cât ia cineva.',
    summary: (median, flat, losing, gaining) => (
      <>
        <strong>Media aproape nu se mișcă. Aproape toată lumea se mișcă.</strong> Postul din mijloc
        își păstrează locul ({median}), dar numai {flat} dintre posturi rămân efectiv pe loc.{' '}
        {losing} coboară și {gaining} urcă. O reformă care ar lăsa ierarhia neatinsă ar arăta
        invers: o singură bară, în mijloc.
      </>
    ),
    howMuch: 'Cât se mișcă posturile',
    bandTitle: (label, count) => `${label}: ${count} posturi`,
    byFamily: 'Pe familii ocupaționale',
    byFamilyLede:
      'Ordonate după cât de mult coboară. Numărul de posturi regăsite e scris lângă fiecare, fiindcă o familie cu două posturi nu susține nicio concluzie.',
    matched: (count) => `${count} ${count === 1 ? 'post regăsit' : 'posturi regăsite'}`,
    tooFew: ' — prea puține pentru o concluzie',
    fall: (share) => `${share} coboară`,
    biggestMoves: 'Cele mai mari mișcări',
    movesTable: 'Distribuția schimbărilor pe familii',
    colPost: 'Postul',
    colFamily: 'Familia',
    colToday: 'Coeficient azi',
    colDraft: 'În proiect',
    colMove: 'Mișcare',
    assumedMatch: ' · potrivire presupusă',
    transitionTitle: 'Diferența salarială tranzitorie (Art. 33)',
    transitionLede:
      'Art. 33 păstrează venitul din noiembrie 2026 acolo unde noua plată ar fi mai mică. Dacă prinde pe cineva nu se poate calcula — România nu publică venituri individuale — dar jumătate din întrebare se poate închide.',
    transitionHero: (priced, oldRef, newRef, breakeven, worst) =>
      `Atâtea posturi dintre cele ${priced} regăsite ar avea salariul de bază mai mic în proiect decât în grila legii în vigoare. Valoarea de referință urcă de la ${oldRef} la ${newRef} lei, deci un post iese în pierdere doar dacă scade în ierarhie sub ${breakeven} din locul lui de azi. Cea mai mare cădere observată se oprește la ${worst}.`,
    blocking: 'blocant',
    transitionCaveat: (
      <>
        Asta <strong>nu</strong> înseamnă că nu pierde nimeni. Comparația de mai sus e cu grila pentru
        2022 tipărită în anexele legii în vigoare, nu cu ce se plătește în noiembrie 2026: peste acele
        sume s-au aplicat majorări an de an, iar Art. 33 se uită la venitul total, cu sporuri cu tot.
        Ce se poate spune este că, la nivel de salariu de bază și față de grila din 2022, creșterea
        referinței acoperă chiar și cea mai mare cădere în ierarhie. Întrebarea propriu-zisă rămâne
        deschisă și nu poate fi închisă cu date publice.
      </>
    ),
    notSaid: 'Ce nu spune pagina asta',
    keepInMind: 'de reținut',
    coverage: (priced, oldPositions, share, grouped) => (
      <>
        Sunt {priced} posturi din cele {oldPositions} ale legii în vigoare — {share}. Restul nu au
        putut fi regăsite după denumire, ceea ce nu înseamnă că au fost desființate. Iar {grouped}{' '}
        legături unesc mai multe posturi pe o parte și nu au un „înainte“ și un „după“ unic, deci nu
        apar aici.
      </>
    ),
    rankNotSum: (
      <>
        Coeficientul e poziția în ierarhie, nu suma. Cu referința urcând de la 2.500 la 4.100 lei, un
        post care coboară cu 10% în coeficient poate primi mai mulți lei decât acum. Pagina spune cine
        urcă <em>față de ceilalți</em>.
      </>
    ),
    assimilation: (
      <>
        Asimilarea nu e publicată de nicio lege: Art. 32 cere reîncadrarea, dar lasă decizia fiecărui
        ordonator de credite. Legăturile sunt reconstruite după denumire și familie, iar cele marcate
        „potrivire presupusă“ au fost făcute după eliminarea gradului și a nivelului de studii.
      </>
    ),
  },
  en: {
    loading: 'Loading the law in force…',
    title: 'Who rises and who falls',
    lead:
      'Every post that could be found in both laws, compared with itself. This is not the change in pay but in place within the hierarchy: the reference value moves from 2,500 lei to 4,100 lei, so the coefficients say who rises against the others, not what anyone earns.',
    summary: (median, flat, losing, gaining) => (
      <>
        <strong>The average barely moves. Almost everyone moves.</strong> The post in the middle
        keeps its place ({median}), yet only {flat} of posts actually stay put. {losing} fall and{' '}
        {gaining} rise. A reform that left the hierarchy untouched would look the other way round:
        a single bar, in the middle.
      </>
    ),
    howMuch: 'How much the posts move',
    bandTitle: (label, count) => `${label}: ${count} posts`,
    byFamily: 'By occupational family',
    byFamilyLede:
      'Ordered by how far they fall. The number of matched posts stands beside each, because a family of two posts supports no conclusion.',
    matched: (count) => `${count} ${count === 1 ? 'matched post' : 'matched posts'}`,
    tooFew: ': too few for a conclusion',
    fall: (share) => `${share} fall`,
    biggestMoves: 'The largest moves',
    movesTable: 'Distribution of the changes by family',
    colPost: 'Post',
    colFamily: 'Family',
    colToday: 'Coefficient today',
    colDraft: 'In the draft',
    colMove: 'Move',
    assumedMatch: ' · assumed match',
    transitionTitle: 'The transitional pay difference (Art. 33)',
    transitionLede:
      'Art. 33 preserves the November 2026 income wherever the new pay would be lower. Whether it catches anyone cannot be computed, since Romania publishes no individual incomes, but half of the question can be closed.',
    transitionHero: (priced, oldRef, newRef, breakeven, worst) =>
      `That many posts out of the ${priced} matched would have a lower base salary in the draft than in the grid of the law in force. The reference value rises from ${oldRef} to ${newRef} lei, so a post loses out only if it falls in the hierarchy below ${breakeven} of its place today. The largest fall observed stops at ${worst}.`,
    blocking: 'blocking',
    transitionCaveat: (
      <>
        This does <strong>not</strong> mean nobody loses. The comparison above is with the 2022 grid
        printed in the annexes of the law in force, not with what is paid in November 2026: raises
        have been applied on top of those sums year after year, and Art. 33 looks at total income,
        allowances included. What can be said is that, at base-salary level and against the 2022
        grid, the rise of the reference covers even the largest fall in the hierarchy. The question
        itself stays open and cannot be closed with public data.
      </>
    ),
    notSaid: 'What this page does not say',
    keepInMind: 'keep in mind',
    coverage: (priced, oldPositions, share, grouped) => (
      <>
        These are {priced} posts out of the {oldPositions} in the law in force: {share}. The rest
        could not be matched by title, which does not mean they were abolished. And {grouped} links
        join several posts on one side and have no single "before" and "after", so they do not appear
        here.
      </>
    ),
    rankNotSum: (
      <>
        The coefficient is the place in the hierarchy, not the sum. With the reference rising from
        2,500 to 4,100 lei, a post that falls 10% in coefficient may receive more lei than today. The
        page says who rises <em>against the others</em>.
      </>
    ),
    assimilation: (
      <>
        No law publishes the assimilation: Art. 32 requires regrading but leaves the decision to each
        budget holder. The links are rebuilt from title and family, and those marked "assumed match"
        were made after dropping the grade and the level of studies.
      </>
    ),
  },
};

/**
 * The reform seen across every post that could be matched, rather than one at a time.
 *
 * The payslip can always be pointed at the job that makes someone's case. This page is
 * the answer to that: the same question asked of the whole matched grid, with the count
 * behind every claim visible so a family represented by one post cannot masquerade as a
 * trend.
 */
export default function DistributionView({
  menu,
  inForce,
  draft,
  crosswalk,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  inForce: Regime | null;
  draft: Regime;
  crosswalk: Crosswalk;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = DISTRIBUTION_STRINGS[lang];
  const locale = LOCALE[lang];
  const families = FAMILY_LABELS[lang];
  const n = (value: number) => value.toLocaleString(locale);
  const pct = (value: number, digits = 0) =>
    `${(value * 100).toLocaleString(locale, { maximumFractionDigits: digits })}%`;
  const move = (ratio: number) =>
    `${ratio >= 1 ? '+' : ''}${((ratio - 1) * 100).toLocaleString(locale, {
      maximumFractionDigits: 1,
    })}%`;

  const d = useMemo(
    () => (inForce ? distribution(inForce, draft, crosswalk) : null),
    [inForce, draft, crosswalk],
  );

  if (!d) return <p className="loading">{t.loading}</p>;

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
        <h1>{t.title}</h1>
        <p>{t.lead}</p>
      </header>
      {menu}

      <div className="disclaimer">{t.summary(move(d.median), pct(flat), pct(d.losing), pct(gaining))}</div>

      <section>
        <h2>{t.howMuch}</h2>
        <div className="card">
          <div className="dist">
            {d.bands.map((band) => (
              <div className="dist-col" key={band.id}>
                <span className="dist-count">{band.count}</span>
                <div
                  className={`dist-bar dir${band.direction}`}
                  style={{ height: `${(band.share / widest) * 100}%` }}
                  title={t.bandTitle(band.label, band.count)}
                />
                <span className="dist-label">{band.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <h2>{t.byFamily}</h2>
        <p className="lede">{t.byFamilyLede}</p>
        <div className="card">
          {d.byFamily.map((f) => {
            const thin = f.moves < MIN_FOR_A_CLAIM;
            return (
              <div className="fam-row" key={f.family}>
                <div className="fam-name">
                  {families[f.family] ?? f.family}
                  <small>
                    {t.matched(f.moves)}
                    {thin && t.tooFew}
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
                  <small>{t.fall(pct(f.losing))}</small>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h2>{t.biggestMoves}</h2>
        <div className="card">
          <Table className="data" label={t.movesTable}>
            <thead>
              <tr>
                <th>{t.colPost}</th>
                <th>{t.colFamily}</th>
                <th className="num">{t.colToday}</th>
                <th className="num">{t.colDraft}</th>
                <th className="num">{t.colMove}</th>
              </tr>
            </thead>
            <tbody>
              {[...falls, ...rises].map((m) => (
                <tr key={m.code}>
                  <td>
                    {m.title.length > 52 ? `${m.title.slice(0, 51)}…` : m.title}
                    {m.confidence === 'assumed' && <em className="occ-caphint">{t.assumedMatch}</em>}
                  </td>
                  <td>{families[m.family] ?? m.family}</td>
                  <td className="num">{n(m.before)}</td>
                  <td className="num">{n(m.after)}</td>
                  <td className={`num ${m.ratio < 1 ? 'fall' : 'rise'}`}>{move(m.ratio)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      </section>

      <section>
        <h2>{t.transitionTitle}</h2>
        <p className="lede">{t.transitionLede}</p>
        <div className="card">
          <div className="comp-hero">
            <span className="big">{d.transition.below}</span>
            <p>
              {t.transitionHero(
                n(d.coverage.priced),
                n(d.transition.oldReference),
                n(d.transition.newReference),
                pct(d.transition.breakeven, 1),
                pct(d.transition.worstRatio, 1),
              )}
            </p>
          </div>
        </div>
        <div className="limits" style={{ marginTop: 14 }}>
          <div className="limit blocking">
            <div className="sev">{t.blocking}</div>
            <p>{t.transitionCaveat}</p>
          </div>
        </div>
      </section>

      <section>
        <h2>{t.notSaid}</h2>
        <div className="limits">
          <div className="limit material">
            <div className="sev">{t.keepInMind}</div>
            <p>
              {t.coverage(
                n(d.coverage.priced),
                n(d.coverage.oldPositions),
                pct(d.coverage.priced / d.coverage.oldPositions),
                n(d.coverage.grouped),
              )}
            </p>
          </div>
          <div className="limit material">
            <div className="sev">{t.keepInMind}</div>
            <p>{t.rankNotSum}</p>
          </div>
          <div className="limit note">
            <div className="sev">{t.keepInMind}</div>
            <p>{t.assimilation}</p>
          </div>
        </div>
      </section>
    </>
  );
}

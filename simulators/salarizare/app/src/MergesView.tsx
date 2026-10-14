import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { PositionName } from './names';
import { Button, Checkbox, Field, Input, NativeSelect, Table } from '@cristiannichifor/civic-ui';

import { byFanIn, mergeCards } from '../../engine/merges';
import type { MergeCard } from '../../engine/merges';
import type { DkOccupation, GroupsDocument } from '../../engine/occupations';
import type { Scenario } from '../../engine/scenario';
import type { Crosswalk, Regime } from '../../engine/types';
import type { Lang } from './i18n';
import { amountLine } from './money';
import type { Rates } from './money';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface MergesStrings {
  title: string;
  purpose: string;
  kpiPositions: string;
  kpiMerged: string;
  kpiWithOld: string;
  kpiWithOldNote: string;
  kpiWithDk: string;
  kpiWithDkNote: string;
  searchLabel: string;
  searchPlaceholder: string;
  familyLabel: string;
  allFamilies: (n: string) => string;
  onlyMerged: string;
  found: (n: string) => string;
  showingFirst: (n: string) => string;
  sumsNote: string;
  more: (n: string) => string;
  fanInTitle: string;
  fanIn: (n: number) => string;
  codeTitle: string;
  tableLabel: (name: string) => string;
  rows: {
    inForce: string;
    inForceMissing: string;
    draft: string;
    draftMissing: string;
    ours: string;
    oursMissing: string;
    denmark: string;
    denmarkMissing: string;
    occupationMedian: string;
    delta: string;
  };
  titlesSummary: (n: number) => string;
  parseNote: (parse: string) => string;
  wasCalledSummary: (n: number) => string;
}

export const MERGES_STRINGS: Record<Lang, MergesStrings> = {
  ro: {
    title: 'Fiecare funcție, cu numele pe care le-a înghițit',
    purpose:
      'Proiectul comasează denumiri: o funcție din grila nouă poate să adune sub ea zece titluri vechi. Un tabel nu poate arăta asta, fiindcă tabelul are deja o singură denumire pe rând. Aici fiecare funcție este o fișă, cu titlurile pe care le-a absorbit și cu banii pe care fiecare sistem îi pune pe aceeași muncă.',
    kpiPositions: 'funcții în grila nouă',
    kpiMerged: 'adună sub ele mai multe denumiri',
    kpiWithOld: 'au un corespondent în legea în vigoare',
    kpiWithOldNote: 'restul nu au: echivalarea cerută de art. 32 nu a fost publicată niciodată',
    kpiWithDk: 'au o cifră daneză comparabilă',
    kpiWithDkNote: 'Danemarca nu are grilă; salariul e măsurat pe ocupație, iar ocupația e mai largă decât funcția',
    searchLabel: 'Caută o denumire',
    searchPlaceholder: 'asistent, referent, șofer…',
    familyLabel: 'Familia ocupațională',
    allFamilies: (n) => `toate (${n})`,
    onlyMerged: 'doar funcțiile care chiar comasează',
    found: (n) => `${n} funcții găsite`,
    showingFirst: (n) => ` — se arată primele ${n}`,
    sumsNote:
      '. Sumele sunt salariul de bază la vechime zero, trecut prin același calcul ca restul paginilor: se compară lei cu lei, nu coeficient cu coeficient, fiindcă cele trei sisteme nu au aceeași valoare de referință.',
    more: (n) => `Încă ${n} funcții`,
    fanInTitle: 'câte denumiri s-au strâns în această funcție',
    fanIn: (n) => `${n} denumiri`,
    codeTitle: 'codul poziției în anexa sursă',
    tableLabel: (name) => `Comparație salarială: ${name}`,
    rows: {
      inForce: 'În vigoare (153/2017)',
      inForceMissing: 'fără echivalare publicată',
      draft: 'Proiectul',
      draftMissing: 'nepublicat',
      ours: 'Propunerea noastră',
      oursMissing: 'neatinsă de propunere',
      denmark: 'Danemarca',
      denmarkMissing: 'în afara grupelor ocupaționale',
      occupationMedian: 'mediana ocupației',
      delta: 'Ce schimbă propunerea',
    },
    titlesSummary: (n) => `Denumirile strânse aici (${n})`,
    parseNote: (parse) =>
      `Celula sursă a fost citită ca „${parse}”. Dacă despărțirea e greșită, greșit e și numărul de denumiri — de aceea scrie aici cum a fost citită.`,
    wasCalledSummary: (n) => `Cum se numea sub legea în vigoare (${n})`,
  },
  en: {
    title: 'Every position, with the names it swallowed',
    purpose:
      'The draft merges titles: one position in the new grid can gather ten old titles under it. A table cannot show that, because a table already has a single title per row. Here every position is a card, with the titles it absorbed and the money each system puts on the same work.',
    kpiPositions: 'positions in the new grid',
    kpiMerged: 'gather several titles under them',
    kpiWithOld: 'have a counterpart in the law in force',
    kpiWithOldNote: 'the rest do not: the mapping required by Art. 32 was never published',
    kpiWithDk: 'have a comparable Danish figure',
    kpiWithDkNote: 'Denmark has no grid; pay is measured by occupation, and the occupation is wider than the position',
    searchLabel: 'Search for a title',
    searchPlaceholder: 'asistent, referent, șofer…',
    familyLabel: 'Occupational family',
    allFamilies: (n) => `all (${n})`,
    onlyMerged: 'only the positions that actually merge',
    found: (n) => `${n} positions found`,
    showingFirst: (n) => ` — showing the first ${n}`,
    sumsNote:
      '. The amounts are base pay at zero seniority, put through the same computation as the rest of the pages: lei are compared with lei, not coefficient with coefficient, because the three systems do not share a reference value.',
    more: (n) => `${n} more positions`,
    fanInTitle: 'how many titles were gathered into this position',
    fanIn: (n) => `${n} titles`,
    codeTitle: 'the position code in the source annex',
    tableLabel: (name) => `Pay comparison: ${name}`,
    rows: {
      inForce: 'In force (153/2017)',
      inForceMissing: 'no published mapping',
      draft: 'The draft',
      draftMissing: 'unpublished',
      ours: 'Our proposal',
      oursMissing: 'untouched by the proposal',
      denmark: 'Denmark',
      denmarkMissing: 'outside the occupation groups',
      occupationMedian: 'occupation median',
      delta: 'What the proposal changes',
    },
    titlesSummary: (n) => `The titles gathered here (${n})`,
    parseNote: (parse) =>
      `The source cell was read as "${parse}". If the split is wrong, so is the number of titles — which is why how it was read is written here.`,
    wasCalledSummary: (n) => `What it was called under the law in force (${n})`,
  },
};

/**
 * Every job as a card: the titles it swallowed, and what three systems pay for it.
 *
 * The grid is 1 031 rows and its central claim — that a great many titles were the same
 * work — is invisible in a table, because a table shows one name per row and the merge
 * happened before the row existed. A card can show the collapse itself: the job at the
 * top, the eleven former titles underneath it, and the money each system attaches to that
 * one job.
 *
 * **Sorted by how much collapsed, not alphabetically.** A reader who arrives here wants
 * the merges, and the biggest ones are the ones most likely to be wrong — eleven titles
 * folded onto one salary is either the finding or the error, and either way it is what
 * should be on screen first.
 *
 * **Four columns, some of them empty.** In force, the draft, our proposal, Denmark. A
 * missing column is a missing document, and it is drawn as missing: the Art. 32 mapping
 * from the old law was never published, so most positions have no predecessor to price,
 * and Denmark has no grid at all — what exists there is measured pay by occupation, which
 * reaches a job only through the occupation groups. Neither absence is filled in.
 */
export default function MergesView({
  menu,
  draft,
  ours,
  inForce,
  crosswalk,
  groups,
  danish,
  rates,
  scenario,
  onScenario,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  draft: Regime;
  ours: Regime | null;
  inForce: Regime | null;
  crosswalk: Crosswalk | null;
  groups: GroupsDocument | null;
  danish: DkOccupation[];
  rates: Rates;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = MERGES_STRINGS[lang];
  const locale = LOCALE[lang];
  const n = (value: number) => value.toLocaleString(locale);

  const all = useMemo(
    () => byFanIn(mergeCards({ draft, ours, inForce, crosswalk, groups, danish })),
    [draft, ours, inForce, crosswalk, groups, danish],
  );

  // The filters live in the address bar like every other control here, so a card worth
  // arguing about is a link rather than a set of instructions for finding it again.
  const query = scenario.extra?.q ?? '';
  const family = scenario.extra?.fam ?? '';
  const onlyMerged = scenario.extra?.merged === '1';
  const limit = Number(scenario.extra?.n ?? 60);

  const setExtra = (patch: Record<string, string | undefined>) => {
    const extra = { ...(scenario.extra ?? {}) };
    for (const [key, value] of Object.entries(patch)) {
      if (value === undefined || value === '') delete extra[key];
      else extra[key] = value;
    }
    onScenario({ ...scenario, extra: Object.keys(extra).length ? extra : undefined });
  };

  const families = useMemo(
    () => [...new Set(all.map((c) => c.family))].sort((a, b) => a.localeCompare(b, 'ro')),
    [all],
  );

  const fold = (text: string) =>
    text
      .toLowerCase()
      .replace(/[șş]/g, 's')
      .replace(/[țţ]/g, 't')
      .replace(/[ăâ]/g, 'a')
      .replace(/î/g, 'i');

  const shown = useMemo(() => {
    const needle = fold(query.trim());
    return all.filter((card) => {
      if (family && card.family !== family) return false;
      if (onlyMerged && card.fanIn < 2) return false;
      if (!needle) return true;
      return (
        fold(card.name).includes(needle) ||
        card.titles.some((t) => fold(t).includes(needle)) ||
        card.wasCalled.some((t) => fold(t).includes(needle))
      );
    });
  }, [all, query, family, onlyMerged]);

  const merged = all.filter((c) => c.fanIn > 1).length;
  const withOld = all.filter((c) => c.inForce !== null).length;
  const withDk = all.filter((c) => c.dk !== null).length;

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.purpose}</p>
      </header>
      {menu}

      <div className="kpis">
        <div className="kpi">
          <div className="v">{n(all.length)}</div>
          <div className="k">{t.kpiPositions}</div>
        </div>
        <div className="kpi">
          <div className="v accent">{n(merged)}</div>
          <div className="k">{t.kpiMerged}</div>
        </div>
        <div className="kpi">
          <div className="v">{n(withOld)}</div>
          <div className="k">
            {t.kpiWithOld}
            <em className="merge-kpi-note">{t.kpiWithOldNote}</em>
          </div>
        </div>
        <div className="kpi">
          <div className="v">{n(withDk)}</div>
          <div className="k">
            {t.kpiWithDk}
            <em className="merge-kpi-note">{t.kpiWithDkNote}</em>
          </div>
        </div>
      </div>

      <div className="merges-controls">
        <div className="merge-filter civic-scope civic-pay">
          <Field id="merge-query" label={t.searchLabel}>
            {(attributes) => (
              <Input
                {...attributes}
                type="search"
                value={query}
                placeholder={t.searchPlaceholder}
                onChange={(e) => setExtra({ q: e.target.value })}
              />
            )}
          </Field>
        </div>
        <div className="merge-filter civic-scope civic-pay">
          <Field id="merge-family" label={t.familyLabel}>
            {(attributes) => (
              <NativeSelect {...attributes} value={family} onChange={(e) => setExtra({ fam: e.target.value })}>
                <option value="">{t.allFamilies(n(all.length))}</option>
                {families.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
        <div className="civic-scope civic-pay">
          <Checkbox
            className="claim"
            label={t.onlyMerged}
            checked={onlyMerged}
            onChange={() => setExtra({ merged: onlyMerged ? undefined : '1' })}
          />
        </div>
      </div>

      <p className="note">
        {t.found(n(shown.length))}
        {shown.length > limit && t.showingFirst(n(limit))}
        {t.sumsNote}
      </p>

      <div className="cards">
        {shown.slice(0, limit).map((card) => (
          <Card key={card.code} card={card} rates={rates} lang={lang} />
        ))}
      </div>

      {shown.length > limit && (
        <Button className="more" onClick={() => setExtra({ n: String(limit + 60) })}>
          {t.more(n(Math.min(60, shown.length - limit)))}
        </Button>
      )}
    </>
  );
}

function Card({ card, rates, lang }: { card: MergeCard; rates: Rates; lang: Lang }) {
  const t = MERGES_STRINGS[lang];
  const locale = LOCALE[lang];
  const ron = (m: number | null) => (m === null ? null : amountLine(m / 100, 'RON', rates, 'native', locale));
  const dkk = (v: number) => amountLine(v, 'DKK', rates, 'native', locale);

  return (
    <article className="card merge-card">
      <header>
        <h3>
          <PositionName name={card.name} />
        </h3>
        {card.fanIn > 1 && (
          <span className="badge" title={t.fanInTitle}>
            {t.fanIn(card.fanIn)}
          </span>
        )}
      </header>
      <p className="merge-meta">
        {card.family}
        {card.chapter && <> · {card.chapter}</>} ·{' '}
        <code title={t.codeTitle}>{card.code}</code>
      </p>

      <Table className="data" label={t.tableLabel(card.name)}>
        <tbody>
          <Row label={t.rows.inForce} value={ron(card.inForce)} missing={t.rows.inForceMissing} />
          <Row label={t.rows.draft} value={ron(card.draft)} missing={t.rows.draftMissing} />
          <Row label={t.rows.ours} value={ron(card.ours)} missing={t.rows.oursMissing} />
          {card.dk ? (
            <tr>
              <td>
                {t.rows.denmark} · {card.dk.occupation}
                <em> {t.rows.occupationMedian}</em>
              </td>
              <td className="num">{dkk(card.dk.median)}</td>
            </tr>
          ) : (
            <Row label={t.rows.denmark} value={null} missing={t.rows.denmarkMissing} />
          )}
          {card.delta && (
            <tr className={card.delta.amount >= 0 ? 'total more' : 'total less'}>
              <td>{t.rows.delta}</td>
              <td className="num">
                {/* One sign for the whole line. Writing it only in front of the lei made
                    "−17 RON · 3 EUR" read as though the euro figure had gone up. */}
                {card.delta.amount >= 0 ? '+' : '−'}
                {amountLine(Math.abs(card.delta.amount) / 100, 'RON', rates, 'native', locale)}
                <em>
                  {card.delta.share >= 0 ? '+' : '−'}
                  {Math.abs(card.delta.share * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}%
                </em>
              </td>
            </tr>
          )}
        </tbody>
      </Table>

      {card.titles.length > 1 && (
        <details className="merge-titles">
          <summary>{t.titlesSummary(card.titles.length)}</summary>
          <ul>
            {card.titles.map((title, i) => (
              <li key={i}>{title}</li>
            ))}
          </ul>
          {card.parse && <p className="note">{t.parseNote(card.parse)}</p>}
        </details>
      )}

      {card.wasCalled.length > 0 && (
        <details className="merge-titles">
          <summary>{t.wasCalledSummary(card.wasCalled.length)}</summary>
          <ul>
            {card.wasCalled.map((title, i) => (
              <li key={i}>{title}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

function Row({ label, value, missing }: { label: string; value: string | null; missing: string }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="num">{value ?? <span className="missing-inline">{missing}</span>}</td>
    </tr>
  );
}

import { useMemo } from 'react';

import { byFanIn, mergeCards } from '../../engine/merges';
import type { MergeCard } from '../../engine/merges';
import type { DkOccupation, GroupsDocument } from '../../engine/occupations';
import type { Scenario } from '../../engine/scenario';
import type { Crosswalk, Regime } from '../../engine/types';
import { amountLine } from './money';
import type { Rates } from './money';

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
  draft,
  ours,
  inForce,
  crosswalk,
  groups,
  danish,
  rates,
  scenario,
  onScenario,
}: {
  draft: Regime;
  ours: Regime | null;
  inForce: Regime | null;
  crosswalk: Crosswalk | null;
  groups: GroupsDocument | null;
  danish: DkOccupation[];
  rates: Rates;
  scenario: Scenario;
  onScenario: (next: Scenario) => void;
}) {
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
        <h1>Fiecare funcție, cu numele pe care le-a înghițit</h1>
        <p>
          Proiectul comasează denumiri: o funcție din grila nouă poate să adune sub ea zece
          titluri vechi. Un tabel nu poate arăta asta, fiindcă tabelul are deja o singură
          denumire pe rând. Aici fiecare funcție este o fișă, cu titlurile pe care le-a
          absorbit și cu banii pe care fiecare sistem îi pune pe aceeași muncă.
        </p>
      </header>

      <div className="kpis">
        <div className="kpi">
          <div className="v">{all.length.toLocaleString('ro-RO')}</div>
          <div className="k">funcții în grila nouă</div>
        </div>
        <div className="kpi">
          <div className="v accent">{merged.toLocaleString('ro-RO')}</div>
          <div className="k">adună sub ele mai multe denumiri</div>
        </div>
        <div className="kpi">
          <div className="v">{withOld.toLocaleString('ro-RO')}</div>
          <div className="k">
            au un corespondent în legea în vigoare
            <em className="merge-kpi-note">
              restul nu au: echivalarea cerută de art. 32 nu a fost publicată niciodată
            </em>
          </div>
        </div>
        <div className="kpi">
          <div className="v">{withDk.toLocaleString('ro-RO')}</div>
          <div className="k">
            au o cifră daneză comparabilă
            <em className="merge-kpi-note">
              Danemarca nu are grilă; salariul e măsurat pe ocupație, iar ocupația e mai largă
              decât funcția
            </em>
          </div>
        </div>
      </div>

      <div className="merges-controls">
        <label className="field">
          <span>Caută o denumire</span>
          <input
            type="search"
            value={query}
            placeholder="asistent, referent, șofer…"
            onChange={(e) => setExtra({ q: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Familia ocupațională</span>
          <select value={family} onChange={(e) => setExtra({ fam: e.target.value })}>
            <option value="">toate ({all.length})</option>
            {families.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label className="claim">
          <input
            type="checkbox"
            checked={onlyMerged}
            onChange={() => setExtra({ merged: onlyMerged ? undefined : '1' })}
          />
          <span>doar funcțiile care chiar comasează</span>
        </label>
      </div>

      <p className="note">
        {shown.length.toLocaleString('ro-RO')} funcții găsite
        {shown.length > limit && <> — se arată primele {limit.toLocaleString('ro-RO')}</>}.
        Sumele sunt salariul de bază la vechime zero, trecut prin același calcul ca restul
        paginilor: se compară lei cu lei, nu coeficient cu coeficient, fiindcă cele trei
        sisteme nu au aceeași valoare de referință.
      </p>

      <div className="cards">
        {shown.slice(0, limit).map((card) => (
          <Card key={card.code} card={card} rates={rates} />
        ))}
      </div>

      {shown.length > limit && (
        <button className="more" onClick={() => setExtra({ n: String(limit + 60) })}>
          Încă {Math.min(60, shown.length - limit)} funcții
        </button>
      )}
    </>
  );
}

function Card({ card, rates }: { card: MergeCard; rates: Rates }) {
  const ron = (m: number | null) =>
    m === null ? null : amountLine(m / 100, 'RON', rates);
  const dkk = (v: number) => amountLine(v, 'DKK', rates);

  return (
    <article className="card merge-card">
      <header>
        <h3>{card.name}</h3>
        {card.fanIn > 1 && (
          <span className="badge" title="câte denumiri s-au strâns în această funcție">
            {card.fanIn} denumiri
          </span>
        )}
      </header>
      <p className="merge-meta">
        {card.family}
        {card.chapter && <> · {card.chapter}</>} · {card.code}
      </p>

      <table className="data">
        <tbody>
          <Row label="În vigoare (153/2017)" value={ron(card.inForce)} missing="fără echivalare publicată" />
          <Row label="Proiectul" value={ron(card.draft)} missing="nepublicat" />
          <Row label="Propunerea noastră" value={ron(card.ours)} missing="neatinsă de propunere" />
          {card.dk ? (
            <tr>
              <td>
                Danemarca · {card.dk.occupation}
                <em> mediana ocupației</em>
              </td>
              <td className="num">{dkk(card.dk.median)}</td>
            </tr>
          ) : (
            <Row label="Danemarca" value={null} missing="în afara grupelor ocupaționale" />
          )}
          {card.delta && (
            <tr className={card.delta.amount >= 0 ? 'total more' : 'total less'}>
              <td>Ce schimbă propunerea</td>
              <td className="num">
                {/* One sign for the whole line. Writing it only in front of the lei made
                    "−17 RON · 3 EUR" read as though the euro figure had gone up. */}
                {card.delta.amount >= 0 ? '+' : '−'}
                {amountLine(Math.abs(card.delta.amount) / 100, 'RON', rates)}
                <em>
                  {card.delta.share >= 0 ? '+' : '−'}
                  {Math.abs(card.delta.share * 100).toLocaleString('ro-RO', {
                    maximumFractionDigits: 1,
                  })}
                  %
                </em>
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {card.titles.length > 1 && (
        <details className="merge-titles">
          <summary>Denumirile strânse aici ({card.titles.length})</summary>
          <ul>
            {card.titles.map((title, i) => (
              <li key={i}>{title}</li>
            ))}
          </ul>
          {card.parse && (
            <p className="note">
              Celula sursă a fost citită ca „{card.parse}”. Dacă despărțirea e greșită, greșit
              e și numărul de denumiri — de aceea scrie aici cum a fost citită.
            </p>
          )}
        </details>
      )}

      {card.wasCalled.length > 0 && (
        <details className="merge-titles">
          <summary>Cum se numea sub legea în vigoare ({card.wasCalled.length})</summary>
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

function Row({
  label,
  value,
  missing,
}: {
  label: string;
  value: string | null;
  missing: string;
}) {
  return (
    <tr>
      <td>{label}</td>
      <td className="num">
        {value ?? <span className="missing-inline">{missing}</span>}
      </td>
    </tr>
  );
}

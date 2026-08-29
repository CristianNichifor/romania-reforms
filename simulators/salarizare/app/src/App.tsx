import { useCallback, useEffect, useMemo, useState } from 'react';

import { payslip } from '../../engine/payslip';
import { applyProposal } from '../../engine/proposal';
import type { AppliedProposal, Proposal } from '../../engine/proposal';
import { decodeScenario, encodeScenario } from '../../engine/scenario';
import type { Scenario, ViewId } from '../../engine/scenario';
import type { EnvelopeBaseline } from '../../engine/envelope';
import type { CapSeries } from '../../engine/cap';
import type { MeasuredSeries } from '../../engine/measured';
import { asOfForYear, periodForYear, phaseYears, yearOfAsOf } from '../../engine/phase';
import type { Shares } from '../../engine/composition';
import type { DkOccupation, GroupsDocument } from '../../engine/occupations';
import type { Crosswalk, Regime } from '../../engine/types';
import CompareView from './CompareView';
import HomeView from './HomeView';
import DistributionView from './DistributionView';
import EnvelopeView from './EnvelopeView';
import OccupationsView from './OccupationsView';
import EquivalenceView from './EquivalenceView';
import PayslipView from './PayslipView';
import StructureView from './StructureView';

const AVAILABLE = ['ro-153-2017', 'ro-draft-2026-07-16', 'dk-stat-2026'];
const PROPOSAL_ID = 'propunere-v1';
const CROSSWALK_ID = 'ro-draft-2026-07-16--dk-stat-2026';
const ASSIMILATION_ID = 'ro-153-2017--ro-draft-2026-07-16';
const FX_ID = 'ecb-fx';
const BENCHMARKS_ID = 'benchmarks';
const FISCAL_ID = 'eurostat-compensation-2026-08';
const HEADCOUNT_ID = 'posturi-ocupate-2026-06';
const GROUPS_ID = 'ro-dk-occupations';
const DK_OCC_ID = 'dk-occupations';
const EXEC_ID = 'executie-personal';
const CAP_ID = 'plafon-sporuri';
const INS_ID = 'ins-ocupatii';

/**
 * Six views used to sit in one undifferentiated row, named after their mechanics —
 * "Comparație", "Forma sistemului", "Plicul". A reader could not tell which of them
 * answered the question they arrived with, and two of the names ("Meserii RO–DK",
 * "Echivalențe RO–DK") read as the same page twice.
 *
 * They are grouped by the question they answer instead, and each carries the sentence
 * that says what it will show. The grouping is the navigation: a citizen wants to know
 * what changes, what people are paid, and whether it is affordable — in that order.
 */
const VIEW_META: Record<ViewId, { label: string; blurb: string }> = {
  acasa: { label: 'Despre proiect', blurb: 'ce este, pe ce date stă, ce nu poate spune' },
  compare: { label: 'Ce se schimbă', blurb: 'proiectul, propunerea și Danemarca, față în față' },
  structure: { label: 'Cum e construită grila', blurb: 'zecimalele, golurile, funcțiile comasate' },
  distributie: {
    label: 'Cine urcă, cine coboară',
    blurb: 'cum se mișcă fiecare post față de legea de azi',
  },
  meserii: { label: 'Meserii, RO vs DK', blurb: 'cât ia aceeași meserie în fiecare țară' },
  payslip: { label: 'Un salariu, calculat', blurb: 'un om anume, sub fiecare regim' },
  echivalente: { label: 'Echivalențe de post', blurb: 'ce denumire daneză corespunde fiecărei funcții' },
  envelope: { label: 'Cât costă tot', blurb: 'plicul, plafonul de 20% și cine trece de el' },
};

/** Views whose numbers move as the draft phases itself in. */
const PHASED_VIEWS: ViewId[] = ['compare', 'structure', 'payslip'];

const NAV_GROUPS: Array<{ title: string; ask: string; views: ViewId[] }> = [
  { title: 'Începe aici', ask: 'Ce e asta?', views: ['acasa'] },
  { title: 'Reforma', ask: 'Ce se schimbă?', views: ['compare', 'distributie', 'structure'] },
  { title: 'Oamenii', ask: 'Cine cât ia?', views: ['meserii', 'payslip', 'echivalente'] },
  { title: 'Banii', ask: 'Ne permitem?', views: ['envelope'] },
];

/**
 * The hash is the state. There is no store: every control writes a scenario into
 * location.hash and the app renders whatever the hash says, so the back button works and
 * any view is a link someone can paste into an argument.
 */
function useHashScenario(): [Scenario, (next: Scenario) => void] {
  const [scenario, setScenario] = useState<Scenario>(() => decodeScenario(location.hash));

  useEffect(() => {
    const onHash = () => setScenario(decodeScenario(location.hash));
    addEventListener('hashchange', onHash);
    return () => removeEventListener('hashchange', onHash);
  }, []);

  const update = useCallback((next: Scenario) => {
    const hash = encodeScenario(next);
    if (hash !== location.hash) location.hash = hash;
    setScenario(next);
  }, []);

  return [scenario, update];
}

export default function App() {
  const [scenario, setScenario] = useHashScenario();
  const [regimes, setRegimes] = useState<Record<string, Regime>>({});
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [crosswalk, setCrosswalk] = useState<Crosswalk | null>(null);
  /** 153/2017 -> draft, so a payslip can say what the post used to be called. */
  const [assimilation, setAssimilation] = useState<Crosswalk | null>(null);
  const [fx, setFx] = useState<{ dkkToRon: number; eurToRon: number; date: string } | null>(null);
  const [benchmarks, setBenchmarks] = useState<{
    avgRo: number; avgDk: number; govRo: number; govDk: number;
    floorRo: number; floorDk: number; year: string;
  } | null>(null);
  const [envelopeBaseline, setEnvelopeBaseline] = useState<EnvelopeBaseline | null>(null);
  const [occGroups, setOccGroups] = useState<GroupsDocument | null>(null);
  const [dkOcc, setDkOcc] = useState<DkOccupation[] | null>(null);
  const [occBench, setOccBench] = useState<{ roMedianBase: number; dkMedian: number } | null>(null);
  /** What Romania actually paid, by budget chapter, keyed by the scope the importer used. */
  const [roComposition, setRoComposition] = useState<Record<string, Record<string, Shares>> | null>(null);
  /** The 20% ceiling measured per ordonator principal and per funding source. */
  const [capSeries, setCapSeries] = useState<CapSeries[] | null>(null);
  /** What INS measured people are actually paid, for education and health. */
  const [measured, setMeasured] = useState<MeasuredSeries[] | null>(null);

  const wanted = scenario.regimeIds;

  // The draft walks its own grid from 2026/2027 to 2031, so "the ratio is 1:8" and "the
  // ratio is 1:7,39" are both true and differ only by the year meant. The years come out
  // of the regime rather than out of a constant here.
  const ministryRegime = regimes['ro-draft-2026-07-16'] ?? null;
  const years = useMemo(() => (ministryRegime ? phaseYears(ministryRegime) : []), [ministryRegime]);
  const year = yearOfAsOf(scenario.asOf, years[0] ?? 2026);
  const period = ministryRegime ? periodForYear(ministryRegime, year) : null;

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/proposals/${PROPOSAL_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`proposal: ${r.status}`))))
      .then(setProposal)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const base = import.meta.env.BASE_URL;
    fetch(`${base}data/crosswalks/${CROSSWALK_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`crosswalk: ${r.status}`))))
      .then(setCrosswalk)
      .catch((e: Error) => setError(e.message));

    fetch(`${base}data/crosswalks/${ASSIMILATION_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`assimilation: ${r.status}`))))
      .then(setAssimilation)
      .catch((e: Error) => setError(e.message));

    // The rate is read from the committed ECB document rather than hard-coded, so a
    // converted figure can always be traced to the day it was taken.
    fetch(`${base}data/fiscal/${FX_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`fx: ${r.status}`))))
      .then((doc) => {
        const rate = (id: string) =>
          doc.series.find((s: { id: string }) => s.id === id)?.observations.at(-1)?.value;
        setFx({ dkkToRon: rate('dkk-ron'), eurToRon: rate('eur-ron'), date: doc.retrieved });
      })
      .catch((e: Error) => setError(e.message));

    fetch(`${base}data/fiscal/${BENCHMARKS_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`benchmarks: ${r.status}`))))
      .then((doc) => {
        const val = (id: string) =>
          doc.series.find((s: { id: string }) => s.id === id)?.observations.at(-1)?.value;
        setBenchmarks({
          avgRo: val('avg-gross-monthly-ro'),
          avgDk: val('avg-gross-monthly-dk'),
          govRo: val('avg-gross-monthly-gov-ro'),
          govDk: val('avg-gross-monthly-gov-dk'),
          floorRo: val('floor-monthly-ro'),
          floorDk: val('floor-monthly-dk'),
          year: doc.retrieved,
        });
      })
      .catch((e: Error) => setError(e.message));

    Promise.all([
      fetch(`${base}data/groups/${GROUPS_ID}.json`).then((r) => r.json()),
      fetch(`${base}data/fiscal/${DK_OCC_ID}.json`).then((r) => r.json()),
      fetch(`${base}data/fiscal/${EXEC_ID}.json`).then((r) => r.json()),
      fetch(`${base}data/fiscal/${CAP_ID}.json`).then((r) => r.json()),
      fetch(`${base}data/fiscal/${INS_ID}.json`).then((r) => r.json()),
    ])
      .then(([groupsDoc, occDoc, execDoc, capDoc, insDoc]) => {
        setCapSeries(capDoc.series);
        setMeasured(insDoc.series);
        setOccGroups(groupsDoc);

        // The Romanian side of the composition: the rollup series, latest year, per
        // budget chapter. The paragraph-level series stay in the file for anyone who
        // wants to regroup them differently.
        // Every year, not only the last: whether the supplement layer is growing is a
        // live political question, and the answer was already in the file.
        const roShares: Record<string, Record<string, Shares>> = {};
        for (const s of execDoc.series) {
          if (s.dims?.kind !== 'composition') continue;
          const scope = s.dims.scope as string;
          for (const o of s.observations) {
            const byYear = (roShares[scope] ??= {});
            byYear[o.period] = { ...byYear[o.period], [s.dims.component]: o.value };
          }
        }
        setRoComposition(roShares);
        // The quartiles arrive as three separate series per occupation; fold them back.
        const byOcc = new Map<string, DkOccupation>();
        for (const s of occDoc.series) {
          const name = s.dims.occupation as string;
          const entry = byOcc.get(name) ?? { occupation: name, q1: 0, median: 0, q3: 0 };
          const value = s.observations.at(-1)?.value ?? 0;
          // 'composition-subitem' is holiday pay, which lives inside basic earnings. It
          // is carried so the page can show what it is worth; the engine knows never to
          // subtract it.
          if (s.dims.kind === 'composition' || s.dims.kind === 'composition-subitem') {
            entry.composition = { ...entry.composition, [s.dims.component]: value };
          } else {
            (entry as unknown as Record<string, number>)[s.dims.quartile] = value;
          }
          byOcc.set(name, entry);
        }
        const all = [...byOcc.values()];
        setDkOcc(all);
        const total = all.find((o) => o.occupation.startsWith('Public employees'));
        setOccBench({ roMedianBase: 0, dkMedian: total?.median ?? 0 });
      })
      .catch((e: Error) => setError(e.message));

    // The envelope baseline used to come from Eurostat's COFOG breakdown, which is one
    // year stale and classifies spending by purpose rather than by the budget chapters
    // the law is written against. The execution reports do both better: they are the
    // accounting the ordonatori actually file, and they run to the current year. Eurostat
    // is still read, but only for nominal GDP — the one number the execution does not have.
    Promise.all([
      fetch(`${base}data/fiscal/${FISCAL_ID}.json`).then((r) => r.json()),
      fetch(`${base}data/headcount/${HEADCOUNT_ID}.json`).then((r) => r.json()),
      fetch(`${base}data/fiscal/${EXEC_ID}.json`).then((r) => r.json()),
    ])
      .then(([fiscal, headcount, execDoc]) => {
        const cash = (id: string) =>
          fiscal.series.find((s: { id: string }) => s.id === id)?.observations.at(-1)?.value ?? 0;
        // Millions of lei in the source; minor units in the engine.
        const toMinor = (millionsOfLei: number) => Math.round(millionsOfLei * 1e6 * 100);

        // Budget chapters onto the draft's occupational families. Defence and public
        // order are one family in the annexes and two chapters in the budget, so they
        // add; nothing else is split.
        const SCOPE_FAMILY: Record<string, string> = {
          invatamant: 'I-invatamant',
          sanatate: 'II-sanatate-asistenta-sociala',
          'asistenta-sociala': 'II-sanatate-asistenta-sociala',
          aparare: 'VI-aparare-ordine-securitate',
          'ordine-publica': 'VI-aparare-ordine-securitate',
          administratie: 'VIII-administratie',
        };

        // The whole of title I, contributions included. The composition view excludes
        // employer contributions so it can be compared with Danish earnings; the envelope
        // must not, because Art. 36 alin. (3) sets its target against personnel
        // expenditure as the budget defines it. Same source, two different questions.
        const byFamilyLei = new Map<string, number>();
        let nationalLei = 0;
        for (const s of execDoc.series) {
          if (s.dims?.kind !== 'titleTotal') continue;
          const value = s.observations.at(-1)?.value ?? 0;
          if (s.dims.scope === 'national') {
            nationalLei = value;
            continue;
          }
          const family = SCOPE_FAMILY[s.dims.scope];
          if (family) byFamilyLei.set(family, (byFamilyLei.get(family) ?? 0) + value);
        }
        const byFamily = new Map(
          [...byFamilyLei].map(([family, lei]) => [family, lei / 1e6]),
        );

        setEnvelopeBaseline({
          currency: 'RON',
          period: 'year',
          total: toMinor(nationalLei / 1e6),
          byFamily: [...byFamily.entries()].map(([family, value]) => ({
            family,
            label: family,
            amount: toMinor(value),
          })),
          posts: headcount.totalPosts,
          gdp: toMinor(cash('gdp-nominal-ro')),
        });
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    // These views read regimes the scenario did not select. compare and echivalente put
    // the systems side by side; payslip needs the law in force to say what a post used to
    // be called, and without it that block renders with the titles and no coefficients.
    // Leaving it to `wanted` once left the landing page — headed "ways to pay the state" —
    // with its entire Danish column as explained dashes.
    const NEEDS_ALL: ViewId[] = ['compare', 'echivalente', 'payslip', 'distributie', 'acasa'];
    const needed = NEEDS_ALL.includes(scenario.view) ? AVAILABLE : wanted;
    const missing = needed.filter((id) => !regimes[id] && AVAILABLE.includes(id));
    if (missing.length === 0) return;
    Promise.all(
      missing.map((id) =>
        fetch(`${import.meta.env.BASE_URL}data/regimes/${id}.json`)
          .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${id}: ${r.status}`))))
          .then((doc: Regime) => [id, doc] as const),
      ),
    )
      .then((pairs) => setRegimes((prev) => ({ ...prev, ...Object.fromEntries(pairs) })))
      .catch((e: Error) => setError(e.message));
  }, [wanted, regimes, scenario.view]);

  const loaded = wanted.map((id) => regimes[id]).filter(Boolean);
  const ministry = regimes['ro-draft-2026-07-16'] ?? null;

  // The proposal is derived, never stored: applying five patches to the ministry's grid
  // is cheap, and keeping it derived means it cannot drift from the data it edits.
  const ours: AppliedProposal | null = useMemo(
    () => (ministry && proposal ? applyProposal(ministry, proposal) : null),
    [ministry, proposal],
  );

  const medianBase = useMemo(() => {
    if (!ministry) return null;
    const bases: number[] = [];
    for (const position of ministry.positions) {
      for (const variant of position.variants) {
        const slip = payslip(
          { positionCode: position.code, seniorityYears: 0, dims: variant.dims },
          ministry,
        );
        if (slip.base > 0) bases.push(slip.base / 100);
      }
    }
    if (!bases.length) return null;
    bases.sort((a, b) => a - b);
    return bases[Math.floor(bases.length / 2)];
  }, [ministry]);

  const share = async () => {
    await navigator.clipboard?.writeText(location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleRegime = (id: string) => {
    const next = wanted.includes(id) ? wanted.filter((r) => r !== id) : [...wanted, id];
    setScenario({ ...scenario, regimeIds: next.length ? next : [AVAILABLE[0]] });
  };

  return (
    <div className="wrap">
      <nav className="tabs">
        {NAV_GROUPS.map((group) => (
          <div className="tabgroup" key={group.title}>
            <span className="tabgroup-title">{group.title}</span>
            <span className="tabgroup-ask">{group.ask}</span>
            {group.views.map((id) => (
              <button
                key={id}
                className={scenario.view === id ? 'on' : ''}
                onClick={() => setScenario({ ...scenario, view: id })}
              >
                <strong>{VIEW_META[id].label}</strong>
                <small>{VIEW_META[id].blurb}</small>
              </button>
            ))}
          </div>
        ))}
        {scenario.view === 'payslip' && (
          <div className="tabgroup regimes">
            {AVAILABLE.map((id) => (
              <label key={id} className="regime-toggle">
                <input
                  type="checkbox"
                  checked={wanted.includes(id)}
                  onChange={() => toggleRegime(id)}
                />
                <span>{id}</span>
              </label>
            ))}
            <button className="share" onClick={share}>
              {copied ? 'link copiat' : 'copiază linkul scenariului'}
            </button>
          </div>
        )}
      </nav>

      {PHASED_VIEWS.includes(scenario.view) && years.length > 1 && (
        <div className="phase">
          <label htmlFor="phase-year">
            <strong>Grila din anul</strong>
            <span>
              proiectul se aplică eșalonat: coeficienții de vârf urcă an de an până în{' '}
              {years[years.length - 1]}
            </span>
          </label>
          <input
            id="phase-year"
            type="range"
            min={years[0]}
            max={years[years.length - 1]}
            step={1}
            value={year}
            onChange={(e) =>
              setScenario({ ...scenario, asOf: asOfForYear(Number(e.target.value)) })
            }
          />
          <output htmlFor="phase-year">
            <b>{year}</b>
            {period && <span>coloana „{period}"</span>}
          </output>
        </div>
      )}

      {error && <p className="loading">Nu s-au putut încărca datele: {error}</p>}
      {!error && loaded.length === 0 && <p className="loading">Se încarcă grila…</p>}

      {scenario.view === 'acasa' && (
        <HomeView
          ministry={ministry ?? null}
          inForce={regimes['ro-153-2017'] ?? null}
          denmark={regimes['dk-stat-2026'] ?? null}
          onOpen={(view) => setScenario({ ...scenario, view })}
        />
      )}
      {scenario.view === 'compare' && ministry && ours && proposal && fx && (
        <CompareView
          ministry={ministry}
          ours={ours.regime}
          inForce={regimes['ro-153-2017'] ?? null}
          denmark={regimes['dk-stat-2026'] ?? null}
          proposal={proposal}
          effects={ours.effects}
          rates={fx}
          capSeries={capSeries}
          period={period}
          onOpen={(view) => setScenario({ ...scenario, view })}
        />
      )}
      {scenario.view === 'distributie' && ministry && assimilation && (
        <DistributionView
          inForce={regimes['ro-153-2017'] ?? null}
          draft={ministry}
          crosswalk={assimilation}
        />
      )}
      {scenario.view === 'meserii' && ministry && occGroups && dkOcc && occBench && fx && (
        <OccupationsView
          regime={ministry}
          groups={occGroups}
          danish={dkOcc}
          benchmarks={{ roMedianBase: medianBase ?? 0, dkMedian: occBench.dkMedian }}
          rates={fx}
          roComposition={roComposition}
          scenario={scenario}
          onScenario={setScenario}
          measured={measured}
          inForce={regimes['ro-153-2017'] ?? null}
        />
      )}
      {scenario.view === 'echivalente' &&
        ministry &&
        regimes['dk-stat-2026'] &&
        crosswalk &&
        fx &&
        benchmarks && (
          <EquivalenceView
            ro={ministry}
            dk={regimes['dk-stat-2026']}
            crosswalk={crosswalk}
            fx={fx}
            benchmarks={benchmarks}
          />
        )}
      {loaded.length > 0 && scenario.view === 'structure' && (
        <StructureView regime={regimes['ro-draft-2026-07-16'] ?? loaded[0]} period={period} />
      )}
      {scenario.view === 'envelope' && fx && (
        <EnvelopeView
          baseline={envelopeBaseline}
          rates={fx}
          capSeries={capSeries}
          scenario={scenario}
          onScenario={setScenario}
        />
      )}
      {loaded.length > 0 && scenario.view === 'payslip' && fx && (
        <PayslipView
          regimes={ours ? [...loaded, ours.regime] : loaded}
          scenario={scenario}
          onChange={setScenario}
          rates={fx}
          assimilation={assimilation}
          inForce={regimes['ro-153-2017'] ?? null}
        />
      )}

      <footer>
        Sursă: proiectul de lege MMFTSS din 16.07.2026 și anexele de coeficienți; pentru Danemarca,
        tabelele IDA din 01.04.2026. Fiecare număr din <code>data/</code> poartă documentul și
        articolul sau celula din care provine.{' '}
        <a href="https://github.com/CristianNichifor/public-pay-simulator">Cod și date</a>. Licență
        Apache-2.0.
      </footer>
    </div>
  );
}

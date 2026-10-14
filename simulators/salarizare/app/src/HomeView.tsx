import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Field, Input } from '@cristiannichifor/civic-ui';

import type { Scenario, ViewId } from '../../engine/scenario';
import type { Regime } from '../../engine/types';
import { GlossaryList } from './Glossary';
import type { Lang } from './i18n';
import { PositionName } from './names';
import NoHit from './NoHit';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

/** Accents are inconsistent across the source sheets, and nobody types them into a search. */
const fold = (s: string) =>
  s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();

interface Entry {
  view: ViewId;
  title: string;
  body: string;
}

interface Question {
  ask: string;
  lead: string;
  entries: Entry[];
}

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface HomeStrings {
  allSimulators: string;
  allSimulatorsTitle: string;
  title: string;
  purpose: string;
  findYourPosition: string;
  findLede: ReactNode;
  searchLabel: string;
  searchPlaceholder: string;
  otherTitles: (n: number) => string;
  codeTitle: string;
  disclaimer: ReactNode;
  questions: Question[];
  sourcesTitle: string;
  sources: {
    draft: ReactNode;
    inForce: ReactNode;
    execution: ReactNode;
    statistics: ReactNode;
    denmark: ReactNode;
  };
  positions: (count: string) => string;
  transcribed: (count: string) => string;
  sourcesNote: string;
  glossaryTitle: string;
  glossaryLede: string;
  cannotTitle: string;
  cannotHeadcount: (positions: string) => ReactNode;
  cannotTakeHome: ReactNode;
  cannotSupplements: ReactNode;
}

export const HOME_STRINGS: Record<Lang, HomeStrings> = {
  ro: {
    allSimulators: '← Toate simulatoarele',
    allSimulatorsTitle: 'Toate simulatoarele de reformă',
    title: 'Cum își plătește România angajații publici',
    purpose:
      'Un instrument pentru dezbaterea publică despre proiectul de lege al salarizării din 20 august 2026: ce schimbă față de legea care plătește oamenii azi, cine urcă și cine coboară în ierarhie, cât costă și cum arată aceleași întrebări într-o țară care a rezolvat altfel problema.',
    findYourPosition: 'Caută-ți funcția',
    findLede: (
      <>
        Scrie o denumire din grilă — <em>asistent medical</em>, <em>șofer</em>,{' '}
        <em>muncitor calificat</em>, <em>consilier</em> — și mergi direct la salariul calculat
        pentru ea, sub fiecare dintre cele patru sisteme.
      </>
    ),
    searchLabel: 'Caută o funcție din grilă',
    searchPlaceholder: 'caută după denumire sau cod',
    otherTitles: (n) => `+${n} denumiri · `,
    codeTitle: 'codul poziției în anexa sursă',
    disclaimer: (
      <>
        <strong>Instrument de dezbatere, nu calculator de salarii.</strong> Calculează ce spune un
        text de lege, nu ce încasează cineva. Nicio cifră de aici nu e un drept al nimănui, și
        niciun scenariu nu e o recomandare. Fiecare număr își poartă documentul și articolul din
        care provine, iar unde datele nu ajung, scrie asta pe pagină în loc să fie completat cu o
        presupunere.
      </>
    ),
    questions: [
      {
        ask: 'Ce se schimbă?',
        lead: 'Proiectul ministerului, pus lângă legea care plătește oamenii azi.',
        entries: [
          {
            view: 'compare',
            title: 'Cele patru sisteme, față în față',
            body: 'Aceleași șapte întrebări puse legii în vigoare, proiectului, propunerii alternative și Danemarcei.',
          },
          {
            view: 'distributie',
            title: 'Cine urcă și cine coboară',
            body: 'Fiecare post regăsit în ambele legi, comparat cu el însuși. Media aproape nu se mișcă; aproape toată lumea se mișcă.',
          },
          {
            view: 'structure',
            title: 'Cum e construită grila',
            body: 'Zecimalele, golurile dintre grade, funcțiile care poartă numele instituției în loc de al meseriei.',
          },
        ],
      },
      {
        ask: 'Cine cât ia?',
        lead: 'De la un post anume până la meseria întreagă, și cât înseamnă asta față de Danemarca.',
        entries: [
          {
            view: 'domenii',
            title: 'Domenii publice, pe aceeași scară',
            body: 'Educație, sănătate, justiție, ordine, apărare, administrație, cercetare și cultură, normalizate la salariul mediu și la salariul minim.',
          },
          {
            view: 'meserii',
            title: 'Meserii, România vs Danemarca',
            body: 'Funcțiile regrupate după meserie, nu după anexă — și grila pusă lângă ce măsoară statistica oficială că se plătește.',
          },
          {
            view: 'payslip',
            title: 'Un salariu, calculat',
            body: 'Alege o funcție și o vechime. Fiecare regim calculează din propriile reguli, iar linkul păstrează scenariul.',
          },
          {
            view: 'echivalente',
            title: 'Echivalențe de post',
            body: 'Ce denumire daneză corespunde fiecărei funcții din grilă, și cât valorează fiecare față de mijlocul propriului sistem.',
          },
        ],
      },
      {
        ask: 'Ne permitem?',
        lead: 'Cât costă tot, și pe cine ar prinde plafonul de 20% dacă lucrurile rămân cum sunt.',
        entries: [
          {
            view: 'envelope',
            title: 'Cât costă tot',
            body: 'Plicul: fixezi cât are voie să coste personalul, iar orice creștere trebuie plătită dintr-o reducere numită.',
          },
        ],
      },
    ],
    sourcesTitle: 'Pe ce se sprijină',
    sources: {
      draft: (
        <>
          <b>Proiectul MMFTSS din 20.08.2026</b> — anexele de coeficienți, citite direct din caietul
          de lucru al ministerului
        </>
      ),
      inForce: (
        <>
          <b>Legea-cadru 153/2017</b>, legea în vigoare — anexele din forma consolidată, unde fiecare
          coeficient e confirmat cu salariul tipărit lângă el
        </>
      ),
      execution: (
        <>
          <b>Execuția bugetară</b> raportată de ordonatorii principali de credite — cât s-a plătit
          efectiv, pe clasificația economică, 2021–2025
        </>
      ),
      statistics: (
        <>
          <b>Institutul Național de Statistică</b> — salariul brut de bază măsurat în învățământ și
          sănătate, pe grupe de ocupații
        </>
      ),
      denmark: (
        <>
          <b>Danmarks Statistik și tabelele IDA</b> — sistemul danez, ca reper de formă
        </>
      ),
    },
    positions: (count) => ` · ${count} funcții`,
    transcribed: (count) => ` · ${count} posturi transcrise`,
    sourcesNote:
      'Toate importurile sunt scripturi din depozit, care se pot rula din nou. Codul și datele sunt publice, iar orice cifră de pe ecran se poate urmări până la celula din care vine.',
    glossaryTitle: 'Cuvintele legii',
    glossaryLede:
      'Paginile de aici folosesc vocabularul statutului, pentru că altfel nicio cifră nu s-ar mai putea urmări până la articolul din care vine. Iată ce înseamnă, o dată pentru toate.',
    cannotTitle: 'Ce nu poate spune',
    cannotHeadcount: (positions) => (
      <>
        <b>Câți oameni sunt pe fiecare funcție.</b> Nimic publicat nu leagă numărul de posturi de
        cele {positions} de funcții din grilă, așa că factura unei propuneri se poate discuta pe
        total, nu pe funcție.
      </>
    ),
    cannotTakeHome: (
      <>
        <b>Cât ia cineva în mână.</b> Diferența salarială tranzitorie din Art. 33 depinde de venitul
        fiecărei persoane în noiembrie 2026, care nu se publică.
      </>
    ),
    cannotSupplements: (
      <>
        <b>Ce se întâmplă cu sporurile în practică.</b> Plafonul de 20% se măsoară pe instituție și
        pe sursă de finanțare, nu pe om — pagina „Cât costă tot” arată pe cine ar prinde, dar nu ce
        va primi un anumit angajat.
      </>
    ),
  },
  en: {
    allSimulators: '← All simulators',
    allSimulatorsTitle: 'All reform simulators',
    title: 'How Romania pays its public employees',
    purpose:
      'An instrument for the public debate on the draft pay law of 20 August 2026: what it changes against the law that pays people today, who rises and who falls in the hierarchy, what it costs, and what the same questions look like in a country that solved the problem differently.',
    findYourPosition: 'Find your position',
    findLede: (
      <>
        Type a title from the grid — <em>asistent medical</em>, <em>șofer</em>,{' '}
        <em>muncitor calificat</em>, <em>consilier</em> — and go straight to the pay computed for
        it under each of the four systems.
      </>
    ),
    searchLabel: 'Search for a position in the grid',
    searchPlaceholder: 'search by title or code',
    otherTitles: (n) => `+${n} titles · `,
    codeTitle: 'the position code in the source annex',
    disclaimer: (
      <>
        <strong>An instrument for debate, not a salary calculator.</strong> It computes what a legal
        text says, not what anyone takes home. No figure here is anyone's entitlement, and no
        scenario is a recommendation. Every number carries the document and article it comes from,
        and where the data runs out the page says so instead of filling the gap with an assumption.
      </>
    ),
    questions: [
      {
        ask: 'What changes?',
        lead: "The ministry's draft, set beside the law that pays people today.",
        entries: [
          {
            view: 'compare',
            title: 'The four systems, side by side',
            body: 'The same seven questions put to the law in force, the draft, the alternative proposal and Denmark.',
          },
          {
            view: 'distributie',
            title: 'Who rises and who falls',
            body: 'Every post found in both laws, compared with itself. The average barely moves; almost everyone moves.',
          },
          {
            view: 'structure',
            title: 'How the grid is built',
            body: 'The decimals, the gaps between grades, the positions named after the institution instead of the trade.',
          },
        ],
      },
      {
        ask: 'Who earns what?',
        lead: 'From one post to a whole trade, and what that means against Denmark.',
        entries: [
          {
            view: 'domenii',
            title: 'Public fields, on one scale',
            body: 'Education, health, justice, public order, defence, administration, research and culture, normalised to the average wage and the minimum wage.',
          },
          {
            view: 'meserii',
            title: 'Trades, Romania vs Denmark',
            body: 'Positions regrouped by trade rather than by annex, and the grid set beside what official statistics measure as actually paid.',
          },
          {
            view: 'payslip',
            title: 'One salary, computed',
            body: 'Pick a position and a seniority. Each regime computes from its own rules, and the link keeps the scenario.',
          },
          {
            view: 'echivalente',
            title: 'Position equivalences',
            body: 'Which Danish title matches each position in the grid, and what each is worth against the middle of its own system.',
          },
        ],
      },
      {
        ask: 'Can we afford it?',
        lead: 'What it all costs, and whom the 20% cap would catch if things stay as they are.',
        entries: [
          {
            view: 'envelope',
            title: 'What it all costs',
            body: 'The envelope: you fix what staff may cost, and any increase has to be paid for by a named cut.',
          },
        ],
      },
    ],
    sourcesTitle: 'What it rests on',
    sources: {
      draft: (
        <>
          <b>The MMFTSS draft of 20.08.2026</b> — the coefficient annexes, read straight from the
          ministry's workbook
        </>
      ),
      inForce: (
        <>
          <b>Framework law 153/2017</b>, the law in force — the annexes of the consolidated text,
          where every coefficient is confirmed by the salary printed beside it
        </>
      ),
      execution: (
        <>
          <b>Budget execution</b> as reported by the principal budget holders — what was actually
          paid, by economic classification, 2021–2025
        </>
      ),
      statistics: (
        <>
          <b>The National Institute of Statistics</b> — gross base pay measured in education and
          health, by occupational group
        </>
      ),
      denmark: (
        <>
          <b>Danmarks Statistik and the IDA tables</b> — the Danish system, as a reference of shape
        </>
      ),
    },
    positions: (count) => ` · ${count} positions`,
    transcribed: (count) => ` · ${count} posts transcribed`,
    sourcesNote:
      'Every import is a script in the repository that can be run again. The code and the data are public, and any figure on screen can be traced to the cell it comes from.',
    glossaryTitle: "The law's words",
    glossaryLede:
      'The pages here use the statute\'s vocabulary, because otherwise no figure could be traced back to the article it comes from. Here is what the words mean, once and for all.',
    cannotTitle: 'What it cannot say',
    cannotHeadcount: (positions) => (
      <>
        <b>How many people are on each position.</b> Nothing published links the number of posts to
        the {positions} positions in the grid, so the bill of a proposal can be discussed in total,
        not per position.
      </>
    ),
    cannotTakeHome: (
      <>
        <b>What anyone takes home.</b> The transitional pay difference of Art. 33 depends on each
        person's income in November 2026, which is not published.
      </>
    ),
    cannotSupplements: (
      <>
        <b>What happens to supplements in practice.</b> The 20% cap is measured per institution and
        per funding source, not per person: the "What it all costs" page shows whom it would catch,
        but not what a given employee will receive.
      </>
    ),
  },
};

/**
 * The first screen.
 *
 * Before this, a visitor landed on a table of structural metrics — retro-calculated
 * coefficients, distinct values in the grid — with no statement of what the tool is or
 * what it will not do. The numbers were right and the entrance was wrong: someone
 * arriving from a link had to infer the scope from the contents.
 *
 * The page is deliberately short and mostly navigation. Counts come from the regimes as
 * loaded, so nothing here can go stale against the data behind it.
 */
/** The empty state of the search (UX-12): it names what was typed and says what to try. */
export const noHit = (query: string): string =>
  `Nicio funcție pentru „${query.trim()}" în grila proiectului. Denumirile sunt cele din anexe, ` +
  'iar multe posturi reale sunt comasate sub un titlu care nu le conține: caută cuvântul ' +
  'cel mai general din meserie.';

export default function HomeView({
  menu,
  ministry,
  inForce,
  denmark,
  onOpen,
  dataLine,
  statusBadge,
  lang = 'ro',
}: {
  /** The section menu, drawn after the search so the question people arrive with comes first. */
  menu?: ReactNode;
  ministry: Regime | null;
  inForce: Regime | null;
  denmark: Regime | null;
  /** "Date: <sursă>, <an>", rendered right under the H1 (UX-5). */
  dataLine: string;
  /** "Date reale": the one status badge on the page (design screen 03, criterion 4). */
  statusBadge: string;
  onOpen: (view: ViewId, patch?: Partial<Scenario>) => void;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = HOME_STRINGS[lang];
  const n = (value: number) => value.toLocaleString(LOCALE[lang]);
  const positions = (regime: Regime | null) => (regime ? regime.positions.length : null);

  // The front door. Every route into this tool used to start with a question about the
  // system — what changes, who wins, what it costs — and none of them started with the
  // question people actually arrive with, which is about their own job. The payslip page
  // could always answer it; there was simply no way to ask from here.
  const [query, setQuery] = useState('');
  const hits = useMemo(() => {
    const q = fold(query.trim());
    if (q.length < 2 || !ministry) return [];
    return ministry.positions
      .filter((p) => fold(p.name).includes(q) || p.code.includes(q))
      .slice(0, 8);
  }, [query, ministry]);

  return (
    <>
      <header className="masthead home-masthead">
        <a className="up" href="../" title={t.allSimulatorsTitle}>
          {t.allSimulators}
        </a>
        <h1>{t.title}</h1>
        <p className="purpose">{t.purpose}</p>
        <p className="data-line">
          {dataLine} <span className="badge status">{statusBadge}</span>
        </p>
      </header>


      <section>
        <h2>{t.findYourPosition}</h2>
        <p className="lede">{t.findLede}</p>
        <div className="card home-search">
          <Field id="home-search" label={t.searchLabel}>
            {(attributes) => (
              <Input
                {...attributes}
                type="search"
                value={query}
                placeholder={t.searchPlaceholder}
                aria-label={t.searchLabel}
                onChange={(e) => setQuery(e.target.value)}
              />
            )}
          </Field>
          {hits.length > 0 && (
            <ul className="home-hits">
              {hits.map((p) => (
                <li key={p.code}>
                  <button onClick={() => onOpen('payslip', { positionCode: p.code, dims: undefined })}>
                    <strong>
                      <PositionName name={p.name} />
                    </strong>
                    <span>
                      {p.titles && p.titles.length > 1 && t.otherTitles(p.titles.length - 1)}
                      <code title={t.codeTitle}>{p.code}</code>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {query.trim().length >= 2 && hits.length === 0 && <NoHit query={query} lang={lang} />}
        </div>
      </section>

      {menu}

      <div className="disclaimer">{t.disclaimer}</div>

      {t.questions.map((q) => (
        <section key={q.ask}>
          <h2>{q.ask}</h2>
          <p className="lede">{q.lead}</p>
          <div className="home-grid">
            {q.entries.map((entry) => (
              <button key={entry.view} className="home-card" onClick={() => onOpen(entry.view)}>
                <strong>{entry.title}</strong>
                <span>{entry.body}</span>
              </button>
            ))}
          </div>
        </section>
      ))}

      <section>
        <h2>{t.sourcesTitle}</h2>
        <div className="card home-sources">
          <ul>
            <li>
              {t.sources.draft}
              {positions(ministry) !== null && <em>{t.positions(n(positions(ministry)!))}</em>}
            </li>
            <li>
              {t.sources.inForce}
              {positions(inForce) !== null && <em>{t.positions(n(positions(inForce)!))}</em>}
            </li>
            <li>{t.sources.execution}</li>
            <li>{t.sources.statistics}</li>
            <li>
              {t.sources.denmark}
              {positions(denmark) !== null && <em>{t.transcribed(n(positions(denmark)!))}</em>}
            </li>
          </ul>
          <p>{t.sourcesNote}</p>
        </div>
      </section>

      <section>
        <h2>{t.glossaryTitle}</h2>
        <p className="lede">{t.glossaryLede}</p>
        <div className="card">
          <GlossaryList />
        </div>
      </section>

      <section>
        <h2>{t.cannotTitle}</h2>
        <div className="card home-sources">
          <ul>
            <li>{t.cannotHeadcount(positions(ministry) !== null ? n(positions(ministry)!) : '')}</li>
            <li>{t.cannotTakeHome}</li>
            <li>{t.cannotSupplements}</li>
          </ul>
        </div>
      </section>
    </>
  );
}

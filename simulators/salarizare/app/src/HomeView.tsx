import type { ViewId } from '../../engine/scenario';
import type { Regime } from '../../engine/types';

const ro = (n: number) => n.toLocaleString('ro-RO');

interface Entry {
  view: ViewId;
  title: string;
  body: string;
}

const QUESTIONS: Array<{ ask: string; lead: string; entries: Entry[] }> = [
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
];

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
export default function HomeView({
  ministry,
  inForce,
  denmark,
  onOpen,
}: {
  ministry: Regime | null;
  inForce: Regime | null;
  denmark: Regime | null;
  onOpen: (view: ViewId) => void;
}) {
  const positions = (regime: Regime | null) => (regime ? regime.positions.length : null);

  return (
    <>
      <header className="masthead home-masthead">
        <a className="to-index" href="../" title="Toate simulatoarele de reformă">
          ← Toate reformele
        </a>
        <h1>Cum își plătește România angajații publici</h1>
        <p>
          Un instrument pentru dezbaterea publică despre proiectul de lege al salarizării din 16
          iulie 2026: ce schimbă față de legea care plătește oamenii azi, cine urcă și cine
          coboară în ierarhie, cât costă și cum arată aceleași întrebări într-o țară care a
          rezolvat altfel problema.
        </p>
      </header>

      <div className="disclaimer">
        <strong>Instrument de dezbatere, nu calculator de salarii.</strong> Calculează ce spune un
        text de lege, nu ce încasează cineva. Nicio cifră de aici nu e un drept al nimănui, și
        niciun scenariu nu e o recomandare. Fiecare număr își poartă documentul și articolul din
        care provine, iar unde datele nu ajung, scrie asta pe pagină în loc să fie completat cu o
        presupunere.
      </div>

      {QUESTIONS.map((q) => (
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
        <h2>Pe ce se sprijină</h2>
        <div className="card home-sources">
          <ul>
            <li>
              <b>Proiectul MMFTSS din 16.07.2026</b> — anexele de coeficienți, citite direct din
              caietul de lucru al ministerului
              {positions(ministry) !== null && <em> · {ro(positions(ministry)!)} funcții</em>}
            </li>
            <li>
              <b>Legea-cadru 153/2017</b>, legea în vigoare — anexele din forma consolidată, unde
              fiecare coeficient e confirmat cu salariul tipărit lângă el
              {positions(inForce) !== null && <em> · {ro(positions(inForce)!)} funcții</em>}
            </li>
            <li>
              <b>Execuția bugetară</b> raportată de ordonatorii principali de credite — cât s-a
              plătit efectiv, pe clasificația economică, 2021–2025
            </li>
            <li>
              <b>Institutul Național de Statistică</b> — salariul brut de bază măsurat în
              învățământ și sănătate, pe grupe de ocupații
            </li>
            <li>
              <b>Danmarks Statistik și tabelele IDA</b> — sistemul danez, ca reper de formă
              {positions(denmark) !== null && <em> · {ro(positions(denmark)!)} posturi transcrise</em>}
            </li>
          </ul>
          <p>
            Toate importurile sunt scripturi din depozit, care se pot rula din nou. Codul și datele
            sunt publice, iar orice cifră de pe ecran se poate urmări până la celula din care vine.
          </p>
        </div>
      </section>

      <section>
        <h2>Ce nu poate spune</h2>
        <div className="card home-sources">
          <ul>
            <li>
              <b>Câți oameni sunt pe fiecare funcție.</b> Nimic publicat nu leagă numărul de
              posturi de cele {positions(ministry) !== null ? ro(positions(ministry)!) : ''} de
              funcții din grilă, așa că factura unei propuneri se poate discuta pe total, nu pe
              funcție.
            </li>
            <li>
              <b>Cât ia cineva în mână.</b> Diferența salarială tranzitorie din Art. 33 depinde de
              venitul fiecărei persoane în noiembrie 2026, care nu se publică.
            </li>
            <li>
              <b>Ce se întâmplă cu sporurile în practică.</b> Plafonul de 20% se măsoară pe
              instituție și pe sursă de finanțare, nu pe om — pagina „Cât costă tot” arată pe cine
              ar prinde, dar nu ce va primi un anumit angajat.
            </li>
          </ul>
        </div>
      </section>
    </>
  );
}

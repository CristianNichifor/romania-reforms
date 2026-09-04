/**
 * The words the law uses, defined once.
 *
 * Every page here is written in the vocabulary of the statute — *coeficient*, *gradație*,
 * *treaptă*, *ordonator principal de credite* — because paraphrasing them would make the
 * numbers untraceable to the article they came from. But that vocabulary is exactly what
 * keeps a citizen out of the argument: "the ratio is 1:8" means nothing without knowing
 * that a coefficient is a multiplier on a single reference value, and someone who has to
 * leave the page to find that out does not come back.
 *
 * So the terms are defined in one place, and every page borrows from it. A definition is
 * a fact about the law, not decoration: where the law itself sets the term, the article
 * is named, so a reader can check the gloss rather than trust it.
 */

export interface GlossaryEntry {
  term: string;
  short: string;
  /** The article that defines it, where the statute does. */
  source?: string;
}

export const TERMS: Record<string, GlossaryEntry> = {
  coeficient: {
    term: 'Coeficient',
    short:
      'Un multiplicator, nu o sumă. Salariul de bază este coeficientul înmulțit cu valoarea de referință, aceeași pentru tot sectorul public. Coeficientul 2,00 înseamnă dublul bazei sistemului, oriunde ar fi postul.',
    source: 'Art. 8',
  },
  'valoare-de-referinta': {
    term: 'Valoarea de referință',
    short:
      'Suma unică din care se calculează toate salariile de bază — 4.100 lei în proiect. Când se mișcă ea, se mișcă toată grila deodată; când se mișcă un coeficient, se mișcă un singur post față de restul.',
    source: 'Art. 36 alin. (2)',
  },
  gradatie: {
    term: 'Gradație',
    short:
      'Treptele de vechime în muncă, aceleași pentru toți: +7,5%, apoi +5%, +5%, +2,5%, +2,5% peste coeficientul de la gradația 0. Se câștigă cu anii lucrați, nu cu funcția.',
    source: 'Art. 13',
  },
  treapta: {
    term: 'Treaptă profesională',
    short:
      'Nivelul din interiorul aceleiași meserii — „muncitor calificat treapta I” până la „treapta IV”. Spune cât de sus e cineva în propria meserie, nu ce meserie are: calificarea concretă (electrician, instalator) nu apare nicăieri în grilă.',
  },
  'grad-salarial': {
    term: 'Grad salarial',
    short:
      'Cele 12 intervale în care proiectul împarte grila, de la 1,00 la 8,00. Încadrarea într-un grad decide evaluarea și promovarea, deci un coeficient care cade între două intervale e un om fără regulă aplicabilă.',
    source: 'Art. 9 alin. (2)',
  },
  spor: {
    term: 'Spor',
    short:
      'Plată peste salariul de bază, pentru condiții de muncă, ore suplimentare sau atribuții suplimentare. Proiectul le plafonează la 20% din cheltuiala cu salariile de bază — dar plafonul se măsoară pe instituție, nu pe om, și mai multe sporuri sunt exceptate de la el.',
    source: 'Art. 21 alin. (2)',
  },
  'ordonator-principal': {
    term: 'Ordonator principal de credite',
    short:
      'Instituția care primește bani direct de la buget — un minister, un consiliu județean, o primărie — și îi împarte mai departe. Plafoanele și raportările se fac pe ordonator, motiv pentru care nimic din ce se publică nu coboară până la funcție.',
  },
  anexa: {
    term: 'Anexă',
    short:
      'Capitolul din lege care conține grila unei familii ocupaționale: Anexa I învățământ, Anexa II sănătate, Anexa VI apărare și ordine publică, Anexa VIII administrație. Anexa spune cine te angajează, nu ce muncă faci — iar grila plătește adesea anexa.',
  },
  'familie-ocupationala': {
    term: 'Familie ocupațională',
    short:
      'Gruparea de posturi pe care o folosește legea, una pentru fiecare anexă. Urmează angajatorul și statutul juridic, nu ocupația — motiv pentru care aceeași meserie apare în mai multe familii, cu coeficienți diferiți.',
  },
  'coeficient-retrocalculat': {
    term: 'Coeficient retro-calculat',
    short:
      'Un coeficient obținut împărțind un salariu existent la altul, în loc să fie ales. Se recunoaște după zecimale: 5,189610389610378 este restul unei împărțiri, 2,40 este o decizie.',
  },
};

/**
 * A term in running text, with its definition attached.
 *
 * `<abbr>` is the honest element here — the word really is standing in for a longer
 * explanation — and it gives the tooltip to a mouse, a long-press on touch, and the
 * accessible name to a screen reader without any script.
 */
export function Term({ id, children }: { id: keyof typeof TERMS | string; children?: React.ReactNode }) {
  const entry = TERMS[id];
  if (!entry) return <>{children}</>;
  const title = entry.source ? `${entry.short} (${entry.source})` : entry.short;
  return (
    <abbr className="term" title={title}>
      {children ?? entry.term.toLowerCase()}
    </abbr>
  );
}

/** The whole vocabulary, for the page that introduces the tool. */
export function GlossaryList() {
  return (
    <dl className="glossary">
      {Object.entries(TERMS).map(([id, entry]) => (
        <div key={id}>
          <dt>
            {entry.term}
            {entry.source && <span className="glossary-src">{entry.source}</span>}
          </dt>
          <dd>{entry.short}</dd>
        </div>
      ))}
    </dl>
  );
}

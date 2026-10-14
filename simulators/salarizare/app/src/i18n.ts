/**
 * Romanian and English for the app shell: the navigation, the controls around the views and the
 * footer. Same rule as the administrative simulator: the language is `lang=` in the hash, so a
 * shared link keeps its language, and a bare link is Romanian, the subject's language.
 *
 * The views themselves are still Romanian prose; in English a notice says so. English text:
 * needs human review.
 */
import type { Scenario, ViewId } from '../../engine/scenario';

export type Lang = 'ro' | 'en';

export interface Strings {
  views: Record<ViewId, { label: string; blurb: string }>;
  groups: Record<'start' | 'reform' | 'alternative' | 'people' | 'money', { title: string; ask: string }>;
  sections: string;
  share: string;
  copied: string;
  phaseLabel: string;
  phaseNote: (until: number) => string;
  phaseColumn: (period: string) => string;
  loadError: (message: string) => string;
  /** The action next to a load error (UX-12). */
  retry: string;
  loading: string;
  footerSource: string;
  /** "Date: <sursă>, <an>" under the home H1 (UX-5): the same package the footer cites. */
  dataLine: string;
  footerCode: string;
  footerLicence: string;
  switchTo: { lang: Lang; label: string };
  viewsInRomanian: string | null;
}

const ro: Strings = {
  views: {
    acasa: { label: 'Despre proiect', blurb: 'ce este, pe ce date stă, ce nu poate spune' },
    compare: { label: 'Ce se schimbă', blurb: 'proiectul, propunerea și Danemarca, față în față' },
    propunere: { label: 'Propunerea noastră', blurb: 'nouă corecturi, fiecare cu întrerupătorul ei' },
    structure: { label: 'Cum e construită grila', blurb: 'zecimalele, golurile, funcțiile comasate' },
    distributie: {
      label: 'Cine urcă, cine coboară',
      blurb: 'cum se mișcă fiecare post față de legea de azi',
    },
    domenii: {
      label: 'Domenii publice',
      blurb: 'educație, sănătate, justiție, ordine, apărare, administrație',
    },
    meserii: { label: 'Meserii, RO vs DK', blurb: 'cât ia aceeași meserie în fiecare țară' },
    payslip: { label: 'Un salariu, calculat', blurb: 'un om anume, sub fiecare regim' },
    echivalente: { label: 'Echivalențe de post', blurb: 'ce denumire daneză corespunde fiecărei funcții' },
    envelope: { label: 'Cât costă tot', blurb: 'plicul, plafonul de 20% și cine trece de el' },
    functii: {
      label: 'Funcție cu funcție',
      blurb: 'ce denumiri a înghițit fiecare post, și cât ia în trei sisteme',
    },
  },
  groups: {
    start: { title: 'Începe aici', ask: 'Ce e asta?' },
    reform: { title: 'Reforma', ask: 'Ce se schimbă?' },
    alternative: { title: 'Alternativa', ask: 'Se poate altfel?' },
    people: { title: 'Oamenii', ask: 'Cine cât ia?' },
    money: { title: 'Banii', ask: 'Ne permitem?' },
  },
  sections: 'Secțiunile instrumentului',
  share: 'copiază linkul scenariului',
  copied: 'link copiat',
  phaseLabel: 'Grila din anul',
  phaseNote: (until) =>
    `proiectul se aplică eșalonat: coeficienții de vârf urcă an de an până în ${until}`,
  phaseColumn: (period) => `; coloana „${period}"`,
  loadError: (message) => `Nu s-au putut încărca datele: ${message}`,
  retry: 'Reîncearcă',
  loading: 'Se încarcă grila…',
  dataLine: 'Date: MMFTSS, pachetul public din 20.08.2026; IDA (Danemarca), 01.04.2026',
  footerSource:
    'Sursă: pachetul public MMFTSS din 20.08.2026 și anexele de coeficienți; pentru Danemarca, tabelele IDA din 01.04.2026. Fiecare număr din data/ poartă documentul și articolul sau celula din care provine.',
  footerCode: 'Cod și date',
  footerLicence: 'Licență Apache-2.0.',
  switchTo: { lang: 'en', label: 'English' },
  viewsInRomanian: null,
};

const en: Strings = {
  views: {
    acasa: { label: 'About the project', blurb: 'what it is, what data it rests on, what it cannot say' },
    compare: { label: 'What changes', blurb: 'the draft, our proposal and Denmark, side by side' },
    propunere: { label: 'Our proposal', blurb: 'nine corrections, each with its own switch' },
    structure: { label: 'How the grid is built', blurb: 'the decimals, the gaps, the merged positions' },
    distributie: {
      label: 'Who goes up, who goes down',
      blurb: "how each post moves against today's law",
    },
    domenii: {
      label: 'Public sectors',
      blurb: 'education, health, justice, public order, defence, administration',
    },
    meserii: { label: 'Occupations, RO vs DK', blurb: 'what the same occupation earns in each country' },
    payslip: { label: 'One salary, calculated', blurb: 'one specific person, under each regime' },
    echivalente: { label: 'Post equivalences', blurb: 'which Danish title matches each position' },
    envelope: { label: 'What it all costs', blurb: 'the envelope, the 20% cap and who exceeds it' },
    functii: {
      label: 'Position by position',
      blurb: 'which titles each post absorbed, and what it pays in three systems',
    },
  },
  groups: {
    start: { title: 'Start here', ask: 'What is this?' },
    reform: { title: 'The reform', ask: 'What changes?' },
    alternative: { title: 'The alternative', ask: 'Could it be done differently?' },
    people: { title: 'The people', ask: 'Who earns what?' },
    money: { title: 'The money', ask: 'Can we afford it?' },
  },
  sections: 'Sections of the tool',
  share: 'copy the scenario link',
  copied: 'link copied',
  phaseLabel: 'Grid in year',
  phaseNote: (until) => `the draft is phased in: the top coefficients rise year by year until ${until}`,
  phaseColumn: (period) => `; column "${period}"`,
  loadError: (message) => `The data could not be loaded: ${message}`,
  retry: 'Try again',
  loading: 'Loading the grid…',
  dataLine: 'Data: MMFTSS, public package of 20.08.2026; IDA (Denmark), 01.04.2026',
  footerSource:
    'Source: the public MMFTSS package of 20.08.2026 and its coefficient annexes; for Denmark, the IDA tables of 01.04.2026. Every number in data/ carries the document and the article or cell it comes from.',
  footerCode: 'Code and data',
  footerLicence: 'Apache-2.0 licence.',
  switchTo: { lang: 'ro', label: 'Română' },
  viewsInRomanian:
    'The navigation is in English; the views themselves are in Romanian for now, as are the documents they read.',
};

export const STRINGS: Record<Lang, Strings> = { ro, en };

export function langOf(scenario: Scenario): Lang {
  return scenario.extra?.lang === 'en' ? 'en' : 'ro';
}

/** The scenario in another language. Romanian is the default, so it leaves no trace in the link. */
export function withLang(scenario: Scenario, lang: Lang): Scenario {
  const { lang: _previous, ...rest } = scenario.extra ?? {};
  const extra = lang === 'en' ? { ...rest, lang } : rest;
  return { ...scenario, extra: Object.keys(extra).length ? extra : undefined };
}

/** The engine's diagnostic severities as the (Romanian) views print them. */
export const SEVERITY_LABELS: Record<'blocking' | 'material' | 'note', string> = {
  blocking: 'blocant',
  material: 'important',
  note: 'de reținut',
};

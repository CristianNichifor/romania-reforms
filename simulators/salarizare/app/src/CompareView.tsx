import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Table } from '@cristiannichifor/civic-ui';

import { readCap } from '../../engine/cap';
import type { CapSeries } from '../../engine/cap';
import type { PatchEffect, Proposal } from '../../engine/proposal';
import { resolveSeries, structure } from '../../engine/structure';
import type { StructureMetrics } from '../../engine/structure';
import type { Regime } from '../../engine/types';
import type { Lang } from './i18n';
import { amountLine } from './money';
import type { Rates } from './money';

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

/** The annexes as a reader would name them, rather than as the importer keys them. */
const FAMILY_LABEL: Record<Lang, Record<string, string>> = {
  ro: {
    'I-invatamant': 'Anexa I — învățământ',
    'II-sanatate-asistenta-sociala': 'Anexa II — sănătate',
    'III-cultura': 'Anexa III — cultură',
    'IV-diplomatie': 'Anexa IV — diplomație',
    'V-justitie': 'Anexa V — justiție',
    'VI-aparare-ordine-securitate': 'Anexa VI — apărare și ordine publică',
    'VII-venituri-proprii': 'Anexa VII — venituri proprii',
    'VIII-administratie': 'Anexa VIII — administrație',
    'IX-demnitati-publice': 'Anexa IX — demnități publice',
  },
  en: {
    'I-invatamant': 'Annex I — education',
    'II-sanatate-asistenta-sociala': 'Annex II — health',
    'III-cultura': 'Annex III — culture',
    'IV-diplomatie': 'Annex IV — diplomacy',
    'V-justitie': 'Annex V — justice',
    'VI-aparare-ordine-securitate': 'Annex VI — defence and public order',
    'VII-venituri-proprii': 'Annex VII — own revenues',
    'VIII-administratie': 'Annex VIII — administration',
    'IX-demnitati-publice': 'Annex IX — public dignitaries',
  },
};

type Col = 'inForce' | 'ministry' | 'ours' | 'dk';
type RowKey = 'backSolved' | 'distinct' | 'positions' | 'fused' | 'gaps' | 'span' | 'years';

/** Every word this view prints, per language (RR-10). English copy is agent-written: needs human review. */
export interface CompareStrings {
  columns: Record<Col, { title: string; sub: string }>;
  oursSub: (repairs: number, changes: number) => string;
  title: string;
  purpose: (patches: string, questions: string) => string;
  briefTitle: string;
  reference: string;
  referenceBody: (one: string, twoAndHalf: string) => string;
  positions: string;
  positionsBody: (distinct: string) => string;
  span: string;
  spanBody: (period: string, lastPeriod: string, firstMove: string) => string;
  wholeGrid: string;
  lastYears: string;
  cap: string;
  capBody: string;
  capMeasured: (share: string) => ReactNode;
  amepipTitle: string;
  amepipLede: string;
  amepipMedian: string;
  amepipMedianBody: (tiers: string) => string;
  amepipTop: string;
  amepipTopBody: (toAvg: string, toPresident: string) => string;
  amepipExtreme: string;
  amepipExtremeBody: (toAvg: string) => string;
  amepipSource: ReactNode;
  heroWithLaw: (law: string, draft: string, times: string, backSolved: string, rounded: string) => string;
  heroWithoutLaw: (rest: string) => string;
  lawNotLoaded: string;
  dkNotLoaded: string;
  rows: Record<RowKey, { label: string; hint: string }>;
  notes: {
    lawTwoDecimals: string;
    dkStepsCarryAmount: string;
    fewer: (n: string) => string;
    dkTranscribed: (n: string) => string;
    merged: (n: string) => string;
    fewerSameTrade: (n: string) => string;
    dkTranscribedNotCount: string;
    upToHalf: string;
    explicitMultiplier: string;
    dkInstitutionLocal: string;
    lawNoGrades: string;
    dkEachStepAmount: string;
    lawSpanUndeclared: string;
    spanInPeriod: (period: string, last: string, lastPeriod: string) => string;
    spanFixed: string;
    dkSpanSample: (n: string) => string;
    lawPhasingEnded: string;
    dkRenegotiated: string;
  };
  sampledTitle: string;
  foot: (dkPositions: string, roPositions: string) => ReactNode;
  patchesTitle: string;
  touched: { positions: string; variants: string; grades: string; supplements: string };
  badgeChange: string;
  badgeRepair: string;
  why: string;
  tradesTitle: string;
  tradesLede: ReactNode;
  baseCoefficient: (value: string) => string;
  tradesTableLabel: string;
  tradesColumns: { absorbed: string; annex: string; coefficient: string; duty: string; residual: string };
  none: string;
  tradesSource: string;
  nextTitle: string;
  next: Record<'propunere' | 'structure' | 'payslip' | 'echivalente', { title: string; body: string }>;
}

export const COMPARE_STRINGS: Record<Lang, CompareStrings> = {
  ro: {
    columns: {
      inForce: { title: 'Legea în vigoare', sub: '153/2017, grila pentru 2022' },
      ministry: { title: 'Proiectul MMFTSS', sub: '20.08.2026' },
      ours: { title: 'Propunerea alternativă', sub: '' },
      dk: { title: 'Danemarca', sub: 'sectorul de stat' },
    },
    oursSub: (repairs, changes) =>
      `${repairs} ${repairs === 1 ? 'reparație' : 'reparații'} + ${changes} ${changes === 1 ? 'schimbare' : 'schimbări'}`,
    title: 'Patru feluri de a plăti statul',
    purpose: (patches, questions) =>
      `Ce se plătește azi, ce propune ministerul, ce s-ar schimba cu ${patches} corecturi, și cum arată sistemul danez. Aceleași ${questions} întrebări puse tuturor.`,
    briefTitle: 'Proiectul, pe scurt',
    reference: 'Valoarea de referință',
    referenceBody: (one, twoAndHalf) =>
      `Orice salariu de bază din sectorul public e această sumă înmulțită cu un coeficient. Un coeficient de 2,50 înseamnă ${twoAndHalf} brut pe lună.`.replace(' această sumă', ` această sumă (${one})`),
    positions: 'Funcții în grilă',
    positionsBody: (distinct) =>
      `Atâtea denumiri de post, cu ${distinct} coeficienți distincți între ele. Din tabelul ăsta iese salariul fiecărui angajat la stat.`,
    span: 'Între cel mai mic și cel mai mare',
    spanBody: (period, lastPeriod, firstMove) =>
      `Art. 5 promite 1 la 8, dar grila urcă an de an: raportul de mai sus e cel din ${period}, iar 1:8 se atinge abia în ${lastPeriod}. Mișcă anul de sus ca să vezi drumul — și observă că nu se schimbă nimic până în ${firstMove}: coeficienții eșalonați rămân sub o funcție care nu e eșalonată deloc.`,
    wholeGrid: 'grila întreagă',
    lastYears: 'ultimii ani',
    cap: 'Plafonul sporurilor',
    capBody: 'Atât pot adăuga sporurile peste salariile de bază — pe instituție și pe sursă de finanțare, nu pe om.',
    capMeasured: (share) => (
      <>
        {' '}
        Din execuția pe 2025, <strong>{share}</strong> din masa salarială de bază stă deja în instituții
        care trec de el.
      </>
    ),
    amepipTitle: 'Companii publice AMEPIP',
    amepipLede:
      'Scara publicată de companiidestat.ro pentru companiile de stat stă lângă grila publică doar ca reper de guvernanță. Datele de aici sunt agregate: fără rânduri nominale, CUI-uri sau liste de companii.',
    amepipMedian: 'Mediana treptelor fixe',
    amepipMedianBody: (tiers) =>
      `Calculată peste ${tiers} trepte fixe agregate. Nu spune cine ia suma, ci unde se așază scara publicată față de grila salarială.`,
    amepipTop: 'Vârful fix publicat',
    amepipTopBody: (toAvg, toPresident) =>
      `${toAvg}× salariul mediu brut 2025 și ${toPresident}× indemnizația Președintelui României.`,
    amepipExtreme: 'Cu bonus anual lunarizat',
    amepipExtremeBody: (toAvg) =>
      `Reper extrem lunarizat de sursă: ${toAvg}× salariul mediu brut 2025. Este context de guvernanță, nu coeficient de salarizare publică.`,
    amepipSource: (
      <>
        Sursă: API-ul public companiidestat.ro, transformat în serii agregate pentru
        <code> salarizare/data/fiscal/amepip-public-enterprise-compensation.json</code>.
      </>
    ),
    heroWithLaw: (law, draft, times, backSolved, rounded) =>
      `Legea în vigoare decide ${law} numere, toate tipărite cu două zecimale. Proiectul cere ${draft} — de ${times} ori mai multe — și ${backSolved} dintre ele au paisprezece zecimale sau mai multe. Nu e o grilă proiectată, ci una dedusă din salariile existente prin împărțire. Rotunjită la două zecimale, s-ar întoarce la ${rounded}.`,
    heroWithoutLaw: (rest) =>
      `Atâtea numere distincte are grila acum, și atâtea i-ar rămâne dacă ar fi rotunjită la două zecimale. Restul de ${rest} nu sunt decizii de politică salarială, ci resturi ale unei împărțiri.`,
    lawNotLoaded: 'legea în vigoare nu e încărcată',
    dkNotLoaded: 'regimul danez nu e încărcat',
    rows: {
      backSolved: { label: 'Coeficienți retro-calculați', hint: 'valori cu 14 zecimale sau mai multe — reziduul unei împărțiri, nu o decizie' },
      distinct: { label: 'Câte numere trebuie decise', hint: 'valori distincte în toată grila' },
      positions: { label: 'Posturi numite în grilă', hint: 'câte denumiri distincte de post apar în documentul oficial' },
      fused: { label: 'Funcții al căror nume ascunde instituția', hint: 'aceeași denumire, coeficienți diferiți după categoria instituției — nu după meserie' },
      gaps: { label: 'Coeficienți fără grad salarial', hint: 'cad în golurile dintre intervalele din Art. 9 alin. (2)' },
      span: { label: 'Distanța dintre cel mai mic și cel mai mare', hint: 'Art. 5 o fixează la 1 la 8' },
      years: { label: 'Ani până se aplică grila declarată', hint: 'câte coloane anuale trebuie parcurse' },
    },
    notes: {
      lawTwoDecimals: 'coeficienții sunt tipăriți cu două zecimale',
      dkStepsCarryAmount: 'treptele poartă direct suma',
      fewer: (n) => `cu ${n} mai puține`,
      dkTranscribed: (n) => `din ${n} posturi transcrise, nu din toată grila daneză`,
      merged: (n) => `${n} comasează mai multe denumiri`,
      fewerSameTrade: (n) => `cu ${n} mai puține — aceeași meserie, un singur nume`,
      dkTranscribedNotCount: 'atâtea am transcris din tabelele IDA — nu e numărul de posturi din Danemarca',
      upToHalf: 'până la ×1,5 sub același nume',
      explicitMultiplier: 'diferența devine un multiplicator explicit',
      dkInstitutionLocal: 'instituția se negociază local, nu intră în denumire',
      lawNoGrades: 'legea în vigoare nu declară grade salariale',
      dkEachStepAmount: 'fiecare treaptă e o sumă — deși scara sare peste treapta 3',
      lawSpanUndeclared: 'nedeclarat în lege; rezultă din anexe',
      spanInPeriod: (period, last, lastPeriod) => `în ${period}; ajunge la ${last} în ${lastPeriod}`,
      spanFixed: 'fix, nu se mai schimbă',
      dkSpanSample: (n) => `nedeclarat în lege; între extremele celor ${n} posturi transcrise`,
      lawPhasingEnded: 'eșalonarea din art. 38 s-a încheiat în 2022',
      dkRenegotiated: 'treptele se renegociază, nu se eșalonează în lege',
    },
    sampledTitle: 'eșantion, nu grilă întreagă',
    foot: (dkPositions, roPositions) => (
      <>
        Barele din fiecare rând sunt proporționale între ele, nu între rânduri. Unde nu există cifră,
        scrie de ce. Celulele cu <em className="sampled">*</em> vin dintr-un eșantion: regimul danez
        de aici are {dkPositions} posturi transcrise din tabelele IDA, față de {roPositions} în grila
        românească. Pentru o pondere asta nu contează, dar pentru un <em>număr</em> de posturi și
        pentru distanța dintre extremele lui contează decisiv — un tabel cu {dkPositions} rânduri va
        părea mereu mai simplu. De aceea acele celule nu câștigă rândul. Comparația daneză serioasă,
        pe câștiguri măsurate, e pe pagina „Meserii, RO vs DK”.
      </>
    ),
    patchesTitle: 'Corecturile propuse',
    touched: { positions: 'funcții', variants: 'variante', grades: 'grade', supplements: 'sporuri' },
    badgeChange: 'schimbă distribuția',
    badgeRepair: 'reparație',
    why: 'De ce',
    tradesTitle: 'Ce plătea anexa, și pentru ce',
    tradesLede: (
      <>
        Pentru meseriile manuale grila plătește anexa, nu meseria: același permis de conducere
        valorează cu 37% mai mult pe o autosanitară decât la o primărie mică, fără ca legea să
        numească vreo atribuție care să explice diferența. Mai jos, fiecare funcție absorbită în
        meserie: cât lua, ce atribuție declarată o justifică, și cât rămâne neexplicat.{' '}
        <b>Restul e rezultatul</b> — acolo unde e mic, anexa plătea ceva ce se poate numi; acolo unde e
        mare, plătea faptul că postul e trecut în altă anexă.
      </>
    ),
    baseCoefficient: (value) => `coeficient de bază ${value}`,
    tradesTableLabel: 'Comparația regimurilor salariale',
    tradesColumns: { absorbed: 'Funcția absorbită', annex: 'Anexa', coefficient: 'Coeficient', duty: 'Atribuție declarată', residual: 'Rest neexplicat' },
    none: 'niciuna',
    tradesSource:
      'Cuantumurile atribuțiilor sunt scrise de noi, nu citite din caietul ministerului — sursa nu conține niciun spor de acest fel. Reperul e cota sporului de condiții măsurată în Danemarca: 8,8% la personalul de îngrijire, 4,9% la polițiști, 0,2% la profesori. Fiecare atribuție e marcată „assumed” în regim și poate fi contestată separat de restul propunerii.',
    nextTitle: 'Mai departe',
    next: {
      propunere: { title: 'Propunerea, corectură cu corectură', body: 'Fiecare modificare cu întrerupătorul ei — stinge una și restul se recalculează' },
      structure: { title: 'Cum e construită grila', body: 'Zecimalele, golurile dintre grade, funcțiile comasate' },
      payslip: { title: 'Un salariu, calculat', body: 'Un om anume, sub fiecare regim, cu linkul scenariului' },
      echivalente: { title: 'Echivalențe de post', body: 'Ce denumire daneză corespunde fiecărei funcții din grilă' },
    },
  },
  en: {
    columns: {
      inForce: { title: 'The law in force', sub: '153/2017, the grid for 2022' },
      ministry: { title: 'The MMFTSS draft', sub: '20.08.2026' },
      ours: { title: 'The alternative proposal', sub: '' },
      dk: { title: 'Denmark', sub: 'the state sector' },
    },
    oursSub: (repairs, changes) =>
      `${repairs} ${repairs === 1 ? 'repair' : 'repairs'} + ${changes} ${changes === 1 ? 'change' : 'changes'}`,
    title: 'Four ways of paying the state',
    purpose: (patches, questions) =>
      `What is paid today, what the ministry proposes, what would change with ${patches} corrections, and what the Danish system looks like. The same ${questions} questions put to all of them.`,
    briefTitle: 'The draft, in brief',
    reference: 'The reference value',
    referenceBody: (one, twoAndHalf) =>
      `Every base salary in the public sector is this amount (${one}) multiplied by a coefficient. A coefficient of 2.50 means ${twoAndHalf} gross a month.`,
    positions: 'Positions in the grid',
    positionsBody: (distinct) =>
      `That many position titles, with ${distinct} distinct coefficients between them. Every state employee's salary comes out of this table.`,
    span: 'Between the lowest and the highest',
    spanBody: (period, lastPeriod, firstMove) =>
      `Art. 5 promises 1 to 8, but the grid climbs year by year: the ratio above is the one for ${period}, and 1:8 is reached only in ${lastPeriod}. Move the year at the top to see the path — and notice that nothing changes until ${firstMove}: the phased coefficients stay below a position that is not phased at all.`,
    wholeGrid: 'the whole grid',
    lastYears: 'the last years',
    cap: 'The cap on supplements',
    capBody: 'That is how much supplements may add on top of base salaries — per institution and per funding source, not per person.',
    capMeasured: (share) => (
      <>
        {' '}
        From the 2025 execution, <strong>{share}</strong> of the base wage bill already sits in
        institutions that exceed it.
      </>
    ),
    amepipTitle: 'AMEPIP public enterprises',
    amepipLede:
      'The scale published by companiidestat.ro for state-owned companies sits beside the public grid only as a governance reference. The data here are aggregated: no named rows, tax identifiers or company lists.',
    amepipMedian: 'Median of the fixed tiers',
    amepipMedianBody: (tiers) =>
      `Computed over ${tiers} aggregated fixed tiers. It does not say who receives the amount, but where the published scale sits against the pay grid.`,
    amepipTop: 'The published fixed top',
    amepipTopBody: (toAvg, toPresident) =>
      `${toAvg}× the 2025 gross average wage and ${toPresident}× the allowance of the President of Romania.`,
    amepipExtreme: 'With the annual bonus spread monthly',
    amepipExtremeBody: (toAvg) =>
      `The source's extreme reference, spread monthly: ${toAvg}× the 2025 gross average wage. It is governance context, not a public pay coefficient.`,
    amepipSource: (
      <>
        Source: the public companiidestat.ro API, transformed into aggregated series for
        <code> salarizare/data/fiscal/amepip-public-enterprise-compensation.json</code>.
      </>
    ),
    heroWithLaw: (law, draft, times, backSolved, rounded) =>
      `The law in force decides ${law} numbers, all printed with two decimals. The draft needs ${draft} — ${times} times as many — and ${backSolved} of them have fourteen decimals or more. It is not a designed grid but one deduced from existing salaries by division. Rounded to two decimals, it would go back to ${rounded}.`,
    heroWithoutLaw: (rest) =>
      `That many distinct numbers the grid has now, and that many it would keep if rounded to two decimals. The remaining ${rest} are not pay-policy decisions but the remainders of a division.`,
    lawNotLoaded: 'the law in force is not loaded',
    dkNotLoaded: 'the Danish regime is not loaded',
    rows: {
      backSolved: { label: 'Back-solved coefficients', hint: 'values with 14 decimals or more — the residue of a division, not a decision' },
      distinct: { label: 'How many numbers have to be decided', hint: 'distinct values across the grid' },
      positions: { label: 'Posts named in the grid', hint: 'how many distinct post titles appear in the official document' },
      fused: { label: 'Positions whose name hides the institution', hint: 'the same title, different coefficients by institution category — not by trade' },
      gaps: { label: 'Coefficients without a pay grade', hint: 'they fall in the gaps between the ranges of Art. 9 (2)' },
      span: { label: 'Distance between the lowest and the highest', hint: 'Art. 5 fixes it at 1 to 8' },
      years: { label: 'Years until the declared grid applies', hint: 'how many annual columns have to be gone through' },
    },
    notes: {
      lawTwoDecimals: 'the coefficients are printed with two decimals',
      dkStepsCarryAmount: 'the steps carry the amount directly',
      fewer: (n) => `${n} fewer`,
      dkTranscribed: (n) => `from ${n} transcribed posts, not from the whole Danish grid`,
      merged: (n) => `${n} merge several titles`,
      fewerSameTrade: (n) => `${n} fewer — the same trade, a single name`,
      dkTranscribedNotCount: 'that many we transcribed from the IDA tables — not the number of posts in Denmark',
      upToHalf: 'up to ×1.5 under the same name',
      explicitMultiplier: 'the difference becomes an explicit multiplier',
      dkInstitutionLocal: 'the institution is negotiated locally, it does not enter the title',
      lawNoGrades: 'the law in force declares no pay grades',
      dkEachStepAmount: 'every step is an amount — though the scale skips step 3',
      lawSpanUndeclared: 'not declared in the law; it follows from the annexes',
      spanInPeriod: (period, last, lastPeriod) => `in ${period}; it reaches ${last} in ${lastPeriod}`,
      spanFixed: 'fixed, it no longer changes',
      dkSpanSample: (n) => `not declared in the law; between the extremes of the ${n} transcribed posts`,
      lawPhasingEnded: 'the phasing of Art. 38 ended in 2022',
      dkRenegotiated: 'the steps are renegotiated, not phased in by law',
    },
    sampledTitle: 'a sample, not the whole grid',
    foot: (dkPositions, roPositions) => (
      <>
        The bars in each row are proportional to each other, not across rows. Where there is no
        figure, it says why. Cells marked <em className="sampled">*</em> come from a sample: the Danish
        regime here has {dkPositions} posts transcribed from the IDA tables, against {roPositions} in
        the Romanian grid. For a share that does not matter, but for a <em>count</em> of posts and
        for the distance between its extremes it matters decisively — a table with {dkPositions} rows
        will always look simpler. That is why those cells do not win the row. The serious Danish
        comparison, on measured earnings, is on the "Occupations, RO vs DK" page.
      </>
    ),
    patchesTitle: 'The proposed corrections',
    touched: { positions: 'positions', variants: 'variants', grades: 'grades', supplements: 'supplements' },
    badgeChange: 'changes the distribution',
    badgeRepair: 'repair',
    why: 'Why',
    tradesTitle: 'What the annex paid, and for what',
    tradesLede: (
      <>
        For manual trades the grid pays the annex, not the trade: the same driving licence is worth
        37% more on an ambulance than at a small town hall, without the law naming any duty that
        would explain the difference. Below, every position absorbed into the trade: what it earned,
        which declared duty justifies it, and how much remains unexplained. <b>The remainder is the
        result</b> — where it is small, the annex paid for something that can be named; where it is
        large, it paid for the post being listed in another annex.
      </>
    ),
    baseCoefficient: (value) => `base coefficient ${value}`,
    tradesTableLabel: 'Comparison of the pay regimes',
    tradesColumns: { absorbed: 'Absorbed position', annex: 'Annex', coefficient: 'Coefficient', duty: 'Declared duty', residual: 'Unexplained remainder' },
    none: 'none',
    tradesSource:
      'The duty rates are written by us, not read from the ministry\'s workbook — the source contains no supplement of this kind. The reference is the share of the conditions supplement measured in Denmark: 8.8% for care staff, 4.9% for police officers, 0.2% for teachers. Every duty is marked "assumed" in the regime and can be contested separately from the rest of the proposal.',
    nextTitle: 'Further',
    next: {
      propunere: { title: 'The proposal, one correction at a time', body: 'Every change with its own switch — turn one off and the rest is recomputed' },
      structure: { title: 'How the grid is built', body: 'The decimals, the gaps between grades, the merged positions' },
      payslip: { title: 'One salary, computed', body: 'One specific person, under each regime, with the scenario link' },
      echivalente: { title: 'Position equivalences', body: 'Which Danish title matches each position in the grid' },
    },
  },
};

interface Cell {
  /** What the bar is drawn from. null renders as an explained dash, never as zero. */
  n: number | null;
  text: string;
  note?: string;
  /**
   * The figure comes from a sample too thin to be scored against a full grid.
   *
   * The Danish regime is 16 hand-built positions against Romania's 1 049. For a share
   * that does not matter — 0% back-solved is 0% either way. For a *count*, and for a
   * span computed from the extremes of a count, it decides the answer: a 16-row table
   * will always look simpler than a 1 049-row one, partly because it is and partly
   * because it is 16 rows. Such a cell still shows its number, but never wins the row.
   */
  sampled?: boolean;
}
interface Row {
  key: RowKey;
  /** Which direction is an improvement, for the one mark of emphasis per row. */
  better: 'lower' | 'higher' | 'none';
  cells: Record<Col, Cell>;
}

export interface PublicEnterpriseCompensationDoc {
  retrieved: string;
  series: Array<{
    id: string;
    unit: string;
    observations: Array<{ period: string; value: number | null }>;
  }>;
}

/**
 * The proposal's subtitle counts its own patches. Written by hand it said "cinci
 * reparații + o schimbare" while the file held six repairs and one change, and the
 * masthead promised six questions against a table of seven rows. Counts that describe
 * data belong to the data.
 */
function columnsFor(proposal: Proposal, t: CompareStrings): Array<{ key: Col; title: string; sub: string }> {
  const changes = proposal.patches.filter((p) => p.policyChange).length;
  const repairs = proposal.patches.length - changes;
  return (['inForce', 'ministry', 'ours', 'dk'] as const).map((key) => ({
    key,
    title: t.columns[key].title,
    sub: key === 'ours' ? t.oursSub(repairs, changes) : t.columns[key].sub,
  }));
}

/**
 * Positions whose variants differ only by where the post sits, not by what the job is.
 *
 * Kept in step with `separateInstitutionFactor`, which is what the count is counting:
 * `celula` is not context, it is the importer saying it could not tell two rows apart.
 */
function fusedCount(regime: Regime): number {
  const context = new Set(['institutionLevel', 'sursa']);
  return regime.positions.filter((p) => {
    if (p.variants.length < 2) return false;
    const jobs = new Set(
      p.variants.map((v) =>
        JSON.stringify(Object.entries(v.dims ?? {}).filter(([k]) => !context.has(k)).sort()),
      ),
    );
    return (
      jobs.size === 1 &&
      p.variants.some((v) => Object.keys(v.dims ?? {}).some((k) => context.has(k)))
    );
  }).length;
}

export default function CompareView({
  menu,
  ministry,
  inForce,
  ours,
  denmark,
  proposal,
  effects,
  onOpen,
  rates,
  capSeries,
  period,
  amepipCompensation,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  ministry: Regime;
  /** Law 153/2017 — what people are paid under today. */
  inForce: Regime | null;
  ours: Regime;
  denmark: Regime | null;
  proposal: Proposal;
  effects: PatchEffect[];
  onOpen: (view: 'structure' | 'payslip' | 'echivalente' | 'propunere') => void;
  rates: Rates;
  capSeries: CapSeries[] | null;
  period: string | null;
  amepipCompensation: PublicEnterpriseCompensationDoc | null;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = COMPARE_STRINGS[lang];
  const locale = LOCALE[lang];
  const families = FAMILY_LABEL[lang];
  const n = (value: number) => value.toLocaleString(locale);
  const pct = (value: number) => `${(value * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}%`;
  const ratio = (value: number) =>
    `1:${value.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const num = (value: number) => value.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money = (value: number) => amountLine(value, 'RON', rates, 'native', locale);

  const COLUMNS = useMemo(() => columnsFor(proposal, t), [proposal, t]);

  // Trades the proposal stopped paying by annex, with what each absorbed post used to
  // earn. Read off the applied regime rather than recomputed here, so the table cannot
  // disagree with the patch that produced it.
  const tradeFolds = useMemo(
    () =>
      ours.positions
        .filter((p) => p.tradeFold?.length)
        .map((position) => ({ position, folds: position.tradeFold! })),
    [ours],
  );
  const dutyName = useMemo(() => {
    const byId = new Map(
      (proposal.patches.flatMap((p) => p.trades ?? []) ?? []).flatMap((t) =>
        t.duties.map((d) => [d.id, d.name] as const),
      ),
    );
    return (id: string) => byId.get(id) ?? id;
  }, [proposal]);
  const opts = period ? { period } : undefined;
  const m = useMemo(() => structure(ministry, opts), [ministry, period]);
  const o = useMemo(() => structure(ours, opts), [ours, period]);
  // The whole schedule, unfiltered: "how many annual columns are there" is a fact about
  // the law, not about the year being viewed, and filtering would always answer one.
  const schedule = useMemo(() => structure(ministry).spanByPeriod, [ministry]);
  const f: StructureMetrics | null = useMemo(
    () => (inForce ? structure(inForce) : null),
    [inForce],
  );

  // 153/2017 declares no salary grades and phases nothing, so two of the seven questions
  // have no answer for it. An explained dash, never a zero that reads as "none".
  const lawCell = (value: number | null, text: string, note?: string): Cell =>
    f ? { n: value, text, note } : { n: null, text: '—', note: t.lawNotLoaded };
  // The first column where the ratio actually moves. It is not the second: the phased
  // dignitary coefficients stay below a post that is not phased at all, so the eșalonare
  // is invisible for its first years — which is only visible if you can step through them.
  const firstMove = useMemo(
    () => schedule.find((p) => p.ratio > (schedule[0]?.ratio ?? 0)) ?? null,
    [schedule],
  );
  const d: StructureMetrics | null = useMemo(
    () => (denmark ? structure(denmark) : null),
    [denmark],
  );

  // The reference value is a dated series, not a constant: read it at the date the draft
  // itself sets rather than assuming the first entry is the one in force.
  const referenceAmount = useMemo(
    () => resolveSeries(ministry.reference.amount, ministry.reference.baseDate),
    [ministry],
  );
  const amepip = useMemo(() => {
    if (!amepipCompensation) return null;
    const value = (id: string) =>
      amepipCompensation.series.find((s) => s.id === id)?.observations.at(-1)?.value ?? null;
    const fixedMedian = value('companiidestat-pay-scale-fixed-median');
    const fixedTop = value('companiidestat-pay-scale-fixed-top');
    const extreme = value('companiidestat-pay-scale-extreme-monthly-equivalent');
    if (fixedMedian === null || fixedTop === null || extreme === null) return null;
    return {
      retrieved: amepipCompensation.retrieved,
      fixedMedian,
      fixedTop,
      extreme,
      fixedTierCount: value('companiidestat-pay-scale-fixed-tier-count') ?? 0,
      fixedTopToAvg: value('companiidestat-pay-scale-fixed-top-to-average-gross') ?? 0,
      extremeToAvg: value('companiidestat-pay-scale-extreme-to-average-gross') ?? 0,
      fixedTopToPresident: value('companiidestat-pay-scale-fixed-top-to-president') ?? 0,
    };
  }, [amepipCompensation]);

  /** How much of the base wage bill already sits above the 20% ceiling, if measured. */
  const overCapWeight = useMemo(() => {
    const reading = capSeries && readCap(capSeries, 'pereche', 'wide');
    return reading ? reading.overCapWeight : null;
  }, [capSeries]);

  // Denmark's figures are computed from its own imported tables, not typed in by hand,
  // so they move if the import changes and cannot quietly go stale.
  const dkCell = (value: number | null, text: string, note?: string): Cell =>
    d ? { n: value, text, note } : { n: null, text: '—', note: t.dkNotLoaded };

  /** The same, for rows where the count of Danish rows is what produces the number. */
  const dkSample = (value: number | null, text: string, note?: string): Cell =>
    d ? { n: value, text, note, sampled: true } : { n: null, text: '—', note: t.dkNotLoaded };

  const lastPeriod = schedule[schedule.length - 1]?.period ?? '';
  const rows: Row[] = [
    {
      key: 'backSolved',
      better: 'lower',
      cells: {
        inForce: lawCell(f?.backSolvedShare ?? 0, pct(f?.backSolvedShare ?? 0), t.notes.lawTwoDecimals),
        ministry: { n: m.backSolvedShare, text: pct(m.backSolvedShare) },
        ours: { n: o.backSolvedShare, text: pct(o.backSolvedShare) },
        dk: dkCell(d?.backSolvedShare ?? 0, pct(d?.backSolvedShare ?? 0), t.notes.dkStepsCarryAmount),
      },
    },
    {
      key: 'distinct',
      better: 'lower',
      cells: {
        inForce: lawCell(f?.distinctValues ?? null, n(f?.distinctValues ?? 0)),
        ministry: { n: m.distinctValues, text: n(m.distinctValues) },
        ours: { n: o.distinctValues, text: n(o.distinctValues), note: t.notes.fewer(n(m.distinctValues - o.distinctValues)) },
        dk: dkSample(d?.distinctValues ?? null, n(d?.distinctValues ?? 0), t.notes.dkTranscribed(n(d?.positions ?? 0))),
      },
    },
    {
      key: 'positions',
      // Fewer is better here: the draft names a job once per employer, so a high count
      // measures how many institutions there are rather than how many occupations.
      better: 'lower',
      cells: {
        inForce: lawCell(f?.positions ?? null, n(f?.positions ?? 0)),
        ministry: { n: m.positions, text: n(m.positions), note: t.notes.merged(n(m.assimilation.mergedPositions)) },
        ours: { n: o.positions, text: n(o.positions), note: t.notes.fewerSameTrade(n(m.positions - o.positions)) },
        dk: dkSample(d?.positions ?? null, n(d?.positions ?? 0), t.notes.dkTranscribedNotCount),
      },
    },
    {
      key: 'fused',
      better: 'lower',
      cells: {
        inForce: lawCell(inForce ? fusedCount(inForce) : null, inForce ? n(fusedCount(inForce)) : '—'),
        ministry: { n: fusedCount(ministry), text: n(fusedCount(ministry)), note: t.notes.upToHalf },
        ours: { n: fusedCount(ours), text: n(fusedCount(ours)), note: t.notes.explicitMultiplier },
        dk: dkCell(0, '0', t.notes.dkInstitutionLocal),
      },
    },
    {
      key: 'gaps',
      better: 'lower',
      cells: {
        inForce: lawCell(null, '—', t.notes.lawNoGrades),
        ministry: { n: m.variantsInGaps, text: n(m.variantsInGaps) },
        ours: { n: o.variantsInGaps, text: n(o.variantsInGaps) },
        dk: dkCell(0, '0', t.notes.dkEachStepAmount),
      },
    },
    {
      key: 'span',
      better: 'none',
      cells: {
        inForce: lawCell(f?.span.ratio ?? null, ratio(f?.span.ratio ?? 0), t.notes.lawSpanUndeclared),
        ministry: {
          n: m.span.ratio,
          text: ratio(m.span.ratio),
          note: period
            ? t.notes.spanInPeriod(period, ratio(schedule[schedule.length - 1]?.ratio ?? m.span.ratio), lastPeriod)
            : undefined,
        },
        ours: { n: o.span.ratio, text: ratio(o.span.ratio), note: t.notes.spanFixed },
        dk: dkSample(d?.span.ratio ?? null, ratio(d?.span.ratio ?? 0), t.notes.dkSpanSample(n(d?.positions ?? 0))),
      },
    },
    {
      key: 'years',
      better: 'lower',
      cells: {
        inForce: lawCell(0, '0', t.notes.lawPhasingEnded),
        ministry: { n: schedule.length, text: n(schedule.length) },
        ours: { n: 0, text: '0' },
        dk: dkCell(0, '0', t.notes.dkRenegotiated),
      },
    },
  ];

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.purpose(n(proposal.patches.length), n(rows.length))}</p>
      </header>
      {menu}

      {/* Before any structural metric, the four facts a reader needs to hold the rest in
          their head: what a salary is made of, how many there are, how far apart, and how
          much can be added on top. Everything below is a detail of one of these. */}
      <section>
        <h2>{t.briefTitle}</h2>
        <div className="brief">
          <div className="brief-card">
            <span className="brief-num">{money(referenceAmount)}</span>
            <strong>{t.reference}</strong>
            <p>{t.referenceBody(money(referenceAmount), money(referenceAmount * 2.5))}</p>
          </div>
          <div className="brief-card">
            <span className="brief-num">{n(m.positions)}</span>
            <strong>{t.positions}</strong>
            <p>{t.positionsBody(n(m.distinctValues))}</p>
          </div>
          <div className="brief-card">
            <span className="brief-num">{ratio(m.span.ratio)}</span>
            <strong>{t.span}</strong>
            <p>{t.spanBody(period ?? t.wholeGrid, lastPeriod || '2031', firstMove?.period ?? t.lastYears)}</p>
          </div>
          <div className="brief-card">
            <span className="brief-num">20%</span>
            <strong>{t.cap}</strong>
            <p>
              {t.capBody}
              {overCapWeight !== null && t.capMeasured(pct(overCapWeight))}
            </p>
          </div>
        </div>
      </section>

      {amepip && (
        <section>
          <h2>{t.amepipTitle}</h2>
          <p className="lede">{t.amepipLede}</p>
          <div className="brief">
            <div className="brief-card">
              <span className="brief-num">{money(amepip.fixedMedian)}</span>
              <strong>{t.amepipMedian}</strong>
              <p>{t.amepipMedianBody(n(amepip.fixedTierCount))}</p>
            </div>
            <div className="brief-card">
              <span className="brief-num">{money(amepip.fixedTop)}</span>
              <strong>{t.amepipTop}</strong>
              <p>{t.amepipTopBody(num(amepip.fixedTopToAvg), num(amepip.fixedTopToPresident))}</p>
            </div>
            <div className="brief-card">
              <span className="brief-num">{money(amepip.extreme)}</span>
              <strong>{t.amepipExtreme}</strong>
              <p>{t.amepipExtremeBody(num(amepip.extremeToAvg))}</p>
            </div>
          </div>
          <p className="src">{t.amepipSource}</p>
        </section>
      )}

      <section className="hero">
        <div className="hero-figure">
          {f && (
            <>
              <span className="from">{n(f.distinctValues)}</span>
              <span className="arrow">→</span>
            </>
          )}
          <span className="to">{n(m.distinctValues)}</span>
          <span className="arrow">→</span>
          <span className="from">{n(o.distinctValues)}</span>
        </div>
        <p className="hero-text">
          {f
            ? t.heroWithLaw(
                n(f.distinctValues),
                n(m.distinctValues),
                (m.distinctValues / f.distinctValues).toLocaleString(locale, { maximumFractionDigits: 1 }),
                pct(m.backSolvedShare),
                n(o.distinctValues),
              )
            : t.heroWithoutLaw(n(m.distinctValues - o.distinctValues))}
        </p>
      </section>

      <section>
        <div className="cmp">
          <div className="cmp-head">
            <div />
            {COLUMNS.map((c) => (
              <div key={c.key} className={`cmp-col col-${c.key}`}>
                <span className="col-title">{c.title}</span>
                <span className="col-sub">{c.sub}</span>
              </div>
            ))}
          </div>

          {rows.map((row) => {
            const values = COLUMNS.map((c) => row.cells[c.key].n).filter(
              (v): v is number => v !== null,
            );
            // A sampled cell is drawn and labelled but kept out of the contest: it
            // cannot win a row whose metric is a function of how many rows there are.
            const contested = COLUMNS.map((c) => row.cells[c.key])
              .filter((cell) => !cell.sampled)
              .map((cell) => cell.n)
              .filter((v): v is number => v !== null);
            const max = Math.max(...values, 1e-9);
            const best =
              row.better === 'none' || contested.length === 0
                ? null
                : row.better === 'lower'
                  ? Math.min(...contested)
                  : Math.max(...contested);

            return (
              <div key={row.key} className="cmp-row">
                <div className="cmp-label">
                  <strong>{t.rows[row.key].label}</strong>
                  <span className="hint">{t.rows[row.key].hint}</span>
                </div>
                {COLUMNS.map((c) => {
                  const cell = row.cells[c.key];
                  const isBest =
                    best !== null && cell.n !== null && cell.n === best && !cell.sampled;
                  return (
                    <div key={c.key} className={`cmp-cell col-${c.key}`}>
                      <div className="cmp-track">
                        <div
                          className={`cmp-fill fill-${c.key}`}
                          style={{
                            width: cell.n === null ? 0 : `${Math.max((cell.n / max) * 100, 2)}%`,
                          }}
                        />
                      </div>
                      <span className={`cmp-value${isBest ? ' best' : ''}`}>
                        {cell.text}
                        {cell.sampled && <em className="sampled" title={t.sampledTitle}>*</em>}
                      </span>
                      {cell.note && <span className="cmp-note">{cell.note}</span>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
        <p className="cmp-foot">{t.foot(n(d?.positions ?? 0), n(m.positions))}</p>
      </section>

      <section>
        <h2>{t.patchesTitle}</h2>
        <p className="lede">{proposal.notPolicy}</p>
        <ol className="patches">
          {proposal.patches.map((patch) => {
            const effect = effects.find((e) => e.patchId === patch.id);
            const touched = effect
              ? [
                  effect.positionsTouched && `${n(effect.positionsTouched)} ${t.touched.positions}`,
                  effect.variantsTouched && `${n(effect.variantsTouched)} ${t.touched.variants}`,
                  effect.gradesTouched && `${n(effect.gradesTouched)} ${t.touched.grades}`,
                  effect.supplementsTouched && `${n(effect.supplementsTouched)} ${t.touched.supplements}`,
                ]
                  .filter(Boolean)
                  .join(' · ')
              : '';
            return (
              <li key={patch.id} className="card patch">
                <div className="patch-head">
                  <h3>{patch.title}</h3>
                  <span className="patch-tags">
                    {patch.policyChange ? (
                      <span className="badge weak">{t.badgeChange}</span>
                    ) : (
                      <span className="badge">{t.badgeRepair}</span>
                    )}
                    {touched && <span className="touched">{touched}</span>}
                  </span>
                </div>
                {patch.expectedEffect && <p className="effect">{patch.expectedEffect}</p>}
                <details>
                  <summary>{t.why}</summary>
                  <p>{patch.rationale}</p>
                </details>
              </li>
            );
          })}
        </ol>
      </section>

      {tradeFolds.length > 0 && (
        <section>
          <h2>{t.tradesTitle}</h2>
          <p className="lede">{t.tradesLede}</p>
          {tradeFolds.map(({ position, folds }) => (
            <div className="card" key={position.code}>
              <h3>
                {position.name}{' '}
                <small>{t.baseCoefficient(num(Math.min(...position.variants.map((v) => Number(v.value ?? 0)))))}</small>
              </h3>
              <Table className="data comparison-data" label={t.tradesTableLabel}>
                <thead>
                  <tr>
                    <th>{t.tradesColumns.absorbed}</th>
                    <th>{t.tradesColumns.annex}</th>
                    <th className="num">{t.tradesColumns.coefficient}</th>
                    <th>{t.tradesColumns.duty}</th>
                    <th className="num">{t.tradesColumns.residual}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...folds]
                    .sort((a, b) => b.residual - a.residual)
                    .map((fold) => (
                      <tr key={fold.code}>
                        <td>{fold.name}</td>
                        <td>{families[fold.family] ?? fold.family}</td>
                        <td className="num">{num(fold.was)}</td>
                        <td>
                          {fold.duties.length
                            ? `${dutyName(fold.duties[0])} · +${pct(fold.dutyRate)}`
                            : <span className="muted">{t.none}</span>}
                        </td>
                        <td className="num">
                          <b>+{pct(fold.residual)}</b>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </Table>
            </div>
          ))}
          <p className="src">{t.tradesSource}</p>
        </section>
      )}

      <section>
        <h2>{t.nextTitle}</h2>
        <div className="next-grid">
          {(['propunere', 'structure', 'payslip', 'echivalente'] as const).map((view) => (
            <button key={view} className="next" onClick={() => onOpen(view)}>
              <strong>{t.next[view].title}</strong>
              <span>{t.next[view].body}</span>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

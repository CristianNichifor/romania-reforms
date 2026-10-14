import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Table } from '@cristiannichifor/civic-ui';

import { structure } from '../../engine/structure';
import { Term } from './Glossary';
import type { Regime } from '../../engine/types';
import { ColumnChart, GradeChart, SpanChart } from './charts';
import type { Bar } from './charts';
import type { Lang } from './i18n';

/** Every word this view prints, per language (RR-10). Sentences that embed glossary terms are
 *  render functions; the rest are strings. English copy is agent-written: needs human review. */
export interface StructureStrings {
  title: string;
  lead: string;
  srcLine: (positions: string, variants: string) => ReactNode;
  disclaimer: ReactNode;
  whatGrid: string;
  kpiBackSolved: ReactNode;
  kpiDistinct: string;
  kpiRounded: string;
  kpiGaps: ReactNode;
  kpiMerged: string;
  precisionTitle: string;
  precisionLede: string;
  precisionY: string;
  precisionSource: string;
  decimals: (dp: number) => string;
  distinctValues: (count: string) => string;
  backSolvedHint: string;
  roundedHint: string;
  intermediateHint: string;
  backSolved: string;
  rounded: string;
  intermediate: string;
  seeTable: string;
  precisionTable: string;
  colDecimals: string;
  colDistinct: string;
  colReading: string;
  spanTitle: string;
  spanLede: (inForce: { ratio: string; period: string } | null, atEnd: { ratio: string; period: string } | null) => string;
  spanSource: string;
  spanAxisNote: string;
  gapsTitle: string;
  gapsLede: (variants: string) => ReactNode;
  gapsSource: string;
  seeGaps: string;
  gapsTable: string;
  colBetween: string;
  colInterval: string;
  colVariants: string;
  gapRange: (from: number, to: number) => string;
  mergeTitle: string;
  mergeLede: (merged: string, needsReview: string) => ReactNode;
  mergeY: string;
  mergeSource: string;
  mergeNote: (singles: string) => string;
  oneName: string;
  mergedNames: (n: number) => string;
  positions: (count: string) => string;
  limitsTitle: string;
  limitsLede: string;
  blocking: string;
  material: string;
}

const LOCALE: Record<Lang, string> = { ro: 'ro-RO', en: 'en-GB' };

export const STRUCTURE_STRINGS: Record<Lang, StructureStrings> = {
  ro: {
    title: 'Forma sistemului de salarizare',
    lead:
      'Structura grilei din proiectul de lege privind salarizarea personalului plătit din fonduri publice, 20.08.2026. Nu cuantumuri, ci formă: câte valori distincte are grila, cât de precise sunt, cât de departe stau capetele, câtă informație despre ocupații se pierde prin comasare.',
    srcLine: (positions, variants) => (
      <>
        {positions} funcții · {variants} variante de coeficient · generate din{' '}
        <code>Proiect-COEFICIENTI-1-8-20-august-2026.xlsx</code>, 49 de foi.
      </>
    ),
    disclaimer: (
      <>
        <strong>Instrument pentru dezbatere publică, nu calculator de salarii.</strong> Arată ce spune
        un proiect de lege, nu ce încasează cineva. Datele individuale de salarizare nu sunt publicate
        în România, deci nicio cifră de aici nu descrie o persoană. Diferența salarială tranzitorie de
        la Art. 33 — care în primii ani domină factura reală — nu poate fi calculată deloc.
      </>
    ),
    whatGrid: 'Ce arată grila',
    kpiBackSolved: (
      <>
        din <Term id="coeficient">coeficienții</Term> distincți au 14 zecimale sau mai multe —{' '}
        <Term id="coeficient-retrocalculat">retro-calculați</Term>, nu proiectați
      </>
    ),
    kpiDistinct: 'valori distincte de coeficient în toată grila',
    kpiRounded: 'sunt rotunjite la două zecimale',
    kpiGaps: (
      <>
        variante cad între <Term id="grad-salarial">gradele salariale</Term>, în niciunul
      </>
    ),
    kpiMerged: 'funcții comasează două sau mai multe denumiri anterioare',
    precisionTitle: 'Coeficienții sunt retro-calculați, nu proiectați',
    precisionLede:
      'O grilă proiectată produce numere ca 2,40 sau 3,29. Una obținută împărțind un salariu la altul produce 5,189610389610378. Distribuția de mai jos numără valorile distincte după câte zecimale poartă: bara de la 16 zecimale este de peste trei ori mai mare decât toate valorile rotunjite la loc.',
    precisionY: 'valori distincte',
    precisionSource: 'valorile distincte ale coeficienților din anexe',
    decimals: (dp) => `${dp} zecimale`,
    distinctValues: (count) => `${count} valori distincte`,
    backSolvedHint: 'retro-calculat dintr-un salariu existent',
    roundedHint: 'rotunjit — o valoare aleasă',
    intermediateHint: 'intermediar',
    backSolved: 'retro-calculat',
    rounded: 'rotunjit',
    intermediate: 'intermediar',
    seeTable: 'Vezi datele ca tabel',
    precisionTable: 'Distribuția coeficienților',
    colDecimals: 'Zecimale',
    colDistinct: 'Valori distincte',
    colReading: 'Interpretare',
    spanTitle: 'Raportul de 1 la 8 este destinația unui eșalonament',
    spanLede: (inForce, atEnd) =>
      `Art. 5 fixează raportul dintre cel mai mic și cel mai mare salariu de bază la 1 la 8. Anexa IX eșalonează coeficienții demnitarilor pe cinci coloane anuale, așa că raportul se mișcă: ${inForce ? `este 1:${inForce.ratio} în ${inForce.period}` : ''}${atEnd ? ` și atinge exact 1:${atEnd.ratio} în ${atEnd.period}` : ''}. Vârful grilei în primii ani nu aparține unei funcții alese, ci unei funcții de manager TIC din Anexa VIII, cu coeficient 7,3919.`,
    spanSource: 'Art. 5 și coloanele anuale din anexe',
    spanAxisNote:
      'Axa verticală este decupată în jurul intervalului 7,3–8,1, altfel eșalonarea ar fi o linie plată lipită de pragul din Art. 5.',
    gapsTitle: 'Structura de grade are goluri în care cad coeficienți reali',
    gapsLede: (variants) => (
      <>
        Art. 9 alin. (2) scrie cele 12 <Term id="grad-salarial">intervale</Term> cu două zecimale —
        gradul 1 se termină la 1,19, gradul 2 începe la 1,20 — în timp ce{' '}
        <Term id="anexa">anexele</Term> livrează coeficienți cu 16 zecimale. Un coeficient de
        1,1907527 este peste plafonul unuia și sub pragul celuilalt: nu aparține niciunui grad
        salarial. {variants} de variante stau în aceste goluri de o sutime, desenate mai jos exact
        acolo unde se află — între bare.
      </>
    ),
    gapsSource: 'Art. 9 alin. (2) și coeficienții din anexe',
    seeGaps: 'Vezi golurile ca tabel',
    gapsTable: 'Intervale pe familii ocupaționale',
    colBetween: 'Între gradele',
    colInterval: 'Interval fără grad',
    colVariants: 'Variante',
    gapRange: (from, to) => `peste ${from} și sub ${to}`,
    mergeTitle: 'Legea comasează funcții, dar nu publică nicio tabelă de asimilare',
    mergeLede: (merged, needsReview) => (
      <>
        Comasarea e vizibilă doar ca punctuație în celula cu denumirea:{' '}
        <em>Director; șef compartiment; inspector șef; comisar șef divizie; …</em> sunt nouă denumiri
        pe un singur cod și un singur coeficient. {merged} de funcții comasează două sau mai multe,
        iar {needsReview} de celule nu pot fi despărțite automat și așteaptă o decizie umană. Art. 32
        cere reîncadrarea, dar lasă maparea în seama fiecărui ordonator: aceeași denumire veche poate
        ajunge pe funcții diferite în instituții diferite.
      </>
    ),
    mergeY: 'funcții',
    mergeSource: 'denumirile anterioare listate la fiecare funcție',
    mergeNote: (singles) =>
      `Câte denumiri anterioare stau pe o singură funcție nouă. Restul de ${singles} de funcții poartă o singură denumire și nu apar în grafic.`,
    oneName: 'o singură denumire',
    mergedNames: (n) => `${n} denumiri comasate`,
    positions: (count) => `${count} funcții`,
    limitsTitle: 'Ce nu poate calcula acest instrument',
    limitsLede:
      'Fiecare regim poartă lista propriilor limite, legată de câmpul pe care îl afectează. Nu sunt note de subsol: unde lipsesc datele, cifra lipsește.',
    blocking: 'blocant',
    material: 'material',
  },
  en: {
    title: 'The shape of the pay system',
    lead:
      'The structure of the grid in the draft law on the pay of staff paid from public funds, 20.08.2026. Not amounts but shape: how many distinct values the grid has, how precise they are, how far apart its ends sit, how much information about occupations is lost by merging.',
    srcLine: (positions, variants) => (
      <>
        {positions} positions · {variants} coefficient variants · generated from{' '}
        <code>Proiect-COEFICIENTI-1-8-20-august-2026.xlsx</code>, 49 sheets.
      </>
    ),
    disclaimer: (
      <>
        <strong>An instrument for public debate, not a salary calculator.</strong> It shows what a
        draft law says, not what anyone takes home. Individual pay data is not published in Romania,
        so no figure here describes a person. The transitional pay difference of Art. 33, which
        dominates the real bill in the first years, cannot be computed at all.
      </>
    ),
    whatGrid: 'What the grid shows',
    kpiBackSolved: (
      <>
        of the distinct <Term id="coeficient">coefficients</Term> carry 14 decimals or more:{' '}
        <Term id="coeficient-retrocalculat">back-solved</Term>, not designed
      </>
    ),
    kpiDistinct: 'distinct coefficient values across the whole grid',
    kpiRounded: 'are rounded to two decimals',
    kpiGaps: (
      <>
        variants fall between the <Term id="grad-salarial">pay grades</Term>, in none of them
      </>
    ),
    kpiMerged: 'positions merge two or more former titles',
    precisionTitle: 'The coefficients are back-solved, not designed',
    precisionLede:
      'A designed grid produces numbers like 2.40 or 3.29. One obtained by dividing one salary by another produces 5.189610389610378. The distribution below counts distinct values by how many decimals they carry: the bar at 16 decimals is more than three times all the rounded values together.',
    precisionY: 'distinct values',
    precisionSource: 'the distinct coefficient values in the annexes',
    decimals: (dp) => `${dp} decimals`,
    distinctValues: (count) => `${count} distinct values`,
    backSolvedHint: 'back-solved from an existing salary',
    roundedHint: 'rounded: a chosen value',
    intermediateHint: 'in between',
    backSolved: 'back-solved',
    rounded: 'rounded',
    intermediate: 'in between',
    seeTable: 'See the data as a table',
    precisionTable: 'Distribution of the coefficients',
    colDecimals: 'Decimals',
    colDistinct: 'Distinct values',
    colReading: 'Reading',
    spanTitle: 'The 1 to 8 ratio is the destination of a phase-in',
    spanLede: (inForce, atEnd) =>
      `Art. 5 fixes the ratio between the lowest and the highest base salary at 1 to 8. Annex IX phases the dignitaries' coefficients over five annual columns, so the ratio moves: ${inForce ? `it is 1:${inForce.ratio} in ${inForce.period}` : ''}${atEnd ? ` and reaches exactly 1:${atEnd.ratio} in ${atEnd.period}` : ''}. The top of the grid in the first years belongs not to an elected office but to an ICT manager position in Annex VIII, with coefficient 7.3919.`,
    spanSource: 'Art. 5 and the annual columns in the annexes',
    spanAxisNote:
      'The vertical axis is cut around the 7.3–8.1 range; otherwise the phase-in would be a flat line glued to the Art. 5 threshold.',
    gapsTitle: 'The grade structure has gaps where real coefficients fall',
    gapsLede: (variants) => (
      <>
        Art. 9 para. (2) writes the 12 <Term id="grad-salarial">intervals</Term> with two decimals
        (grade 1 ends at 1.19, grade 2 starts at 1.20) while the <Term id="anexa">annexes</Term>{' '}
        deliver coefficients with 16 decimals. A coefficient of 1.1907527 is above the ceiling of one
        and below the floor of the other: it belongs to no pay grade. {variants} variants sit in
        these one-hundredth gaps, drawn below exactly where they are: between the bars.
      </>
    ),
    gapsSource: 'Art. 9 para. (2) and the coefficients in the annexes',
    seeGaps: 'See the gaps as a table',
    gapsTable: 'Intervals by occupational family',
    colBetween: 'Between grades',
    colInterval: 'Interval with no grade',
    colVariants: 'Variants',
    gapRange: (from, to) => `above ${from} and below ${to}`,
    mergeTitle: 'The law merges positions but publishes no assimilation table',
    mergeLede: (merged, needsReview) => (
      <>
        The merging is visible only as punctuation in the title cell:{' '}
        <em>Director; șef compartiment; inspector șef; comisar șef divizie; …</em> are nine titles on
        one code and one coefficient. {merged} positions merge two or more, and {needsReview} cells
        cannot be split automatically and await a human decision. Art. 32 requires regrading but
        leaves the mapping to each budget holder: the same old title may land on different positions
        in different institutions.
      </>
    ),
    mergeY: 'positions',
    mergeSource: 'the former titles listed at each position',
    mergeNote: (singles) =>
      `How many former titles sit on one new position. The remaining ${singles} positions carry a single title and do not appear in the chart.`,
    oneName: 'a single title',
    mergedNames: (n) => `${n} merged titles`,
    positions: (count) => `${count} positions`,
    limitsTitle: 'What this instrument cannot compute',
    limitsLede:
      'Every regime carries the list of its own limits, tied to the field each one affects. These are not footnotes: where the data is missing, the figure is missing.',
    blocking: 'blocking',
    material: 'material',
  },
};

export default function StructureView({
  menu,
  regime,
  period,
  lang = 'ro',
}: {
  /** The section menu, drawn under the title so the page says what it is first. */
  menu?: ReactNode;
  regime: Regime;
  /** The annual column in force, or null when the regime phases nothing. */
  period: string | null;
  /** The page language (RR-10): the view prints its own words in it, numbers follow its locale. */
  lang?: Lang;
}) {
  const t = STRUCTURE_STRINGS[lang];
  const locale = LOCALE[lang];
  const n = (value: number): string => value.toLocaleString(locale);
  const num = (value: number, d = 2): string =>
    value.toLocaleString(locale, { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (value: number): string =>
    `${(value * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}%`;

  const metrics = useMemo(
    () => structure(regime, period ? { period } : undefined),
    [regime, period],
  );

  const reading = (dp: number) => (dp >= 14 ? t.backSolved : dp <= 2 ? t.rounded : t.intermediate);
  const precisionBars: Bar[] = Object.entries(metrics.precisionHistogram)
    .map(([dp, count]) => ({ dp: Number(dp), count }))
    .sort((a, b) => a.dp - b.dp)
    .map(({ dp, count }) => ({
      label: String(dp),
      value: count,
      emphasis: dp >= 14,
      tooltip: (
        <>
          <strong>{t.decimals(dp)}</strong>
          <div>{t.distinctValues(n(count))}</div>
          <div className="muted">
            {dp >= 14 ? t.backSolvedHint : dp <= 2 ? t.roundedHint : t.intermediateHint}
          </div>
        </>
      ),
    }));

  const fanIn = Object.entries(metrics.assimilation.fanInHistogram)
    .map(([k, count]) => ({ n: Number(k), count }))
    .sort((a, b) => a.n - b.n);
  const singles = fanIn.find((f) => f.n === 1)?.count ?? 0;
  // Charting the fanIn=1 bar alongside the merges buries them: 1013 against 74.
  // The singles are context, so they are stated as a sentence and the plot shows the
  // distribution that is actually in question.
  const fanInBars: Bar[] = fanIn.filter(({ n: k }) => k > 1).map(({ n: k, count }) => ({
    label: String(k),
    value: count,
    emphasis: true,
    tooltip: (
      <>
        <strong>{k === 1 ? t.oneName : t.mergedNames(k)}</strong>
        <div>{t.positions(n(count))}</div>
      </>
    ),
  }));

  const blocking = regime.limitations.filter((l) => l.severity === 'blocking');
  const material = regime.limitations.filter((l) => l.severity === 'material');

  const inForce = metrics.spanByPeriod[0];
  const atEnd = metrics.spanByPeriod[metrics.spanByPeriod.length - 1];
  const span = (point: typeof inForce | undefined) =>
    point ? { ratio: num(point.ratio), period: point.period } : null;

  return (
    <>
      <header className="masthead">
        <h1>{t.title}</h1>
        <p>{t.lead}</p>
        <p className="src">{t.srcLine(n(metrics.positions), n(metrics.variants))}</p>
      </header>
      {menu}

      <div className="disclaimer">{t.disclaimer}</div>

      <section>
        <h2>{t.whatGrid}</h2>
        <div className="kpis">
          <div className="kpi">
            <div className="v accent">{pct(metrics.backSolvedShare)}</div>
            <div className="k">{t.kpiBackSolved}</div>
          </div>
          <div className="kpi">
            <div className="v">{n(metrics.distinctValues)}</div>
            <div className="k">{t.kpiDistinct}</div>
          </div>
          <div className="kpi">
            <div className="v">{pct(metrics.roundedShare)}</div>
            <div className="k">{t.kpiRounded}</div>
          </div>
          <div className="kpi">
            <div className="v">{n(metrics.variantsInGaps)}</div>
            <div className="k">{t.kpiGaps}</div>
          </div>
          <div className="kpi">
            <div className="v">{n(metrics.assimilation.mergedPositions)}</div>
            <div className="k">{t.kpiMerged}</div>
          </div>
        </div>
      </section>

      <section>
        <h2>{t.precisionTitle}</h2>
        <p className="lede">{t.precisionLede}</p>
        <div className="card">
          <ColumnChart
            bars={precisionBars}
            yLabel={t.precisionY}
            source={`${regime.provenance.locator}; ${t.precisionSource}`}
          />
        </div>
        <details className="table-view">
          <summary>{t.seeTable}</summary>
          <Table className="data" label={t.precisionTable}>
            <thead>
              <tr><th>{t.colDecimals}</th><th>{t.colDistinct}</th><th>{t.colReading}</th></tr>
            </thead>
            <tbody>
              {precisionBars.map((b) => (
                <tr key={b.label}>
                  <td>{b.label}</td>
                  <td className="num">{n(b.value)}</td>
                  <td>{reading(Number(b.label))}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </details>
      </section>

      <section>
        <h2>{t.spanTitle}</h2>
        <p className="lede">{t.spanLede(span(inForce), span(atEnd))}</p>
        <div className="card">
          <SpanChart
            points={metrics.spanByPeriod}
            declared={metrics.declaredRatio}
            source={`${regime.provenance.locator}; ${t.spanSource}`}
          />
          <p className="src" style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-secondary)' }}>
            {t.spanAxisNote}
          </p>
        </div>
      </section>

      <section>
        <h2>{t.gapsTitle}</h2>
        <p className="lede">{t.gapsLede(n(metrics.variantsInGaps))}</p>
        <div className="card">
          <GradeChart
            grades={metrics.gradeOccupancy}
            gaps={metrics.bandGaps}
            source={`${regime.provenance.locator}; ${t.gapsSource}`}
          />
        </div>
        <details className="table-view">
          <summary>{t.seeGaps}</summary>
          <Table className="data" label={t.gapsTable}>
            <thead>
              <tr><th>{t.colBetween}</th><th>{t.colInterval}</th><th>{t.colVariants}</th></tr>
            </thead>
            <tbody>
              {metrics.bandGaps.filter((g) => g.variants > 0).map((g) => (
                <tr key={g.belowGradeId}>
                  <td>{g.belowGradeId.replace('g', '')} → {g.aboveGradeId.replace('g', '')}</td>
                  <td>{t.gapRange(g.from, g.to)}</td>
                  <td className="num">{g.variants}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </details>
      </section>

      <section>
        <h2>{t.mergeTitle}</h2>
        <p className="lede">
          {t.mergeLede(n(metrics.assimilation.mergedPositions), n(metrics.assimilation.needsReview))}
        </p>
        <div className="card">
          <ColumnChart
            bars={fanInBars}
            yLabel={t.mergeY}
            source={`${regime.provenance.locator}; ${t.mergeSource}`}
          />
          <p className="src" style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-secondary)' }}>
            {t.mergeNote(n(singles))}
          </p>
        </div>
      </section>

      <section>
        <h2>{t.limitsTitle}</h2>
        <p className="lede">{t.limitsLede}</p>
        <div className="limits">
          {[...blocking, ...material].map((l) => (
            <div key={l.id} className={`limit ${l.severity ?? 'material'}`}>
              <div className="sev">
                {l.severity === 'blocking' ? t.blocking : t.material} · {l.affects.join(', ')}
              </div>
              <p>{l.text}</p>
            </div>
          ))}
        </div>
      </section>

    </>
  );
}

import { useMemo } from 'react';

import { structure } from '../../engine/structure';
import type { Regime } from '../../engine/types';
import { ColumnChart, GradeChart, SpanChart } from './charts';
import type { Bar } from './charts';

function ro(n: number): string {
  return n.toLocaleString('ro-RO');
}
function num(n: number, d = 2): string {
  return n.toLocaleString('ro-RO', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function pct(n: number): string {
  return `${(n * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`;
}

export default function StructureView({
  regime,
  period,
}: {
  regime: Regime;
  /** The annual column in force, or null when the regime phases nothing. */
  period: string | null;
}) {
  const metrics = useMemo(
    () => structure(regime, period ? { period } : undefined),
    [regime, period],
  );

  const precisionBars: Bar[] = Object.entries(metrics.precisionHistogram)
    .map(([dp, count]) => ({ dp: Number(dp), count }))
    .sort((a, b) => a.dp - b.dp)
    .map(({ dp, count }) => ({
      label: String(dp),
      value: count,
      emphasis: dp >= 14,
      tooltip: (
        <>
          <strong>{dp} zecimale</strong>
          <div>{ro(count)} valori distincte</div>
          <div className="muted">
            {dp >= 14
              ? 'retro-calculat dintr-un salariu existent'
              : dp <= 2
                ? 'rotunjit — o valoare aleasă'
                : 'intermediar'}
          </div>
        </>
      ),
    }));

  const fanIn = Object.entries(metrics.assimilation.fanInHistogram)
    .map(([n, count]) => ({ n: Number(n), count }))
    .sort((a, b) => a.n - b.n);
  const singles = fanIn.find((f) => f.n === 1)?.count ?? 0;
  // Charting the fanIn=1 bar alongside the merges buries them: 1013 against 74.
  // The singles are context, so they are stated as a sentence and the plot shows the
  // distribution that is actually in question.
  const fanInBars: Bar[] = fanIn.filter(({ n }) => n > 1).map(({ n, count }) => ({
    label: String(n),
    value: count,
    emphasis: true,
    tooltip: (
      <>
        <strong>{n === 1 ? 'o singură denumire' : `${n} denumiri comasate`}</strong>
        <div>{ro(count)} funcții</div>
      </>
    ),
  }));

  const blocking = regime.limitations.filter((l) => l.severity === 'blocking');
  const material = regime.limitations.filter((l) => l.severity === 'material');

  const inForce = metrics.spanByPeriod[0];
  const atEnd = metrics.spanByPeriod[metrics.spanByPeriod.length - 1];

  return (
    <>
      <header className="masthead">
        <h1>Forma sistemului de salarizare</h1>
        <p>
          Structura grilei din proiectul de lege privind salarizarea personalului plătit din
          fonduri publice, 16.07.2026. Nu cuantumuri, ci formă: câte valori distincte are grila,
          cât de precise sunt, cât de departe stau capetele, câtă informație despre ocupații
          se pierde prin comasare.
        </p>
        <p className="src">
          {ro(metrics.positions)} funcții · {ro(metrics.variants)} variante de coeficient · generate din{' '}
          <code>Proiect-COEFICIENTI-1-8-MMFTSS-16.07.2026-1000.xlsx</code>, 48 de foi.
        </p>
      </header>

      <div className="disclaimer">
        <strong>Instrument pentru dezbatere publică, nu calculator de salarii.</strong> Arată ce
        spune un proiect de lege, nu ce încasează cineva. Datele individuale de salarizare nu
        sunt publicate în România, deci nicio cifră de aici nu descrie o persoană. Diferența
        salarială tranzitorie de la Art. 33 — care în primii ani domină factura reală — nu poate
        fi calculată deloc.
      </div>

      <section>
        <h2>Ce arată grila</h2>
        <div className="kpis">
          <div className="kpi">
            <div className="v accent">{pct(metrics.backSolvedShare)}</div>
            <div className="k">
              din coeficienții distincți au 14 zecimale sau mai multe — retro-calculați, nu
              proiectați
            </div>
          </div>
          <div className="kpi">
            <div className="v">{ro(metrics.distinctValues)}</div>
            <div className="k">valori distincte de coeficient în toată grila</div>
          </div>
          <div className="kpi">
            <div className="v">{pct(metrics.roundedShare)}</div>
            <div className="k">sunt rotunjite la două zecimale</div>
          </div>
          <div className="kpi">
            <div className="v">{ro(metrics.variantsInGaps)}</div>
            <div className="k">variante cad între gradele salariale, în niciunul</div>
          </div>
          <div className="kpi">
            <div className="v">{ro(metrics.assimilation.mergedPositions)}</div>
            <div className="k">
              funcții comasează două sau mai multe denumiri anterioare
            </div>
          </div>
        </div>
      </section>

      <section>
        <h2>Coeficienții sunt retro-calculați, nu proiectați</h2>
        <p className="lede">
          O grilă proiectată produce numere ca 2,40 sau 3,29. Una obținută împărțind un salariu
          la altul produce 5,189610389610378. Distribuția de mai jos numără valorile distincte
          după câte zecimale poartă: bara de la 16 zecimale este de peste trei ori mai mare
          decât toate valorile rotunjite la loc.
        </p>
        <div className="card">
          <ColumnChart
            bars={precisionBars}
            yLabel="valori distincte"
            directLabel={(b) => b.value > 100}
          />
        </div>
        <details className="table-view">
          <summary>Vezi datele ca tabel</summary>
          <table className="data">
            <thead>
              <tr><th>Zecimale</th><th>Valori distincte</th><th>Interpretare</th></tr>
            </thead>
            <tbody>
              {precisionBars.map((b) => (
                <tr key={b.label}>
                  <td>{b.label}</td>
                  <td className="num">{ro(b.value)}</td>
                  <td>{Number(b.label) >= 14 ? 'retro-calculat' : Number(b.label) <= 2 ? 'rotunjit' : 'intermediar'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section>
        <h2>Raportul de 1 la 8 este destinația unui eșalonament</h2>
        <p className="lede">
          Art. 5 fixează raportul dintre cel mai mic și cel mai mare salariu de bază la 1 la 8.
          Anexa IX eșalonează coeficienții demnitarilor pe cinci coloane anuale, așa că raportul
          se mișcă: {inForce && <>este 1:{num(inForce.ratio)} în {inForce.period}</>}
          {atEnd && <> și atinge exact 1:{num(atEnd.ratio)} în {atEnd.period}</>}. Vârful
          grilei în primii ani nu aparține unei funcții alese, ci unei funcții de manager TIC din
          Anexa VIII, cu coeficient 7,3919.
        </p>
        <div className="card">
          <SpanChart points={metrics.spanByPeriod} declared={metrics.declaredRatio} />
          <p className="src" style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-secondary)' }}>
            Axa verticală este decupată în jurul intervalului 7,3–8,1, altfel eșalonarea ar fi o
            linie plată lipită de pragul din Art. 5.
          </p>
        </div>
      </section>

      <section>
        <h2>Structura de grade are goluri în care cad coeficienți reali</h2>
        <p className="lede">
          Art. 9 alin. (2) scrie cele 12 intervale cu două zecimale — gradul 1 se termină la 1,19,
          gradul 2 începe la 1,20 — în timp ce anexele livrează coeficienți cu 16 zecimale. Un
          coeficient de 1,1907527 este peste plafonul unuia și sub pragul celuilalt:{' '}
          nu aparține niciunui grad salarial. {ro(metrics.variantsInGaps)} de variante stau în
          aceste goluri de o sutime, desenate mai jos exact acolo unde se află — între bare.
        </p>
        <div className="card">
          <GradeChart grades={metrics.gradeOccupancy} gaps={metrics.bandGaps} />
        </div>
        <details className="table-view">
          <summary>Vezi golurile ca tabel</summary>
          <table className="data">
            <thead>
              <tr><th>Între gradele</th><th>Interval fără grad</th><th>Variante</th></tr>
            </thead>
            <tbody>
              {metrics.bandGaps.filter((g) => g.variants > 0).map((g) => (
                <tr key={g.belowGradeId}>
                  <td>{g.belowGradeId.replace('g', '')} → {g.aboveGradeId.replace('g', '')}</td>
                  <td>peste {g.from} și sub {g.to}</td>
                  <td className="num">{g.variants}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section>
        <h2>Legea comasează funcții, dar nu publică nicio tabelă de asimilare</h2>
        <p className="lede">
          Comasarea e vizibilă doar ca punctuație în celula cu denumirea:{' '}
          <em>Director; șef compartiment; inspector șef; comisar șef divizie; …</em> sunt nouă
          denumiri pe un singur cod și un singur coeficient.{' '}
          {ro(metrics.assimilation.mergedPositions)} de funcții comasează două sau mai multe, iar{' '}
          {ro(metrics.assimilation.needsReview)} de celule nu pot fi despărțite automat și
          așteaptă o decizie umană. Art. 32 cere reîncadrarea, dar lasă maparea în seama fiecărui
          ordonator: aceeași denumire veche poate ajunge pe funcții diferite în instituții
          diferite.
        </p>
        <div className="card">
          <ColumnChart
            bars={fanInBars}
            yLabel="funcții"
            directLabel={(b) => b.value >= 5}
          />
          <p className="src" style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-secondary)' }}>
            Câte denumiri anterioare stau pe o singură funcție nouă. Restul de {ro(singles)} de
            funcții poartă o singură denumire și nu apar în grafic.
          </p>
        </div>
      </section>

      <section>
        <h2>Ce nu poate calcula acest instrument</h2>
        <p className="lede">
          Fiecare regim poartă lista propriilor limite, legată de câmpul pe care îl afectează.
          Nu sunt note de subsol: unde lipsesc datele, cifra lipsește.
        </p>
        <div className="limits">
          {[...blocking, ...material].map((l) => (
            <div key={l.id} className={`limit ${l.severity ?? 'material'}`}>
              <div className="sev">{l.severity === 'blocking' ? 'blocant' : 'material'} · {l.affects.join(', ')}</div>
              <p>{l.text}</p>
            </div>
          ))}
        </div>
      </section>

    </>
  );
}

/**
 * The court map.
 *
 * Two views of the same 241 courts. **Astăzi** is what the CSM report describes: every court
 * where it sits, sized by the dossiers it had to resolve, coloured by how its load per judge
 * compares with the national average for its grade. **Propunerea** is the reform paper's
 * proposal — 176 judecătorii and 42 tribunale collapsing into 42 consolidated tribunale —
 * modelled as each county's judecătorii merging into that county's tribunal.
 *
 * That last sentence is an assumption and the panel says so. The report contains no arondare:
 * which judecătorie answers to which tribunal is set by law, not by this document. County is
 * the reading the proposal implies — there are 42 tribunale and 41 counties plus Bucharest —
 * but it is a reading, and the access question underneath it stays unanswerable either way.
 */
import {
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type MapMouseEvent,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { assign, loadCoupling, type Arondare, type Coupled } from './arondare';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

// MapLibre 6 ships its worker as a separate file rather than inlining it, and a bundled app
// has to say where that file ended up. Without this every source fails to load silently —
// no error event, no failed request, just a map that renders its background and stays empty.
// `?worker&url` rather than `?url`: the worker imports a shared chunk, and plain `?url`
// copies the file without following its imports, so it dies in production while working in
// dev. Learned in the administrative map; repeated here rather than rediscovered.
setWorkerUrl(maplibreWorkerUrl);

interface Court {
  id: string;
  name: string;
  tier: 'iccj' | 'curte-de-apel' | 'tribunal' | 'judecatorie';
  volume: number;
  resolved: number;
  loadPerJudge?: number;
  loadPerPost?: number;
  judges?: number;
  posts?: number;
  /** Level-1 judges the county has today, carried on a merged court for comparison. */
  judgesToday?: number;
  county: string;
  siruta: string | null;
  placedBy: 'name' | 'county-seat' | 'city';
  point: [number, number];
}

interface Limitation {
  id: string;
  text: string;
  severity: string;
  affects: string[];
}

interface Servicii {
  summary: {
    comparableUnits: number;
    meanMetresToCourt: number;
    meanMetresToHospitalAtMost: number;
    medianMetresToCourt: number;
    medianMetresToHospitalAtMost: number;
    seatsThatAreHospitalTowns: number;
    seatsThatAreCourtTowns: number;
    seatsThatArePoliceTowns: number;
    medianMetresToPoliceAtMost: number;
    units: number;
    todayCourts: number;
    medianMetresToTodayCourt: number;
    medianMetresToProposedCourt: number;
    seatsThatAreTodayCourtTowns: number;
    meanMetresToTodayCourt: number;
    meanMetresToProposedCourt: number;
    unitsLosingTheirLocalCourt: number;
    peopleLosingTheirLocalCourt: number;
    allPeople: number;
    beyond: Record<
      string,
      { todayUnits: number; todayPeople: number; proposedUnits: number; proposedPeople: number }
    >;
    peopleFurtherFromCourt: number;
    comparablePeople: number;
  };
  limitations: Limitation[];
}

interface Politie {
  summary: {
    stations: number;
    countiesCovered: number;
    uatsWithStation: number;
    courtSeatsWithStation: number;
    courtSeats: number;
  };
  limitations: Limitation[];
}

interface Spitale {
  summary: {
    registerHospitals: number;
    registerCounties: number;
    registerInMissingCounties: number;
    hospitals: number;
    located: number;
    countiesCovered: number;
    countiesTotal: number;
    countiesMissing: string[];
    courtSeatsCheckable: number;
    courtSeatsWithHospital: number;
    hospitalsInCourtSeatTowns: number;
  };
  limitations: Limitation[];
}

interface ArondareNoua {
  courtSeats: number;
  summary: {
    units: number;
    routed: number;
    crossingCounty: number;
    peopleCrossingCounty: number;
    wouldSplitByCommune: number;
    meanMetresOwnCounty: number;
    meanMetresNearest: number;
    metresSavedEachCrossing: number;
  };
  units: {
    name: string;
    county: string;
    courtName: string | null;
    courtCounty: string | null;
    metres: number | null;
    ownCountyMetres: number | null;
    crossesCounty: boolean;
  }[];
  limitations: Limitation[];
}

interface Proiect {
  referenceLei: number;
  byTier: {
    tier: Court['tier'];
    coefficient: number;
    monthlyLei: number;
    todayMonthlyLei: number;
    ratioToToday: number;
  }[];
  spread: { todayRatio: number; draftRatio: number; compresses: boolean };
  gradeGap: { todayMonthlyLei: number; draftMonthlyLei: number; narrows: boolean };
  gradeChoiceSwing: { target: number; todayLei: number; draftLei: number }[];
  limitations: Limitation[];
}

interface Sporuri {
  scope: { filledPosts: number; baseMonthlyLeiPerPost: number };
  sporuri: { narrow: number; wide: number };
  draftCap: { percent: number; overCap: boolean; gapPercentagePoints: number };
  judges: { count: number; shareOfCourtsBase: number };
  pension: {
    currentPercent: number;
    proposedPercent: number;
    reductionWithoutSporuriPercent: number;
    ifJudgesDrawNoSporuriPercent: number;
    ifSporuriSpreadEvenlyPercent: number;
    readings: { measure: string; reductionPercent: number }[];
  };
  limitations: Limitation[];
}

interface Pensii {
  averageGrossWageLei: number;
  paper: { formula: string; retirementAgeFrom: number; retirementAgeTo: number };
  bill: { percent: number; seniorityYears: number; netCapPercent: number };
  byGrade: {
    grade: string;
    currentLei: number;
    billFloorLei: number;
    paperCapLei: number;
    paperCapBelowBillFloor: boolean;
  }[];
  disagreements: { id: string; text: string }[];
  limitations: Limitation[];
}

interface Costuri {
  monthlyLeiByTier: Record<string, number>;
  today: {
    annualLei: number;
    levelOne: { judges: number; annualLei: number };
    byTier: { tier: string; judges: number; judgesDerived: number }[];
  };
  auxiliary: {
    posts: number;
    annualLowLei: number;
    annualHighLei: number;
  } | null;
  reconciliation: {
    payrollPosts: number;
    judgesFilled: number;
    auxiliaryFilled: number;
    unaccounted: number;
    executionBaseAnnualLei: number;
  } | null;
  limitations: Limitation[];
}

interface Design {
  chapters: {
    number: number;
    title: string;
    page: number;
    excerpt: string;
  }[];
}

type AccesKey = 'metresToday' | 'metresByCounty' | 'metresNearest';

interface Acces {
  summary: {
    communes: number;
    people: number;
    communesWithoutRoad: number;
    bucharestMultipleOfMean: number;
    balanced: Record<
      string,
      {
        ceilingMultiplier: number;
        variation: number;
        meanMetres: number;
        communesNotAtNearest: number;
      }
    >;
    median: Record<AccesKey, number>;
    mean: Record<AccesKey, number>;
    beyond: Record<string, Record<AccesKey, number>>;
    crossCounty: number;
    crossCountyPeople: number;
  };
  limitations: Limitation[];
  /** Metres to the court, per UAT index in the administrative payload. -1 where no road. */
  today: number[];
  byCounty: number[];
  nearest: number[];
  /** Per-ceiling distances, keyed by the ceiling as a multiple of the average court. */
  balanced: Record<string, number[]>;
}

interface Proposal {
  publisher: string;
  published: boolean;
  provenance: { note?: string };
  tinta: { nivel1: { instante: number; motivInstante?: string } };
  limitations: Limitation[];
}

interface Document {
  period: string;
  courts: Court[];
  nationalAverages: { byTier: { tier: string; perJudge: number; perPost: number }[] };
  limitations: Limitation[];
}

const TIER_LABEL: Record<Court['tier'], string> = {
  iccj: 'Înalta Curte',
  'curte-de-apel': 'Curte de apel',
  tribunal: 'Tribunal',
  judecatorie: 'Judecătorie',
};

const ro = new Intl.NumberFormat('ro-RO');
/** Millions, because a wage bill in bare lei is nine digits nobody reads. */
const milioane = (lei: number): string =>
  `${(lei / 1e6).toLocaleString('ro-RO', { maximumFractionDigits: 1 })} mil.`;

const base = import.meta.env.BASE_URL;
const el = <T extends HTMLElement>(q: string): T => {
  const node = document.querySelector<T>(q);
  if (!node) throw new Error(`missing ${q}`);
  return node;
};

/**
 * A blank style: no tiles, no remote basemap, no third-party request.
 *
 * The same choice the administrative map makes, for the same reasons — the page stays free to
 * host, works offline, and asks nothing of anyone's browser that the reader did not choose.
 */
const BLANK = {
  version: 8 as const,
  // `glyphs` is omitted, not set to undefined. MapLibre validates the style and rejects a
  // key that is present with no value — "glyphs: string expected, undefined found" — and the
  // failure is quiet in the worst way: the style never loads, so `load` never fires, so no
  // layers are ever added and the page shows an empty canvas with a working panel beside it.
  // Nothing 404s and nothing throws where a reader would look.
  sources: {},
  layers: [{ id: 'bg', type: 'background' as const, paint: { 'background-color': '#0b0d10' } }],
};

async function main(): Promise<void> {
  const [
    doc,
    counties,
    proposal,
    manifest,
    design,
    costuri,
    pensii,
    sporuri,
    proiect,
    arondare,
    spitale,
    servicii,
    politie,
  ] = await Promise.all([
    fetch(`${base}data/instante.json`).then((r) => r.json() as Promise<Document>),
    fetch(`${base}data/counties.geojson`).then((r) => r.json()),
    fetch(`${base}data/propunere.json`).then((r) => r.json() as Promise<Proposal>),
    fetch(`${base}data/manifest.json`).then(
      (r) => r.json() as Promise<{ countyNames?: Record<string, string> }>,
    ),
    fetch(`${base}data/design.json`).then((r) => r.json() as Promise<Design>),
    fetch(`${base}data/costuri.json`).then((r) => r.json() as Promise<Costuri>),
    fetch(`${base}data/pensii.json`).then((r) => r.json() as Promise<Pensii>),
    fetch(`${base}data/sporuri.json`).then((r) => r.json() as Promise<Sporuri>),
    fetch(`${base}data/proiect.json`).then((r) => r.json() as Promise<Proiect>),
    fetch(`${base}data/arondare-noua.json`).then((r) => r.json() as Promise<ArondareNoua>),
    fetch(`${base}data/spitale.json`).then((r) => r.json() as Promise<Spitale>),
    fetch(`${base}data/servicii.json`).then((r) => r.json() as Promise<Servicii>),
    fetch(`${base}data/politie.json`).then((r) => r.json() as Promise<Politie>),
  ]);
  const countyName = (code: string): string => manifest.countyNames?.[code] ?? code;

  // The year comes from the document, not the markup. The CSM publishes annually and this
  // page had 2023 written into its subtitle while reading 2025 — a caption that disagrees
  // with its own figures is worse than none.
  el('#sub').textContent =
    `${ro.format(doc.courts.length)} de instanțe, dosarele pe care le-au avut de soluționat ` +
    `în ${doc.period} și încărcătura pe judecător.`;

  const averageFor = new Map(doc.nationalAverages.byTier.map((t) => [t.tier, t.perJudge]));

  /**
   * A court's load per judge, as a multiple of the yardstick it should be judged against.
   *
   * Today that is the national average for its own grade, which the report prints: a
   * judecatorie against 1.454,7 and a tribunal against 932,3, so a small court is not made
   * to look good by being compared with the Inalta Curte.
   *
   * Under the proposal it cannot be. A merged court carries the judecatorie work of its whole
   * county at tribunal grade, so measuring it against the *old* tribunal average paints every
   * one of the 42 red — which says nothing about the reform and everything about comparing a
   * court with a yardstick built before it existed. The proposal is therefore measured against
   * itself: the mean load per judge across the merged courts. That answers the question the
   * view can actually support — which of them would be worse off than the rest.
   */
  const ratioAgainst = (
    court: { tier: string; loadPerJudge?: number },
    yardstick: number | undefined,
  ): number | null => {
    if (!yardstick || !court.loadPerJudge) return null;
    return court.loadPerJudge / yardstick;
  };

  /**
   * The proposal: every judecătorie in a county folds into that county's tribunal.
   *
   * Curțile de apel and the Înalta Curte are left as they are — the paper keeps 15 courts of
   * appeal and there are already 15. Where a county has several tribunale, the specialised
   * ones fold in too, which is what "42 consolidated tribunale" means.
   */
  /**
   * The proposal: one level-1 court per county, sized by the work it inherits.
   *
   * The count is fixed by territorial coverage — 41 counties and Bucharest, hence 42 — and a
   * county with more work gets a bigger court rather than another one. Judges follow from the
   * volume and the target rate; the number of courts does not move.
   *
   * The paper also says each court would serve 150.000-200.000 inhabitants. That cannot hold
   * at 42 — the average is 453.662 — and it is recorded in the proposal document as wording
   * to correct rather than modelled here. Curtile de apel and the Inalta Curte are untouched.
   */
  const proposed = (target: number): Court[] => {
    const kept = doc.courts.filter((c) => c.tier === 'iccj' || c.tier === 'curte-de-apel');
    const byCounty = new Map<string, Court[]>();
    for (const court of doc.courts) {
      if (court.tier === 'iccj' || court.tier === 'curte-de-apel') continue;
      const list = byCounty.get(court.county) ?? [];
      list.push(court);
      byCounty.set(court.county, list);
    }
    const merged: Court[] = [];
    for (const [county, courts] of byCounty) {
      // Seated where the county's tribunal already is: it is the level-1 court that exists
      // at county scale, so it is the one with a building that plausibly takes the rest.
      const seat = courts.find((c) => c.tier === 'tribunal') ?? courts[0]!;
      const volume = courts.reduce((n, c) => n + c.volume, 0);
      const resolved = courts.reduce((n, c) => n + c.resolved, 0);
      merged.push({
        ...seat,
        id: `t-${county}`,
        name: `Instanța ${countyName(county)}`,
        tier: 'tribunal',
        volume,
        resolved,
        // Staffing is the output here, not an input carried over: this is what the court
        // would need to run at the chosen rate, which is the question consolidation raises.
        judges: volume / target,
        judgesToday: courts.reduce((n, c) => n + (c.judges ?? 0), 0),
        loadPerJudge: target,
        posts: undefined,
        loadPerPost: undefined,
      });
    }
    return [...kept, ...merged];
  };

  /** Judges at level 1 today, the figure the proposal's staffing is compared against. */
  const judgesToday = doc.courts
    .filter((c) => c.tier === 'judecatorie' || c.tier === 'tribunal')
    .reduce((n, c) => n + (c.judges ?? 0), 0);

  const asFeatures = (courts: Court[], ratioOf: (c: Court) => number | null) => ({
    type: 'FeatureCollection' as const,
    features: courts.map((c) => {
      const ratio = ratioOf(c);
      return {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: c.point },
        properties: {
          ...c,
          judges: c.judges ?? 0,
          loadPerJudge: c.loadPerJudge ?? 0,
          ratio: ratio ?? 1,
          hasRatio: ratio === null ? 0 : 1,
          tierLabel: TIER_LABEL[c.tier],
        },
      };
    }),
  });

  const map = new MapLibreMap({
    container: 'map',
    style: BLANK,
    center: [25.0, 45.9],
    zoom: 6.1,
    attributionControl: false,
    pitchWithRotate: false,
    dragRotate: false,
  });
  map.addControl(new NavigationControl({ showCompass: false }), 'top-right');

  let mode: 'today' | 'proposed' | 'acces' = 'today';

  /**
   * The access view, loaded only when asked for.
   *
   * The commune outlines are 2,9 MB — bigger than everything else on the page put together —
   * and most readers never open this view, so nothing is fetched until one does. Polygons are
   * painted through feature state rather than by rebuilding the source: 3.184 shapes upload
   * once and only their colour changes afterwards.
   */
  let accesLoaded: Promise<Acces> | null = null;
  const loadAcces = (): Promise<Acces> => {
    accesLoaded ??= (async () => {
      const [figures, shapes] = await Promise.all([
        fetch(`${base}data/acces.json`).then((r) => r.json() as Promise<Acces>),
        fetch(`${base}data/uats.geojson`).then((r) => r.json()),
      ]);
      map.addSource('uats', { type: 'geojson', data: shapes });
      map.addLayer(
        {
          id: 'acces-fill',
          type: 'fill',
          source: 'uats',
          layout: { visibility: 'none' },
          paint: {
            // Extra kilometres, in bands rather than a gradient: the question is which side
            // of "an hour further" a commune falls, not a smooth ramp nobody can read.
            'fill-color': [
              'case',
              ['<', ['coalesce', ['feature-state', 'extra'], -1], 0],
              '#3a4149',
              [
                'step',
                ['feature-state', 'extra'],
                '#2f7d4f',
                1,
                '#7fa86a',
                10000,
                '#d9c05a',
                25000,
                '#d98040',
                50000,
                '#c2453a',
              ],
            ] as unknown as ExpressionSpecification,
            'fill-opacity': 0.75,
          },
        },
        'county-lines',
      );
      for (let index = 0; index < figures.byCounty.length; index += 1) {
        const today = figures.today[index] ?? -1;
        const proposed = figures.byCounty[index] ?? -1;
        map.setFeatureState(
          { source: 'uats', id: index },
          { extra: today < 0 || proposed < 0 ? -1 : proposed - today },
        );
      }
      return figures;
    })();
    return accesLoaded;
  };
  const targetInput = el<HTMLInputElement>('#target');
  const courtsFor = (m: typeof mode) =>
    m === 'today' ? doc.courts : proposed(Number(targetInput.value));

  /**
   * What the colour means differs by view, because the two views vary in different things.
   *
   * Today: load per judge against the national average for the court's own grade, so a
   * judecatorie is compared with judecatorii.
   *
   * Under the proposal every merged court runs at exactly the chosen rate — that is how its
   * staffing is derived — so colouring by load would paint all forty-two identically. What
   * actually varies is whether a county would need more judges than it has, which is the
   * question the merge raises and the one a reader can act on.
   */
  const ratioFor = (m: typeof mode, courts: Court[]): ((c: Court) => number | null) => {
    if (m === 'today') return (c) => ratioAgainst(c, averageFor.get(c.tier));
    return (c) => {
      if (!c.id.startsWith('t-')) return ratioAgainst(c, averageFor.get(c.tier));
      if (!c.judgesToday || !c.judges) return null;
      return c.judges / c.judgesToday;
    };
  };

  map.on('load', () => {
    map.addSource('counties', { type: 'geojson', data: counties });
    map.addLayer({
      id: 'county-lines',
      type: 'line',
      source: 'counties',
      paint: { 'line-color': '#2b333c', 'line-width': 1 },
    });

    map.addSource('courts', {
      type: 'geojson',
      data: asFeatures(courtsFor(mode), ratioFor(mode, courtsFor(mode))),
    });

    // Radius by the square root of the volume: area reads as quantity, radius does not, and
    // the largest court carries a hundred times the smallest.
    const radius = [
      'interpolate',
      ['linear'],
      ['sqrt', ['get', 'volume']],
      0,
      3,
      300,
      22,
    ] as unknown as ExpressionSpecification;

    // Diverging on the ratio to the grade's own average, so a judecătorie is compared with
    // judecătorii and not with the Înalta Curte.
    const colour = [
      'case',
      ['==', ['get', 'hasRatio'], 0],
      '#6b7280',
      [
        'interpolate',
        ['linear'],
        ['get', 'ratio'],
        0.6,
        '#2f7d4f',
        0.85,
        '#7fa86a',
        1.0,
        '#d9c05a',
        1.2,
        '#d98040',
        1.6,
        '#c2453a',
      ],
    ] as unknown as ExpressionSpecification;

    map.addLayer({
      id: 'courts',
      type: 'circle',
      source: 'courts',
      paint: {
        'circle-radius': radius,
        'circle-color': colour,
        'circle-opacity': 0.85,
        'circle-stroke-color': '#0b0d10',
        'circle-stroke-width': 1,
      },
    });

    const detail = el('#detail');
    const show = (f: MapGeoJSONFeature | null): void => {
      if (!f) {
        detail.innerHTML = '<p class="hint">Treci cu mouse-ul peste o instanță.</p>';
        return;
      }
      const p = f.properties as unknown as Court & { tierLabel: string; ratio: number };
      const average = p.id.startsWith('t-') ? null : averageFor.get(p.tier);
      const load = p.loadPerJudge ? Math.round(p.loadPerJudge) : null;
      detail.innerHTML = `
        <div class="court">${p.name}</div>
        <div class="tier">${p.tierLabel}</div>
        <dl>
          <dt>Dosare de soluționat</dt><dd>${ro.format(p.volume)}</dd>
          <dt>Soluționate</dt><dd>${ro.format(p.resolved)}</dd>
          <dt>Judecători</dt><dd>${p.judges ? ro.format(Math.round(p.judges * 10) / 10) : '—'}</dd>
          <dt>Indemnizații de bază</dt><dd>${
            p.judges && costuri.monthlyLeiByTier[p.tier]
              ? `${milioane(p.judges * costuri.monthlyLeiByTier[p.tier]! * 12)} lei/an`
              : '—'
          }</dd>
          <dt>Pe judecător</dt><dd>${load ? ro.format(load) : '—'}${
            load && average
              ? ` <span class="vs">(media gradului ${ro.format(Math.round(average))})</span>`
              : load
                ? ' <span class="vs">(comparat cu media instanțelor comasate)</span>'
                : ''
          }</dd>
        </dl>`;
    };

    map.on('mousemove', 'courts', (e: MapMouseEvent & { features?: MapGeoJSONFeature[] }) => {
      map.getCanvas().style.cursor = 'pointer';
      show(e.features?.[0] ?? null);
    });
    map.on('mouseleave', 'courts', () => {
      map.getCanvas().style.cursor = '';
      show(null);
    });

    /** Applied here rather than in render, because the layer does not exist until it loads. */
    const showAccesLayer = (visible: boolean): void => {
      if (!map.getLayer('acces-fill')) return;
      map.setLayoutProperty('acces-fill', 'visibility', visible ? 'visible' : 'none');
    };

    /**
     * What those judges would cost, at both readings of a question the paper leaves open.
     *
     * It merges judecatorii and tribunale and never says what grade the merged court's judges
     * hold. At 17.250 lei a month against 22.500 the same headcount differs by hundreds of
     * millions a year, so both are shown and neither is called the answer.
     */
    const wageBill = (judges: number): string => {
      const pay = costuri.monthlyLeiByTier;
      const today = costuri.today.levelOne.annualLei;
      const at = (grade: 'judecatorie' | 'tribunal'): string => {
        const annual = judges * (pay[grade] ?? 0) * 12;
        const delta = annual - today;
        return (
          `<div class="figure">la grad de ${grade === 'judecatorie' ? 'judecătorie' : 'tribunal'}: ` +
          `<strong>${milioane(annual)}</strong> lei/an ` +
          `<span class="vs">(${delta >= 0 ? '+' : '−'}${milioane(Math.abs(delta))} față de azi)</span></div>`
        );
      };
      const aux = costuri.auxiliary;
      const rec = costuri.reconciliation;
      return (
        `<div class="figure" style="margin-top:.5rem">indemnizația de bază a judecătorilor de
          nivel 1, azi <strong>${milioane(today)}</strong> lei/an</div>` +
        at('judecatorie') +
        at('tribunal') +
        (aux && rec
          ? `<p class="note">Judecătorii nu sunt cea mai mare parte a statului de plată.
               CSM numără ${ro.format(rec.judgesFilled)} de posturi de judecător ocupate și
               ${ro.format(rec.auxiliaryFilled)} de posturi auxiliare; toată grila de bază a
               instanțelor iese la ${milioane(costuri.today.annualLei + aux.annualLowLei)}–${milioane(
                 costuri.today.annualLei + aux.annualHighLei,
               )} lei/an, față de ${milioane(rec.executionBaseAnnualLei)} cheltuiți efectiv în
               2025. Diferența e în anii diferiți — grila e din 2022 — și în cele
               ${ro.format(rec.unaccounted)} de posturi pe care niciuna dintre cele două surse
               nu le numără.</p>`
          : '')
      );
    };

    const km = (metres: number): string => (metres / 1000).toFixed(1).replace('.', ',');

    const paint = (figures: Acces, key: string): void => {
      const lane = figures.balanced[key] ?? figures.byCounty;
      for (let index = 0; index < lane.length; index += 1) {
        const today = figures.today[index] ?? -1;
        const after = lane[index] ?? -1;
        map.setFeatureState(
          { source: 'uats', id: index },
          { extra: today < 0 || after < 0 ? -1 : after - today },
        );
      }
    };

    const ceilingInput = el<HTMLInputElement>('#ceiling-input');
    let ceilingsLoaded: string[] = [];

    const renderAcces = (figures: Acces): void => {
      showAccesLayer(mode === 'acces');
      el('#ceiling').hidden = false;

      // Ceilings in order, loosest last, so the control reads left to right from strict to
      // none and rests on no-ceiling: the reader meets the unconstrained map first and
      // tightens it themselves rather than being handed a balanced one as the default.
      if (!ceilingsLoaded.length) {
        ceilingsLoaded = Object.keys(figures.summary.balanced).sort(
          (a, c) => Number(a) - Number(c),
        );
        ceilingInput.max = String(ceilingsLoaded.length - 1);
        ceilingInput.value = String(ceilingsLoaded.length - 1);
        ceilingInput.addEventListener('input', () => renderAcces(figures));
      }
      const key = ceilingsLoaded[Number(ceilingInput.value)] ?? ceilingsLoaded.at(-1)!;
      const scenario = figures.summary.balanced[key]!;
      paint(figures, key);
      const noCeiling = scenario.ceilingMultiplier > 10;
      el<HTMLOutputElement>('#ceiling-value').textContent = noCeiling
        ? 'fără'
        : `${scenario.ceilingMultiplier.toLocaleString('ro-RO')}× media`;
      const s = figures.summary;
      // Its caveats join the others rather than sitting apart: population is a poor proxy for
      // litigants, and kilometres are not hours.
      // The access caveats arrive with the lazy load, so they join the fold late — and the
      // count on the summary has to follow them, or it goes quietly stale.
      if (!el('#limits').dataset.acces) {
        el('#limits').dataset.acces = 'yes';
        el('#limits').innerHTML += figures.limitations
          .map((l) => `<p class="limit">${l.text}</p>`)
          .join('');
        el('#limits-count').textContent =
          `${el('#limits').querySelectorAll('p').length} rezerve`;
      }
      const band = (label: string, colour: string) =>
        `<div><i style="background:${colour}"></i>${label}</div>`;
      el('#acces-note').innerHTML =
        'Cât are de mers un locuitor până la instanța lui, azi și dacă județul păstrează una ' +
        'singură. Distanțe pe drum, între reședința comunei și sediul instanței.';
      el('#ramp-title').textContent = 'Cât în plus ar avea de mers';
      const fifty = s.beyond['50']!;
      el('#summary').innerHTML = `
        <div class="figure">drum median <strong>${km(s.median.metresToday)} km</strong> →
          <strong>${km(s.median.metresByCounty)} km</strong></div>
        <div class="figure">peste 50 km de instanță:
          <strong>${ro.format(fifty.metresToday)}</strong> →
          <strong>${ro.format(fifty.metresByCounty)}</strong> de oameni</div>
        <div class="figure">peste 100 km:
          ${ro.format(s.beyond['100']!.metresToday)} →
          <strong>${ro.format(s.beyond['100']!.metresByCounty)}</strong></div>
        <div class="figure">dacă granița de județ nu ar conta, cei de peste 50 km ar fi
          <strong>${ro.format(fifty.metresNearest)}</strong> —
          <strong>${ro.format(s.crossCounty)}</strong> de comune sunt mai aproape de instanța
          altui județ</div>
        <div class="figure">${ro.format(s.communesWithoutRoad)} comune nu au drum până la nicio
          instanță; sunt lăsate necolorate</div>
        <div class="figure" style="margin-top:.5rem">cu plafonul de mai jos: drum mediu
          <strong>${km(scenario.meanMetres)} km</strong>, inegalitate între instanțe
          <strong>${scenario.variation.toLocaleString('ro-RO')}</strong>,
          <strong>${ro.format(scenario.communesNotAtNearest)}</strong> comune trimise altundeva
          decât la cea mai apropiată</div>
        <div class="figure">Bucureștiul singur cântărește
          <strong>${s.bucharestMultipleOfMean.toLocaleString('ro-RO')}×</strong> media unei
          instanțe și nu poate fi echilibrat: sectoarele lui nu pot merge în alt județ</div>
        <div class="steps">
          ${band('nu se schimbă', '#2f7d4f')}
          ${band('sub 10 km în plus', '#7fa86a')}
          ${band('10–25 km', '#d9c05a')}
          ${band('25–50 km', '#d98040')}
          ${band('peste 50 km', '#c2453a')}
        </div>`;
    };

    const render = (): void => {
      const courts = courtsFor(mode === 'acces' ? 'proposed' : mode);
      const ratioOf = ratioFor(mode === 'acces' ? 'proposed' : mode, courts);
      (map.getSource('courts') as GeoJSONSource).setData(asFeatures(courts, ratioOf));

      el('#ramp-title').textContent =
        mode === 'today'
          ? 'Încărcătura față de media pe grad'
          : 'Judecători necesari față de câți sunt azi';
      el('#staffing').hidden = mode !== 'proposed';
      el('#authorship').hidden = mode === 'today';
      el('#acces-note').hidden = mode !== 'acces';
      el('#ceiling').hidden = mode !== 'acces';
      // The old diverging ramp describes a comparison this view does not make; the access
      // view brings its own stepped legend with the summary.
      el('.ramp').hidden = mode === 'acces';
      el('.ramp-ends').hidden = mode === 'acces';
      showAccesLayer(mode === 'acces');
      el<HTMLOutputElement>('#target-value').textContent = ro.format(Number(targetInput.value));

      if (mode === 'acces') {
        void loadAcces().then(renderAcces);
        return;
      }

      const total = courts.reduce((n, c) => n + c.volume, 0);
      if (mode === 'today') {
        const over = courts.filter((c) => (ratioOf(c) ?? 0) > 1).length;
        el('#summary').innerHTML = `
          <div class="figure"><strong>${ro.format(courts.length)}</strong> instanțe</div>
          <div class="figure"><strong>${ro.format(total)}</strong> dosare</div>
          <div class="figure"><strong>${ro.format(over)}</strong> peste media gradului</div>`;
        return;
      }

      const merged = courts.filter((c) => c.id.startsWith('t-'));
      const needed = merged.reduce((n, c) => n + (c.judges ?? 0), 0);
      // The dossiers the forty-two would actually carry. Printing the system-wide figure
      // beside "42 instante de nivel 1" reads as though they handle the appeals too.
      const levelOne = merged.reduce((n, c) => n + c.volume, 0);
      const delta = needed - judgesToday;
      const volumes = merged.map((c) => c.volume).sort((a, c) => a - c);
      const spread = volumes.length ? volumes[volumes.length - 1]! / volumes[0]! : 0;
      el('#summary').innerHTML = `
        <div class="figure"><strong>${ro.format(merged.length)}</strong> instanțe de nivel 1,
          câte una pe județ</div>
        <div class="figure"><strong>${ro.format(levelOne)}</strong> dosare de nivel 1
          <span class="vs">(din ${ro.format(total)} în tot sistemul)</span></div>
        <div class="figure"><strong>${ro.format(Math.round(needed))}</strong> judecători
          necesari, față de ${ro.format(Math.round(judgesToday))} azi
          <span class="vs">(${delta >= 0 ? '+' : ''}${ro.format(Math.round(delta))})</span></div>
        <div class="figure">cea mai mare instanță ar avea de
          <strong>${spread.toFixed(0)}×</strong> mai multe dosare decât cea mai mică</div>
        ${wageBill(needed)}`;
    };

    for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
      button.addEventListener('click', () => {
        mode = button.dataset.mode as typeof mode;
        for (const other of document.querySelectorAll('[data-mode]')) other.classList.remove('on');
        button.classList.add('on');
        render();
      });
    }
    targetInput.addEventListener('input', render);
    render();
  });

  // Who wrote the proposal, stated on the view that shows it. The baseline is a CSM report
  // and the proposal is one person's paper; a reader seeing "Astăzi / Propunerea" has no way
  // to tell them apart unless the page says so. Read from the document, so it cannot drift
  // from what the data claims.
  el('#authorship').innerHTML = proposal.published
    ? `Propunere publicată de ${proposal.publisher}.`
    : `<strong>Propunere neinstituțională.</strong> Documentul este al lui ` +
      `${proposal.publisher}, autorul acestui simulator. Nu este act normativ și nu a trecut ` +
      `printr-un proces public. Baza de comparație — activitatea instanțelor — este raportul ` +
      `Consiliului Superior al Magistraturii.`;

  // Coefficients carry up to sixteen decimals in the grid and the spreads are bare ratios, so
  // both are printed at a fixed two places — otherwise a column reads 5,5 beside 5,363 and the
  // difference looks like precision rather than formatting.
  const dec2 = (x: number): string =>
    x.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  // The tightest staffing target, where the grade choice costs the most. Sorted rather than
  // indexed, and the fold is skipped entirely if the document ships no targets at all.
  const [lowest] = [...proiect.gradeChoiceSwing].sort((a, b) => a.target - b.target);
  const sp = spitale.summary;
  el('#spitale-chev').textContent = `${sp.courtSeatsWithHospital} din ${sp.courtSeatsCheckable}`;
  el('#spitale-body').innerHTML =
    `<p class="note">Capitolul 7 susține comasarea și prin logistică: instanța, parchetul și
       poliția județeană într-un singur oraș. Spitalele sunt singurul serviciu de rang județean
       cu registru public localizabil, deci sunt testul disponibil — nu dovada.</p>
     <div class="pens-row">
       <span class="pens-head">ce</span>
       <span class="pens-head">cât</span>
       <span class="pens-head">din</span>
       <span class="pens-head"></span>
       <span>sedii cu spital</span>
       <span>${sp.courtSeatsWithHospital}</span>
       <span>${sp.courtSeatsCheckable}</span>
       <span>verificabile</span>
       <span>spitale în orașe-sedii</span>
       <span>${sp.hospitalsInCourtSeatTowns}</span>
       <span>${sp.located}</span>
       <span>${Math.round((100 * sp.hospitalsInCourtSeatTowns) / sp.located)}%</span>
       <span>județe pe hartă</span>
       <span class="pens-low">${sp.countiesCovered}</span>
       <span>${sp.countiesTotal}</span>
       <span class="pens-low">lipsesc ${sp.countiesMissing.length}</span>
       <span>în registrul ANMCS</span>
       <span>${ro.format(sp.registerHospitals)}</span>
       <span>${sp.registerCounties}</span>
       <span>județe</span>
     </div>
     <p class="disagree">Fiecare sediu de instanță pe care harta îl acoperă are un spital —
       ${sp.courtSeatsWithHospital} din ${sp.courtSeatsCheckable}. Sediile propuse sunt deci
       deja centre de servicii. Harta ministerului nu are însă
       ${sp.countiesMissing.length} județe (${sp.countiesMissing.join(', ')}), iar registrul de
       acreditare al ANMCS listează ${sp.registerInMissingCounties} de spitale exact în ele:
       lipsește localizarea lor, nu existența.</p>
     <p class="disagree">Poliția, din OpenStreetMap fiindcă niciun registru nu o publică:
       ${ro.format(politie.summary.stations)} de secții, în toate cele
       ${politie.summary.countiesCovered} de județe și în
       ${ro.format(politie.summary.uatsWithStation)} de UAT-uri. Toate cele
       ${politie.summary.courtSeatsWithStation} din ${politie.summary.courtSeats} de sedii
       propuse au deja secție — iar asta rezistă la o hartă incompletă: punctele lipsă ar face
       potrivirea mai grea, nu mai ușoară.</p>
     <p class="disagree">Aceleași sedii, față de toate trei rețelele:
       ${servicii.summary.seatsThatArePoliceTowns} din ${ro.format(servicii.summary.units)} au
       poliție, ${servicii.summary.seatsThatAreHospitalTowns} din
       ${ro.format(servicii.summary.comparableUnits)} au spital, dar doar
       ${servicii.summary.seatsThatAreCourtTowns} ar avea instanță. Orașele pe care reforma le
       alege sunt deja centre de poliție și de sănătate; singurul lucru care le-ar lipsi e
       instanța.</p>
     <p class="disagree">În kilometri, mediana drumului ar fi
       ${Math.round(servicii.summary.medianMetresToCourt / 1000)} km până la instanță, față de
       ${Math.round(servicii.summary.medianMetresToPoliceAtMost / 1000)} km până la poliție și
       ${Math.round(servicii.summary.medianMetresToHospitalAtMost / 1000)} km până la spital.
       Rețeaua de justiție ar fi mult mai rară decât celelalte două. Ambele distanțe din urmă
       sunt limite de sus: un punct nemarcat scurtează drumul, nu îl lungește.</p>
     <p class="disagree">Invers, ${Math.round(
       100 - (100 * sp.hospitalsInCourtSeatTowns) / sp.located,
     )}% dintre spitale nu sunt în orașul unui sediu. Concentrarea serviciilor în 42 de orașe
       le apropie de instanță, dar le depărtează de restul spitalelor.</p>`;

  // Assignment by distance rather than by county line, on the consolidated units rather than
  // on today's communes. The split count leads because it is the part that only appears once
  // the unit, not the commune, is the thing being assigned.
  //
  // Rendered from a shape both the shipped document and the browser's own recomputation
  // satisfy, so the reader sees one table whichever produced it.
  const arKm = (metres: number): string => `${Math.round(metres / 1000)} km`;
  interface ArondareRow {
    name: string;
    county: string;
    courtCounty: string | null;
    metres: number | null;
    ownCountyMetres: number | null;
    crossesCounty: boolean;
  }
  const arTop = (rows: ArondareRow[]): ArondareRow[] =>
    rows
      .filter((u) => u.crossesCounty && u.metres !== null && u.ownCountyMetres !== null)
      .sort((x, y) => y.ownCountyMetres! - y.metres! - (x.ownCountyMetres! - x.metres!))
      .slice(0, 6);

  const renderArondare = (
    sum: ArondareNoua['summary'],
    rows: ArondareRow[],
    live: boolean,
  ): void => {
    el('#arondare-chev').textContent = `${sum.crossingCounty} peste județ`;
    const sv = servicii.summary;
    const pctPeople = (n: number): string => `${Math.round((100 * n) / sv.allPeople)}%`;
    el('#arondare-body').innerHTML =
      `<p class="disagree">Azi există ${sv.todayCourts} de judecătorii, iar
         ${sv.seatsThatAreTodayCourtTowns} din ${ro.format(sv.units)} de unități consolidate au
         una chiar în oraș: mediana drumului e ${Math.round(
           sv.medianMetresToTodayCourt / 1000,
         )} km. După comasare ar rămâne 42, în ${sv.seatsThatAreCourtTowns} dintre orașele
         acestea, iar mediana ar urca la ${Math.round(
           sv.medianMetresToProposedCourt / 1000,
         )} km — media ponderată de la ${(sv.meanMetresToTodayCourt / 1000)
        .toFixed(1)
        .replace('.', ',')} la ${(sv.meanMetresToProposedCourt / 1000)
        .toFixed(1)
        .replace('.', ',')} km.</p>
       <p class="disagree">${ro.format(sv.unitsLosingTheirLocalCourt)} de unități —
         ${pctPeople(sv.peopleLosingTheirLocalCourt)} din locuitori — ar pierde instanța pe care
         o au acum în oraș. Peste 50 km de mers sunt azi ${sv.beyond['50']?.todayUnits} unități
         (${pctPeople(sv.beyond['50']?.todayPeople ?? 0)}), după reformă
         ${sv.beyond['50']?.proposedUnits} (${pctPeople(sv.beyond['50']?.proposedPeople ?? 0)});
         peste 75 km azi nu e nimeni, după reformă
         ${pctPeople(sv.beyond['75']?.proposedPeople ?? 0)} din țară. Nu e o înrăutățire de
         grad, e una de fel.</p>
       <p class="note">Cele ${ro.format(sum.units)} de unități consolidate din reforma
         administrativă, arondate fiecare la cea mai apropiată dintre cele
         ${arondare.courtSeats} de instanțe, pe drum, fără să conteze granița de județ.</p>
       <div class="pens-row">
         <span class="pens-head">unitate</span>
         <span class="pens-head">jud.</span>
         <span class="pens-head">instanța</span>
         <span class="pens-head">în jud.</span>
         ${arTop(rows)
           .map(
             (u) =>
               `<span>${u.name.replace(/^(ORAȘ|MUNICIPIUL) /, '')}</span>
                <span>${u.county}</span>
                <span class="pens-low">${arKm(u.metres!)} (${u.courtCounty ?? '—'})</span>
                <span>${arKm(u.ownCountyMetres!)}</span>`,
           )
           .join('')}
       </div>
       <p class="disagree">Reședințele de județ nu sunt așezate uniform, așa că
         ${sum.crossingCounty} de unități — ${ro.format(sum.peopleCrossingCounty)} de
         locuitori — au o instanță mai apropiată în alt județ decât în al lor. Pentru ei drumul
         e mai scurt cu ${arKm(sum.metresSavedEachCrossing)} în medie, iar pe țară media scade
         de la ${arKm(sum.meanMetresOwnCounty)} la ${arKm(sum.meanMetresNearest)}.</p>
       <p class="disagree">Unitatea se arondează întreagă, nu comună cu comună. Dacă fiecare
         comună și-ar alege singură instanța cea mai apropiată,
         ${sum.wouldSplitByCommune} din ${ro.format(sum.units)} de unități noi s-ar rupe între
         două instanțe — o arondare pe care nicio administrație nu ar putea-o ține.</p>
       <div id="arondare-live">${
         live
           ? `<label class="slider">Populația-țintă a unei unități
                <input type="range" id="p-target" min="20000" max="120000" step="5000" />
                <output id="p-target-out"></output></label>`
           : `<p class="note"><button id="arondare-couple" type="button">Recalculează cu
                propriile praguri</button> — rulează modelul administrativ aici (1,9 MB) și
                reface arondarea la fiecare mișcare.</p>`
       }</div>`;
  };

  renderArondare(arondare.summary, arondare.units, false);

  // The two reforms, coupled: the merge is re-run in the browser so the judicial map follows
  // whatever administrative map the reader has built, not only the shipped defaults. Loaded on
  // demand — most readers never open this fold, and the payload is most of the page's weight.
  let coupled: Coupled | null = null;
  const showLive = (result: Arondare, target: number): void => {
    renderArondare(
      result.summary,
      result.units.map((u) => ({
        ...u,
        courtCounty: u.courtRow === null ? null : (coupled?.meta.courts[u.courtRow]?.county ?? null),
      })),
      true,
    );
    const input = document.querySelector<HTMLInputElement>('#p-target');
    if (!input) return;
    input.value = String(target);
    el('#p-target-out').textContent = `${ro.format(target)} loc.`;
    input.addEventListener('input', () => {
      const next = Number(input.value);
      el('#p-target-out').textContent = `${ro.format(next)} loc.`;
      if (coupled) showLive(assign(coupled, { ...coupled.defaults, pTarget: next }), next);
    });
  };
  el('#arondare-body').addEventListener('click', (event) => {
    if (!(event.target as HTMLElement).closest('#arondare-couple')) return;
    el('#arondare-live').innerHTML = '<p class="note">Se încarcă modelul administrativ…</p>';
    void loadCoupling(base)
      .then((ready) => {
        coupled = ready;
        showLive(assign(ready, ready.defaults), ready.defaults.pTarget);
      })
      .catch((error: unknown) => {
        el('#arondare-live').innerHTML =
          `<p class="note">Nu s-a putut încărca modelul: ${String(error)}</p>`;
      });
  });

  el('#proiect-chev').textContent = proiect.spread.compresses
    ? 'comprimă grila'
    : 'lărgește grila';
  el('#proiect-body').innerHTML =
    `<p class="note">Proiectul din iulie 2026 plătește după coeficient × o valoare de referință
       de ${ro.format(proiect.referenceLei)} lei. Sumele de azi sunt în lei 2022 și cele din
       proiect în lei 2026, deci nivelurile nu se compară — rapoartele, da.</p>
     <div class="pens-row">
       <span class="pens-head">grad</span>
       <span class="pens-head">coef.</span>
       <span class="pens-head">proiect</span>
       <span class="pens-head">azi</span>
       ${proiect.byTier
         .map(
           (t) =>
             `<span>${TIER_LABEL[t.tier]}</span>
              <span>${dec2(t.coefficient)}</span>
              <span class="${t.ratioToToday < 1 ? 'pens-low' : ''}">${ro.format(t.monthlyLei)}</span>
              <span>${ro.format(t.todayMonthlyLei)}</span>`,
         )
         .join('')}
     </div>
     <p class="disagree">Evantaiul de la vârf la bază se strânge de la
       ${dec2(proiect.spread.todayRatio)} la ${dec2(proiect.spread.draftRatio)}: gradele
       de sus sunt tăiate, judecătoria e urcată. Nu e o creștere generală, e o comprimare.</p>
     <p class="disagree">Pentru simulatorul ăsta contează direct. Instanța de nivel 1 este
       tribunalul — lucrarea desființează judecătoriile —, dar nu spune dacă judecătorii veniți
       de acolo își păstrează gradul în tranziție. Diferența dintre grade scade de la
       ${ro.format(proiect.gradeGap.todayMonthlyLei)} la
       ${ro.format(proiect.gradeGap.draftMonthlyLei)} lei pe lună, deci întrebarea aceea
       valorează azi ${ro.format(Math.round((lowest?.todayLei ?? 0) / 1e6))} milioane de lei pe
       an și ar valora ${ro.format(Math.round((lowest?.draftLei ?? 0) / 1e6))} de milioane după
       proiect.</p>`;

  // The one number three other sections used to say could not be found. Shown against the two
  // things it decides — the draft law's ceiling and the pension bill's headline — because a
  // percentage of a wage bill means nothing to a reader on its own.
  const pct = (x: number): string => `${ro.format(Math.round(x * 1000) / 10)}%`;
  const narrow = sporuri.pension.readings.find((r) => r.measure === 'narrow');
  const wide = sporuri.pension.readings.find((r) => r.measure === 'wide');
  el('#sporuri-chev').textContent = pct(sporuri.sporuri.narrow);
  el('#sporuri-body').innerHTML =
    `<p class="note">Execuția bugetară pe 2025, pentru ordonatorul principal sub care
       raportează instanțele: ${ro.format(sporuri.scope.filledPosts)} de posturi ocupate.</p>
     <div class="pens-row">
       <span class="pens-head">măsură</span>
       <span class="pens-head">cotă</span>
       <span class="pens-head">plafon</span>
       <span class="pens-head">diferență</span>
       <span>sporuri</span>
       <span class="${sporuri.draftCap.overCap ? 'pens-low' : ''}">${pct(sporuri.sporuri.narrow)}</span>
       <span>${sporuri.draftCap.percent}%</span>
       <span class="${sporuri.draftCap.overCap ? 'pens-low' : ''}">${
         sporuri.draftCap.gapPercentagePoints > 0 ? '+' : ''
       }${ro.format(sporuri.draftCap.gapPercentagePoints)} p.p.</span>
       <span>peste bază</span>
       <span>${pct(sporuri.sporuri.wide)}</span>
       <span>—</span>
       <span>—</span>
     </div>
     <p class="note">„Sporuri” sunt paragrafele 10.01.05 și 10.01.06 din execuție; „peste bază”
       este tot ce se plătește în afara salariului de bază, indiferent cum se numește.</p>
     <p class="disagree">Proiectul de salarizare din iulie 2026 plafonează sporurile la
       ${sporuri.draftCap.percent}% din salariile de bază, pe ordonator principal. Instanțele
       sunt ${sporuri.draftCap.overCap ? 'peste' : 'sub'} acest plafon.</p>
     <p class="disagree">Proiectul de pensii taie procentul de la
       ${sporuri.pension.currentPercent}% la ${sporuri.pension.proposedPercent}%, dar în același
       timp lărgește baza de calcul cu exact aceste sporuri. Fără ele în bază, scăderea pare de
       ${ro.format(sporuri.pension.reductionWithoutSporuriPercent)}%; cu ele, este de
       ${ro.format(narrow?.reductionPercent ?? 0)}%${
         wide ? ` — sau ${ro.format(wide.reductionPercent)}% la definiția largă` : ''
       }.</p>
     <p class="note">Judecătorii sunt ${ro.format(Math.round(sporuri.judges.count))} din cei
       ${ro.format(sporuri.scope.filledPosts)} de angajați și ${pct(
         sporuri.judges.shareOfCourtsBase,
       )} din masa salarială de bază, deci procentul de mai sus e dat mai ales de grefieri.
       Dacă sporurile se împart uniform, scăderea pensiei e de
       ${ro.format(sporuri.pension.ifSporuriSpreadEvenlyPercent)}%; dacă judecătorii nu iau
       deloc sporuri, rămâne ${ro.format(sporuri.pension.ifJudgesDrawNoSporuriPercent)}%.
       Între ele, datele nu pot alege.</p>`;

  // The two pension reforms, against the same judge. The paper's cap is a flat sum and the
  // bill's floor is a share of each grade's own indemnity, so the two cross: for every grade
  // but the trainee the paper pays less than the bill's minimum. Marked where that happens
  // rather than left for a reader to compare four columns by eye.
  // Four columns in a 314-pixel panel: the headers have to be one word each or they wrap into
  // two lines apiece and the table becomes taller than the figures in it.
  const short = (grade: string): string =>
    grade.replace(/^Judecător (cu grad de )?/, '').replace(/,.*$/, '');
  el('#pensii-body').innerHTML =
    `<p class="note">Lei pe lună, la vârful grilei: pensia după regula de azi, pragul din
      proiectul Ministerului Justiției și plafonul propus de lucrare.</p>
     <div class="pens-row">
       <span class="pens-head">grad</span>
       <span class="pens-head">azi</span>
       <span class="pens-head">proiect</span>
       <span class="pens-head">lucrare</span>
       ${pensii.byGrade
         .map(
           (g) =>
             `<span>${short(g.grade)}</span>
              <span>${ro.format(g.currentLei)}</span>
              <span>${ro.format(g.billFloorLei)}</span>
              <span class="${g.paperCapBelowBillFloor ? 'pens-low' : ''}">${ro.format(
                g.paperCapLei,
              )}</span>`,
         )
         .join('')}
     </div>` +
    pensii.disagreements.map((d) => `<p class="disagree">${d.text}</p>`).join('');

  // The chapters that argue rather than measure, listed beneath the views that compute. Kept
  // collapsed: they are context for the map, not the map itself, and a reader who wants the
  // reasoning can open it while one reading the numbers is not made to scroll past it.
  el('#design-list').innerHTML = design.chapters
    .map(
      (c) =>
        `<details>
           <summary>${c.title}<span>cap. ${c.number}, p. ${c.page}</span></summary>
           <p class="excerpt">${c.excerpt}…</p>
         </details>`,
    )
    .join('');

  // The limitations are part of the map, not a footnote to it. The blocking one is the reason
  // this shows where courts are and refuses to show what closing one would cost.
  // Blocking caveats stay in the open; the rest fold. Thirteen paragraphs under a map is a
  // wall a reader scrolls past, and the ones that change how a number should be read are not
  // the ones to lose that way.
  const allLimits = [
    ...doc.limitations,
    ...proposal.limitations,
    ...costuri.limitations,
    ...pensii.limitations,
    ...sporuri.limitations,
    ...proiect.limitations,
    ...arondare.limitations,
    ...spitale.limitations,
    ...servicii.limitations,
    ...politie.limitations,
  ];
  const blocking = allLimits.filter((l) => l.severity === 'blocking');
  const rest = allLimits.filter((l) => l.severity !== 'blocking');
  el('#blocking').innerHTML = blocking
    .map((l) => `<p class="limit blocking"><strong>Nu putem răspunde:</strong> ${l.text}</p>`)
    .join('');
  el('#limits').innerHTML = rest.map((l) => `<p class="limit">${l.text}</p>`).join('');
  el('#limits-count').textContent = `${rest.length} rezerve`;
}

main().catch((error: unknown) => {
  el('#detail').innerHTML = `<p class="hint">Harta nu s-a putut încărca: ${String(error)}</p>`;
});

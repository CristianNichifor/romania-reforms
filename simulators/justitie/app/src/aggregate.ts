/**
 * Adding courts together, and taking statistics out of the sum.
 *
 * `portal-instante.json` deliberately publishes no percentile, for a reason that governs this
 * whole file: a median does not add. Two courts whose median case runs 120 days do not make a
 * county whose median case runs 120 days, and there is no weighting that recovers it — the
 * median of a union is not a function of the medians of its parts. What the file publishes
 * instead are counts and histograms, both of which do add, and the quantile is taken here, from
 * the summed bins. That is the quantile of the pooled distribution, which is the thing a reader
 * asking about a county actually means.
 *
 * The same argument applies twice more:
 *
 *   * A survival curve is not averageable either, so durations arrive as a life table — how many
 *     cases were resolved in each bin and how many were still running — and the curve is
 *     computed after summing. The actuarial estimator is what consumes that shape.
 *   * A share is not averageable when the denominators differ. Every ratio here is computed as
 *     summed numerator over summed denominator, never as a mean of per-court ratios, because the
 *     second silently weights a court of 500 cases like a court of 150.000.
 *
 * One thing this file refuses to do: include a court the crawl did not finish. Those rows carry
 * `acoperire.trunchiat` and are dropped from every aggregate, with the count reported, because a
 * county total that quietly included a court measured at 0,5% of its size would be wrong in a
 * direction nothing on the page could show.
 */

export interface Coverage {
  volumCsm: number | null;
  raportFataDeVolum: number | null;
  trunchiat: boolean;
}

export interface Adjournments {
  termeneCuSolutie: number;
  amanareCauza: number;
  amanarePronuntare: number;
  termenPreschimbat: number;
}

export interface LifeTable {
  dosare: number;
  urmarireZile: number;
  evenimente: number[];
  cenzurate: number[];
}

export interface Court {
  institutie: string;
  nume: string | null;
  level: string;
  judet: string | null;
  siruta: string | null;
  acoperire: Coverage;
  dosare: number;
  dosarePenale: number;
  sectii: number;
  completuri: number;
  peCategorie: Record<string, number>;
  amanari: Adjournments;
  peRol: number[];
  primulTermen: number[];
  intervalTermene: number[];
  durata: LifeTable;
}

export interface Edges {
  termene: number[];
  durata: number[];
  peRol: number[];
}

export interface CourtsFile {
  snapshot: {
    crawledAt: string;
    instante: number;
    dosare: number;
    institutieDinFisier: boolean;
    cohortMonths: number;
    cohortFrom: string;
    faraJudet: number;
    instanteTrunchiate: number;
    pragTrunchiere: number;
  };
  praguriZile: Edges;
  judete: Record<string, string>;
  instante: Court[];
  faraPotrivireDeNume: string[];
  instanteTrunchiate: string[];
  limitations: { id: string; text: string; severity: 'blocking' | 'material' | 'note' }[];
}

export interface Pooled {
  /** How many courts went in, and how many were left out for being unmeasured. */
  instante: number;
  trunchiate: number;
  dosare: number;
  dosarePenale: number;
  completuri: number;
  peCategorie: Record<string, number>;
  amanari: Adjournments;
  peRol: number[];
  primulTermen: number[];
  intervalTermene: number[];
  durata: LifeTable;
}

const add = (a: number[], b: number[]): number[] => a.map((value, index) => value + (b[index] ?? 0));

const zeros = (length: number): number[] => Array.from({ length }, () => 0);

/** Sum a selection of courts. Courts the crawl did not finish are excluded and counted. */
export function pool(courts: Court[], edges: Edges): Pooled {
  const usable = courts.filter((court) => !court.acoperire.trunchiat);
  const out: Pooled = {
    instante: usable.length,
    trunchiate: courts.length - usable.length,
    dosare: 0,
    dosarePenale: 0,
    completuri: 0,
    peCategorie: {},
    amanari: {
      termeneCuSolutie: 0,
      amanareCauza: 0,
      amanarePronuntare: 0,
      termenPreschimbat: 0,
    },
    peRol: zeros(edges.peRol.length),
    primulTermen: zeros(edges.termene.length),
    intervalTermene: zeros(edges.termene.length),
    durata: {
      dosare: 0,
      urmarireZile: 0,
      evenimente: zeros(edges.durata.length),
      cenzurate: zeros(edges.durata.length),
    },
  };

  for (const court of usable) {
    out.dosare += court.dosare;
    out.dosarePenale += court.dosarePenale;
    // Panels add across courts because each hearing belongs to exactly one court — the importer
    // assigns it by which court held the file that day. Under the older case-number mapping this
    // sum would have double-counted every escalated case's panels.
    out.completuri += court.completuri;
    for (const [categorie, count] of Object.entries(court.peCategorie)) {
      out.peCategorie[categorie] = (out.peCategorie[categorie] ?? 0) + count;
    }
    out.amanari.termeneCuSolutie += court.amanari.termeneCuSolutie;
    out.amanari.amanareCauza += court.amanari.amanareCauza;
    out.amanari.amanarePronuntare += court.amanari.amanarePronuntare;
    out.amanari.termenPreschimbat += court.amanari.termenPreschimbat;
    out.peRol = add(out.peRol, court.peRol);
    out.primulTermen = add(out.primulTermen, court.primulTermen);
    out.intervalTermene = add(out.intervalTermene, court.intervalTermene);
    out.durata.dosare += court.durata.dosare;
    out.durata.urmarireZile = Math.max(out.durata.urmarireZile, court.durata.urmarireZile);
    out.durata.evenimente = add(out.durata.evenimente, court.durata.evenimente);
    out.durata.cenzurate = add(out.durata.cenzurate, court.durata.cenzurate);
  }
  return out;
}

export interface Quantile {
  /** Days. Null when the selection has no observations at all. */
  zile: number | null;
  /** True when the answer fell in the open-ended last bin, so it is a floor and not a value. */
  esteUnPrag: boolean;
}

/**
 * A quantile off a summed histogram, interpolated inside the bin it lands in.
 *
 * Returning the bin's lower edge would quantise every answer to the grid and make two counties
 * that differ by a week read identically. Interpolating assumes the mass is spread evenly inside
 * the bin, which is wrong in the tail and nearly right where the bins are a day wide — and the
 * bins are a day wide exactly where the mass is.
 *
 * The last bin has no upper edge, so a quantile landing in it is reported as a threshold. It is
 * the one place a made-up number would be invisible: "more than a year" invented as "400 days"
 * looks like a measurement.
 */
export function quantileFromBins(counts: number[], edges: number[], fraction: number): Quantile {
  const total = counts.reduce((sum, count) => sum + count, 0);
  if (!total) return { zile: null, esteUnPrag: false };
  const target = total * fraction;
  let seen = 0;
  for (let index = 0; index < counts.length; index += 1) {
    const count = counts[index] ?? 0;
    if (seen + count >= target && count > 0) {
      const low = edges[index] ?? 0;
      const high = edges[index + 1];
      if (high === undefined) return { zile: low, esteUnPrag: true };
      const within = (target - seen) / count;
      return { zile: low + within * (high - low), esteUnPrag: false };
    }
    seen += count;
  }
  return { zile: edges[edges.length - 1] ?? null, esteUnPrag: true };
}

export interface Survival {
  dosare: number;
  solutionate: number;
  inCurs: number;
  urmarireZile: number;
  medianaZile: number | null;
  /** Share resolved by each requested day, or null where the cohort was not watched that long. */
  rezolvatePana: Record<string, number | null>;
}

/**
 * The actuarial survival estimate over a summed life table.
 *
 * Cases still running are not cases resolved, and the difference is the whole point: treating a
 * censored case as unresolved-forever makes a court look slow, and dropping it makes the court
 * look twice as fast as it is. The standard correction is to count a bin's censored cases as at
 * risk for half of it, which is what `effective` is.
 *
 * The curve stops at the follow-up. Past it there is no observation, and a resolution share
 * there is a projection wearing the clothes of a measurement — the caller gets null and draws
 * an outline rather than a bar.
 */
export function survival(table: LifeTable, edges: number[], marks = [90, 180, 365]): Survival {
  const events = table.evenimente.reduce((sum, count) => sum + count, 0);
  let atRisk = table.dosare;
  let running = 1;
  // Survival at each bin's *upper* edge, which is where the bin's events have all happened.
  const at: { day: number; alive: number }[] = [{ day: edges[0] ?? 0, alive: 1 }];

  for (let index = 0; index < table.evenimente.length; index += 1) {
    const happened = table.evenimente[index] ?? 0;
    const lost = table.cenzurate[index] ?? 0;
    const effective = atRisk - lost / 2;
    if (effective > 0) running *= 1 - happened / effective;
    atRisk -= happened + lost;
    const upper = edges[index + 1];
    if (upper !== undefined) at.push({ day: upper, alive: running });
  }

  /** Linear interpolation between the two bracketing bin edges. */
  const aliveAt = (day: number): number | null => {
    if (day > table.urmarireZile) return null;
    let previous = at[0];
    if (!previous) return null;
    for (const point of at) {
      if (point.day >= day) {
        const span = point.day - previous.day;
        if (span <= 0) return point.alive;
        const share = (day - previous.day) / span;
        return previous.alive + share * (point.alive - previous.alive);
      }
      previous = point;
    }
    return null;
  };

  let median: number | null = null;
  let previous = at[0];
  for (const point of at) {
    if (previous && point.alive <= 0.5 && previous.alive > 0.5) {
      const drop = previous.alive - point.alive;
      const share = drop > 0 ? (previous.alive - 0.5) / drop : 0;
      median = Math.round(previous.day + share * (point.day - previous.day));
      break;
    }
    previous = point;
  }

  return {
    dosare: table.dosare,
    solutionate: events,
    inCurs: table.dosare - events,
    urmarireZile: table.urmarireZile,
    medianaZile: median,
    rezolvatePana: Object.fromEntries(
      marks.map((day) => {
        const alive = aliveAt(day);
        return [`zi${day}`, alive === null ? null : Number((1 - alive).toFixed(4))];
      }),
    ),
  };
}

/** Percentile triple in the shape the quartile strips want, in days. */
export function strip(counts: number[], edges: number[]): {
  n: number;
  p25?: number;
  p50?: number;
  p75?: number;
} {
  const n = counts.reduce((sum, count) => sum + count, 0);
  if (!n) return { n: 0 };
  const value = (fraction: number) => {
    const found = quantileFromBins(counts, edges, fraction);
    return found.zile === null ? undefined : Math.round(found.zile);
  };
  return { n, p25: value(0.25), p50: value(0.5), p75: value(0.75) };
}

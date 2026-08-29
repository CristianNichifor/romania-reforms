/**
 * Reading the Art. 21(2) ceiling out of the budget execution.
 *
 * The statute caps supplements at 20% of the base wage bill **per ordonator principal de
 * credite and per funding source**. Every page that touched the ceiling until now had to
 * stop at illustrating it — add 20% to a base salary and see what it looks like — because
 * the data was thought not to exist at that level. It does, so the ceiling can be
 * evaluated: which institutions it binds, and how much of the wage bill sits behind them.
 *
 * Two choices decide what the numbers mean, and both are offered rather than picked here:
 *
 *   * **scope** — `pereche` counts ordonator × funding source, which is what the law
 *     measures; `ordonator` merges the sources, which is how the rule is usually read. The
 *     two differ substantially, and that gap is itself the finding.
 *   * **measure** — `narrow` is the two paragraphs the budget labels supplements, the
 *     nearest published proxy for the statutory set; `wide` is everything above base pay
 *     that is not a reimbursed expense. An institution can look compliant on the narrow
 *     reading purely by booking the money under a different paragraph, so the wide reading
 *     is the one that cannot be arranged away.
 */

export type CapScope = 'pereche' | 'ordonator';
export type CapMeasure = 'narrow' | 'wide';

/** A fiscal-document series, narrowed to the fields this module reads. */
export interface CapSeries {
  id: string;
  unit: string;
  dims?: Record<string, string>;
  observations: Array<{ period: string; value: number }>;
}

export interface CapBand {
  label: string;
  count: number;
  /** True when the whole band sits above the 20% ceiling. */
  overCap: boolean;
  /** Share of the units in this scope, for drawing. */
  share: number;
}

export interface CapReading {
  bands: CapBand[];
  /** How many units breach the ceiling. */
  overCapCount: number;
  /** How many units the scope contains at all. */
  total: number;
  /**
   * The share of the base wage bill inside breaching units. This is the number that
   * matters: counting institutions treats a commune and a ministry alike.
   */
  overCapWeight: number;
}

export interface CapEntity {
  cui: string;
  name: string;
  entityType: string;
  /** Base wage bill in lei — the size that decides whether a breach matters. */
  base: number;
  narrow: number;
  wide: number;
}

const last = (s: CapSeries): number => s.observations.at(-1)?.value ?? 0;

const matches = (s: CapSeries, kind: string, scope: CapScope, measure: CapMeasure): boolean =>
  s.dims?.kind === kind && s.dims?.scope === scope && s.dims?.measure === measure;

/**
 * The distribution for one scope and measure.
 *
 * Bands are ordered by the index the importer wrote, never by parsing their labels: a
 * label is prose and would re-sort the moment someone rewrote "sub 10%" as "0–10%".
 */
export function readCap(
  series: CapSeries[],
  scope: CapScope,
  measure: CapMeasure,
): CapReading | null {
  const bandSeries = series
    .filter((s) => matches(s, 'band', scope, measure))
    .sort((a, b) => Number(a.dims!.bandIndex ?? 0) - Number(b.dims!.bandIndex ?? 0));

  if (bandSeries.length === 0) return null;

  const counts = bandSeries.map((s) => ({
    label: s.dims!.band ?? '',
    count: last(s),
    overCap: s.dims!.overCap === 'true',
  }));
  const total = counts.reduce((sum, b) => sum + b.count, 0);

  const overCapSeries = series.find((s) => matches(s, 'overCap', scope, measure));
  const weightSeries = series.find((s) => matches(s, 'overCapWeight', scope, measure));

  return {
    bands: counts.map((b) => ({ ...b, share: total ? b.count / total : 0 })),
    // Prefer the importer's own count over re-summing the bands: if the two ever disagree
    // the bands are the thing that lost a row, and silently agreeing would hide it.
    overCapCount: overCapSeries ? last(overCapSeries) : counts.filter((b) => b.overCap).reduce((n, b) => n + b.count, 0),
    total,
    overCapWeight: weightSeries ? last(weightSeries) : 0,
  };
}

/** The named institutions, largest wage bill first. */
export function readCapEntities(series: CapSeries[]): CapEntity[] {
  const byCui = new Map<string, CapEntity>();

  const entry = (cui: string, dims: Record<string, string>): CapEntity => {
    const found = byCui.get(cui);
    if (found) return found;
    const made: CapEntity = {
      cui,
      name: dims.name ?? cui,
      entityType: dims.entityType ?? '',
      base: 0,
      narrow: 0,
      wide: 0,
    };
    byCui.set(cui, made);
    return made;
  };

  for (const s of series) {
    const dims = s.dims;
    if (!dims?.cui) continue;
    if (dims.kind === 'entity' && (dims.measure === 'narrow' || dims.measure === 'wide')) {
      entry(dims.cui, dims)[dims.measure as CapMeasure] = last(s);
    } else if (dims.kind === 'entityBase') {
      entry(dims.cui, dims).base = last(s);
    }
  }

  return [...byCui.values()].sort((a, b) => b.base - a.base);
}

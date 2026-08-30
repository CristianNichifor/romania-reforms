/**
 * The judicial map, recomputed from whatever administrative map the reader is looking at.
 *
 * The shipped arondare answers one question: which court each consolidated UAT would answer
 * to, at the administrative simulator's default settings. But those settings are sliders, and
 * a reader who moves them is looking at a different country — different units, different
 * seats, and therefore a different judicial map. Answering only for the defaults would be
 * answering a question nobody asked.
 *
 * So the merge runs here too. The administrative model is already a TypeScript port with a
 * verified parity fixture against its Python reference, and it is imported rather than
 * reimplemented — a second implementation of a 2.000-line solver would be a second set of
 * bugs, and the two would disagree silently.
 *
 * What the browser cannot do is route. Dijkstra over 3.186 nodes on every slider drag is the
 * wrong place to spend a frame, so road distance arrives precomputed: 42 court seats by 3.186
 * UATs, unsigned 16-bit hundreds of metres, 261 KB. Assignment is then one pass over 42
 * numbers per unit.
 *
 * Assignment is by unit and by distance alone. A consolidated UAT goes whole to its nearest
 * seat — splitting one between two courts is not an arondare anyone could administer — and
 * county lines do not enter it, because resedintele de judet are not evenly spaced and a
 * citizen near a county border has no reason to drive past a nearer courthouse.
 */

import { decode } from '../../../administrativ/web/src/model/load';
import { runModel } from '../../../administrativ/web/src/model/model';
import { DEFAULT_PARAMS } from '../../../administrativ/web/src/model/types';
import type { ModelData, Params } from '../../../administrativ/web/src/model/types';

export interface CourtSeat {
  county: string;
  siruta: string;
  name: string;
}

export interface CourtDistanceMeta {
  file: string;
  scaleMetres: number;
  unreachable: number;
  rows: number;
  columns: number;
  courts: CourtSeat[];
}

export interface AssignedUnit {
  seatIndex: number;
  name: string;
  county: string;
  members: number;
  population: number;
  courtRow: number | null;
  metres: number | null;
  ownCountyMetres: number | null;
  crossesCounty: boolean;
}

export interface Arondare {
  units: AssignedUnit[];
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
  /** Court row index per UAT, so the map can paint every commune by the court it answers to. */
  courtOf: Int16Array;
}

export interface Coupled {
  data: ModelData;
  meta: CourtDistanceMeta;
  distance: Uint16Array;
  /** Court row index per county code, for "the court inside your own county". */
  rowOfCounty: Map<string, number>;
  defaults: Params;
}

/**
 * Load the administrative model's payload and the court distance matrix.
 *
 * Both are fetched from this app's own `data/`, not across from the administrative site.
 * Duplicating 1,6 MB is the price of the page working when it is the only one deployed, and a
 * cross-app relative fetch would break in preview and in any single-simulator build.
 */
export async function loadCoupling(base: string): Promise<Coupled> {
  const get = (name: string) => fetch(`${base}data/${name}`);
  const [manifest, attributes, attributesBin, adjacencyBin, candidacyBin, meta] =
    await Promise.all([
      get('admin-manifest.json').then((r) => r.json()),
      get('admin-attributes.json').then((r) => r.json()),
      get('admin-attributes.bin').then((r) => r.arrayBuffer()),
      get('admin-adjacency.bin').then((r) => r.arrayBuffer()),
      get('admin-candidacy.bin').then((r) => r.arrayBuffer()),
      get('court-distance.json').then((r) => r.json() as Promise<CourtDistanceMeta>),
    ]);

  const data = decode({ manifest, attributes, attributesBin, adjacencyBin, candidacyBin });
  const buffer = await (await get(meta.file)).arrayBuffer();
  const distance = new Uint16Array(buffer);
  if (distance.length !== meta.rows * meta.columns) {
    throw new Error(
      `court distance is ${distance.length} cells, expected ${meta.rows * meta.columns}`,
    );
  }
  if (meta.columns !== data.uatCount) {
    throw new Error(`distance covers ${meta.columns} UATs, the model has ${data.uatCount}`);
  }

  const rowOfCounty = new Map<string, number>();
  meta.courts.forEach((court, row) => rowOfCounty.set(court.county, row));

  // The administrative model's own defaults, imported rather than retyped. The first version
  // of this file copied the thirteen values by hand and got `x` — the absorber population
  // threshold — wrong at 0 instead of 7.500, which produced 259 units where the Python
  // reference produces 249. The parameters are the whole input; there is no safe place to
  // paraphrase them.
  return { data, meta, distance, rowOfCounty, defaults: { ...DEFAULT_PARAMS } };
}

/** Nearest court row for one UAT column, or null where no seat reaches it. */
function nearestRow(
  distance: Uint16Array,
  meta: CourtDistanceMeta,
  column: number,
): { row: number; metres: number } | null {
  // Every index below is bounded by the shape the loader already checked against the model's
  // UAT count, so the assertions are asserting a fact rather than papering over an unknown.
  let bestRow = -1;
  let best = meta.unreachable;
  for (let row = 0; row < meta.rows; row += 1) {
    const value = distance[row * meta.columns + column]!;
    if (value < best) {
      best = value;
      bestRow = row;
    }
  }
  // An all-unreachable column must yield nothing rather than row zero. Taking the minimum of a
  // row of sentinels and keeping the index is how the Python version silently handed Sulina
  // the alphabetically first court in the country.
  return bestRow < 0 ? null : { row: bestRow, metres: best * meta.scaleMetres };
}

/** Run the merge at these parameters, then assign every consolidated unit to a court. */
export function assign(coupled: Coupled, params: Params): Arondare {
  const { data, meta, distance, rowOfCounty } = coupled;
  const result = runModel(data, params);
  const { regionOf } = result;

  const members = new Map<number, number[]>();
  for (let uat = 0; uat < data.uatCount; uat += 1) {
    const seat = regionOf[uat]!;
    const list = members.get(seat);
    if (list) list.push(uat);
    else members.set(seat, [uat]);
  }

  const courtOf = new Int16Array(data.uatCount).fill(-1);
  const units: AssignedUnit[] = [];
  let split = 0;

  for (const [seat, list] of [...members.entries()].sort((a, b) => a[0] - b[0])) {
    const county = data.attributes.county[seat]!;
    const nearest = nearestRow(distance, meta, seat);
    const ownRow = rowOfCounty.get(county);
    const ownRaw =
      ownRow === undefined ? meta.unreachable : distance[ownRow * meta.columns + seat]!;

    let population = 0;
    for (const uat of list) {
      population += data.population[uat]!;
      courtOf[uat] = nearest ? nearest.row : -1;
    }

    // Would routing each commune on its own have torn this unit between two courts? Counted
    // because it is the argument for assigning the unit whole rather than a preference.
    //
    // Communes no road reaches are skipped rather than treated as a court of their own. Eight
    // of the eleven are in the Delta, and counting them as disagreement marked three units as
    // split that no routing would ever have split — 113 against the reference model's 110.
    let first: number | null = null;
    for (const uat of list) {
      const each = nearestRow(distance, meta, uat);
      if (!each) continue;
      if (first === null) first = each.row;
      else if (each.row !== first) {
        split += 1;
        break;
      }
    }

    units.push({
      seatIndex: seat,
      name: data.attributes.name[seat]!,
      county,
      members: list.length,
      population,
      courtRow: nearest ? nearest.row : null,
      metres: nearest ? nearest.metres : null,
      ownCountyMetres: ownRaw === meta.unreachable ? null : ownRaw * meta.scaleMetres,
      crossesCounty: nearest ? meta.courts[nearest.row]!.county !== county : false,
    });
  }

  const routed = units.filter((u) => u.metres !== null);
  const crossing = routed.filter((u) => u.crossesCounty);
  const comparable = crossing.filter((u) => u.ownCountyMetres !== null);
  const people = routed.reduce((sum, u) => sum + u.population, 0) || 1;
  const withOwn = routed.filter((u) => u.ownCountyMetres !== null);
  const ownPeople = withOwn.reduce((sum, u) => sum + u.population, 0) || 1;
  const crossingPeople = comparable.reduce((sum, u) => sum + u.population, 0);

  return {
    units,
    courtOf,
    summary: {
      units: units.length,
      routed: routed.length,
      crossingCounty: crossing.length,
      peopleCrossingCounty: crossing.reduce((sum, u) => sum + u.population, 0),
      wouldSplitByCommune: split,
      meanMetresOwnCounty: Math.round(
        withOwn.reduce((sum, u) => sum + u.ownCountyMetres! * u.population, 0) / ownPeople,
      ),
      meanMetresNearest: Math.round(
        routed.reduce((sum, u) => sum + u.metres! * u.population, 0) / people,
      ),
      metresSavedEachCrossing: crossingPeople
        ? Math.round(
            comparable.reduce(
              (sum, u) => sum + (u.ownCountyMetres! - u.metres!) * u.population,
              0,
            ) / crossingPeople,
          )
        : 0,
    },
  };
}

/**
 * The transport network, recomputed from whatever administrative map the reader is looking at.
 *
 * The page used to carry five consolidation scenarios frozen at build time, with a selector.
 * That was always the wrong shape. `export_hubs.py` opens by saying it freezes *one*
 * administrative scenario; the sweep then quietly re-decided the same thing five more ways and
 * put a control on the page for it. Administrativ owns consolidation. A reader who moves its
 * sliders is looking at a different country — different centres, different absorbers — and
 * answering only for five presets is answering a question nobody asked.
 *
 * So the merge runs here, exactly as `justitie` already does it, and by importing the same
 * model rather than reimplementing it. A second implementation of that solver would be a
 * second set of bugs and the two would disagree in silence.
 *
 * **What this adds over justitie's coupling is routing.** The judicial map needs distance from
 * 42 fixed courts, so it ships a precomputed matrix. Transport's centres are not fixed — they
 * are whatever the reader's scenario produced — so no matrix can be precomputed. It needs the
 * graph, and the graph is small: 9.281 edges between adjacent UATs, 73 KB, and Dijkstra over
 * it takes milliseconds. That is the whole reason this is possible at all, and I wrongly
 * assumed for most of this project that it was not.
 *
 * **Journey shape.** A commune reaches its centre on a feeder, waits, and rides a trunk to the
 * county capital. Both legs are shortest paths over road time; the wait is the timetable's,
 * and belongs to the service standard rather than to geography.
 */

import { decode } from '../../../administrativ/web/src/model/load';
import { runModel } from '../../../administrativ/web/src/model/model';
import { decode as decodeScenario } from '../../../administrativ/web/src/app/scenario';
import { DEFAULT_PARAMS } from '../../../administrativ/web/src/model/types';
import type { ModelData, Params, Pin } from '../../../administrativ/web/src/model/types';

/** The road graph, in compressed rows, weighted by seconds rather than metres. */
export interface RoadTime {
  /** Neighbour UAT index, grouped by source. */
  target: Uint16Array;
  /** Seconds to that neighbour, aligned with `target`. Impassable edges are omitted. */
  seconds: Float32Array;
  /** Row start per UAT index; `start[i]`..`start[i+1]` are i's edges. */
  start: Uint32Array;
  edgeCount: number;
  impassable: number;
}

export interface Coupled {
  data: ModelData;
  road: RoadTime;
  defaults: Params;
}

/** One commune's journey to its county capital, in minutes, under one scenario. */
export interface Journey {
  /** Minutes to the centre that absorbs this commune, or -1 with no road. Zero for a centre. */
  feeder: number;
  /** Minutes from that centre to the county capital, or -1 with no road. */
  trunk: number;
  /** Centre UAT index. */
  centre: number;
  /** Both legs exist. */
  reachable: boolean;
}

export interface Network {
  journeys: Journey[];
  centres: number[];
  /**
   * Communes with no road route to their own centre — the delta and the river islands.
   *
   * Counted separately from `centresWithoutTrunk` on purpose. Collapsing the two put 45
   * communes here against the pipeline's 14, because every member of a centre that could not
   * reach its capital was being called unreachable even though its feeder was fine. Two
   * different failures that need two different answers: one village is cut off, the other has
   * a bus to its town and no onward service.
   */
  unroutable: number;
  /** Centres with no road route to their county capital. */
  centresWithoutTrunk: number;
}

const IMPASSABLE = -1;

/**
 * Build compressed rows from the flat edge list.
 *
 * Impassable edges are dropped rather than kept at infinity. An unmeasured edge must never
 * become a shortcut, and a missing edge says that more plainly than a large number does.
 */
function toRows(
  a: Uint16Array,
  b: Uint16Array,
  seconds: Float32Array,
  uatCount: number,
): RoadTime {
  const degree = new Uint32Array(uatCount + 1);
  let kept = 0;
  for (let e = 0; e < seconds.length; e += 1) {
    if (!Number.isFinite(seconds[e])) continue;
    degree[a[e]] += 1;
    degree[b[e]] += 1;
    kept += 1;
  }

  const start = new Uint32Array(uatCount + 1);
  for (let i = 0; i < uatCount; i += 1) start[i + 1] = start[i] + degree[i];

  const cursor = start.slice(0, uatCount);
  const target = new Uint16Array(kept * 2);
  const weight = new Float32Array(kept * 2);
  for (let e = 0; e < seconds.length; e += 1) {
    const s = seconds[e];
    if (!Number.isFinite(s)) continue;
    target[cursor[a[e]]] = b[e];
    weight[cursor[a[e]]] = s;
    cursor[a[e]] += 1;
    target[cursor[b[e]]] = a[e];
    weight[cursor[b[e]]] = s;
    cursor[b[e]] += 1;
  }

  return {
    target,
    seconds: weight,
    start,
    edgeCount: kept,
    impassable: seconds.length - kept,
  };
}

/** The bytes `assemble` needs: administrativ's model payload plus the road-time graph. */
export interface Payload {
  manifest: unknown;
  attributes: unknown;
  attributesBin: ArrayBuffer;
  adjacencyBin: ArrayBuffer;
  candidacyBin: ArrayBuffer;
  roadMeta: { edgeCount: number };
  roadBin: ArrayBuffer;
}

/**
 * Assemble the model and graph from already-fetched bytes.
 *
 * Split from the fetching so a test can feed it the same files off disk and check that the
 * browser reproduces the Python pipeline. Without that check the two would be free to disagree
 * quietly, which is the standing risk in porting a model to the page that displays it.
 */
export function assemble(payload: Payload): Coupled {
  const { manifest, attributes, attributesBin, adjacencyBin, candidacyBin, roadMeta, roadBin } =
    payload;
  const data = decode({
    manifest,
    attributes,
    attributesBin,
    adjacencyBin,
    candidacyBin,
  } as never);

  const n = roadMeta.edgeCount as number;
  const expected = n * 2 + n * 2 + n * 4;
  if (roadBin.byteLength !== expected) {
    throw new Error(
      `road-time.bin is ${roadBin.byteLength} bytes, expected ${expected} for ${n} edges`,
    );
  }
  const a = new Uint16Array(roadBin, 0, n);
  const b = new Uint16Array(roadBin, n * 2, n);
  const seconds = new Float32Array(roadBin.slice(n * 4));

  // The endpoints are indices into administrativ's UAT order. If that order ever changed
  // without this file being regenerated, every edge would join two different communes and the
  // resulting map would look completely reasonable.
  //
  // The first version of this guard read `Math.max(...[a[0], b[0]], data.uatCount - 1)`, which
  // includes the bound it is checking against and therefore can never exceed it. It was a
  // guard that could not fail — the most expensive kind, because it reads as protection.
  let maxIndex = 0;
  for (let e = 0; e < n; e += 1) {
    if (a[e] > maxIndex) maxIndex = a[e];
    if (b[e] > maxIndex) maxIndex = b[e];
  }
  if (maxIndex >= data.uatCount) {
    throw new Error(`road-time references UAT ${maxIndex}, the model has ${data.uatCount}`);
  }

  return {
    data,
    road: toRows(a, b, seconds, data.uatCount),
    // The model's own defaults, imported rather than retyped. Justitie's first attempt copied
    // the thirteen values by hand, got the absorber threshold wrong, and produced 259 units
    // where the reference produces 249. There is no safe place to paraphrase the parameters.
    defaults: { ...DEFAULT_PARAMS },
  };
}

/** Fetch the payload from this app's own data directory, then assemble it. */
export async function loadCoupling(base: string): Promise<Coupled> {
  const get = (name: string) => fetch(`${base}data/${name}`);
  const [manifest, attributes, attributesBin, adjacencyBin, candidacyBin, roadMeta, roadBin] =
    await Promise.all([
      get('admin-manifest.json').then((r) => r.json()),
      get('admin-attributes.json').then((r) => r.json()),
      get('admin-attributes.bin').then((r) => r.arrayBuffer()),
      get('admin-adjacency.bin').then((r) => r.arrayBuffer()),
      get('admin-candidacy.bin').then((r) => r.arrayBuffer()),
      get('road-time.json').then((r) => r.json()),
      get('road-time.bin').then((r) => r.arrayBuffer()),
    ]);
  return assemble({
    manifest,
    attributes,
    attributesBin,
    adjacencyBin,
    candidacyBin,
    roadMeta,
    roadBin,
  });
}

/** The scenario the reader arrived with — sliders and pins — or the model's defaults. */
export function readScenario(hash: string): { params: Params; pins: Pin[] } {
  // The decoder fills every parameter from the model's defaults, so an empty hash yields the
  // default country rather than a half-built one. Same call justitie makes.
  const scenario = decodeScenario(hash, 'ro');
  return { params: scenario.params, pins: scenario.pins };
}

/** Which sliders the reader actually moved. Empty means they are on the defaults. */
export function changedParams(params: Params): (keyof Params)[] {
  return (Object.keys(DEFAULT_PARAMS) as (keyof Params)[]).filter(
    (key) => params[key] !== DEFAULT_PARAMS[key],
  );
}

/**
 * Shortest road time in seconds from one source to every UAT it can reach.
 *
 * A plain binary heap over 3.186 nodes. Called once per centre and once per county capital,
 * which is a few hundred searches over a 9.281-edge graph — well inside a frame budget, and
 * the reason none of this needs precomputing.
 */
export function shortestTimes(
  road: RoadTime,
  source: number,
  uatCount: number,
  zoneOf?: Uint8Array,
): Float64Array {
  // A feeder serves one routing zone and may not leave it. Without this the search happily
  // reaches a commune through the next county and the browser strands 9 communes where the
  // pipeline strands 14 — it was finding roads the service standard does not allow.
  const zone = zoneOf ? zoneOf[source] : -1;
  const dist = new Float64Array(uatCount).fill(Infinity);
  dist[source] = 0;

  const heapNode: number[] = [source];
  const heapCost: number[] = [0];

  const swap = (i: number, j: number) => {
    [heapNode[i], heapNode[j]] = [heapNode[j], heapNode[i]];
    [heapCost[i], heapCost[j]] = [heapCost[j], heapCost[i]];
  };

  const push = (node: number, cost: number) => {
    heapNode.push(node);
    heapCost.push(cost);
    let i = heapNode.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (heapCost[parent] <= heapCost[i]) break;
      swap(parent, i);
      i = parent;
    }
  };

  const pop = (): number => {
    const top = heapNode[0];
    const last = heapNode.length - 1;
    swap(0, last);
    heapNode.pop();
    heapCost.pop();
    let i = 0;
    for (;;) {
      const l = i * 2 + 1;
      const r = l + 1;
      let small = i;
      if (l < heapNode.length && heapCost[l] < heapCost[small]) small = l;
      if (r < heapNode.length && heapCost[r] < heapCost[small]) small = r;
      if (small === i) break;
      swap(small, i);
      i = small;
    }
    return top;
  };

  const settled = new Uint8Array(uatCount);
  while (heapNode.length) {
    const node = pop();
    if (settled[node]) continue;
    settled[node] = 1;
    for (let e = road.start[node]; e < road.start[node + 1]; e += 1) {
      const next = road.target[e];
      if (zoneOf && zoneOf[next] !== zone) continue;
      const cost = dist[node] + road.seconds[e];
      if (cost < dist[next]) {
        dist[next] = cost;
        push(next, cost);
      }
    }
  }
  return dist;
}

/**
 * Run the reader's scenario and route it.
 *
 * `regionOf` from the administrative model *is* this simulator's hub assignment — the absorber
 * index for each commune. Nothing is re-derived; the centres are whatever that scenario made.
 */
export function zonesOf(data: ModelData): Uint8Array {
  // The routing zone is the county, with one exception the road network forces: Bucharest and
  // Ilfov are one travel-to-work area, and 28 Ilfov communes are absorbed by a Bucharest
  // sector. Treating them as separate zones cuts those communes off from their own centre.
  const zone = Uint8Array.from(data.countyOf);
  if (data.bucharestCounty >= 0 && data.ilfovCounty >= 0) {
    for (let i = 0; i < zone.length; i += 1) {
      if (zone[i] === data.ilfovCounty) zone[i] = data.bucharestCounty;
    }
  }
  return zone;
}

export function buildNetwork(coupled: Coupled, params: Params, pins: Pin[] = []): Network {
  const { data, road } = coupled;
  const zoneOf = zonesOf(data);
  const result = runModel(data, params, pins);
  const { regionOf } = result;
  const uatCount = data.uatCount;

  const centres = Array.from(new Set(Array.from(regionOf))).sort((x, y) => x - y);

  // One search per centre gives every commune its feeder time. Searching from the centre
  // rather than from each commune is what makes this 249 searches instead of 3.186.
  const feederOf = new Float64Array(uatCount).fill(Infinity);
  for (const centre of centres) {
    const dist = shortestTimes(road, centre, uatCount, zoneOf);
    for (let i = 0; i < uatCount; i += 1) {
      if (regionOf[i] === centre) feederOf[i] = dist[i];
    }
  }

  // And one per county capital gives every centre its trunk time. A capital's own unit has no
  // trunk leg: the passenger is already there.
  const trunkOfCentre = new Map<number, number>();
  for (const [county, capital] of data.capitalOfCounty) {
    const dist = shortestTimes(road, capital, uatCount, zoneOf);
    for (const centre of centres) {
      if (data.countyOf[centre] === county) trunkOfCentre.set(centre, dist[centre]);
    }
  }

  let unroutable = 0;
  const journeys: Journey[] = [];
  for (let i = 0; i < uatCount; i += 1) {
    const centre = regionOf[i];
    const feederS = feederOf[i];
    const trunkS = trunkOfCentre.get(centre) ?? Infinity;
    const hasFeeder = Number.isFinite(feederS);
    const hasTrunk = Number.isFinite(trunkS);
    if (!hasFeeder) unroutable += 1;
    journeys.push({
      feeder: hasFeeder ? feederS / 60 : IMPASSABLE,
      trunk: hasTrunk ? trunkS / 60 : IMPASSABLE,
      centre,
      reachable: hasFeeder && hasTrunk,
    });
  }

  const centresWithoutTrunk = centres.filter(
    (centre) => !Number.isFinite(trunkOfCentre.get(centre) ?? Infinity),
  ).length;

  return { journeys, centres, unroutable, centresWithoutTrunk };
}

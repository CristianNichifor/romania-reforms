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
  /** Metres to that neighbour, aligned with `target`. Costing is per kilometre, not per minute. */
  metres: Float32Array;
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
  /** Kilometres of that same trunk leg. Costing is per kilometre; without it the trunk tier
   *  runs for free and the network reads about a sixth cheaper than it is. */
  trunkKm: number;
  /** Centre UAT index. */
  centre: number;
  /** Both legs exist. */
  reachable: boolean;
}

export interface Network {
  journeys: Journey[];
  centres: number[];
  /**
   * Which centre each UAT belongs to — the administrative model's own `regionOf`, exposed
   * rather than kept inside the build.
   *
   * The map needs it to answer the question a reader actually asks of this page: not "how many
   * minutes" but "minutes to WHERE". Without it the popup reports a journey to an unnamed
   * destination, and the live coupling to the administrative reform — the whole point of the
   * page — is invisible, because moving a slider changes a number with no visible cause.
   */
  regionOf: Uint16Array;
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
  metres: Float32Array,
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
  const length = new Float32Array(kept * 2);
  for (let e = 0; e < seconds.length; e += 1) {
    const s = seconds[e];
    if (!Number.isFinite(s)) continue;
    target[cursor[a[e]]] = b[e];
    weight[cursor[a[e]]] = s;
    length[cursor[a[e]]] = metres[e];
    cursor[a[e]] += 1;
    target[cursor[b[e]]] = a[e];
    weight[cursor[b[e]]] = s;
    length[cursor[b[e]]] = metres[e];
    cursor[b[e]] += 1;
  }

  return {
    target,
    seconds: weight,
    metres: length,
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
  const expected = n * 2 + n * 2 + n * 4 + n * 4;
  if (roadBin.byteLength !== expected) {
    throw new Error(
      `road-time.bin is ${roadBin.byteLength} bytes, expected ${expected} for ${n} edges`,
    );
  }
  const a = new Uint16Array(roadBin, 0, n);
  const b = new Uint16Array(roadBin, n * 2, n);
  const seconds = new Float32Array(roadBin.slice(n * 4, n * 8));
  const metres = new Float32Array(roadBin.slice(n * 8));

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
    road: toRows(a, b, seconds, metres, data.uatCount),
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
  const trunkKmOfCentre = new Map<number, number>();
  for (const [county, capital] of data.capitalOfCounty) {
    // `tree` rather than `shortestTimes`: it carries metres along the same chosen path, and the
    // trunk leg has to be paid for in kilometres as well as counted in minutes.
    const t = tree(road, capital, uatCount, zoneOf);
    for (const centre of centres) {
      if (data.countyOf[centre] === county) {
        trunkOfCentre.set(centre, t.distance[centre]);
        trunkKmOfCentre.set(centre, t.metres[centre] / 1000);
      }
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
    const km = trunkKmOfCentre.get(centre) ?? Infinity;
    journeys.push({
      feeder: hasFeeder ? feederS / 60 : IMPASSABLE,
      trunk: hasTrunk ? trunkS / 60 : IMPASSABLE,
      trunkKm: Number.isFinite(km) ? km : IMPASSABLE,
      centre,
      reachable: hasFeeder && hasTrunk,
    });
  }

  const centresWithoutTrunk = centres.filter(
    (centre) => !Number.isFinite(trunkOfCentre.get(centre) ?? Infinity),
  ).length;

  return { journeys, centres, unroutable, centresWithoutTrunk, regionOf };
}


/** One route: a hub, the leaf it runs out to, and the communes it is responsible for. */
export interface Route {
  hub: number;
  leaf: number;
  /** Every UAT on the path, hub last. Each is a stop, and dwell is charged per stop. */
  stops: number[];
  /** The UATs this route is responsible for — a commune is served by exactly one. */
  serves: number[];
  oneWayMin: number;
  oneWayKm: number;
}

interface Tree {
  distance: Float64Array;
  metres: Float64Array;
  parent: Int32Array;
  seen: Uint8Array;
}

/**
 * Shortest-path tree from a hub, carrying metres along the chosen path.
 *
 * Distance decides the tree; metres are accumulated along it rather than minimised separately.
 * Taking the shortest-metres path would describe a different route from the one the timetable
 * runs, and the two would disagree about the same bus.
 */
function tree(road: RoadTime, hub: number, uatCount: number, zoneOf: Uint8Array): Tree {
  const distance = new Float64Array(uatCount).fill(Infinity);
  const metres = new Float64Array(uatCount).fill(Infinity);
  const parent = new Int32Array(uatCount).fill(-1);
  const seen = new Uint8Array(uatCount);
  distance[hub] = 0;
  metres[hub] = 0;
  seen[hub] = 1;

  const zone = zoneOf[hub];
  const nodes: number[] = [hub];
  const costs: number[] = [0];
  const swap = (i: number, j: number) => {
    [nodes[i], nodes[j]] = [nodes[j], nodes[i]];
    [costs[i], costs[j]] = [costs[j], costs[i]];
  };
  const push = (node: number, cost: number) => {
    nodes.push(node);
    costs.push(cost);
    let i = nodes.length - 1;
    while (i > 0) {
      const up = (i - 1) >> 1;
      if (costs[up] <= costs[i]) break;
      swap(up, i);
      i = up;
    }
  };
  const pop = () => {
    const top = nodes[0];
    swap(0, nodes.length - 1);
    nodes.pop();
    costs.pop();
    let i = 0;
    for (;;) {
      const l = i * 2 + 1;
      const r = l + 1;
      let small = i;
      if (l < nodes.length && costs[l] < costs[small]) small = l;
      if (r < nodes.length && costs[r] < costs[small]) small = r;
      if (small === i) break;
      swap(small, i);
      i = small;
    }
    return top;
  };

  const settled = new Uint8Array(uatCount);
  while (nodes.length) {
    const here = pop();
    if (settled[here]) continue;
    settled[here] = 1;
    for (let e = road.start[here]; e < road.start[here + 1]; e += 1) {
      const next = road.target[e];
      if (zoneOf[next] !== zone) continue;
      const through = distance[here] + road.seconds[e];
      if (through < distance[next]) {
        distance[next] = through;
        metres[next] = metres[here] + road.metres[e];
        parent[next] = here;
        seen[next] = 1;
        push(next, through);
      }
    }
  }
  return { distance, metres, parent, seen };
}

function chain(node: number, parent: Int32Array): number[] {
  const out = [node];
  for (;;) {
    const up = parent[out[out.length - 1]];
    if (up < 0) break;
    out.push(up);
  }
  return out;
}

/**
 * Routes out of one hub.
 *
 * Every leaf of the tree becomes a route stopping at each UAT down its branch. That alone
 * collapses thousands of village-to-centre shuttles into hundreds of routes, because a village
 * on the way to a further village is a stop rather than a service of its own.
 *
 * Leaves are taken largest-population first so the biggest place on a branch decides the
 * vehicle, and `served` stops a commune being counted twice when branches overlap.
 */
export function routesForHub(
  road: RoadTime,
  hub: number,
  members: number[],
  uatCount: number,
  zoneOf: Uint8Array,
  population: Uint32Array,
): Route[] {
  const { distance, metres, parent, seen } = tree(road, hub, uatCount, zoneOf);
  const reachable = members.filter((m) => m !== hub && seen[m] === 1);
  if (!reachable.length) return [];

  const ancestors = new Set<number>();
  for (const m of reachable) for (const node of chain(m, parent).slice(1)) ancestors.add(node);

  const leaves = reachable
    .filter((m) => !ancestors.has(m))
    .sort((a, b) => population[b] - population[a] || a - b);

  const memberSet = new Set(members);
  const served = new Set<number>();
  const routes: Route[] = [];
  for (const leaf of leaves) {
    const stops = chain(leaf, parent);
    const serves = stops.filter((s) => s !== hub && memberSet.has(s) && !served.has(s));
    serves.forEach((s) => served.add(s));
    routes.push({
      hub,
      leaf,
      stops,
      serves,
      oneWayMin: distance[leaf] / 60,
      oneWayKm: metres[leaf] / 1000,
    });
  }
  return routes;
}

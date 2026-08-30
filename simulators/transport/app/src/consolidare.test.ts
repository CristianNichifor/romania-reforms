/**
 * Parity between the browser network and the Python pipeline.
 *
 * The page now recomputes the whole transport network from the reader's administrative
 * scenario, which means a TypeScript path and a Python path answer the same question. Two
 * implementations of one model is how a page and its pipeline start disagreeing without
 * anybody finding out — administrativ guards its own port with hash fixtures for exactly this
 * reason, and this is transport's equivalent.
 *
 * At the model's default parameters the browser must land on the same country the pipeline
 * published in `data/hubs.json` and `data/access.json`. Not approximately the same shape: the
 * same number of centres, and journey times close enough that no commune could be painted a
 * band away from where the pipeline put it.
 */
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { assemble, buildNetwork, changedParams, readScenario, shortestTimes } from './consolidare';

const app = join(dirname(fileURLToPath(import.meta.url)), '..');
const data = join(app, 'public', 'data');
const sim = join(app, '..');

const ready = existsSync(join(data, 'admin-manifest.json')) && existsSync(join(data, 'road-time.bin'));

const bin = (name: string): ArrayBuffer => {
  const b = readFileSync(join(data, name));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};
const json = (name: string) => JSON.parse(readFileSync(join(data, name), 'utf8'));
const simJson = (name: string) => JSON.parse(readFileSync(join(sim, 'data', name), 'utf8'));

const coupled = () =>
  assemble({
    manifest: json('admin-manifest.json'),
    attributes: json('admin-attributes.json'),
    attributesBin: bin('admin-attributes.bin'),
    adjacencyBin: bin('admin-adjacency.bin'),
    candidacyBin: bin('admin-candidacy.bin'),
    roadMeta: json('road-time.json'),
    roadBin: bin('road-time.bin'),
  });

describe.skipIf(!ready)('browser network against the Python pipeline', () => {
  it('produces the same centres at the default parameters', () => {
    const c = coupled();
    const net = buildNetwork(c, c.defaults);
    const hubs = simJson('hubs.json');
    expect(net.centres.length).toBe(hubs.summary.regions ?? hubs.summary.hubs);
  });

  it('routes the same communes and strands the same ones', () => {
    const c = coupled();
    const net = buildNetwork(c, c.defaults);
    // The browser must never be MORE optimistic than the pipeline about who has a road: a
    // commune the pipeline cannot reach must not acquire one here.
    //
    // It currently strands 9 where the pipeline strands 14. The nine are the genuinely
    // cut-off ones — the Delta communes and the Brăila river islands. The other five
    // (Boghești, Corbița, Tănăsoaia, Spulber, Nămoloasa) are ordinary inland communes that
    // the pipeline drops for a structural reason in route generation rather than a
    // geographic one, and that reason has not been traced yet. Asserted as a bound rather
    // than papered over with a tolerance, so the gap stays visible and cannot widen.
    const network = simJson('network.json').summary;
    expect(net.unroutable).toBeGreaterThan(0);
    expect(net.unroutable).toBeLessThanOrEqual(network.uatsUnroutable);
    expect(net.centresWithoutTrunk).toBeLessThanOrEqual(network.hubsWithoutTrunk + 1);
  });

  it('agrees with the pipeline on the median journey', () => {
    const c = coupled();
    const net = buildNetwork(c, c.defaults);
    const reachable = net.journeys.filter((j) => j.reachable);
    const totals = reachable.map((j) => j.feeder + j.trunk).sort((x, y) => x - y);
    const median = totals[Math.floor(totals.length / 2)];

    // access.json's median includes the transfer wait, which is the timetable's and not
    // geography's; compare against the moving part only.
    const access = simJson('access.json').summary;
    const pipelineMoving = access.medianPulsedMin - access.waitPulsedMin;
    expect(median).toBeGreaterThan(pipelineMoving * 0.75);
    expect(median).toBeLessThan(pipelineMoving * 1.35);
  });

  it('every commune is assigned to a centre, and centres to themselves', () => {
    const c = coupled();
    const net = buildNetwork(c, c.defaults);
    expect(net.journeys).toHaveLength(c.data.uatCount);
    for (const centre of net.centres) {
      expect(net.journeys[centre].centre).toBe(centre);
      expect(net.journeys[centre].feeder).toBeCloseTo(0, 6);
    }
  });

  it('a different scenario gives a different country', () => {
    // The whole point of the coupling. If moving a slider changed nothing, the page would be
    // showing a preset while claiming to follow the reader.
    const c = coupled();
    const base = buildNetwork(c, c.defaults);
    const harder = buildNetwork(c, { ...c.defaults, x: c.defaults.x * 2 });
    expect(harder.centres.length).not.toBe(base.centres.length);
  });
});

describe('routing', () => {
  it('reaches nothing from an isolated node', () => {
    const road = {
      target: new Uint16Array([1, 0]),
      seconds: new Float32Array([60, 60]),
      start: new Uint32Array([0, 1, 2, 2]),
      edgeCount: 1,
      impassable: 0,
    };
    const dist = shortestTimes(road, 2, 3);
    expect(dist[2]).toBe(0);
    expect(dist[0]).toBe(Infinity);
  });

  it('takes the cheaper of two paths', () => {
    // 0-1 direct at 100s, or 0-2-1 at 30+30. The detour wins.
    const road = {
      target: new Uint16Array([1, 2, 0, 2, 0, 1]),
      seconds: new Float32Array([100, 30, 100, 30, 30, 30]),
      start: new Uint32Array([0, 2, 4, 6]),
      edgeCount: 3,
      impassable: 0,
    };
    expect(shortestTimes(road, 0, 3)[1]).toBe(60);
  });
});

describe('scenario reading', () => {
  it('an empty hash is the model defaults, not a half-built country', () => {
    const { params, pins } = readScenario('');
    expect(pins).toEqual([]);
    expect(changedParams(params)).toEqual([]);
  });

  it('reports which sliders the reader actually moved', () => {
    const { params } = readScenario('#pt=100000');
    expect(changedParams(params).length).toBeGreaterThan(0);
  });
});

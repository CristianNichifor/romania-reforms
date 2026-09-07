/**
 * Turning a route into lines.
 *
 * The one thing that must never happen here is a straight line passing for a road. A
 * schematic leg carries a real distance label but is not that distance long, so it is drawn
 * dashed and marked — and these tests hold that mark in place, because it is invisible in
 * code review and obvious only to a reader who trusts the map.
 */

import { describe, expect, it } from 'vitest';

import { buildChain, edgeKey, hopsOf, indexShard, routeTo } from '../src/app/chain';

/** parentOf as a small array: 3 <- 2 <- 1, and 5 unplaced. */
const parents = (): Int16Array => Int16Array.from([-1, 0, 1, 2, -1, -1]);

describe('walking back to the centre', () => {
  it('follows the chain to its root', () => {
    expect(routeTo(parents(), 3)).toEqual([3, 2, 1, 0]);
  });

  it('has no route for a commune accretion never placed', () => {
    // A leftover, an orphan cluster, a consolidation or a pin. No route was measured, so
    // none is offered — the panel names the rule instead.
    expect(routeTo(parents(), 5)).toBeNull();
    expect(routeTo(parents(), 0)).toBeNull();
  });

  it('refuses a cycle rather than looping forever', () => {
    // A cycle would be a bug in the model. It must not become a hung render.
    const cyclic = Int16Array.from([1, 0, -1]);
    expect(routeTo(cyclic, 0)).toBeNull();
  });

  it('splits a route into the legs actually travelled', () => {
    expect(hopsOf([3, 2, 1, 0])).toEqual([
      [3, 2],
      [2, 1],
      [1, 0],
    ]);
    expect(hopsOf([7])).toEqual([]);
  });
});

describe('finding a leg in the county shard', () => {
  it('keys a border the same whichever end is named first', () => {
    // The shards store each border once, in the pipeline's order; a route walks it in the
    // direction it grew, which is often the other. Keying unordered is what makes it hit.
    expect(edgeKey('161179', '160644')).toBe(edgeKey('160644', '161179'));
  });
});

describe('reading a county shard', () => {
  const shard = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { a: '161179', b: '160644' },
        geometry: { type: 'LineString', coordinates: [[28.1, 45.1], [28.2, 45.2]] },
      },
    ],
  };

  it('indexes a leg so either direction finds it', () => {
    const index = indexShard(shard);
    expect(index.get(edgeKey('160644', '161179'))).toHaveLength(2);
    expect(index.get(edgeKey('161179', '160644'))).toHaveLength(2);
  });

  it('survives a shard that is missing, empty or malformed', () => {
    // The shards are fetched from a release and can legitimately be absent from a build. A
    // broken one must cost the route, not the map.
    expect(indexShard(null).size).toBe(0);
    expect(indexShard({}).size).toBe(0);
    expect(indexShard({ features: 'nonsense' }).size).toBe(0);
    expect(indexShard({ features: [{ properties: {}, geometry: {} }] }).size).toBe(0);
    expect(
      indexShard({ features: [{ properties: { a: 'x', b: 'y' }, geometry: { coordinates: [[1, 2]] } }] }).size,
    ).toBe(0);
  });
});

describe('building the drawable route', () => {
  const seats = new Map<number, [number, number]>([
    [0, [28.0, 45.0]],
    [1, [28.1, 45.1]],
    [2, [28.2, 45.2]],
    [3, [28.3, 45.3]],
  ]);
  const seatOf = (u: number): [number, number] | undefined => seats.get(u);
  const metres = (): number => 9_400;

  it('draws routed geometry where the shard has it', () => {
    const geometry = (): [number, number][] => [
      [28.3, 45.3],
      [28.25, 45.22],
      [28.2, 45.2],
    ];
    const { features, legs, totalMetres } = buildChain([3, 2], metres, geometry, seatOf);
    expect(features).toHaveLength(1);
    expect(features[0]!.properties.kind).toBe('road');
    expect(features[0]!.geometry.coordinates).toHaveLength(3);
    expect(legs[0]!.real).toBe(true);
    expect(totalMetres).toBe(9_400);
  });

  it('falls back to a straight line, and marks it as one', () => {
    // The distance label is still true; the line is not the road. Marking it is the whole
    // point — an unmarked straight line reads as evidence.
    const { features, legs } = buildChain([3, 2], metres, () => null, seatOf);
    expect(features[0]!.properties.kind).toBe('schematic');
    expect(features[0]!.geometry.coordinates).toEqual([
      [28.3, 45.3],
      [28.2, 45.2],
    ]);
    expect(legs[0]!.real).toBe(false);
  });

  it('mixes real and schematic legs in one route', () => {
    // A shard can legitimately be missing a single edge — the pipeline refuses to write one
    // whose reconstruction disagreed with the published distance.
    const geometry = (a: number): [number, number][] | null =>
      a === 3 ? [[28.3, 45.3], [28.2, 45.2]] : null;
    const { features, legs } = buildChain([3, 2, 1], metres, geometry, seatOf);
    expect(features.map((f) => f.properties.kind)).toEqual(['road', 'schematic']);
    expect(legs.map((l) => l.real)).toEqual([true, false]);
  });

  it('sums the real distances whichever way each leg is drawn', () => {
    const { totalMetres } = buildChain([3, 2, 1], metres, () => null, seatOf);
    expect(totalMetres).toBe(18_800);
  });

  it('drops a leg it cannot draw at all rather than inventing one', () => {
    const { features, legs } = buildChain([3, 99], metres, () => null, seatOf);
    expect(features).toEqual([]);
    expect(legs).toEqual([]);
  });
});

/**
 * The train against the bus.
 *
 * The trap this module exists to avoid: a rail verdict computed once, against the default
 * consolidation, and shown beside a map the reader has changed. It was true about a country
 * they were not looking at. So the tests here are mostly about the verdict *moving*.
 */
import { describe, expect, it } from 'vitest';

import {
  STATION_WALK_KM,
  compareWithBus,
  loadRailAccess,
  railJourneyMin,
  trainHeadwayMin,
  walkMin,
} from './feroviar';

function access(station: number[], seat: number[], km: number[]) {
  return {
    stationKm: Float32Array.from(station),
    seatStationKm: Float32Array.from(seat),
    railKm: Float32Array.from(km),
  };
}

describe('the walk to the station', () => {
  it('is longer than the straight line', () => {
    // Streets are not crow-flies, and timing the walk on the straight line flatters rail.
    expect(walkMin(1)).toBeGreaterThan((1 / 4.5) * 60);
  });

  it('is zero for a station on the doorstep', () => {
    expect(walkMin(0)).toBe(0);
  });
});

describe('when a train is offered at all', () => {
  const near = access([1], [0.5], [60]);

  it('walk, train, walk', () => {
    const minutes = railJourneyMin(near, 0, 60, 10)!;
    expect(minutes).toBeCloseTo(walkMin(1) + 10 + 60 + walkMin(0.5));
  });

  it('refuses a station beyond walking distance', () => {
    const far = access([STATION_WALK_KM + 0.1], [0.5], [60]);
    expect(railJourneyMin(far, 0, 60, 10)).toBeNull();
  });

  it('refuses a county seat whose own station is too far', () => {
    // This removes a whole county at once, which is the right answer for the five seats whose
    // station sits outside the town.
    const farSeat = access([1], [STATION_WALK_KM + 0.1], [60]);
    expect(railJourneyMin(farSeat, 0, 60, 10)).toBeNull();
  });

  it('refuses a NaN rather than returning one', () => {
    // A missing value arrives from the binary as NaN, and every comparison against NaN is
    // false — so without an explicit finite check an unreachable commune passes the distance
    // test, produces a NaN journey, and that NaN wins a comparison against a real number.
    for (const bad of [access([NaN], [0.5], [60]), access([1], [NaN], [60]), access([1], [0.5], [NaN])]) {
      expect(railJourneyMin(bad, 0, 60, 10)).toBeNull();
    }
  });
});

describe('headway', () => {
  it('falls as service rises', () => {
    expect(trainHeadwayMin(20, 16)).toBeCloseTo(48);
    expect(trainHeadwayMin(40, 16)).toBeLessThan(trainHeadwayMin(20, 16));
  });

  it('refuses a service that does not run', () => {
    expect(() => trainHeadwayMin(0, 16)).toThrow();
    expect(() => trainHeadwayMin(20, 0)).toThrow();
  });
});

describe('the verdict against the bus', () => {
  const three = access([0.5, 0.5, 5], [0.5, 0.5, 0.5], [30, 30, 30]);
  const population = Uint32Array.from([1000, 2000, 3000]);

  it('counts only communes where the train actually wins', () => {
    // Rail is ~32 min here. First commune's bus is slower, second is faster.
    const v = compareWithBus(three, [90, 10, 90], population, 60, 5);
    expect(v.withOption).toBe(2);
    expect(v.faster).toBe(1);
    expect(v.people).toBe(1000);
  });

  it('moves when the bus network moves — the whole point', () => {
    const slowBus = compareWithBus(three, [200, 200, 200], population, 60, 5);
    const fastBus = compareWithBus(three, [5, 5, 5], population, 60, 5);
    expect(slowBus.faster).toBe(2);
    expect(fastBus.faster).toBe(0);
  });

  it('moves when the timetable moves', () => {
    // A train at a 48-minute headway loses to a pulsed bus far more often than to an
    // uncoordinated one, so the wait is part of the verdict rather than a constant.
    const pulsed = compareWithBus(three, [60, 60, 60], population, 60, 5);
    const uncoordinated = compareWithBus(three, [60, 60, 60], population, 60, 24);
    expect(pulsed.faster).toBeGreaterThan(uncoordinated.faster);
  });

  it('never claims a train for a commune that has none', () => {
    const v = compareWithBus(three, [90, 90, 90], population, 60, 5);
    expect(v.minutes[2]).toBe(-1);
  });

  it('leaves an unroutable commune alone', () => {
    // A commune with no bus journey at all must not be counted as "faster by rail" — it has
    // nothing to be faster than.
    const v = compareWithBus(three, [null, null, null], population, 60, 5);
    expect(v.withOption).toBe(2);
    expect(v.faster).toBe(0);
  });
});

describe('loading the payload', () => {
  it('refuses a buffer of the wrong shape', () => {
    // Three float32 arrays per UAT. A file half that size would decode into nonsense rather
    // than fail, and every commune would get another commune's station.
    expect(() => loadRailAccess(new ArrayBuffer(8), 3)).toThrow(/expected/);
  });

  it('splits the three arrays in order', () => {
    const buffer = new ArrayBuffer(3 * 4 * 2);
    new Float32Array(buffer).set([1, 2, 3, 4, 5, 6]);
    const a = loadRailAccess(buffer, 2);
    expect(Array.from(a.stationKm)).toEqual([1, 2]);
    expect(Array.from(a.seatStationKm)).toEqual([3, 4]);
    expect(Array.from(a.railKm)).toEqual([5, 6]);
  });
});

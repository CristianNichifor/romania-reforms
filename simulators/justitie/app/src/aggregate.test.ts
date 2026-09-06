/**
 * The claim under test is the one the whole filter rests on: that a county's statistic taken
 * from summed histograms is the county's statistic, and not an average of its courts'.
 *
 * A wrong answer here is invisible in the output. Every number would still be a plausible number
 * of days, in the right range, moving in the right direction when the selection changes. So the
 * tests compare against a brute-force computation over the underlying sample rather than against
 * a recorded value.
 */

import { describe, expect, it } from 'vitest';
import { pool, quantileFromBins, strip, survival, type Court, type Edges } from './aggregate';

const EDGES: Edges = {
  termene: [0, 7, 14, 28, 56],
  durata: [0, 30, 60, 90, 120],
  peRol: [0, 90, 180, 365, 547],
};

function histogram(values: number[], edges: number[]): number[] {
  const counts = edges.map(() => 0);
  for (const value of values) {
    let index = -1;
    for (let i = 0; i < edges.length; i += 1) if (value >= (edges[i] as number)) index = i;
    if (index >= 0) counts[index] = (counts[index] as number) + 1;
  }
  return counts;
}

function court(overrides: Partial<Court>): Court {
  return {
    institutie: 'X',
    nume: 'X',
    level: 'judecătorie',
    judet: 'TM',
    siruta: '1',
    acoperire: { volumCsm: 1000, raportFataDeVolum: 1.5, trunchiat: false },
    dosare: 0,
    dosarePenale: 0,
    sectii: 1,
    completuri: 0,
    peCategorie: {},
    amanari: {
      termeneCuSolutie: 0,
      amanareCauza: 0,
      amanarePronuntare: 0,
      termenPreschimbat: 0,
    },
    peRol: EDGES.peRol.map(() => 0),
    primulTermen: EDGES.termene.map(() => 0),
    intervalTermene: EDGES.termene.map(() => 0),
    durata: {
      dosare: 0,
      urmarireZile: 120,
      evenimente: EDGES.durata.map(() => 0),
      cenzurate: EDGES.durata.map(() => 0),
    },
    ...overrides,
  };
}

describe('pooling', () => {
  it('is the pooled median, not the mean of the two medians', () => {
    // The error this catches would be defensible-looking and wrong. One fast court, one slow
    // one, deliberately different sizes so that a mean of medians and a weighted mean of
    // medians both give the wrong answer and give different wrong answers.
    const fast = [1, 2, 3, 4, 5, 6, 8, 10];
    const slow = [40, 45, 50, 55, 60, 70];
    const pooledSample = [...fast, ...slow].sort((a, b) => a - b);

    const selection = [
      court({ intervalTermene: histogram(fast, EDGES.termene) }),
      court({ intervalTermene: histogram(slow, EDGES.termene) }),
    ];
    const summed = pool(selection, EDGES);
    const found = strip(summed.intervalTermene, EDGES.termene);

    const trueMedian = pooledSample[Math.floor(pooledSample.length / 2)] as number;
    const meanOfMedians = (5 + 52.5) / 2;

    // Inside the bin the true median falls in, and nowhere near the average of the two medians.
    expect(found.p50).toBeLessThanOrEqual(trueMedian + 14);
    expect(Math.abs((found.p50 as number) - meanOfMedians)).toBeGreaterThan(5);
  });

  it('leaves out the courts the crawl did not finish, and says how many', () => {
    // The failure mode is a county total quietly summed over a court measured at 0,5% of its
    // size. It has to be excluded, and the exclusion has to be visible.
    const selection = [
      court({ dosare: 100_000 }),
      court({
        dosare: 69,
        acoperire: { volumCsm: 20_944, raportFataDeVolum: 0.003, trunchiat: true },
      }),
    ];
    const summed = pool(selection, EDGES);
    expect(summed.dosare).toBe(100_000);
    expect(summed.instante).toBe(1);
    expect(summed.trunchiate).toBe(1);
  });

  it('adds panels, which only became addable when each hearing got one court', () => {
    const selection = [court({ completuri: 40 }), court({ completuri: 25 })];
    expect(pool(selection, EDGES).completuri).toBe(65);
  });
});

describe('quantileFromBins', () => {
  it('interpolates inside the bin instead of snapping to its edge', () => {
    // Ten observations spread evenly through the 0-7 bin: the median should land mid-bin, not
    // at 0. Snapping would make two counties a week apart read identically.
    const counts = [10, 0, 0, 0, 0];
    const found = quantileFromBins(counts, EDGES.termene, 0.5);
    expect(found.zile).toBeGreaterThan(0);
    expect(found.zile).toBeLessThan(7);
    expect(found.esteUnPrag).toBe(false);
  });

  it('reports the open last bin as a threshold rather than inventing a value', () => {
    // "More than 56 days" written as "80 days" is a made-up number that looks measured.
    const counts = [0, 0, 0, 0, 10];
    const found = quantileFromBins(counts, EDGES.termene, 0.5);
    expect(found.zile).toBe(56);
    expect(found.esteUnPrag).toBe(true);
  });

  it('gives nothing rather than zero for an empty selection', () => {
    expect(quantileFromBins([0, 0, 0, 0, 0], EDGES.termene, 0.5).zile).toBeNull();
  });
});

describe('survival', () => {
  it('does not count a running case as a resolved one', () => {
    const resolvedOnly = survival(
      { dosare: 100, urmarireZile: 120, evenimente: [50, 0, 0, 0, 0], cenzurate: [0, 0, 0, 0, 0] },
      EDGES.durata,
      [30],
    );
    const halfRunning = survival(
      { dosare: 100, urmarireZile: 120, evenimente: [50, 0, 0, 0, 0], cenzurate: [50, 0, 0, 0, 0] },
      EDGES.durata,
      [30],
    );
    // Same 50 resolutions; the second court has half its cohort still running, so a smaller
    // share of it is *known* to have finished — but the estimate must be higher, not lower,
    // because those 50 were only at risk for part of the bin.
    expect(halfRunning.rezolvatePana['zi30']).toBeGreaterThan(
      resolvedOnly.rezolvatePana['zi30'] as number,
    );
  });

  it('refuses to report a share past the follow-up', () => {
    const short = survival(
      { dosare: 100, urmarireZile: 45, evenimente: [20, 0, 0, 0, 0], cenzurate: [80, 0, 0, 0, 0] },
      EDGES.durata,
      [30, 90],
    );
    expect(short.rezolvatePana['zi30']).not.toBeNull();
    // 90 days from a cohort watched 45: an extrapolation wearing the clothes of a measurement.
    expect(short.rezolvatePana['zi90']).toBeNull();
  });

  it('has no median while more than half the cohort is still running', () => {
    const mostlyRunning = survival(
      { dosare: 100, urmarireZile: 120, evenimente: [10, 0, 0, 0, 0], cenzurate: [0, 0, 0, 0, 90] },
      EDGES.durata,
    );
    expect(mostlyRunning.medianaZile).toBeNull();
  });
});

/**
 * The ported service standard, fleet and cost, against the Python reference.
 *
 * These constants live twice — once in `scripts/tiers.py` and once in `serviciu.ts` — because
 * the browser cannot import Python. Duplicated constants drift, so this compares the port's
 * whole output to the pipeline's published figures at the default scenario. If the two ever
 * separate, a bus count on screen stops meaning what the repository says it means.
 */
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { assemble, buildNetwork } from './consolidare';
import {
  DAY_PROFILE,
  SERVICES,
  annualCost,
  classify,
  costNetwork,
  cycleSlack,
  farebox,
  fleetRequired,
  loadPrices,
  resourcesForRoute,
  vehiclesForPeriod,
} from './serviciu';

const app = join(dirname(fileURLToPath(import.meta.url)), '..');
const data = join(app, 'public', 'data');
const sim = join(app, '..');
const ready = existsSync(join(data, 'road-time.bin'));

const bin = (name: string): ArrayBuffer => {
  const b = readFileSync(join(data, name));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};
const json = (name: string) => JSON.parse(readFileSync(join(data, name), 'utf8'));
const simJson = (name: string) => JSON.parse(readFileSync(join(sim, 'data', name), 'utf8'));

describe('the service standard', () => {
  it('gives a small commune four departures, all on the peaks', () => {
    const basic = SERVICES.basic.departures;
    expect(basic.am_peak + basic.pm_peak).toBe(4);
    expect(basic.midday + basic.evening).toBe(0);
  });

  it('makes a hub trunk whatever its population', () => {
    expect(classify(500, true)).toBe('trunk');
    expect(classify(500, false)).toBe('basic');
    expect(classify(4000, false)).toBe('feeder');
    expect(classify(40000, false)).toBe('trunk');
  });

  it('runs a service day of sixteen hours', () => {
    expect(Object.values(DAY_PROFILE).reduce((a, b) => a + b, 0)).toBe(16);
  });
});

describe('fleet arithmetic', () => {
  it('takes the peak of the periods, never their sum', () => {
    // Two buses in the morning and two in the afternoon are the same two buses.
    const r = resourcesForRoute(50, { am_peak: 3, midday: 0, pm_peak: 3, evening: 0 }, 40);
    expect(r.peakVehicles).toBe(vehiclesForPeriod(50, 10, 60));
  });

  it('does not buy a vehicle for padding the cycle', () => {
    // The claim an earlier draft made and this disproves: rounding a cycle up to a whole pulse
    // leaves a bus standing, it does not require another one.
    expect(vehiclesForPeriod(65, 0, 60)).toBe(vehiclesForPeriod(120, 0, 60));
    expect(cycleSlack(65, 0, 60)).toBeCloseTo(55);
  });

  it('applies the spare ratio once, not per route', () => {
    // Per route: ceil(1 × 1.15) = 2 for each of a hundred single-bus services, doubling them.
    expect(fleetRequired(100, 0.15)).toBe(115);
    expect(Array.from({ length: 100 }, () => fleetRequired(1, 0.15)).reduce((a, b) => a + b)).toBe(
      200,
    );
  });

  it('a route with no departures costs nothing', () => {
    const r = resourcesForRoute(50, { am_peak: 0, midday: 0, pm_peak: 0, evening: 0 }, 40);
    expect(r).toEqual({ peakVehicles: 0, busHours: 0, busKm: 0, cycleSlackMin: 0 });
  });
});

describe('cost arithmetic', () => {
  const prices = {
    perBusHour: 50,
    perBusKmByClass: { basic: 2, trunk: 4 },
    perVehicleYear: 10_000,
    adminShare: 0.1,
    vehiclePrice: { basic: 100_000, trunk: 300_000 },
    vehicleLifeYears: 10,
    spareRatio: 0.15,
    serviceSpeedFactor: 0.75,
    dwellMinPerStop: 0.75,
    weekdaysPerYear: 10,
  };

  it('keeps capital out of operating', () => {
    const c = annualCost(10, { basic: 10 }, { basic: 1 }, prices);
    expect(c.operatingRon + c.capitalRon).toBeCloseTo(c.totalRon);
    expect(c.capitalRon).toBeGreaterThan(0);
    expect(c.operatingRon).not.toBe(c.totalRon);
  });

  it('charges a parked bus its standing cost', () => {
    const c = annualCost(0, {}, { basic: 3 }, prices);
    expect(c.standingRon).toBeCloseTo(3 * 10_000);
    expect(c.runningRon).toBe(0);
  });

  it('charges admin on direct cost only, and not on itself', () => {
    const c = annualCost(10, { basic: 10 }, { basic: 1 }, prices);
    expect(c.adminRon).toBeCloseTo((c.driverRon + c.runningRon + c.standingRon) * 0.1);
  });

  it('reads the real price file without paraphrasing it', () => {
    const real = loadPrices(simJson('cost-inputs.json'));
    expect(real.perBusHour).toBeGreaterThan(0);
    expect(real.perBusKmByClass.trunk).toBeGreaterThan(real.perBusKmByClass.basic);
  });
});

describe.skipIf(!ready)('against the Python pipeline at default parameters', () => {
  const built = () => {
    const c = assemble({
      manifest: json('admin-manifest.json'),
      attributes: json('admin-attributes.json'),
      attributesBin: bin('admin-attributes.bin'),
      adjacencyBin: bin('admin-adjacency.bin'),
      candidacyBin: bin('admin-candidacy.bin'),
      roadMeta: json('road-time.json'),
      roadBin: bin('road-time.bin'),
    });
    const net = buildNetwork(c, c.defaults);
    return costNetwork(c, net, loadPrices(simJson('cost-inputs.json')));
  };

  it('generates about the same number of routes', () => {
    const network = simJson('network.json').summary;
    const mine = built().routes;
    // Feeders should match closely; the trunk tier is one run per centre here against the
    // pipeline's chained routes, so the totals differ by roughly that tier.
    expect(mine).toBeGreaterThan(network.feeder.routes * 0.9);
    expect(mine).toBeLessThan(network.routes * 1.15);
  });

  it('lands within a tenth of the pipeline on fleet', () => {
    const pipeline = simJson('cost.json').fleet.total;
    expect(built().fleetTotal).toBeGreaterThan(pipeline * 0.9);
    expect(built().fleetTotal).toBeLessThan(pipeline * 1.1);
  });

  it('lands within a tenth of the pipeline on annual cost', () => {
    // Tightened from a fifth once trunk kilometres were carried through. Before that the trunk
    // tier ran for free and the whole network priced 17% low — a gap wide enough to look like
    // a finding about consolidation rather than a missing multiplication.
    const pipeline = simJson('cost.json').annualRon.total;
    const mine = built().cost.totalRon;
    expect(mine).toBeGreaterThan(pipeline * 0.9);
    expect(mine).toBeLessThan(pipeline * 1.1);
  });

  it('pays for the trunk tier in kilometres, not only in hours', () => {
    // The specific regression: a trunk leg counted in minutes and zero kilometres.
    expect(built().busKmPerWeekday).toBeGreaterThan(simJson('cost.json').perWeekday.busKm * 0.9);
  });
});

describe('the farebox', () => {
  const fleet = { basic: 100, feeder: 100, trunk: 100 };

  it('reports recovery as an output, not an assumption', () => {
    // Revenue is built from a fare and a quantity. Assuming the ratio would make the subsidy a
    // restatement of the cost, and the benchmark could never disagree with it.
    const f = farebox(1000, fleet, 1_000_000, 100, 0.35, 0.22, 250);
    expect(f.recovery).toBeCloseTo(f.revenueRon / 1_000_000);
  });

  it('scales revenue with the load factor and nothing else does the work', () => {
    const low = farebox(1000, fleet, 1, 100, 0.35, 0.1, 250);
    const high = farebox(1000, fleet, 1, 100, 0.35, 0.2, 250);
    expect(high.revenueRon).toBeCloseTo(2 * low.revenueRon);
  });

  it('does not report a surplus as a negative subsidy', () => {
    const f = farebox(1_000_000, fleet, 1, 100, 0.35, 0.22, 250);
    expect(f.revenueRon).toBeGreaterThan(1);
    expect(f.subsidyRon).toBe(0);
  });

  it('uses the fleet it was given to find the average seat count', () => {
    // A network of minibuses earns less per kilometre than one of coaches at the same load.
    const small = farebox(1000, { basic: 300 }, 1, 100, 0.35, 0.22, 250);
    const large = farebox(1000, { trunk: 300 }, 1, 100, 0.35, 0.22, 250);
    expect(large.revenueRon).toBeGreaterThan(small.revenueRon);
  });

  it('survives an empty fleet without dividing by zero', () => {
    const f = farebox(0, {}, 0, 0, 0.35, 0.22, 250);
    expect(f.passengerKm).toBe(0);
    expect(Number.isFinite(f.subsidyPerPersonYearRon)).toBe(true);
  });
});

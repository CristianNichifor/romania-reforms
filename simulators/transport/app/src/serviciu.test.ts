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
  SERVICE_LEVELS,
  driversRequired,
  levelById,
  annualCost,
  chooseTraction,
  classify,
  costNetwork,
  cycleSlack,
  demandFrom,
  farebox,
  fleetRequired,
  lifetimeCost,
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
    electricRangeKm: 180,
    stopsPerKmForHybrid: 0.35,
    priceRatio: { electric: 1.8, hybrid: 1.3, diesel: 1 },
    perKmByTraction: {
      electric: { basic: 1.5, trunk: 2 },
      hybrid: { basic: 1.8, trunk: 3 },
      diesel: { basic: 2, trunk: 4 },
    },
    passengerKmPerPersonYear: 300,
    depotCapexPerBus: 745_500,
    depotElectricPremiumPerBus: 497_000,
    depotLifeYears: 40,
    driverPaidHoursMonth: 165,
    platformToPaidRatio: 1.3,
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
  it('reports recovery as an output, not an assumption', () => {
    // Revenue is built from a fare and a quantity. Assuming the ratio would make the subsidy a
    // restatement of the cost, and the benchmark could never disagree with it.
    const f = farebox(2_000_000, 1_000_000, 100, 0.35);
    expect(f.recovery).toBeCloseTo(f.revenueRon / 1_000_000);
  });

  it('does not report a surplus as a negative subsidy', () => {
    const f = farebox(100_000_000, 1, 100, 0.35);
    expect(f.revenueRon).toBeGreaterThan(1);
    expect(f.subsidyRon).toBe(0);
  });

  it('survives an empty network without dividing by zero', () => {
    const f = farebox(0, 0, 0, 0.35);
    expect(f.passengerKm).toBe(0);
    expect(Number.isFinite(f.subsidyPerPersonYearRon)).toBe(true);
  });
});

describe('demand from population', () => {
  it('makes the load factor a result rather than an input', () => {
    const d = demandFrom(1_000_000, 1_000_000_000, 300);
    expect(d.passengerKm).toBe(300_000_000);
    expect(d.loadFactor).toBeCloseTo(0.3);
  });

  it('says so when the timetable cannot carry the people', () => {
    // The point of comparing the two: a model that assumed occupancy could never report this.
    expect(demandFrom(1_000_000, 100_000_000, 300).overCapacity).toBe(true);
    expect(demandFrom(1_000_000, 1_000_000_000, 300).overCapacity).toBe(false);
  });

  it('falls as service rises, for the same population', () => {
    const thin = demandFrom(1_000_000, 500_000_000, 300).loadFactor;
    const dense = demandFrom(1_000_000, 1_500_000_000, 300).loadFactor;
    expect(dense).toBeLessThan(thin);
  });
});

describe('service levels', () => {
  it('offers a floor, a proposal and an extension', () => {
    expect(SERVICE_LEVELS.map((l) => l.id)).toEqual(['minim', 'implicit', 'extins']);
  });

  it('orders them by what they actually run', () => {
    const total = (id: string) =>
      Object.values(levelById(id).departures).reduce(
        (sum, tier) => sum + Object.values(tier).reduce((a, b) => a + b, 0),
        0,
      );
    expect(total('minim')).toBeLessThan(total('implicit'));
    expect(total('implicit')).toBeLessThan(total('extins'));
  });

  it('never leaves the smallest commune with nothing', () => {
    // The floor is a floor, not an abolition: every level runs on both peaks.
    for (const l of SERVICE_LEVELS) {
      expect(l.departures.basic.am_peak).toBeGreaterThan(0);
      expect(l.departures.basic.pm_peak).toBeGreaterThan(0);
    }
  });

  it('falls back to the proposed standard on an unknown id', () => {
    expect(levelById('nonesuch').id).toBe('implicit');
  });
});

describe('drivers', () => {
  it('needs more drivers than buses, because a driver is paid for more than driving', () => {
    // One bus on the road for a full service day cannot be one driver.
    const hours = 6_917_575;
    expect(driversRequired(hours, 165, 1.3)).toBeGreaterThan(4000);
  });

  it('scales with the platform-to-paid ratio', () => {
    expect(driversRequired(100_000, 165, 1.3)).toBeGreaterThan(
      driversRequired(100_000, 165, 1.0),
    );
  });

  it('returns none for a service that does not run', () => {
    expect(driversRequired(0, 165, 1.3)).toBe(0);
    expect(driversRequired(100, 0, 1.3)).toBe(0);
  });
});

describe('capacity and whole-life cost', () => {
  const cost = {
    driverRon: 100,
    runningRon: 100,
    standingRon: 100,
    adminRon: 100,
    capitalRon: 50,
    operatingRon: 400,
    totalRon: 450,
  };

  it('charges the fleet once and the running cost every year', () => {
    // capitalRon is the annualised slice; a policy question wants the bill, so the vehicles
    // are bought at full price and the service is run for its life.
    const lc = lifetimeCost(cost, 12, 12);
    expect(lc.fleetCapexRon).toBe(50 * 12);
    expect(lc.opexRon).toBe(400 * 12);
    expect(lc.totalRon).toBe(lc.capexRon + lc.opexRon);
  });

  it('charges the depot separately, and it is not small', () => {
    // Buildings the network cannot run without, and the least defensible input in the model.
    // Kept as its own line so it can be argued with on its own.
    const withDepot = lifetimeCost(cost, 12, 12, 100, 745_500);
    expect(withDepot.depotCapexRon).toBe(100 * 745_500);
    expect(withDepot.totalRon).toBeGreaterThan(lifetimeCost(cost, 12, 12).totalRon);
  });

  it('charges no depot when none is asked for', () => {
    expect(lifetimeCost(cost, 12, 12).depotCapexRon).toBe(0);
  });

  it('does not discount, and says which years it covers', () => {
    // Undiscounted on purpose: a discount rate decides what a journey in 2038 is worth against
    // one now, which is a political choice and must not be buried in arithmetic.
    expect(lifetimeCost(cost, 12, 1).opexRon).toBe(400);
    expect(lifetimeCost(cost, 12, 24).years).toBe(24);
  });
});

describe.skipIf(!ready)('capacity on the real network', () => {
  const level = (id: string) => {
    const c = assemble({
      manifest: json('admin-manifest.json'),
      attributes: json('admin-attributes.json'),
      attributesBin: bin('admin-attributes.bin'),
      adjacencyBin: bin('admin-adjacency.bin'),
      candidacyBin: bin('admin-candidacy.bin'),
      roadMeta: json('road-time.json'),
      roadBin: bin('road-time.bin'),
    });
    return costNetwork(c, buildNetwork(c, c.defaults), loadPrices(simJson('cost-inputs.json')), levelById(id));
  };

  it('offers more capacity at a higher service level', () => {
    expect(level('extins').seatKmPerYear).toBeGreaterThan(level('minim').seatKmPerYear);
  });

  it('costs less per seat-km the more the fleet is used', () => {
    // The result worth showing: running the same buses more spreads their purchase and their
    // depot over more kilometres, so capacity gets cheaper as service gets denser.
    expect(level('extins').ronPerSeatKm).toBeLessThan(level('minim').ronPerSeatKm);
  });

  it('reports capacity offered, in a plausible band for a national bus network', () => {
    const perSeatKm = level('implicit').ronPerSeatKm;
    expect(perSeatKm).toBeGreaterThan(0.05);
    expect(perSeatKm).toBeLessThan(1);
  });
});


describe('choosing traction from the route', () => {
  const prices = {
    electricRangeKm: 180,
    stopsPerKmForHybrid: 0.35,
  } as never as Parameters<typeof chooseTraction>[2];

  it('takes electric where a battery can do the day', () => {
    expect(chooseTraction(120, 0.1, prices)).toBe('electric');
    expect(chooseTraction(180, 0.9, prices)).toBe('electric');
  });

  it('will not put a battery on a route it cannot finish', () => {
    // The binding constraint, and it is binding whatever anyone would prefer: a vehicle that
    // runs 300 km between depot visits is not battery-electric without charging en route.
    expect(chooseTraction(300, 0.9, prices)).not.toBe('electric');
  });

  it('takes hybrid on a long route with dense stops, diesel without them', () => {
    // Regenerative braking earns its premium only where there is braking to recover.
    expect(chooseTraction(300, 0.9, prices)).toBe('hybrid');
    expect(chooseTraction(300, 0.05, prices)).toBe('diesel');
  });

  it('uses the winter range, not the average one', () => {
    // A public service runs in January too. 240 km derated for cold is the number that decides
    // whether a commune keeps its bus when it is minus fifteen.
    expect(chooseTraction(200, 0.9, prices)).not.toBe('electric');
  });
});

describe.skipIf(!ready)('the mix the routes ask for', () => {
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
    return costNetwork(c, buildNetwork(c, c.defaults), loadPrices(simJson('cost-inputs.json')));
  };

  it('is a mix, not a monoculture', () => {
    const mix = built().tractionMix;
    const total = mix.electric + mix.hybrid + mix.diesel;
    expect(total).toBeGreaterThan(0);
    expect(mix.electric).toBeGreaterThan(0);
  });

  it('accounts for every vehicle exactly once', () => {
    const r = built();
    const total = r.tractionMix.electric + r.tractionMix.hybrid + r.tractionMix.diesel;
    expect(Math.abs(total - r.fleetTotal)).toBeLessThanOrEqual(3);
  });
});

describe('depot capital follows the traction mix', () => {
  const cost = {
    driverRon: 0, runningRon: 0, standingRon: 0, adminRon: 0,
    capitalRon: 0, operatingRon: 0, totalRon: 0,
  };

  it('charges the charging premium only to electric spaces', () => {
    // A diesel space needs a hall and a pit; it does not need a substation. Spreading the
    // premium across the whole fleet would price chargers for buses that never plug in.
    const allDiesel = lifetimeCost(cost, 12, 12, 100, 745_500, 0, 497_000);
    const halfElectric = lifetimeCost(cost, 12, 12, 100, 745_500, 50, 497_000);
    expect(allDiesel.depotCapexRon).toBe(100 * 745_500);
    expect(halfElectric.depotCapexRon).toBe(100 * 745_500 + 50 * 497_000);
  });

  it('rises with the electric share and not with a policy target', () => {
    const few = lifetimeCost(cost, 12, 12, 100, 745_500, 10, 497_000).depotCapexRon;
    const many = lifetimeCost(cost, 12, 12, 100, 745_500, 90, 497_000).depotCapexRon;
    expect(many).toBeGreaterThan(few);
  });
});

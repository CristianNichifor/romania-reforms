/**
 * The service standard, the fleet it needs, and what that costs — for the reader's scenario.
 *
 * A port of `scripts/tiers.py`, `scripts/fleet.py` and `scripts/costs.py`. Porting a model to
 * the page that displays it is how a page and its pipeline start disagreeing, so every number
 * here is checked against the Python reference in `serviciu.test.ts` at the default scenario.
 * The constants are duplicated because the browser cannot import Python; the test exists
 * because duplicated constants drift.
 *
 * The boundaries are the Python file's, kept deliberately:
 *
 * - **tiers** decides what a place is owed — vehicle and departures. Dispute the standard here.
 * - **fleet** turns that into vehicles and hours. Dispute the arithmetic here.
 * - **cost** turns those into lei. Dispute the prices in `data/cost-inputs.json`.
 *
 * None of the three has to accept the others to be argued with, which is the whole point.
 */

/** Hours in each period of the service day. Weekend is a separate profile, not a period. */
export const DAY_PROFILE: Record<string, number> = {
  am_peak: 3.0,
  midday: 5.0,
  pm_peak: 4.0,
  evening: 4.0,
};

export interface Service {
  tier: string;
  seats: number;
  departures: Record<string, number>;
}

/**
 * Departures per period, one direction. All fixed, all published — nothing booked ahead.
 *
 * `basic` is four a day and every one of them sits on a peak. Four spread evenly through the
 * day would serve nobody; timed to school and work they serve most of the trips a small
 * commune actually makes.
 */
export const SERVICES: Record<string, Service> = {
  basic: {
    tier: 'basic',
    seats: 20,
    departures: { am_peak: 2, midday: 0, pm_peak: 2, evening: 0 },
  },
  feeder: {
    tier: 'feeder',
    seats: 40,
    departures: { am_peak: 3, midday: 2, pm_peak: 3, evening: 1 },
  },
  // Hourly across the service day: the pulse the feeders are timed to meet.
  trunk: {
    tier: 'trunk',
    seats: 50,
    departures: { am_peak: 3, midday: 5, pm_peak: 4, evening: 4 },
  },
};

const BASIC_MAX_POPULATION = 2_000;
const FEEDER_MAX_POPULATION = 5_000;

/**
 * Which class a UAT falls into.
 *
 * A hub is always trunk whatever its population: a centre that twelve UATs feed into carries
 * their transfers, not only its own residents.
 */
export function classify(population: number, isHub: boolean): string {
  if (isHub) return 'trunk';
  if (population <= BASIC_MAX_POPULATION) return 'basic';
  if (population <= FEEDER_MAX_POPULATION) return 'feeder';
  return 'trunk';
}

/** Minutes a vehicle stands at a terminus: relief, recovery, and the dwell that meets a feeder. */
export const LAYOVER_MIN = 10.0;

export interface Resources {
  peakVehicles: number;
  busHours: number;
  busKm: number;
  cycleSlackMin: number;
}

/** Vehicles to hold a headway, with the cycle rounded up to a whole pulse. */
export function vehiclesForPeriod(
  roundTripMin: number,
  layoverMin: number,
  headwayMin: number,
): number {
  if (headwayMin <= 0) return 0;
  return Math.max(1, Math.ceil((roundTripMin + layoverMin) / headwayMin));
}

/**
 * Minutes a vehicle stands idle because the cycle does not fill a whole pulse.
 *
 * Padding does *not* buy an extra vehicle — `ceil(cycle / headway)` is unchanged by it. What it
 * buys is waiting, and reporting that as idle minutes says how much of the fleet's paid time
 * the timetable's shape spends on nothing.
 */
export function cycleSlack(roundTripMin: number, layoverMin: number, headwayMin: number): number {
  if (headwayMin <= 0) return 0;
  const cycle = roundTripMin + layoverMin;
  return Math.ceil(cycle / headwayMin) * headwayMin - cycle;
}

/** Everything one route costs, from its duration and its published departures. */
export function resourcesForRoute(
  roundTripMin: number,
  departures: Record<string, number>,
  kmRoundTrip: number,
  layoverMin = LAYOVER_MIN,
): Resources {
  const total = Object.values(departures).reduce((a, b) => a + b, 0);
  if (total === 0) return { peakVehicles: 0, busHours: 0, busKm: 0, cycleSlackMin: 0 };

  let peak = 0;
  let slack = 0;
  for (const [period, count] of Object.entries(departures)) {
    if (count <= 0) continue;
    const hours = DAY_PROFILE[period] ?? 0;
    const headway = hours > 0 ? (hours * 60) / count : 0;
    // The maximum, never the sum: adding period counts would buy four buses where the same
    // two serve both the morning and the afternoon.
    peak = Math.max(peak, vehiclesForPeriod(roundTripMin, layoverMin, headway));
    // The worst period's slack, not the sum — it describes the cycle against the pulse, and
    // adding across periods would count the same standing bus twice.
    slack = Math.max(slack, cycleSlack(roundTripMin, layoverMin, headway));
  }

  return {
    peakVehicles: peak,
    busHours: (total * roundTripMin) / 60,
    busKm: total * kmRoundTrip,
    cycleSlackMin: slack,
  };
}

/**
 * Buses to own, so a vehicle in the workshop does not cancel a departure.
 *
 * **Applied once, to a network total.** Per route it buys a spare for every village shuttle:
 * `ceil(1 × 1.15)` is 2, a 100% margin from a 15% ratio. On the real country that mistake gave
 * 6.809 buses against 4.502 — over half again as much fleet as the ratio asks for.
 */
export function fleetRequired(peakVehicles: number, spareRatio: number): number {
  return Math.ceil(peakVehicles * (1 + spareRatio));
}

export interface Prices {
  perBusHour: number;
  perBusKmByClass: Record<string, number>;
  perVehicleYear: number;
  adminShare: number;
  vehiclePrice: Record<string, number>;
  vehicleLifeYears: number;
  spareRatio: number;
  serviceSpeedFactor: number;
  dwellMinPerStop: number;
  weekdaysPerYear: number;
}

export interface Cost {
  driverRon: number;
  runningRon: number;
  standingRon: number;
  adminRon: number;
  capitalRon: number;
  operatingRon: number;
  totalRon: number;
}

/**
 * A year of cost, kept in the pieces it was built from.
 *
 * Operating scales with what the buses do; capital with how many must exist. Fold them into one
 * per-hour figure and the trade between a peaky timetable and a large fleet disappears, which
 * is how a transit system gets costed wrong in a way nobody can see.
 */
export function annualCost(
  busHoursPerWeekday: number,
  busKmPerWeekdayByClass: Record<string, number>,
  fleetByClass: Record<string, number>,
  prices: Prices,
): Cost {
  const driver = busHoursPerWeekday * prices.weekdaysPerYear * prices.perBusHour;
  let running = 0;
  for (const [name, km] of Object.entries(busKmPerWeekdayByClass)) {
    running += km * prices.weekdaysPerYear * (prices.perBusKmByClass[name] ?? 0);
  }
  const fleet = Object.values(fleetByClass).reduce((a, b) => a + b, 0);
  const standing = fleet * prices.perVehicleYear;
  const admin = (driver + running + standing) * prices.adminShare;
  let capital = 0;
  for (const [name, count] of Object.entries(fleetByClass)) {
    capital += (count * (prices.vehiclePrice[name] ?? 0)) / prices.vehicleLifeYears;
  }
  const operating = driver + running + standing + admin;
  return {
    driverRon: driver,
    runningRon: running,
    standingRon: standing,
    adminRon: admin,
    capitalRon: capital,
    operatingRon: operating,
    totalRon: operating + capital,
  };
}

/** Resolve `data/cost-inputs.json` into the rates the model needs. */
export function loadPrices(document: {
  items: Record<string, { value: number }>;
  vehicles: Record<string, { seats: number; priceRon: number; dieselPer100Km: number }>;
}): Prices {
  const item = (name: string) => document.items[name].value;

  // A gross wage is not an employer cost, and a bus-hour is not a paid hour. Both steps are
  // easy to forget and together they are worth about a third of the largest line.
  const employerMonthly = item('driverGrossMonthly') * (1 + item('employerContributionRate'));
  const perPaidHour = employerMonthly / item('driverPaidHoursMonth');

  const labour = item('maintenanceLabourShare');
  const maintenance =
    item('maintenanceEurPerKm') *
    (labour * item('maintenanceWageRatio') + (1 - labour)) *
    item('ronPerEur');

  const perKm: Record<string, number> = {};
  const price: Record<string, number> = {};
  for (const [name, spec] of Object.entries(document.vehicles)) {
    perKm[name] =
      (spec.dieselPer100Km / 100) * item('dieselPricePerLitre') + maintenance + item('tyresPerKm');
    price[name] = spec.priceRon;
  }

  return {
    perBusHour: perPaidHour * item('platformToPaidRatio'),
    perBusKmByClass: perKm,
    perVehicleYear:
      item('insurancePerVehicleYear') + item('depotPerVehicleYear') + item('roadTaxPerVehicleYear'),
    adminShare: item('adminOverheadShare'),
    vehiclePrice: price,
    vehicleLifeYears: item('vehicleLifeYears'),
    spareRatio: 0.15,
    serviceSpeedFactor: item('serviceSpeedFactor'),
    dwellMinPerStop: item('dwellMinPerStop'),
    weekdaysPerYear: 250,
  };
}


import type { Coupled, Network } from './consolidare';
import { routesForHub, zonesOf } from './consolidare';

export interface NetworkCost {
  routes: number;
  /**
   * Routes whose kilometres are unknown, and which are therefore left out of cost.
   *
   * 149 edges in the graph have a measured travel time but no measured road distance: the
   * time search reaches further along fast roads than the 60 km bound the distance search
   * uses. A route whose path crosses one of them has a real duration and no length. The
   * pipeline does the same thing and reports `routesWithoutLength`; inventing a distance from
   * the time would be assuming the speed the whole model exists to derive.
   */
  routesWithoutLength: number;
  peakVehicles: number;
  busHoursPerWeekday: number;
  busKmPerWeekday: number;
  fleetByClass: Record<string, number>;
  fleetTotal: number;
  cost: Cost;
}

/**
 * Buses, hours and lei for the reader's whole network.
 *
 * Two rules here have already been got wrong once each in this project, and both are load
 * bearing:
 *
 * - a **T3 feeder takes the class of the largest UAT on its branch**, because one bus serves
 *   the whole branch and sizing it to the smallest village would leave the largest standing;
 * - the **spare ratio is applied once, to the network total**, never per route. Per route it
 *   buys a spare for every single-bus service and inflates the fleet by half again.
 */
export function costNetwork(coupled: Coupled, net: Network, prices: Prices): NetworkCost {
  const { data, road } = coupled;
  const zoneOf = zonesOf(data);

  const members = new Map<number, number[]>();
  net.journeys.forEach((j, i) => {
    const list = members.get(j.centre);
    if (list) list.push(i);
    else members.set(j.centre, [i]);
  });

  const peakByClass: Record<string, number> = { basic: 0, feeder: 0, trunk: 0 };
  const kmByClass: Record<string, number> = { basic: 0, feeder: 0, trunk: 0 };
  let hours = 0;
  let routeCount = 0;
  let withoutLength = 0;
  let busKm = 0;

  const add = (name: string, roundTripMin: number, kmRoundTrip: number) => {
    const service = SERVICES[name];
    const r = resourcesForRoute(roundTripMin, service.departures, kmRoundTrip);
    peakByClass[name] += r.peakVehicles;
    kmByClass[name] += r.busKm;
    hours += r.busHours;
    busKm += r.busKm;
    routeCount += 1;
  };

  // T3 feeders: every commune to the centre that absorbs it.
  for (const [centre, group] of members) {
    for (const route of routesForHub(road, centre, group, data.uatCount, zoneOf, data.population)) {
      const largest = Math.max(0, ...route.serves.map((s) => data.population[s]));
      const name = classify(largest, false);
      if (!Number.isFinite(route.oneWayKm)) {
        withoutLength += 1;
        continue;
      }
      const runningMin = (2 * route.oneWayMin) / prices.serviceSpeedFactor;
      const dwell = route.stops.length * prices.dwellMinPerStop;
      add(name, runningMin + dwell, 2 * route.oneWayKm);
    }
  }

  // T2 trunk: every centre to its county capital. A capital's own centre needs no trunk run.
  for (const centre of net.centres) {
    const journey = net.journeys[centre];
    const trunk = journey?.trunk ?? -1;
    const km = journey?.trunkKm ?? -1;
    if (trunk <= 0) continue;
    if (km < 0) {
      withoutLength += 1;
      continue;
    }
    const runningMin = (2 * trunk) / prices.serviceSpeedFactor;
    // A trunk run stops at the centres between, which this model does not enumerate; two stops
    // is the pair it certainly has, so trunk dwell here is a floor. The kilometres are real.
    add('trunk', runningMin + 2 * prices.dwellMinPerStop, 2 * km);
  }

  const peakTotal = Object.values(peakByClass).reduce((a, b) => a + b, 0);
  const fleetByClass: Record<string, number> = {};
  for (const [name, peak] of Object.entries(peakByClass)) {
    fleetByClass[name] = Math.round(fleetRequired(peakTotal, prices.spareRatio) * (peak / peakTotal));
  }
  const fleetTotal = Object.values(fleetByClass).reduce((a, b) => a + b, 0);

  return {
    routes: routeCount,
    routesWithoutLength: withoutLength,
    peakVehicles: peakTotal,
    busHoursPerWeekday: hours,
    busKmPerWeekday: busKm,
    fleetByClass,
    fleetTotal,
    cost: annualCost(hours, kmByClass, fleetByClass, prices),
  };
}

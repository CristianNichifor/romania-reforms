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

/**
 * When each period of the service day starts and ends.
 *
 * The day profile gives lengths; a duty needs clock times, because what decides how many
 * drivers a vehicle needs is not how long it runs but how far apart its first and last
 * departures are. A vehicle out from 06:00 to 22:00 needs two people whatever it does between.
 */
export const PERIOD_CLOCK: Record<string, { start: number; end: number }> = {
  am_peak: { start: 6, end: 9 },
  midday: { start: 9, end: 14 },
  pm_peak: { start: 14, end: 18 },
  evening: { start: 18, end: 22 },
};

/** Hours from the first departure of the day to the last, for a set of departures. */
export function dutySpanHours(departures: Record<string, number>): number {
  const live = Object.entries(departures).filter(([, n]) => n > 0).map(([p]) => p);
  if (!live.length) return 0;
  const start = Math.min(...live.map((p) => PERIOD_CLOCK[p]?.start ?? 0));
  const end = Math.max(...live.map((p) => PERIOD_CLOCK[p]?.end ?? 0));
  return Math.max(0, end - start);
}

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

/**
 * Service levels: what the network promises, as departures per period per class.
 *
 * These are the lever the whole simulator exists to price. Cost is not a single number — it is
 * a function of what you decide to run — and the interesting question is not "what does this
 * cost" but "what does each extra departure a day cost, and who gets it".
 *
 * Written out per level rather than as a multiplier on the default. A multiplier reads as
 * arithmetic; these are policies, and each one has to be defensible on its own terms:
 *
 * - **minim** — peaks only, everywhere. A commuter and a pupil can travel; nobody else can.
 *   This is roughly what much of rural Romania has today, and it is the floor a reader should
 *   be able to compare against rather than an option anyone should choose.
 * - **implicit** — the standard the design document argues for: four a day to the smallest
 *   commune, all on the peaks, and an hourly trunk to hold the pulse together.
 * - **extins** — midday and evening on the feeders too, so the network serves a hospital
 *   appointment and an evening shift rather than only the journey to work.
 *
 * The trunk tier matters most: it carries every transfer, so thinning it degrades journeys for
 * communes that never see a trunk bus.
 */
export interface ServiceLevel {
  id: string;
  label: string;
  departures: Record<string, Record<string, number>>;
}

export const SERVICE_LEVELS: ServiceLevel[] = [
  {
    id: 'minim',
    label: 'Minim — doar vârfurile',
    departures: {
      basic: { am_peak: 1, midday: 0, pm_peak: 1, evening: 0 },
      feeder: { am_peak: 2, midday: 0, pm_peak: 2, evening: 0 },
      trunk: { am_peak: 2, midday: 2, pm_peak: 2, evening: 1 },
    },
  },
  {
    id: 'implicit',
    label: 'Implicit — standardul propus',
    departures: {
      basic: { am_peak: 2, midday: 0, pm_peak: 2, evening: 0 },
      feeder: { am_peak: 3, midday: 2, pm_peak: 3, evening: 1 },
      trunk: { am_peak: 3, midday: 5, pm_peak: 4, evening: 4 },
    },
  },
  {
    id: 'extins',
    label: 'Extins — și după-amiaza, și seara',
    departures: {
      basic: { am_peak: 2, midday: 1, pm_peak: 2, evening: 1 },
      feeder: { am_peak: 4, midday: 4, pm_peak: 4, evening: 2 },
      trunk: { am_peak: 4, midday: 7, pm_peak: 5, evening: 6 },
    },
  },
];

export function levelById(id: string): ServiceLevel {
  return SERVICE_LEVELS.find((l) => l.id === id) ?? SERVICE_LEVELS[1];
}

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

export type Traction = 'electric' | 'hybrid' | 'diesel';

/**
 * Which traction a route needs — decided by the route, not by a policy quota.
 *
 * Two questions in order, because they are not equally binding:
 *
 * 1. **Can a battery do the day?** A vehicle that runs 300 km between depot visits cannot be
 *    battery-electric without charging on the road, whatever anyone would prefer. The range
 *    used is the WINTER range, because a public service has to run in January and not only on
 *    average — that is the same principle that removed the flex tier.
 * 2. **Do the stops pay for a hybrid?** Beyond battery range, regenerative braking earns its
 *    premium only where there is braking to recover. A long run between two towns is a diesel;
 *    a long run threading twenty villages is a hybrid.
 *
 * This is a rule, not an operations study. It has no charging on the road, no gradient, and no
 * grid capacity at the depot — which in much of Romania is the real constraint rather than the
 * vehicle. Declared in `tractiunea-e-o-regula-nu-o-masuratoare`.
 */
export function chooseTraction(
  dailyKmPerVehicle: number,
  stopsPerKm: number,
  prices: Prices,
): Traction {
  if (dailyKmPerVehicle <= prices.electricRangeKm) return 'electric';
  return stopsPerKm >= prices.stopsPerKmForHybrid ? 'hybrid' : 'diesel';
}

export interface Prices {
  electricRangeKm: number;
  stopsPerKmForHybrid: number;
  /** Purchase price multiplier against the diesel vehicle of the same class. */
  priceRatio: Record<Traction, number>;
  /** Energy and maintenance per km, by traction and seat class. */
  perKmByTraction: Record<Traction, Record<string, number>>;
  perBusHour: number;
  perBusKmByClass: Record<string, number>;
  perVehicleYear: number;
  adminShare: number;
  vehiclePrice: Record<string, number>;
  vehicleLifeYears: number;
  spareRatio: number;
  /** Passenger-kilometres one inhabitant makes on this network in a year. */
  passengerKmPerPersonYear: number;
  /** Paid hours a full-time driver works in a month. */
  /** Capital to build one vehicle space: parking, workshop, wash, admin. */
  depotCapexPerBus: number;
  /** Extra capital for a charging-equipped space, on top of the base one. */
  depotElectricPremiumPerBus: number;
  /** A depot outlives three generations of bus, so it is annualised on its own horizon. */
  depotLifeYears: number;
  /** Cost of one PAID driver-hour, before the platform-to-paid ratio. */
  perPaidHour: number;
  /** EU 561/2006: nine hours of driving a day, and a break after four and a half. */
  maxDrivingHoursDay: number;
  /** How much of the day one duty may span, sign-on to sign-off. */
  maxDutySpanHours: number;
  /** Nobody is employed for ninety minutes. */
  minimumPaidShiftHours: number;
  /** Paid hours a full-time driver works in a month. */
  driverPaidHoursMonth: number;
  /** Paid hours per hour the bus is moving: sign-on, breaks, deadhead. */
  platformToPaidRatio: number;
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
  const perKmByTraction: Record<Traction, Record<string, number>> = {
    electric: {},
    hybrid: {},
    diesel: {},
  };
  for (const [name, spec] of Object.entries(document.vehicles)) {
    const fuel = (spec.dieselPer100Km / 100) * item('dieselPricePerLitre');
    const tyres = item('tyresPerKm');
    perKm[name] = fuel + maintenance + tyres;
    price[name] = spec.priceRon;

    // Energy and maintenance both move with traction, and in opposite directions: electricity
    // is cheaper per kilometre than diesel and an electric drivetrain needs less work, but the
    // vehicle costs more to buy. Which way that lands is the whole question.
    perKmByTraction.diesel[name] = perKm[name];
    perKmByTraction.hybrid[name] = fuel * (1 - item('hybridFuelSaving')) + maintenance + tyres;
    perKmByTraction.electric[name] =
      item('electricKwhPerKm') * item('electricityPriceRonKwh') +
      maintenance * (1 - item('electricMaintenanceSaving')) +
      tyres;
  }

  return {
    perBusHour: perPaidHour * item('platformToPaidRatio'),
    perBusKmByClass: perKm,
    perVehicleYear:
      item('insurancePerVehicleYear') + item('depotPerVehicleYear') + item('roadTaxPerVehicleYear'),
    adminShare: item('adminOverheadShare'),
    vehiclePrice: price,
    vehicleLifeYears: item('vehicleLifeYears'),
    electricRangeKm: item('electricRangeKm'),
    stopsPerKmForHybrid: item('stopsPerKmForHybrid'),
    priceRatio: {
      electric: item('electricPriceRatio'),
      hybrid: item('hybridPriceRatio'),
      diesel: 1,
    },
    perKmByTraction: perKmByTraction,
    spareRatio: 0.15,
    depotCapexPerBus: item('depotCapexPerBusRon'),
    depotElectricPremiumPerBus: item('depotElectricPremiumPerBusRon'),
    depotLifeYears: item('depotLifeYears'),
    passengerKmPerPersonYear: item('passengerKmPerPersonYear'),
    perPaidHour,
    maxDrivingHoursDay: item('maxDrivingHoursDay'),
    maxDutySpanHours: item('maxDutySpanHours'),
    minimumPaidShiftHours: item('minimumPaidShiftHours'),
    driverPaidHoursMonth: item('driverPaidHoursMonth'),
    platformToPaidRatio: item('platformToPaidRatio'),
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
  /**
   * Drivers to employ, full-time equivalent.
   *
   * Not the same as buses, and larger: a driver is paid for sign-on, breaks and deadhead as
   * well as for driving, and one bus running sixteen hours a day needs more than one driver.
   * Costing at bus-hours alone would understate the largest single line by roughly a third —
   * which is why `perBusHour` already carries the ratio, and why this headcount has to carry
   * it too rather than dividing bus-hours by a working year.
   */
  drivers: number;
  /** Driver duties a weekday — the shifts that must be rostered, not the hours driven. */
  dutiesPerWeekday: number;
  /** Paid driver-hours a weekday, including dead time a peak timetable creates. */
  paidHoursPerWeekday: number;
  cost: Cost;
  /** Capacity the timetable offers, in seat-kilometres a year. */
  seatKmPerYear: number;
  /** Seats standing in the fleet — what the system owns, rather than what it moves. */
  seatsOwned: number;
  /**
   * Cost per seat-kilometre offered, in lei.
   *
   * The unit a policy decision is actually made in, and the reason vehicle mix does not need
   * to be a lever: a network is judged on the capacity it puts on the road and what that
   * capacity costs, not on how it is packaged. It is also the one figure here that can be set
   * beside another country's without converting anything but currency.
   *
   * Capacity OFFERED, not used. This is a fact about the timetable — seats past a stop — and
   * says nothing about whether anyone is sitting in them. That is the honest boundary of a
   * model with no demand in it.
   */
  ronPerSeatKm: number;
  /** Peak vehicles by traction — the mix the routes asked for, not one anybody chose. */
  tractionMix: Record<Traction, number>;
}

/**
 * Whole-life cost over a horizon, undiscounted.
 *
 * `Cost.capitalRon` is the annualised slice of the fleet; a policy question wants the bill,
 * so the vehicles are charged once at full price and the running cost is charged every year.
 *
 * **Undiscounted, in today's lei.** A discount rate is a political choice as much as a
 * financial one — it decides how much a journey in 2038 is worth against one now — and
 * picking one silently inside a model would bury that choice in arithmetic.
 */
export function lifetimeCost(
  cost: Cost,
  vehicleLifeYears: number,
  years: number,
  fleet = 0,
  depotCapexPerBus = 0,
  electricSpaces = 0,
  depotElectricPremiumPerBus = 0,
): {
  fleetCapexRon: number;
  depotCapexRon: number;
  capexRon: number;
  opexRon: number;
  totalRon: number;
  years: number;
} {
  const fleetCapex = cost.capitalRon * vehicleLifeYears;
  // The depot is charged once at full price over this horizon, not annualised: a network being
  // built needs the buildings before it runs, and a policy question wants the bill. Its longer
  // life shows up as the reason the same buildings serve the NEXT fleet too — which is why the
  // twelve-year figure overstates the true whole-life cost of the buildings and the code says
  // so rather than quietly spreading it.
  // Every space costs the base; only the electric ones carry a charger and a grid connection.
  // So the depot bill rises exactly as far as the route rule asks for battery vehicles, rather
  // than by a policy percentage nobody derived.
  const depotCapex = fleet * depotCapexPerBus + electricSpaces * depotElectricPremiumPerBus;
  const opex = cost.operatingRon * years;
  return {
    fleetCapexRon: fleetCapex,
    depotCapexRon: depotCapex,
    capexRon: fleetCapex + depotCapex,
    opexRon: opex,
    totalRon: fleetCapex + depotCapex + opex,
    years,
  };
}

/**
 * Paid driver-hours for one vehicle's day, which is not its driving hours.
 *
 * Three things push it up, and the model used to catch only the first:
 *
 * 1. **Sign-on, breaks and deadhead** — the platform-to-paid ratio.
 * 2. **The span.** A vehicle out from 06:00 to 22:00 exceeds what one duty may cover, so it
 *    needs two, whatever it drives. EU 561/2006 caps daily driving at nine hours.
 * 3. **The minimum shift.** Four departures on the peaks is about three hours of driving spread
 *    across twelve, with a five-hour hole in the middle. Nobody is employed on those terms, and
 *    charging three hours for it made a peak-only service look cheaper than it is.
 *
 * This is where a service concentrated on the peaks stops being cheap: it buys very little
 * driving over a very long day, and the day is what has to be staffed.
 */
export function paidDriverHours(
  drivingHours: number,
  spanHours: number,
  prices: Pick<
    Prices,
    'platformToPaidRatio' | 'maxDutySpanHours' | 'minimumPaidShiftHours' | 'maxDrivingHoursDay'
  >,
): { hours: number; duties: number } {
  if (drivingHours <= 0) return { hours: 0, duties: 0 };
  // A duty is limited both by how long it may span and by how much may be driven inside it.
  const bySpan = Math.ceil(spanHours / prices.maxDutySpanHours);
  const byDriving = Math.ceil(drivingHours / prices.maxDrivingHoursDay);
  const duties = Math.max(1, bySpan, byDriving);
  const withRatio = drivingHours * prices.platformToPaidRatio;
  const withMinimum = duties * prices.minimumPaidShiftHours;
  return { hours: Math.max(withRatio, withMinimum), duties };
}

/** Full-time drivers for a year of PAID hours. */
export function driversRequired(paidHoursPerYear: number, paidHoursMonth: number): number {
  if (paidHoursMonth <= 0) return 0;
  return Math.ceil(paidHoursPerYear / (paidHoursMonth * 12));
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
export function costNetwork(
  coupled: Coupled,
  net: Network,
  prices: Prices,
  level: ServiceLevel = levelById('implicit'),
): NetworkCost {
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
  const peakByTraction: Record<Traction, number> = { electric: 0, hybrid: 0, diesel: 0 };
  const runningRon: Record<string, number> = {};
  let paidHours = 0;
  let duties = 0;
  let hours = 0;
  let routeCount = 0;
  let withoutLength = 0;
  let busKm = 0;

  const add = (name: string, roundTripMin: number, kmRoundTrip: number, stops: number) => {
    const r = resourcesForRoute(roundTripMin, level.departures[name], kmRoundTrip);
    peakByClass[name] += r.peakVehicles;
    kmByClass[name] += r.busKm;
    hours += r.busHours;
    busKm += r.busKm;
    routeCount += 1;

    // Drivers are staffed against the vehicle's DAY, not its driving. A route on the peaks
    // spans twelve hours to move for three, and someone has to be there for the span.
    const span = dutySpanHours(level.departures[name]);
    const perVehicle = paidDriverHours(r.busHours / Math.max(1, r.peakVehicles), span, prices);
    paidHours += perVehicle.hours * Math.max(1, r.peakVehicles);
    duties += perVehicle.duties * Math.max(1, r.peakVehicles);

    // What this route needs, from what it does: kilometres a vehicle covers in a day, and how
    // often it stops. Both come out of the resources just computed rather than being assumed.
    const dailyKmPerVehicle = r.peakVehicles ? r.busKm / r.peakVehicles : 0;
    const stopsPerKm = kmRoundTrip > 0 ? (2 * stops) / kmRoundTrip : 0;
    const traction = chooseTraction(dailyKmPerVehicle, stopsPerKm, prices);
    peakByTraction[traction] += r.peakVehicles;
    runningRon[traction] =
      (runningRon[traction] ?? 0) +
      r.busKm * prices.weekdaysPerYear * (prices.perKmByTraction[traction][name] ?? 0);
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
      add(name, runningMin + dwell, 2 * route.oneWayKm, route.stops.length);
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
    add('trunk', runningMin + 2 * prices.dwellMinPerStop, 2 * km, 2);
  }

  const peakTotal = Object.values(peakByClass).reduce((a, b) => a + b, 0);
  const fleetByClass: Record<string, number> = {};
  for (const [name, peak] of Object.entries(peakByClass)) {
    fleetByClass[name] = Math.round(fleetRequired(peakTotal, prices.spareRatio) * (peak / peakTotal));
  }
  const fleetTotal = Object.values(fleetByClass).reduce((a, b) => a + b, 0);

  // Capacity offered: every kilometre a bus runs, multiplied by the seats it carries past.
  const seatKmPerYear = Object.entries(kmByClass).reduce(
    (sum, [name, km]) => sum + km * prices.weekdaysPerYear * (SERVICES[name]?.seats ?? 0),
    0,
  );
  const seatsOwned = Object.entries(fleetByClass).reduce(
    (sum, [name, n]) => sum + n * (SERVICES[name]?.seats ?? 0),
    0,
  );
  // Vehicles cost what their traction costs. The mix is an output of the route rule, so the
  // capital bill follows the network rather than a procurement decision made in advance.
  const peakAll = Object.values(peakByTraction).reduce((a, b) => a + b, 0);
  const fleetTotalAll = fleetRequired(peakAll, prices.spareRatio);
  let capitalRon = 0;
  const tractionMix: Record<Traction, number> = { electric: 0, hybrid: 0, diesel: 0 };
  for (const t of ['electric', 'hybrid', 'diesel'] as Traction[]) {
    const share = peakAll ? peakByTraction[t] / peakAll : 0;
    const vehicles = Math.round(fleetTotalAll * share);
    tractionMix[t] = vehicles;
    // Base price is the fleet's own class mix, scaled by what this traction costs to buy.
    const basePrice = fleetTotal
      ? Object.entries(fleetByClass).reduce(
          (sum, [name, n]) => sum + (prices.vehiclePrice[name] ?? 0) * n,
          0,
        ) / fleetTotal
      : 0;
    capitalRon += (vehicles * basePrice * prices.priceRatio[t]) / prices.vehicleLifeYears;
  }

  const running = Object.values(runningRon).reduce((a, b) => a + b, 0);
  // Paid hours, not bus-hours. The difference is the dead time a peak service creates.
  const driver = paidHours * prices.weekdaysPerYear * prices.perPaidHour;
  const standing = fleetTotal * prices.perVehicleYear;
  const admin = (driver + running + standing) * prices.adminShare;
  const operating = driver + running + standing + admin;
  const totals: Cost = {
    driverRon: driver,
    runningRon: running,
    standingRon: standing,
    adminRon: admin,
    capitalRon,
    operatingRon: operating,
    totalRon: operating + capitalRon,
  };

  return {
    routes: routeCount,
    routesWithoutLength: withoutLength,
    seatKmPerYear,
    seatsOwned,
    tractionMix,
    ronPerSeatKm: seatKmPerYear ? totals.totalRon / seatKmPerYear : 0,
    drivers: driversRequired(paidHours * prices.weekdaysPerYear, prices.driverPaidHoursMonth),
    dutiesPerWeekday: duties,
    paidHoursPerWeekday: paidHours,
    peakVehicles: peakTotal,
    busHoursPerWeekday: hours,
    busKmPerWeekday: busKm,
    fleetByClass,
    fleetTotal,
    cost: totals,
  };
}


export interface Demand {
  /** Passenger-kilometres a year, from population alone. */
  passengerKm: number;
  /** Seats offered over the same year. */
  seatKm: number;
  /**
   * Share of offered seats actually occupied — an OUTPUT now, not an assumption.
   *
   * This is the whole point of extrapolating demand from population: the load factor was the
   * single number governing every subsidy figure in the model, and it was picked. Now it falls
   * out of how many people live in the country and how much service is run for them, and it
   * can exceed 1 — which is a finding, not an error.
   */
  loadFactor: number;
  /** True where the timetable cannot carry the population it serves. */
  overCapacity: boolean;
}

/**
 * Demand extrapolated from population, and the capacity it meets.
 *
 * Deliberately crude and deliberately not hidden: every inhabitant generates the same
 * passenger-kilometres regardless of age, income, car ownership or how far they are from their
 * county seat. What it buys is that the service level and the demand can finally be compared —
 * the model can say "this timetable cannot carry these people" instead of assuming an occupancy
 * that makes the sum work.
 */
export function demandFrom(
  people: number,
  seatKmPerYear: number,
  passengerKmPerPersonYear: number,
): Demand {
  const passengerKm = people * passengerKmPerPersonYear;
  const loadFactor = seatKmPerYear ? passengerKm / seatKmPerYear : 0;
  return { passengerKm, seatKm: seatKmPerYear, loadFactor, overCapacity: loadFactor > 1 };
}

export interface Farebox {
  passengerKm: number;
  revenueRon: number;
  subsidyRon: number;
  recovery: number;
  subsidyPerPersonYearRon: number;
}

/**
 * Ticket revenue and the subsidy left over, for the reader's own network.
 *
 * The recovery ratio is an OUTPUT. Assuming Denmark's ~50% and multiplying would be circular:
 * it says subsidy = cost x (1 - r) and the benchmark could never disagree with it. So revenue
 * is built from a fare and a quantity, and the ratio falls out where Movia can check it.
 *
 * The quantity is the weak half and weak in a specific way: passenger-kilometres come from the
 * capacity the network offers times an assumed load factor. That means this can say what a
 * given service would earn and cannot say whether anyone would ride it — and revenue is exactly
 * proportional to that assumption.
 */
export function farebox(
  passengerKm: number,
  operatingRon: number,
  people: number,
  fare: number,
): Farebox {
  const revenue = passengerKm * fare;
  // Clamped at zero: a service earning more than it costs needs no subsidy, and a negative
  // subsidy is a surplus — a different claim that must not arrive disguised as this one.
  const subsidy = Math.max(0, operatingRon - revenue);
  return {
    passengerKm,
    revenueRon: revenue,
    subsidyRon: subsidy,
    recovery: operatingRon ? revenue / operatingRon : 0,
    subsidyPerPersonYearRon: people ? subsidy / people : 0,
  };
}

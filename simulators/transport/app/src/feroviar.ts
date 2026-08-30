/**
 * The train, offered against the bus, for the reader's own network.
 *
 * **The rail journey does not depend on the consolidation.** A train runs to the county
 * capital whatever centres a scenario invents; the track and the stations are where they are.
 * What does depend on the scenario is whether that train *beats the bus* — because the bus
 * journey runs through whichever centre absorbed the commune. So the pipeline ships the
 * ingredients (two walks and a rail distance) and the verdict is reached here, next to the bus
 * journey it is competing with.
 *
 * That distinction is the reason the rail panel was wrong before this file existed: it reported
 * "247 communes faster by train" computed against the default 249 centres, on a page that was
 * by then drawing 216. The number was true about a country the reader was not looking at.
 *
 * **A train is only offered where both ends are walkable.** Station distance is known as a
 * straight line, and turning a long straight line into a bus leg is precisely the
 * geometry-as-road-time error the rail speed model was written to avoid. A commune with its
 * halt five kilometres away is not served by the line that passes it, and the model says so
 * rather than inventing a shuttle.
 */

/** Walking speed, km/h. */
const WALK_KMH = 4.5;

/** Straight line to street distance for a short walk. Streets are not crow-flies. */
const WALK_DETOUR = 1.3;

/** Beyond this a station does not serve a settlement on foot. Matches the Python constant. */
export const STATION_WALK_KM = 2.0;

export interface RailAccess {
  /** Straight-line km from each UAT to its nearest station. NaN where unknown. */
  stationKm: Float32Array;
  /** Straight-line km from the county capital to its own nearest station. */
  seatStationKm: Float32Array;
  /** Rail distance in km from that station to the county capital's station. */
  railKm: Float32Array;
}

/** Minutes on foot to cover a straight-line gap, allowing for streets. */
export function walkMin(straightKm: number): number {
  return (straightKm * WALK_DETOUR * 60) / WALK_KMH;
}

/** Minutes between trains, from a daily count over the operating day. */
export function trainHeadwayMin(trainsPerWeekday: number, serviceHours: number): number {
  if (trainsPerWeekday <= 0 || serviceHours <= 0) {
    throw new Error('trains per weekday and service hours must both be positive');
  }
  return (serviceHours * 60) / trainsPerWeekday;
}

export function loadRailAccess(buffer: ArrayBuffer, uatCount: number): RailAccess {
  const expected = uatCount * 4 * 3;
  if (buffer.byteLength !== expected) {
    throw new Error(
      `rail-access.bin is ${buffer.byteLength} bytes, expected ${expected} for ${uatCount} UATs`,
    );
  }
  return {
    stationKm: new Float32Array(buffer.slice(0, uatCount * 4)),
    seatStationKm: new Float32Array(buffer.slice(uatCount * 4, uatCount * 8)),
    railKm: new Float32Array(buffer.slice(uatCount * 8)),
  };
}

/**
 * Walk, train, walk — or null where the train is not a real option.
 *
 * Both ends must be walkable. The condition at the destination removes a whole county at once,
 * which is the correct and slightly brutal answer for the five county seats whose station sits
 * outside the town.
 */
export function railJourneyMin(
  access: RailAccess,
  index: number,
  railKmh: number,
  wait: number,
): number | null {
  const station = access.stationKm[index];
  const seat = access.seatStationKm[index];
  const km = access.railKm[index];
  // `Number.isFinite` and not a null check: a missing value arrives from the binary as NaN, and
  // every comparison against NaN is false — so an unreachable commune would sail through a
  // distance test and produce a NaN journey that then wins a Math.min against a real one.
  if (![station, seat, km].every(Number.isFinite)) return null;
  if (station > STATION_WALK_KM || seat > STATION_WALK_KM) return null;
  return walkMin(station) + wait + (km / railKmh) * 60 + walkMin(seat);
}

export interface RailVerdict {
  /** Rail journey per UAT under this timetable, or -1 where no train is on offer. */
  minutes: Float64Array;
  /** UATs where a train exists at all. */
  withOption: number;
  /** UATs where the train beats the bus. */
  faster: number;
  /** People in those UATs. */
  people: number;
}

/**
 * Compare the train against the bus, commune by commune.
 *
 * `busMinutes` is the reader's own network, so this verdict moves when they move a slider —
 * which is the entire point of computing it here rather than shipping a number.
 */
export function compareWithBus(
  access: RailAccess,
  busMinutes: Array<number | null>,
  population: Uint32Array,
  railKmh: number,
  wait: number,
): RailVerdict {
  const minutes = new Float64Array(busMinutes.length).fill(-1);
  let withOption = 0;
  let faster = 0;
  let people = 0;

  for (let i = 0; i < busMinutes.length; i += 1) {
    const rail = railJourneyMin(access, i, railKmh, wait);
    if (rail === null) continue;
    minutes[i] = rail;
    withOption += 1;
    const bus = busMinutes[i];
    if (bus !== null && rail < bus) {
      faster += 1;
      people += population[i];
    }
  }

  return { minutes, withOption, faster, people };
}

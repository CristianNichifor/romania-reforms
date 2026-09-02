/**
 * Both taxes, recomputed in the browser as the reader moves the assumptions.
 *
 * This is a port of `build_valoare_teren.py` and `build_impozit.py`, and it exists because
 * the assumptions move the answer more than the data does. A page that showed only the
 * Python's chosen assumption would be showing a conclusion; this one shows a calculation.
 *
 * Four things the reader controls, and each is an admission rather than a feature:
 *
 *   share      how much land is intravilan. The land register does not record the split, so
 *              the default treats curți-construcții as the whole of it. Raising the share
 *              takes hectares from arable, because village gardens are arable land inside the
 *              intravilan — which is exactly where the default is wrong.
 *   value      which published price stands for a whole commune. The grid prints one per
 *              village with no areas to weight them by.
 *   fiscal     which lawful reading of article 465. The Code states a range and leaves the
 *              choice to the local council; the zone and the rank are council decisions too.
 *   rate       the land value tax rate, the only one of the four that is a policy choice
 *              rather than a gap in the sources.
 */

export type Band = { low: number; central: number; high: number };
export type BandKey = keyof Band;

export type Locality = {
  siruta: string;
  name: string;
  rank: 'municipii' | 'orase' | 'comune' | null;
  pricedBy: 'zone' | 'village';
  parts: number;
  totalHa: number;
  builtHa: number;
  forestHa: number;
  areaHa: Record<string, number>;
  intravilanEurPerM2: Band;
  extravilanEurPerM2: Record<string, number>;
};

export type FiscalCode = {
  zones: string[];
  ranks: string[];
  intravilanBuiltLeiPerHa: Record<string, Record<string, { min: number; max: number }>>;
  extravilanLeiPerHa: Record<string, { min: number; max: number }>;
  zoneRankCoefficient: Record<string, Record<string, number>>;
};

export type Settings = {
  /** Multiplier on the built-up area treated as intravilan. 1 is the Python default. */
  share: number;
  value: BandKey;
  fiscal: BandKey;
  /** Percent of land value. */
  rate: number;
  /**
   * Percent of land value that the land under buildings earns in a year. Turns the stock into
   * the flow, which is the unit a land tax argument is actually about: "takes 7% of what the
   * land earns" is a sentence you can weigh, and "0,33% of land value" is not. Nobody
   * publishes a yield for building land in Romania, so it is a control rather than a constant.
   */
  landYield: number;
  /**
   * Percent for the agricultural part, which unlike the above **is** measured: INS surveys
   * both the sale price and the rent of farmland, and the ratio is about 1,5% a year. Not a
   * control, because it is an observation — it arrives from the dataset and the reader is
   * shown it rather than asked for it.
   */
  landYieldAgricultural: number;
  /**
   * Per cadastral code, where the survey measured that code separately — arable at about
   * 1,43% and permanent grassland at 1,61% are different measurements, not one rounded two
   * ways. Codes absent here fall back to `landYieldAgricultural`; forest is present but
   * borrowed, which the rent dataset flags.
   */
  landYieldByCategory: Record<string, number>;
  ronPerEur: number;
};

export type Result = {
  siruta: string;
  name: string;
  rank: Locality['rank'];
  intravilanHa: number;
  landValueRon: number;
  fiscalCodeRon: number;
  lvtRon: number;
  /** Positive means the land value tax charges more than the Fiscal Code would. */
  deltaRon: number;
  landRentRon: number;
};

const M2_PER_HA = 10_000;
/** The Fiscal Code's extravilan rows, against the categories the land register counts in. */
const EXTRAVILAN_ROWS: Array<[string, string]> = [
  ['Teren arabil', 'A'],
  ['Pășune', 'P+F'],
  ['Fâneață', 'P+F'],
  ['Vie', 'V+L'],
  ['Livadă', 'V+L'],
  ['Teren cu apă', 'AP'],
  ['Drumuri și căi ferate', 'DR'],
  ['Teren neproductiv', 'NP'],
];
/** Where the extra intravilan hectares come from when the reader raises the share. */
export const DONOR_CATEGORY = 'A';
/** Forest, which the land register reports outside `areaHa` — see `landValueParts`. */
export const FOREST_CATEGORY = 'PADURE';

/**
 * A commune's seat is rank IV and its other villages rank V, with no areas to split them by.
 * Towns have one rank each. Mirrors `rank_of` in build_impozit.py.
 */
export function fiscalRank(rank: Locality['rank'], name: string, band: BandKey): string {
  if (rank === 'municipii') return RANK_I.has(fold(name)) ? 'I' : 'II';
  if (rank === 'orase') return 'III';
  return band === 'low' ? 'V' : 'IV';
}

// Legea nr. 351/2001, anexa IV. The Fiscal Code uses the ranks without defining them.
const RANK_I = new Set([
  'bacau', 'brasov', 'braila', 'clujnapoca', 'constanta', 'craiova',
  'galati', 'iasi', 'oradea', 'ploiesti', 'timisoara',
]);

function fold(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z]/g, '');
}

function pick(cell: { min: number; max: number }, band: BandKey): number {
  if (band === 'low') return cell.min;
  if (band === 'high') return cell.max;
  return (cell.min + cell.max) / 2;
}

/** How the built-up area and its donor category move when the reader raises the share. */
export function splitArea(locality: Locality, share: number) {
  const donor = locality.areaHa[DONOR_CATEGORY] ?? 0;
  // Capped at the donor: the intravilan cannot eat land the commune does not have, and an
  // uncapped multiplier silently invents hectares in communes that are mostly forest.
  const wanted = locality.builtHa * (share - 1);
  const moved = Math.max(0, Math.min(wanted, donor));
  return { intravilanHa: locality.builtHa + moved, movedFromDonor: moved };
}

/**
 * The two halves of a locality's land value, kept apart because they earn at different rates.
 *
 * Farmland's yield is measured and the land under houses' is assumed, and the two differ by a
 * factor of three, so a single total cannot produce the right rent. Mirrors the split
 * `build_impozit.py` writes as `extravilanValueRon`.
 */
export function landValueParts(
  locality: Locality,
  settings: Settings,
): { built: number; agricultural: number; byCode: Record<string, number> } {
  const { intravilanHa, movedFromDonor } = splitArea(locality, settings.share);
  const built = intravilanHa * M2_PER_HA * locality.intravilanEurPerM2[settings.value];
  const byCode: Record<string, number> = {};
  let agricultural = 0;
  for (const [code, hectares] of Object.entries(locality.areaHa)) {
    if (code === 'CC') continue;
    const price = locality.extravilanEurPerM2[code];
    if (price === undefined) continue;
    const remaining = code === DONOR_CATEGORY ? hectares - movedFromDonor : hectares;
    // Two register categories can fold onto one notary code, so the price is applied to the
    // hectares once — the register's own split is already lost by the time it reaches here.
    const amount = Math.max(0, remaining) * M2_PER_HA * price;
    agricultural += amount;
    byCode[code] = (byCode[code] ?? 0) + amount;
  }
  // Forest is not in areaHa: the register keeps the forest fund apart from the agricultural
  // one, so it arrives as its own field and the two add up to the locality. Missing it here
  // while build_valoare_teren.py priced it is what the rent parity test caught — a third of
  // the surface of these counties, absent from the browser and present in the file.
  const forest = locality.extravilanEurPerM2[FOREST_CATEGORY];
  if (forest !== undefined) {
    const amount = locality.forestHa * M2_PER_HA * forest;
    agricultural += amount;
    byCode[FOREST_CATEGORY] = (byCode[FOREST_CATEGORY] ?? 0) + amount;
  }
  return { built, agricultural, byCode };
}

export function landValueEur(locality: Locality, settings: Settings): number {
  const { built, agricultural } = landValueParts(locality, settings);
  return built + agricultural;
}

export function fiscalCodeRon(locality: Locality, code: FiscalCode, settings: Settings): number {
  const band = settings.fiscal;
  const rank = fiscalRank(locality.rank, locality.name, band);
  // The cheapest lawful reading pairs the cheapest zone with the bottom of the statutory
  // range; the dearest pairs the opposite. Both are things a council could lawfully charge.
  const zones = band === 'low' ? ['D'] : band === 'high' ? ['A'] : code.zones;
  const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length;

  const { intravilanHa, movedFromDonor } = splitArea(locality, settings.share);
  const built = mean(zones.map((zone) => pick(code.intravilanBuiltLeiPerHa[zone]![rank]!, band)));
  let total = intravilanHa * built;

  for (const [fiscalName, notaryCode] of EXTRAVILAN_ROWS) {
    const hectares = locality.areaHa[notaryCode] ?? 0;
    if (!hectares) continue;
    const row = Object.entries(code.extravilanLeiPerHa).find(([key]) =>
      key.startsWith(fiscalName),
    );
    if (!row) continue;
    const share = EXTRAVILAN_ROWS.filter(([, c]) => c === notaryCode).length;
    const remaining = notaryCode === DONOR_CATEGORY ? hectares - movedFromDonor : hectares;
    const coefficient = mean(zones.map((zone) => code.zoneRankCoefficient[zone]![rank]!));
    total += (Math.max(0, remaining) / share) * pick(row[1], band) * coefficient;
  }
  return total;
}

/**
 * Add up several counties' results into one.
 *
 * Not a matter of concatenating rows and calling `evaluate` again: each county is priced at
 * its own exchange rate and its own measured farmland yield, so the arithmetic has to happen
 * per county and only the money may be added. The map has done this since it was written —
 * it paints every county at that county's own rates — and the "toate județele" total is the
 * same operation with the results summed instead of coloured.
 *
 * The three ratios are recomputed from the sums rather than averaged. A mean of forty-two
 * capture rates answers "what is the typical county's capture"; the sum answers "what does
 * the country's land raise against what it yields", and that is the question the page asks.
 */
export function combine(parts: Array<ReturnType<typeof evaluate>>): ReturnType<typeof evaluate> {
  const rows = parts.flatMap((part) => part.rows);
  const total = (get: (t: (typeof parts)[number]['totals']) => number) =>
    parts.reduce((sum, part) => sum + get(part.totals), 0);
  const value = total((t) => t.value);
  const fiscal = total((t) => t.fiscal);
  const lvt = total((t) => t.lvt);
  const rent = total((t) => t.rent);
  return {
    rows,
    totals: {
      fiscal,
      lvt,
      value,
      rent,
      neutral: value ? (100 * fiscal) / value : 0,
      fiscalCapture: rent ? (100 * fiscal) / rent : 0,
      lvtCapture: rent ? (100 * lvt) / rent : 0,
    },
  };
}

export function evaluate(
  localities: Locality[],
  code: FiscalCode,
  settings: Settings,
): {
  rows: Result[];
  totals: {
    fiscal: number;
    lvt: number;
    value: number;
    neutral: number;
    rent: number;
    fiscalCapture: number;
    lvtCapture: number;
  };
} {
  const rows = localities.map((locality) => {
    const parts = landValueParts(locality, settings);
    const value = (parts.built + parts.agricultural) * settings.ronPerEur;
    const fiscal = fiscalCodeRon(locality, code, settings);
    const lvt = (value * settings.rate) / 100;
    // A yield per cadastral code, mirroring build_renta.py. Anything the breakdown does not
    // account for keeps the general agricultural band rather than dropping out of the rent.
    let rent = (parts.built * settings.ronPerEur * settings.landYield) / 100;
    let accounted = 0;
    for (const [code, amount] of Object.entries(parts.byCode)) {
      const band = settings.landYieldByCategory[code] ?? settings.landYieldAgricultural;
      rent += (amount * settings.ronPerEur * band) / 100;
      accounted += amount;
    }
    rent +=
      (Math.max(0, parts.agricultural - accounted) *
        settings.ronPerEur *
        settings.landYieldAgricultural) /
      100;
    return {
      siruta: locality.siruta,
      name: locality.name,
      rank: locality.rank,
      intravilanHa: splitArea(locality, settings.share).intravilanHa,
      landValueRon: value,
      fiscalCodeRon: fiscal,
      lvtRon: lvt,
      deltaRon: lvt - fiscal,
      landRentRon: rent,
    };
  });
  const sum = (get: (row: Result) => number) => rows.reduce((a, row) => a + get(row), 0);
  const value = sum((r) => r.landValueRon);
  const fiscal = sum((r) => r.fiscalCodeRon);
  const lvt = sum((r) => r.lvtRon);
  const rent = sum((r) => r.landRentRon);
  return {
    rows,
    totals: {
      fiscal,
      lvt,
      value,
      rent,
      // The headline: the rate that raises what the Fiscal Code raises under the same reading.
      neutral: value ? (100 * fiscal) / value : 0,
      // What share of the flow each tax takes. A tax on the whole rent is the textbook full
      // land value tax, so these say how far from that either one is.
      fiscalCapture: rent ? (100 * fiscal) / rent : 0,
      lvtCapture: rent ? (100 * lvt) / rent : 0,
    },
  };
}

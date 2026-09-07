/**
 * How many people a merger removes from the political layer, and how many it leaves.
 *
 * Every figure here is statutory. Nothing is estimated, modelled or inferred from election
 * results: Romanian law fixes the size of a local council by population band and the number
 * of mayors and vice-mayors by the standing of the unit, so both sides of a merger are
 * arithmetic once the population is known. That is what makes it worth showing — it is the
 * one consequence of consolidation that can be stated without a counterfactual.
 *
 * Sources, both quoted verbatim where they are used below:
 *
 * - **Art. 112, Codul administrativ (OUG 57/2019)** — the council-size bands. The number is
 *   set by order of the prefect on the INS population as of 1 January of the election year.
 * - **Art. 148, Codul administrativ** — "Comunele, oraşele şi municipiile au câte un primar
 *   şi câte un viceprimar, iar municipiile reşedinţă de judeţ au câte un primar şi câte 2
 *   viceprimari".
 */

/**
 * Art. 112: local councillors by population.
 *
 * Upper bounds, inclusive, ascending. The last entry has no upper bound in the statute; it is
 * written here as Infinity so the lookup is one shape rather than a special case.
 */
const COUNCIL_BANDS: readonly (readonly [upperInclusive: number, councillors: number])[] = [
  [1_500, 9],
  [3_000, 11],
  [5_000, 13],
  [10_000, 15],
  [20_000, 17],
  [50_000, 19],
  [100_000, 21],
  [200_000, 23],
  [400_000, 27],
  [Infinity, 31],
];

/**
 * The Consiliul General of Bucharest, fixed at 55 by the same article rather than banded.
 *
 * The city is one unit in this model, so it never merges with anything and this figure never
 * changes — but a panel that silently applied the 31-member band to it would be wrong.
 */
export const BUCHAREST_COUNCIL = 55;

/** Councillors a unit of this population elects, under Art. 112. */
export function councillorsFor(population: number): number {
  // A unit cannot have a negative population, and zero is a data problem rather than a legal
  // question: the smallest band is the honest answer to both.
  const people = Math.max(0, population);
  for (const [upper, councillors] of COUNCIL_BANDS) {
    if (people <= upper) return councillors;
  }
  return COUNCIL_BANDS[COUNCIL_BANDS.length - 1]![1];
}

/**
 * Vice-mayors, under Art. 148.
 *
 * `isCountyCapital` is the statute's "municipiu reşedinţă de judeţ" and nothing broader: a
 * municipiu that is not its county's seat has one vice-mayor like any commune.
 */
export function viceMayorsFor(isCountyCapital: boolean): number {
  return isCountyCapital ? 2 : 1;
}

export interface Representation {
  councillors: number;
  mayors: number;
  viceMayors: number;
}

/** Everyone the political layer of a single UAT carries today. */
export function representationOfUat(population: number, isCountyCapital: boolean): Representation {
  return {
    councillors: councillorsFor(population),
    mayors: 1,
    viceMayors: viceMayorsFor(isCountyCapital),
  };
}

/** The sum across a set of communes: what exists before they merge. */
export function representationBefore(
  members: readonly { population: number; isCountyCapital: boolean }[],
): Representation {
  return members.reduce<Representation>(
    (total, member) => {
      const one = representationOfUat(member.population, member.isCountyCapital);
      return {
        councillors: total.councillors + one.councillors,
        mayors: total.mayors + one.mayors,
        viceMayors: total.viceMayors + one.viceMayors,
      };
    },
    { councillors: 0, mayors: 0, viceMayors: 0 },
  );
}

/**
 * What the merged unit would carry.
 *
 * The population is the sum of its members, and the standing that decides the vice-mayors is
 * the seat's: a unit seated on a county capital keeps that capital's two.
 */
export function representationAfter(
  totalPopulation: number,
  seatIsCountyCapital: boolean,
): Representation {
  return {
    councillors: councillorsFor(totalPopulation),
    mayors: 1,
    viceMayors: viceMayorsFor(seatIsCountyCapital),
  };
}

/**
 * The band a Danish municipality of this size would choose within.
 *
 * Denmark has no formula to copy. `Kommunestyrelsesloven § 5` fixes a range and leaves the
 * number to each municipality's own governing statute — so this is a comparison, never a
 * proposal, and the panel must say so. Copenhagen's 55 is a statutory exception and is not
 * modelled here, because no Romanian unit is Copenhagen.
 *
 * The statute reads "over 20.000" for the higher floor and "under 20.000" for the lower, so
 * exactly 20,000 falls in neither. Treated as the lower band, which is the reading that does
 * not invent a constraint the text does not impose.
 */
export function danishBandFor(population: number): { min: number; max: number } {
  return population > 20_000 ? { min: 19, max: 31 } : { min: 9, max: 31 };
}

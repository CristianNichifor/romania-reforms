/**
 * How votes become council seats, under Legea 115/2015.
 *
 * Romania does not use D'Hondt. Seats are allocated by an electoral coefficient with a
 * threshold, and the remainder by largest unused votes — which is more proportional at the top
 * than Denmark's D'Hondt, and harsher at the bottom, because a list under the threshold takes
 * nothing at all however close it came.
 *
 * That asymmetry is the whole reason this is worth computing for a merger. Pooling several
 * communes raises the denominator, so a list that cleared 5% in a commune of 2,000 can fall
 * under it in a unit of 20,000 and lose every seat it held. Whether that happens is
 * arithmetic, not opinion, and it is the representation loss small communes actually fear.
 *
 * The rules, from the law:
 *
 * - **Threshold**: 5% of validly expressed votes in the constituency. An alliance of two adds
 *   2%; an alliance of three or more faces 8%.
 * - **Coefficient**: the whole number, no decimals and unrounded, from dividing the total
 *   valid votes for all lists by the number of council seats.
 * - **First pass**: each qualifying list takes as many seats as the coefficient fits into its
 *   votes.
 * - **Second pass**: the seats left over go to the largest *unused* votes, in descending
 *   order, repeating until none remain.
 */

export interface VoteList {
  /** Interned party or alliance index, for the caller to name. */
  party: number;
  votes: number;
  /**
   * Members in an electoral alliance, where it is one. 1 for a single party.
   *
   * The threshold rises with the size of an alliance, so this changes who qualifies.
   */
  allianceSize?: number;
}

export interface SeatAward {
  party: number;
  seats: number;
  votes: number;
  /** True where the list was excluded for falling under its threshold. */
  belowThreshold: boolean;
}

/** The share of valid votes a list must reach, given how many parties stood together. */
export function thresholdFor(allianceSize: number): number {
  if (allianceSize >= 3) return 0.08;
  if (allianceSize === 2) return 0.07;
  return 0.05;
}

/**
 * Seats per list, and who the threshold excluded.
 *
 * `seats` is the council size, which comes from Art. 112 and the unit's population — not from
 * anything in the votes. The two are independent, which is what makes their agreement a test
 * rather than a tautology.
 */
export function allocateSeats(lists: readonly VoteList[], seats: number): SeatAward[] {
  const totalVotes = lists.reduce((sum, l) => sum + Math.max(0, l.votes), 0);

  const awards: SeatAward[] = lists.map((l) => ({
    party: l.party,
    seats: 0,
    votes: Math.max(0, l.votes),
    belowThreshold:
      totalVotes > 0 && Math.max(0, l.votes) < thresholdFor(l.allianceSize ?? 1) * totalVotes,
  }));

  if (seats <= 0 || totalVotes <= 0) return awards;

  const qualifying = awards.filter((a) => !a.belowThreshold && a.votes > 0);
  // Everyone under the threshold is a real outcome, not a reason to relax it: an election
  // where no list clears 5% leaves the seats unfilled here rather than inventing a winner.
  if (qualifying.length === 0) return awards;

  // The law divides the votes for *all* lists, not only the qualifying ones.
  const coefficient = Math.floor(totalVotes / seats);
  if (coefficient <= 0) return awards;

  let awarded = 0;
  for (const a of qualifying) {
    const whole = Math.floor(a.votes / coefficient);
    a.seats = Math.min(whole, seats - awarded);
    awarded += a.seats;
  }

  // Second pass: largest unused votes first, one seat at a time, repeating. Ties break on the
  // larger vote total and then on the interned party index, so the result is deterministic —
  // the law does not say, and a map that reshuffles between runs is not one anybody can cite.
  while (awarded < seats) {
    const ranked = [...qualifying].sort((a, b) => {
      const unusedA = a.votes - a.seats * coefficient;
      const unusedB = b.votes - b.seats * coefficient;
      if (unusedA !== unusedB) return unusedB - unusedA;
      if (a.votes !== b.votes) return b.votes - a.votes;
      return a.party - b.party;
    });
    const next = ranked[0];
    if (!next) break;
    next.seats += 1;
    awarded += 1;
  }

  return awards;
}

/**
 * What merging does to representation.
 *
 * `before` is each member commune's own allocation; `after` is the pooled one. The lists that
 * matter are those holding a seat somewhere today and none in the merged unit — that is the
 * loss, and it is the number this whole exercise exists to produce.
 */
export interface RepresentationShift {
  before: Map<number, number>;
  after: Map<number, number>;
  /** Parties with seats today and none after. */
  losesAllSeats: number[];
  /** Parties excluded by the threshold in the merged unit but not everywhere before. */
  newlyBelowThreshold: number[];
}

export function representationShift(
  perCommune: readonly SeatAward[][],
  merged: readonly SeatAward[],
): RepresentationShift {
  const before = new Map<number, number>();
  const qualifiedSomewhere = new Set<number>();
  for (const commune of perCommune) {
    for (const a of commune) {
      if (a.seats > 0) before.set(a.party, (before.get(a.party) ?? 0) + a.seats);
      if (!a.belowThreshold && a.votes > 0) qualifiedSomewhere.add(a.party);
    }
  }

  const after = new Map<number, number>();
  const belowAfter = new Set<number>();
  for (const a of merged) {
    if (a.seats > 0) after.set(a.party, a.seats);
    if (a.belowThreshold) belowAfter.add(a.party);
  }

  return {
    before,
    after,
    losesAllSeats: [...before.keys()].filter((p) => !after.has(p)).sort((a, b) => a - b),
    newlyBelowThreshold: [...belowAfter]
      .filter((p) => qualifiedSomewhere.has(p))
      .sort((a, b) => a - b),
  };
}

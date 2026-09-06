/**
 * What each proposed court would have to judge, at whatever map the reader is looking at.
 *
 * The reform's 42 courts do not exist, so no source states their caseload and none ever will.
 * What can be done is route the caseload of the courts that do exist through the map the reader
 * has built:
 *
 *     court -> the communes it serves       (arondare-instante, resolved in Python)
 *       -> the consolidated unit each belongs to   (the administrative model, run in the browser)
 *         -> the seat that unit answers to         (arondare.ts, by road distance)
 *
 * The middle two links move when a slider moves, which is why this runs here rather than being
 * precomputed. `incarcatura-noua.json` already answers the same question at the default
 * parameters and would keep answering it after the reader had changed the country underneath.
 *
 * **The population split is the assumption, and it is measured rather than asserted.** A
 * judecătorie's cases are divided among its communes in proportion to population, because how
 * many cases each commune generates is not published. Most of the answer does not rest on it:
 * where every commune of a court lands at the same seat, that seat inherits the whole court
 * whatever the weighting. `cotaInvarianta` is the share of caseload in that position, so a
 * reader can see how much of the result is arithmetic and how much is modelling.
 *
 * Two things are left out rather than estimated. Appeal courts have no published
 * circumscription, so their work cannot be routed at all. Courts the crawl did not finish are
 * excluded and counted, because a court measured at half a percent of its size would drag a
 * seat's median toward whatever those few cases happened to be.
 */

import { blend, emptyPool, type Court, type CourtsFile, type Edges, type Pooled } from './aggregate';
import type { Arondare, Coupled } from './arondare';

export interface CourtCommunes {
  institutie: string;
  grad: string;
  judet: string | null;
  /** Indices into the administrative model's UAT array, not SIRUTA codes. */
  uat: number[];
}

export interface ArondareInstante {
  summary: { uatCount: number };
  instante: CourtCommunes[];
}

export interface ProposedCourt {
  /** Row in `Coupled.meta.courts` — the seat this court would sit at. */
  seat: number;
  nume: string;
  judet: string;
  populatie: number;
  unitati: number;
  pooled: Pooled;
  /** Share of this court's caseload that arrived whole, from courts no seat had to split. */
  cotaInvarianta: number;
}

export interface Proposal {
  courts: ProposedCourt[];
  /** Courts left out because the crawl did not finish them. */
  trunchiate: number;
  /** Courts whose communes reach no seat at all — the Delta, which no road serves. */
  nerutate: number;
  /**
   * Share of the whole caseload that arrived at its seat undivided, across the country.
   *
   * The number that says how much of this rests on the population split.
   *
   * `build_incarcatura.py` reports the same quantity at the default parameters and gets 74,7%
   * where this gets 66,6%. The gap is not a disagreement about the map — per-seat populations
   * match that file exactly, checked at București (2.336.706), Cluj (623.860) and Craiova
   * (676.111) — but about the weight. That one counts CSM's volume of activity over all 175
   * judecătorii; this one counts cases visible on the portal and drops the 41 courts the crawl
   * did not finish, so a different set of courts is being weighed by a different measure of
   * size. Both answer "how much of this is arithmetic rather than modelling", and neither is the
   * other's check.
   */
  cotaInvariantaNationala: number;
}

/**
 * Route every existing court's figures onto the seats of the map in `arondare`.
 *
 * Guards the payload version before using it: the commune list addresses UATs by index, and an
 * administrative payload rebuilt with a different number of units would address the wrong ones
 * silently — every figure still plausible, every one attached to the wrong place.
 */
export function proposedCourts(
  arondare: Arondare,
  coupled: Coupled,
  communes: ArondareInstante,
  courts: CourtsFile,
  edges: Edges,
): Proposal {
  if (communes.summary.uatCount !== coupled.data.uatCount) {
    throw new Error(
      `arondare-instante addresses ${communes.summary.uatCount} UATs, the model has ${coupled.data.uatCount}`,
    );
  }

  const byInstitutie = new Map<string, Court>();
  for (const court of courts.instante) byInstitutie.set(court.institutie, court);

  const pools = new Map<number, Pooled>();
  const whole = new Map<number, number>();
  const total = new Map<number, number>();
  let trunchiate = 0;
  let nerutate = 0;

  for (const entry of communes.instante) {
    const court = byInstitutie.get(entry.institutie);
    if (!court) continue;
    if (court.acoperire.trunchiat) {
      trunchiate += 1;
      continue;
    }

    // Population weights over this court's own communes, and which seat each reaches.
    const shares = new Map<number, number>();
    let weight = 0;
    for (const uat of entry.uat) {
      const people = coupled.data.population[uat] ?? 0;
      const seat = arondare.courtOf[uat] ?? -1;
      if (seat < 0) continue;
      shares.set(seat, (shares.get(seat) ?? 0) + people);
      weight += people;
    }
    if (weight <= 0) {
      nerutate += 1;
      continue;
    }

    // A court whose communes all reach the same seat contributes its whole self, and the
    // population split has no effect on the answer. That is what `cotaInvarianta` counts.
    const undivided = shares.size === 1;
    for (const [seat, people] of shares) {
      const fraction = people / weight;
      let pool = pools.get(seat);
      if (!pool) {
        pool = emptyPool(edges);
        pools.set(seat, pool);
      }
      blend(pool, court, fraction);
      total.set(seat, (total.get(seat) ?? 0) + court.dosare * fraction);
      if (undivided) whole.set(seat, (whole.get(seat) ?? 0) + court.dosare * fraction);
    }
  }

  // Population and unit counts come from the assignment itself rather than being recomputed:
  // the map already decided which consolidated units answer to which seat, and a second walk
  // over the same question is a second chance to answer it differently.
  const people = new Map<number, number>();
  const units = new Map<number, number>();
  for (const unit of arondare.units) {
    if (unit.courtRow === null) continue;
    people.set(unit.courtRow, (people.get(unit.courtRow) ?? 0) + unit.population);
    units.set(unit.courtRow, (units.get(unit.courtRow) ?? 0) + 1);
  }

  const result: ProposedCourt[] = [];
  for (const [seat, pooled] of pools) {
    const meta = coupled.meta.courts[seat];
    if (!meta) continue;
    const dosare = total.get(seat) ?? 0;
    result.push({
      seat,
      nume: meta.name,
      judet: meta.county,
      populatie: people.get(seat) ?? 0,
      unitati: units.get(seat) ?? 0,
      pooled,
      cotaInvarianta: dosare ? (whole.get(seat) ?? 0) / dosare : 0,
    });
  }
  result.sort((a, b) => b.pooled.dosare - a.pooled.dosare);
  const everything = [...total.values()].reduce((sum, value) => sum + value, 0);
  const undividedAll = [...whole.values()].reduce((sum, value) => sum + value, 0);
  return {
    courts: result,
    trunchiate,
    nerutate,
    cotaInvariantaNationala: everything ? undividedAll / everything : 0,
  };
}

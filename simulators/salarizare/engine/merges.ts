/**
 * One job, one card: what it used to be called, and what three systems pay for it.
 *
 * The grid's central claim is that a great many titles describe the same work. The draft
 * already acts on it — 1 031 positions carry an `assimilation.rawTitleCell` holding every
 * former title the sheet merged onto them — but that fact is buried in a cell, and a
 * table of coefficients cannot show it. A merge is not a number; it is a list of names
 * collapsing into one, and it has to be *seen* collapsing.
 *
 * So the unit here is the merge, not the position. Each card names the job, lists the
 * titles it absorbed, and puts the three systems side by side for that same job:
 *
 *     în vigoare (153/2017) → proiectul → propunerea noastră → Danemarca
 *
 * **Why the money and not the coefficient.** A coefficient is only meaningful against its
 * own reference value, and the three regimes do not share one — comparing 2,499 with 1,86
 * is comparing two different rulers. Every figure here is run through `payslip()` at no
 * seniority, so what is compared is lei against lei, produced by the same arithmetic the
 * rest of the simulator uses.
 *
 * **Why some cards are missing a column, and why that is not a gap to be filled.** The old
 * pay is present only where the crosswalk links this position to one under 153/2017 — 227
 * links, not 1 031, because the draft creates posts that did not exist and the mapping it
 * requires under Art. 32 was never published. The Danish figure is present only where the
 * occupation groups reach this position, because Denmark has no grid: what exists is
 * measured pay per occupation, and an occupation is coarser than a position. Both absences
 * are reported as absences. Filling them with a national average would turn "nobody
 * published this" into a number, which is the one thing this repository refuses to do.
 */

import { payslip } from './payslip';
import type { DkOccupation, GroupsDocument, ResolvedGroup } from './occupations';
import { resolveGroups } from './occupations';
import type { Crosswalk, Money, Position, PositionKind, Regime } from './types';

export interface MergeCard {
  code: string;
  name: string;
  family: string;
  chapter?: string;
  kind: PositionKind;
  /** Every former title the draft folded onto this position, the sheet's own spelling. */
  titles: string[];
  /**
   * How many titles collapsed here. The sheet's own count where it published one, the
   * length of the title list otherwise — never a guess, and 1 means no merge happened.
   */
  fanIn: number;
  /** How the merged cell was read, so a bad split can be disputed rather than trusted. */
  parse?: string;
  /** Base pay at no seniority under each system, in that system's own minor units. */
  inForce: Money | null;
  draft: Money | null;
  ours: Money | null;
  /** What the old titles were called before, where the crosswalk links them. */
  wasCalled: string[];
  /** Danish measured pay for the occupation this job belongs to, monthly kroner. */
  dk: { occupation: string; q1: number; median: number; q3: number } | null;
  /** What our proposal did to this position, in lei and as a share. */
  delta: { amount: Money; share: number } | null;
}

export interface MergeInputs {
  /** The ministry draft: the regime whose merges are being shown. */
  draft: Regime;
  /** The same regime with our proposal applied. */
  ours: Regime | null;
  inForce: Regime | null;
  crosswalk: Crosswalk | null;
  groups: GroupsDocument | null;
  danish: DkOccupation[];
}

const titlesOf = (position: Position): string[] =>
  (position.titles ?? []).map((t) => (t.qualifier ? `${t.name}, ${t.qualifier}` : t.name));

/** Base pay at no seniority, or null when the regime does not know this position. */
function baseOf(regime: Regime | null, code: string): Money | null {
  if (!regime) return null;
  if (!regime.positions.some((p) => p.code === code)) return null;
  const slip = payslip({ positionCode: code, seniorityYears: 0 }, regime);
  return slip.base > 0 ? slip.base : null;
}

/**
 * Position code to the occupation group that caught it.
 *
 * A position can match more than one group's rule — the rules are editorial and were not
 * written to partition the grid — so the first match wins and the card names which group
 * it came from. Hiding the choice would make a coarse comparison look exact.
 */
function dkByPosition(
  draft: Regime,
  groups: GroupsDocument,
  danish: DkOccupation[],
): Map<string, ResolvedGroup> {
  const resolved = resolveGroups(draft, groups, danish, {
    roPublicAverage: 1,
    dkPublicMedian: 1,
  });
  const out = new Map<string, ResolvedGroup>();
  for (const group of resolved) {
    for (const position of group.matched) {
      if (!out.has(position.code)) out.set(position.code, group);
    }
  }
  return out;
}

/** Position code to the titles it carried under the law now in force. */
function formerTitles(crosswalk: Crosswalk | null): Map<string, string[]> {
  const out = new Map<string, string[]>();
  if (!crosswalk) return out;
  for (const link of crosswalk.links) {
    for (const target of link.to) {
      const found = out.get(target.positionCode) ?? [];
      for (const source of link.from) {
        const title = source.title ?? source.positionCode;
        if (!found.includes(title)) found.push(title);
      }
      out.set(target.positionCode, found);
    }
  }
  return out;
}

/** Position code to the code it had under 153/2017, for pricing the old job. */
function formerCodes(crosswalk: Crosswalk | null): Map<string, string[]> {
  const out = new Map<string, string[]>();
  if (!crosswalk) return out;
  for (const link of crosswalk.links) {
    for (const target of link.to) {
      const found = out.get(target.positionCode) ?? [];
      for (const source of link.from) {
        if (!found.includes(source.positionCode)) found.push(source.positionCode);
      }
      out.set(target.positionCode, found);
    }
  }
  return out;
}

export function mergeCards(inputs: MergeInputs): MergeCard[] {
  const { draft, ours, inForce, crosswalk, groups, danish } = inputs;
  const dkFor = groups ? dkByPosition(draft, groups, danish) : new Map<string, ResolvedGroup>();
  const titlesBefore = formerTitles(crosswalk);
  const codesBefore = formerCodes(crosswalk);

  return draft.positions.map((position) => {
    const titles = titlesOf(position);
    const group = dkFor.get(position.code);
    const dk = group?.dk
      ? {
          occupation: group.group.label,
          q1: group.dk.q1,
          median: group.dk.median,
          q3: group.dk.q3,
        }
      : null;

    // The cheapest of the old posts that became this one. Cheapest rather than an average:
    // the claim a merge makes is that these were the same job, and the spread between them
    // is the evidence for or against it — an average would hide exactly that.
    const old = (codesBefore.get(position.code) ?? [])
      .map((code) => baseOf(inForce, code))
      .filter((m): m is Money => m !== null);

    const draftBase = baseOf(draft, position.code);
    const oursBase = baseOf(ours, position.code);

    return {
      code: position.code,
      name: position.name,
      family: position.family,
      chapter: position.chapter,
      kind: position.kind,
      titles,
      fanIn: position.assimilation?.fanIn ?? titles.length ?? 1,
      parse: position.assimilation?.parse,
      inForce: old.length ? Math.min(...old) : null,
      draft: draftBase,
      ours: oursBase,
      wasCalled: titlesBefore.get(position.code) ?? [],
      dk,
      delta:
        draftBase !== null && oursBase !== null && draftBase > 0
          ? { amount: oursBase - draftBase, share: (oursBase - draftBase) / draftBase }
          : null,
    };
  });
}

/** The cards a reader is most likely to want first: the biggest merges. */
export function byFanIn(cards: MergeCard[]): MergeCard[] {
  return [...cards].sort((a, b) => b.fanIn - a.fanIn || a.name.localeCompare(b.name, 'ro'));
}

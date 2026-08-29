/**
 * Occupation groups: the Romanian grid regrouped by what the job is, then set beside the
 * Danish figures for the same job.
 *
 * The draft groups positions by employer and legal status — annex, ordonator, category of
 * civil servant. Denmark's statistics group them by occupation, which is also how the
 * labour market and ISCO do it. Comparing the two therefore needs a regrouping, and the
 * regrouping is an editorial act: every group states the rule that selected it and how
 * many positions the rule caught, so a reader can dispute the grouping rather than only
 * the numbers.
 *
 * The two sides are not symmetrical, and the asymmetry is the finding. Romania publishes
 * what the law allows, before supplements. Denmark publishes what people are actually
 * paid, because for these occupations there is no grid — pay is negotiated over a
 * collective-agreement floor. Reporting one as the other would be the easiest lie in this
 * whole project, so both ranges carry what they are.
 */

import { payslip } from './payslip';
import type { Money } from './types';
import type { Regime } from './types';

export interface GroupRule {
  family?: string;
  kind?: string[];
  studyLevel?: string[];
  nameMatches?: string;
  excludeMatches?: string;
}

export interface OccupationGroup {
  id: string;
  sector: string;
  label: string;
  proposedName: string;
  ro: GroupRule;
  dkOccupations: string[];
  basis: string;
  confidence: 'verbatim' | 'derived' | 'assumed';
  disputed?: boolean;
}

export interface GroupsDocument {
  id: string;
  title: string;
  from: string;
  groups: OccupationGroup[];
}

/** One occupation's Danish quartiles, monthly, in kroner. */
export interface DkOccupation {
  occupation: string;
  q1: number;
  median: number;
  q3: number;
  /** Shares of total pay, where published. */
  composition?: {
    basic?: number;
    conditions?: number;
    overtime?: number;
    irregular?: number;
    fringe?: number;
    holiday?: number;
  };
}

export interface ResolvedGroup {
  group: OccupationGroup;
  /** Romanian positions the rule selected. */
  matched: Array<{ code: string; name: string }>;
  /** Lowest base pay in the group, at no seniority. */
  roMin: Money | null;
  /** Highest base pay in the group, at full seniority. */
  roMax: Money | null;
  /**
   * The middle half of the group's own positions, so there is something directly
   * comparable with Denmark's quartiles. The full min-max is kept alongside because the
   * legal extremes are the point of a grid, but comparing a min-max against an
   * interquartile would make Romania look wider than it is by construction.
   */
  roQ1: Money | null;
  roMedian: Money | null;
  roQ3: Money | null;
  /**
   * The same range with the Art. 21(2) ceiling added on top.
   *
   * The ceiling is 20% of the base wage bill per ordonator principal, per funding source —
   * an institutional average, not a personal entitlement — so applying it to one position
   * is an illustration of what the cap implies, not a figure anyone is owed. It is worth
   * showing because the Danish side already includes supplements, and comparing a
   * Romanian base against Danish total pay understates Romania by whatever supplements add.
   */
  roCapped: { q1: Money; q3: Money } | null;
  /** Positions in the group whose published coefficient is a midpoint, not a figure. */
  bandedPositions: number;
  /** Supplements the statute places outside that ceiling, so the reader can see what it omits. */
  exemptSupplements: Array<{ id: string; name: string; rate: number | null; basis: string }>;
  dk: { q1: number; median: number; q3: number } | null;
  /**
   * What Danish pay for this occupation is actually made of. The comparable line is the
   * condition supplement: Denmark pays it where the work genuinely differs — shift work,
   * care, policing — and at essentially zero for desk jobs. Romania's ceiling applies the
   * same 20% to everyone, which is a different design rather than a different number.
   */
  dkComposition: DkOccupation['composition'] | null;
  /** Each side against its own country's public-sector benchmark. */
  roRatio: { min: number; max: number } | null;
  dkRatio: { q1: number; q3: number; median: number } | null;
}

function matches(
  position: { family: string; kind: string; studyLevel?: string; name: string },
  rule: GroupRule,
): boolean {
  if (rule.family && position.family !== rule.family) return false;
  if (rule.kind && !rule.kind.includes(position.kind)) return false;
  if (rule.studyLevel && !rule.studyLevel.includes(position.studyLevel ?? '')) return false;

  // Accents are inconsistent across the source sheets — the same word appears with ș and
  // ş, ț and ţ — so matching folds them away rather than listing every spelling.
  const name = position.name
    .toLowerCase()
    .replace(/[șş]/g, 's')
    .replace(/[țţ]/g, 't')
    .replace(/[ăâ]/g, 'a')
    .replace(/î/g, 'i');
  const fold = (p: string) =>
    p.toLowerCase().replace(/[șş]/g, 's').replace(/[țţ]/g, 't').replace(/[ăâ]/g, 'a').replace(/î/g, 'i');

  if (rule.nameMatches && !new RegExp(fold(rule.nameMatches)).test(name)) return false;
  if (rule.excludeMatches && new RegExp(fold(rule.excludeMatches)).test(name)) return false;
  return true;
}

export function resolveGroups(
  regime: Regime,
  document: GroupsDocument,
  danish: DkOccupation[],
  benchmarks: { roPublicAverage: number; dkPublicMedian: number },
): ResolvedGroup[] {
  const dkByName = new Map(danish.map((d) => [d.occupation, d]));

  return document.groups.map((group) => {
    const matched = regime.positions.filter((p) =>
      matches({ family: p.family, kind: p.kind, studyLevel: p.studyLevel, name: p.name }, group.ro),
    );

    // The range is what the law permits across the group: the cheapest position at no
    // seniority, the dearest at full seniority. Using only the published coefficient
    // would understate the top by up to a quarter, since the gradatii sit on top of it.
    const lows: Money[] = [];
    const highs: Money[] = [];
    let banded = 0;
    for (const position of matched) {
      // Annex II Art. 10 makes the printed coefficient the middle of a ±15% band set per
      // category of health unit. For those positions the published figure is not a salary
      // but a midpoint, so the legal range has to carry the band or it understates both
      // ends for every doctor and nurse in the grid.
      const factor = position.institutionFactor;
      if (factor) banded += 1;
      const atStart = payslip({ positionCode: position.code, seniorityYears: 0 }, regime);
      const atEnd = payslip({ positionCode: position.code, seniorityYears: 40 }, regime);
      for (let i = 0; i < position.variants.length; i += 1) {
        const dims = position.variants[i].dims;
        const start = payslip({ positionCode: position.code, seniorityYears: 0, dims }, regime);
        const end = payslip({ positionCode: position.code, seniorityYears: 40, dims }, regime);
        if (start.base > 0) lows.push(Math.round(start.base * (factor?.min ?? 1)));
        if (end.base > 0) highs.push(Math.round(end.base * (factor?.max ?? 1)));
      }
      if (atStart.base > 0) lows.push(Math.round(atStart.base * (factor?.min ?? 1)));
      if (atEnd.base > 0) highs.push(Math.round(atEnd.base * (factor?.max ?? 1)));
    }

    const roMin = lows.length ? Math.min(...lows) : null;
    const roMax = highs.length ? Math.max(...highs) : null;

    const spread = [...lows, ...highs].sort((a, b) => a - b);
    const at = (f: number) => (spread.length ? spread[Math.floor((spread.length - 1) * f)] : null);
    const roQ1 = at(0.25);
    const roMedian = at(0.5);
    const roQ3 = at(0.75);

    const capPct = (() => {
      const cap = regime.caps.find((c) => c.id === 'cap-sporuri-20' || c.kind === 'shareOfBase');
      if (!cap?.pct) return 0;
      return typeof cap.pct === 'number' ? cap.pct : cap.pct[0].value;
    })();
    const roCapped =
      roQ1 !== null && roQ3 !== null
        ? { q1: Math.round(roQ1 * (1 + capPct)), q3: Math.round(roQ3 * (1 + capPct)) }
        : null;

    const exemptSupplements = regime.supplements
      .filter((s) => s.countsToCap === false || s.countsToCap === 'partial')
      .map((s) => ({
        id: s.id,
        name: s.name,
        rate: s.rate === undefined ? null : typeof s.rate === 'number' ? s.rate : s.rate[0].value,
        basis: s.base,
      }));

    const parts = group.dkOccupations.map((name) => dkByName.get(name)).filter(Boolean) as DkOccupation[];
    const dk = parts.length
      ? {
          q1: Math.min(...parts.map((p) => p.q1)),
          median: parts.reduce((s, p) => s + p.median, 0) / parts.length,
          q3: Math.max(...parts.map((p) => p.q3)),
        }
      : null;

    return {
      group,
      matched: matched.map((p) => ({ code: p.code, name: p.name })),
      roMin,
      roMax,
      roQ1,
      roMedian,
      roQ3,
      roCapped,
      bandedPositions: banded,
      exemptSupplements,
      dk,
      dkComposition: parts.find((p) => p.composition)?.composition ?? null,
      roRatio:
        roMin !== null && roMax !== null && benchmarks.roPublicAverage > 0
          ? {
              min: roMin / 100 / benchmarks.roPublicAverage,
              max: roMax / 100 / benchmarks.roPublicAverage,
            }
          : null,
      dkRatio:
        dk && benchmarks.dkPublicMedian > 0
          ? {
              q1: dk.q1 / benchmarks.dkPublicMedian,
              median: dk.median / benchmarks.dkPublicMedian,
              q3: dk.q3 / benchmarks.dkPublicMedian,
            }
          : null,
    };
  });
}

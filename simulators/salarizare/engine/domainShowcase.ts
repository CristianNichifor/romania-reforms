import { matchesRule } from './occupations';
import type { DkOccupation, GroupsDocument, OccupationGroup } from './occupations';
import { payslip } from './payslip';
import type { Regime } from './types';

export interface DomainBand {
  /** Monthly amount in the side's own currency, major units. */
  q1: number;
  median: number;
  q3: number;
  min: number;
  max: number;
  /** Same amounts divided by that system's own public-sector middle. */
  ratio: { q1: number; median: number; q3: number };
}

export interface DomainSide {
  label: string;
  currency: string;
  basis: 'legal-base' | 'measured-earnings';
  count: number;
  band: DomainBand | null;
  missingReason?: string;
}

export interface DomainRow {
  group: OccupationGroup;
  sides: {
    inForce: DomainSide;
    draft: DomainSide;
    proposal: DomainSide;
    denmark: DomainSide;
  };
}

export interface DomainRegimes {
  inForce: Regime | null;
  draft: Regime;
  proposal: Regime;
}

function at(sorted: number[], fraction: number): number | null {
  if (!sorted.length) return null;
  return sorted[Math.floor((sorted.length - 1) * fraction)];
}

export function medianBase(regime: Regime): number {
  const values: number[] = [];
  for (const position of regime.positions) {
    for (const variant of position.variants) {
      const slip = payslip(
        { positionCode: position.code, seniorityYears: 0, dims: variant.dims },
        regime,
      );
      if (slip.base > 0) values.push(slip.base / 100);
    }
  }
  values.sort((a, b) => a - b);
  return at(values, 0.5) ?? 0;
}

function roSide(
  label: string,
  regime: Regime | null,
  group: OccupationGroup,
  benchmark: number,
): DomainSide {
  if (!regime) {
    return {
      label,
      currency: 'RON',
      basis: 'legal-base',
      count: 0,
      band: null,
      missingReason: 'regimul nu este încărcat',
    };
  }

  const matched = regime.positions.filter((position) =>
    matchesRule(
      {
        family: position.family,
        kind: position.kind,
        studyLevel: position.studyLevel,
        name: position.name,
      },
      group.ro,
    ),
  );

  const lows: number[] = [];
  const highs: number[] = [];
  for (const position of matched) {
    const factor = position.institutionFactor;
    for (const variant of position.variants) {
      const dims = variant.dims;
      const start = payslip({ positionCode: position.code, seniorityYears: 0, dims }, regime);
      const end = payslip({ positionCode: position.code, seniorityYears: 40, dims }, regime);
      if (start.base > 0) lows.push((start.base * (factor?.min ?? 1)) / 100);
      if (end.base > 0) highs.push((end.base * (factor?.max ?? 1)) / 100);
    }
  }

  const spread = [...lows, ...highs].sort((a, b) => a - b);
  const q1 = at(spread, 0.25);
  const median = at(spread, 0.5);
  const q3 = at(spread, 0.75);
  if (q1 === null || median === null || q3 === null || benchmark <= 0) {
    return {
      label,
      currency: regime.currency,
      basis: 'legal-base',
      count: matched.length,
      band: null,
      missingReason: matched.length
        ? 'nu s-a putut calcula un interval pentru posturile găsite'
        : 'niciun post nu se potrivește regulii în acest regim',
    };
  }

  return {
    label,
    currency: regime.currency,
    basis: 'legal-base',
    count: matched.length,
    band: {
      q1,
      median,
      q3,
      min: spread[0],
      max: spread[spread.length - 1],
      ratio: { q1: q1 / benchmark, median: median / benchmark, q3: q3 / benchmark },
    },
  };
}

function dkSide(danish: DkOccupation[], group: OccupationGroup, benchmark: number): DomainSide {
  const byName = new Map(danish.map((entry) => [entry.occupation, entry]));
  const parts = group.dkOccupations.map((name) => byName.get(name)).filter(Boolean) as DkOccupation[];
  if (!parts.length || benchmark <= 0) {
    return {
      label: 'Danemarca',
      currency: 'DKK',
      basis: 'measured-earnings',
      count: 0,
      band: null,
      missingReason: 'nu există comparator danez încărcat pentru grupa aceasta',
    };
  }

  const q1 = Math.min(...parts.map((part) => part.q1));
  const median = parts.reduce((sum, part) => sum + part.median, 0) / parts.length;
  const q3 = Math.max(...parts.map((part) => part.q3));

  return {
    label: 'Danemarca',
    currency: 'DKK',
    basis: 'measured-earnings',
    count: parts.length,
    band: {
      q1,
      median,
      q3,
      min: q1,
      max: q3,
      ratio: { q1: q1 / benchmark, median: median / benchmark, q3: q3 / benchmark },
    },
  };
}

export function resolveDomainShowcase(
  regimes: DomainRegimes,
  groups: GroupsDocument,
  danish: DkOccupation[],
): DomainRow[] {
  const benchmarks = {
    inForce: regimes.inForce ? medianBase(regimes.inForce) : 0,
    draft: medianBase(regimes.draft),
    proposal: medianBase(regimes.proposal),
    denmark: danish.find((entry) => entry.occupation.startsWith('Public employees'))?.median ?? 0,
  };

  return groups.groups.map((group) => ({
    group,
    sides: {
      inForce: roSide('Legea în vigoare', regimes.inForce, group, benchmarks.inForce),
      draft: roSide('Proiectul MMFTSS', regimes.draft, group, benchmarks.draft),
      proposal: roSide('Propunerea', regimes.proposal, group, benchmarks.proposal),
      denmark: dkSide(danish, group, benchmarks.denmark),
    },
  }));
}

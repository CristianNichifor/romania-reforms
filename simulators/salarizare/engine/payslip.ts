/**
 * payslip() and aggregate().
 *
 * All money is integer minor units — bani, øre. Floats are used only for coefficients
 * and rates, where the source data is float garbage and rounding it would defeat the
 * point. No money value is ever produced by float arithmetic that has not been put
 * through `round()`.
 *
 * Pure. No imports beyond the type contract and the structure helpers.
 */

import { resolveSeries } from './structure';
import type {
  Cap,
  Diagnostic,
  IsoDate,
  Ladder,
  Levy,
  Money,
  Position,
  PositionVariant,
  Regime,
  Rounding,
  Supplement,
} from './types';

export interface Person {
  positionCode: string;
  dims?: Readonly<Record<string, string>>;
  seniorityYears: number;
  ladderStepId?: string;
  fte?: number;
  /** Where a variant gives a range, the point chosen inside it (0..1). */
  rangePoint?: number;
  claims?: ReadonlyArray<SupplementClaim>;
  ordonator?: string;
  fundingSource?: string;
}

export interface SupplementClaim {
  supplementId: string;
  /** For 'upTo' supplements: the rate actually granted. Defaults to the ceiling. */
  rate?: number;
  /** For countsToCap 'partial': the share settled from outside title I, hence exempt. */
  externallyFundedShare?: number;
}

export interface SupplementLine {
  id: string;
  name: string;
  requestedRate: number | null;
  allowedRate: number | null;
  amount: Money;
  base: Supplement['base'];
  countsToCap: boolean | 'partial';
  capCountingAmount: Money;
  suppressedBy?: string;
}

export interface CapUtilisation {
  capId: string;
  numerator: Money;
  denominator: Money;
  ratio: number;
  limit: number;
  /**
   * True only when the cap's own scope is 'person'. Article 21(2) is measured per
   * ordonator principal de credite, per funding source, so a single payslip can
   * neither breach it nor comply with it. The UI must label the rest as notional.
   */
  authoritative: boolean;
  scopeNote: string;
}

export interface Payslip {
  regimeId: string;
  asOf: IsoDate | null;
  currency: string;
  /** Everything in this payslip is denominated per this period. */
  period: 'month' | 'year';

  base: Money;
  seniority: {
    stepId: string | null;
    factor: number;
    /** Difference between the base at this step and the base at step 0. */
    amount: Money;
    bakedIn: boolean;
  };
  supplements: SupplementLine[];
  gross: Money;
  employerCost: Money;
  /** null when the regime has no provenanced tax schedule. Denmark is null. */
  net: Money | null;
  pensionSplit: { employee: Money; employer: Money; total: Money } | null;
  capUtilisation: CapUtilisation[];
  diagnostics: Diagnostic[];
}

// ------------------------------------------------------------------- rounding

export function round(minor: number, rounding: Rounding): Money {
  const { step, mode } = rounding;
  if (mode === 'none' || step <= 1) return Math.round(minor);
  const q = minor / step;
  switch (mode) {
    case 'ceil':
      return Math.ceil(q - 1e-9) * step;
    case 'floor':
      return Math.floor(q + 1e-9) * step;
    case 'halfEven': {
      const f = Math.floor(q);
      const diff = q - f;
      if (Math.abs(diff - 0.5) > 1e-9) return Math.round(q) * step;
      return (f % 2 === 0 ? f : f + 1) * step;
    }
    default:
      return Math.floor(q + 0.5 + 1e-9) * step;
  }
}

// -------------------------------------------------------------------- helpers

function note(
  code: string,
  severity: Diagnostic['severity'],
  message: string,
  affects: Diagnostic['affects'],
): Diagnostic {
  return { code, severity, message, affects };
}

function variantFor(position: Position, dims: Record<string, string> | undefined) {
  if (!dims || Object.keys(dims).length === 0) return position.variants[0];
  const exact = position.variants.find((v) =>
    Object.entries(dims).every(([k, val]) => v.dims?.[k] === val),
  );
  return exact ?? position.variants[0];
}

function variantValue(variant: PositionVariant, asOf: IsoDate | undefined, rangePoint: number) {
  if (variant.value !== undefined) return resolveSeries(variant.value, asOf);
  if (variant.range) {
    const lo = resolveSeries(variant.range.min, asOf);
    const hi = resolveSeries(variant.range.max, asOf);
    return lo + (hi - lo) * Math.min(Math.max(rangePoint, 0), 1);
  }
  return 0;
}

/** The step a person's seniority lands on, following the position's own path. */
function stepFor(ladder: Ladder, position: Position, person: Person) {
  const path = position.ladderPath
    ? position.ladderPath.map((id) => ladder.steps.find((s) => s.id === id)).filter(Boolean)
    : ladder.steps;
  const steps = path as Ladder['steps'];
  if (person.ladderStepId) {
    const named = steps.findIndex((s) => s.id === person.ladderStepId);
    if (named >= 0) return { index: named, steps };
  }
  let index = 0;
  for (let i = 0; i < steps.length; i += 1) {
    const from = steps[i].fromYears ?? 0;
    if (person.seniorityYears >= from) index = i;
  }
  return { index, steps };
}

// -------------------------------------------------------------------- payslip

export function payslip(person: Person, regime: Regime, opts?: { asOf?: IsoDate }): Payslip {
  const asOf = opts?.asOf ?? regime.effectiveFrom;
  const diagnostics: Diagnostic[] = [];
  const position = regime.positions.find((p) => p.code === person.positionCode);

  const currency = regime.currency;
  const period = regime.reference.period;
  const empty: Payslip = {
    regimeId: regime.id,
    asOf: asOf ?? null,
    currency,
    period,
    base: 0,
    seniority: { stepId: null, factor: 1, amount: 0, bakedIn: false },
    supplements: [],
    gross: 0,
    employerCost: 0,
    net: null,
    pensionSplit: null,
    capUtilisation: [],
    diagnostics,
  };

  if (!position) {
    diagnostics.push(
      note('position-not-found', 'blocking', `Nicio functie cu codul ${person.positionCode}.`, 'base'),
    );
    return empty;
  }

  const refAmount = resolveSeries(regime.reference.amount, asOf);
  const refFactor = resolveSeries(regime.reference.factor, asOf);
  const unit = refAmount * refFactor;
  const rounding = regime.reference.rounding;
  const fte = person.fte ?? 1;

  const variant = variantFor(position, person.dims);
  if (person.dims && variant !== position.variants.find((v) => v.dims && person.dims &&
      Object.entries(person.dims).every(([k, val]) => v.dims?.[k] === val))) {
    diagnostics.push(
      note('variant-fallback', 'material',
        'Nu exista o varianta pentru dimensiunile cerute; s-a folosit prima varianta a functiei.',
        'base'),
    );
  }
  if (variant.range) {
    diagnostics.push(
      note('range-position', 'material',
        'Sursa da un interval, nu un punct. Cuantumul depinde de o decizie a conducatorului institutiei, nu de lege.',
        'base'),
    );
  }

  let value = variantValue(variant, asOf, person.rangePoint ?? 0);
  if (variant.modifier) {
    value *= 1 + resolveSeries(variant.modifier.pct, asOf);
    diagnostics.push(note('coefficient-modifier', 'note', variant.modifier.reason, 'base'));
  }

  const baseAtStepZero = round(value * unit * 100 * fte, rounding);

  // --- seniority
  const ladder = position.ladder ? regime.ladders[position.ladder] : undefined;
  const bakedIn = Boolean(ladder?.bakedInto?.includes(position.kind));
  let base = baseAtStepZero;
  let stepId: string | null = null;
  let factor = 1;

  if (!ladder) {
    if (position.ladder === null) {
      diagnostics.push(
        note('no-ladder', 'material',
          'Functia nu foloseste gradatiile: anexa publica un coeficient pe transa de vechime, deci vechimea e deja in coeficient.',
          'seniority'),
      );
    }
  } else if (bakedIn) {
    diagnostics.push(
      note('seniority-baked-in', 'note',
        'Gradatia maxima este deja inclusa in coeficientul publicat pentru aceasta categorie, deci nu se mai aplica.',
        'seniority'),
    );
  } else {
    const { index, steps } = stepFor(ladder, position, person);
    stepId = steps[index]?.id ?? null;
    if (ladder.kind === 'compoundingUplift') {
      // Art. 13(3): each step raises "salariul de baza avut", and Art. 10(4) rounds a
      // salariu de baza to whole lei. Read together that means rounding at every step.
      // The law does not say so outright, so the choice is declared rather than hidden.
      let running = baseAtStepZero;
      for (let i = 1; i <= index; i += 1) {
        const pct = steps[i].pct ? resolveSeries(steps[i].pct!, asOf) : 0;
        running = round(running * (1 + pct), rounding);
      }
      base = running;
      factor = baseAtStepZero > 0 ? base / baseAtStepZero : 1;
      if (index > 0) {
        diagnostics.push(
          note('rounding-per-step', 'note',
            'Gradatiile se aplica succesiv, cu rotunjire la fiecare treapta. Legea nu precizeaza daca rotunjirea se face pe treapta sau o singura data la final.',
            'seniority'),
        );
      }
    } else {
      const stepValue = steps[index]?.value;
      if (stepValue !== undefined) {
        base = round(resolveSeries(stepValue, asOf) * unit * 100 * fte, rounding);
        factor = baseAtStepZero > 0 ? base / baseAtStepZero : 1;
      }
    }
  }

  // --- supplements
  const claims = person.claims ?? [];
  const byId = new Map(regime.supplements.map((s) => [s.id, s]));
  const claimed = new Set(claims.map((c) => c.supplementId));
  const lines: SupplementLine[] = [];

  for (const claim of claims) {
    const supplement = byId.get(claim.supplementId);
    if (!supplement) {
      diagnostics.push(
        note('supplement-not-found', 'material', `Sporul ${claim.supplementId} nu exista in acest regim.`, 'supplements'),
      );
      continue;
    }

    // Mutually exclusive supplements: the three-shift 15% replaces the 25% night rate.
    const blocker = regime.supplements.find(
      (s) => claimed.has(s.id) && s.id !== supplement.id && s.excludes?.includes(supplement.id),
    );

    const ceiling = supplement.rate !== undefined ? resolveSeries(supplement.rate, asOf) : null;
    const requested = claim.rate ?? ceiling;
    const allowed = ceiling !== null && requested !== null ? Math.min(requested, ceiling) : requested;
    if (ceiling !== null && requested !== null && requested > ceiling) {
      diagnostics.push(
        note('supplement-over-ceiling', 'material',
          `${supplement.name}: s-a cerut ${(requested * 100).toFixed(1)}%, plafonul legal este ${(ceiling * 100).toFixed(1)}%.`,
          'supplements'),
      );
    }

    let amount = 0;
    if (!blocker) {
      switch (supplement.base) {
        case 'baseSalary':
          amount = round(base * (allowed ?? 0), supplement.rounding ?? rounding);
          break;
        case 'referenceValue':
          amount = round(unit * 100 * (allowed ?? 0) * fte, supplement.rounding ?? rounding);
          break;
        case 'absolute':
          amount = round(
            (supplement.amount !== undefined ? resolveSeries(supplement.amount, asOf) : 0) * unit * 100 * fte,
            supplement.rounding ?? rounding,
          );
          break;
        default:
          diagnostics.push(
            note('supplement-base-unsupported', 'material',
              `${supplement.name} se calculeaza la "${supplement.base}", care nu intra intr-un stat de plata lunar.`,
              'supplements'),
          );
      }
      if (supplement.mode === 'upTo') {
        diagnostics.push(
          note('supplement-discretionary', 'material',
            `${supplement.name} este un plafon ("pana la"), nu un drept. Cuantumul efectiv il stabileste ordonatorul.`,
            'supplements'),
        );
      }
    }

    let capCounting = 0;
    if (supplement.countsToCap === true) capCounting = amount;
    else if (supplement.countsToCap === 'partial') {
      const exemptShare = claim.externallyFundedShare ?? 0;
      capCounting = round(amount * (1 - Math.min(Math.max(exemptShare, 0), 1)), rounding);
      diagnostics.push(
        note('cap-partial', 'material',
          `${supplement.name}: doar partea cofinantata din titlul I intra in plafonul de la Art. 21. Aici s-a folosit o cota exceptata de ${(exemptShare * 100).toFixed(0)}%.`,
          'capUtilisation'),
      );
    }

    lines.push({
      id: supplement.id,
      name: supplement.name,
      requestedRate: requested,
      allowedRate: allowed,
      amount,
      base: supplement.base,
      countsToCap: supplement.countsToCap,
      capCountingAmount: capCounting,
      suppressedBy: blocker?.id,
    });
  }

  const supplementTotal = lines.reduce((sum, l) => sum + l.amount, 0);

  // --- levies
  const levies = [...regime.levies].sort((a, b) => a.order - b.order);
  const amounts = new Map<string, Money>();
  let inGrossTotal = 0;
  let pension: Payslip['pensionSplit'] = null;

  const baseFor = (levy: Levy, gross: number): number => {
    switch (levy.base) {
      case 'baseSalary':
        return base;
      case 'netSalary':
        return base + supplementTotal;
      case 'grossLessDeductions':
        return gross - (levy.deducts ?? []).reduce((s, id) => s + (amounts.get(id) ?? 0), 0);
      default:
        return gross;
    }
  };

  // First pass: levies that are added into gross rather than taken out of it.
  for (const levy of levies.filter((l) => l.inGross)) {
    const rate = levy.rate !== undefined ? resolveSeries(levy.rate, asOf) : 0;
    const amount = round(baseFor(levy, base + supplementTotal) * rate, rounding);
    amounts.set(levy.id, amount);
    inGrossTotal += amount;
    if (levy.kind === 'pension') {
      const split = levy.split ?? { employee: 0, employer: 1 };
      pension = {
        total: amount,
        employee: round(amount * split.employee, rounding),
        employer: round(amount * split.employer, rounding),
      };
    }
  }

  const gross = base + supplementTotal + inGrossTotal;

  for (const levy of levies.filter((l) => !l.inGross)) {
    const rate = levy.rate !== undefined ? resolveSeries(levy.rate, asOf) : 0;
    amounts.set(levy.id, round(baseFor(levy, gross) * rate, rounding));
  }

  const employerOnly = levies
    .filter((l) => !l.inGross && l.payer === 'employer')
    .reduce((sum, l) => sum + (amounts.get(l.id) ?? 0), 0);
  const employeeOnly = levies
    .filter((l) => !l.inGross && l.payer === 'employee')
    .reduce((sum, l) => sum + (amounts.get(l.id) ?? 0), 0);

  const hasIncomeTax = levies.some((l) => l.kind === 'incomeTax');
  let net: Money | null = null;
  if (hasIncomeTax) {
    net = gross - employeeOnly;
  } else {
    diagnostics.push(
      note('no-tax-schedule', 'blocking',
        'Regimul nu contine un barem de impozitare provenit dintr-o sursa citabila, deci venitul net nu se calculeaza. Nu este zero: lipseste.',
        'net'),
    );
  }

  // --- caps
  const capUtilisation: CapUtilisation[] = [];
  for (const cap of regime.caps) {
    if (cap.kind !== 'shareOfBase' || cap.scope.period !== 'month') continue;
    const numerator = lines
      .filter((l) => !cap.numerator?.exclude?.includes(l.id))
      .reduce((sum, l) => sum + l.capCountingAmount, 0);
    const limit = cap.pct !== undefined ? resolveSeries(cap.pct, asOf) : 0;
    const authoritative = cap.scope.level === 'person';
    capUtilisation.push({
      capId: cap.id,
      numerator,
      denominator: base,
      ratio: base > 0 ? numerator / base : 0,
      limit,
      authoritative,
      scopeNote: authoritative
        ? 'Plafon per persoana.'
        : `Plafonul se masoara pe ${cap.scope.level}${cap.scope.partitionBy?.length ? ` si pe ${cap.scope.partitionBy.join(', ')}` : ''}. Cifra de aici este notionala: arata cat ar fi raportul daca toata lumea din institutie ar avea acest profil.`,
    });
    if (!authoritative) {
      diagnostics.push(
        note('cap-not-per-person', 'material',
          `${cap.label ?? cap.id}: un stat de plata individual nu poate incalca si nici respecta acest plafon. Cifra reala apare doar in modul agregat.`,
          'capUtilisation'),
      );
    }
  }

  return {
    regimeId: regime.id,
    asOf: asOf ?? null,
    currency,
    period,
    base,
    seniority: { stepId, factor, amount: base - baseAtStepZero, bakedIn },
    supplements: lines,
    gross,
    employerCost: gross + employerOnly,
    net,
    pensionSplit: pension,
    capUtilisation,
    diagnostics,
  };
}

// ------------------------------------------------------------------ aggregate

export interface HeadcountRow {
  positionCode: string;
  dims?: Readonly<Record<string, string>>;
  family?: string;
  ordonator: string;
  fundingSource?: string;
  /** Filled posts. Romania publishes no per-person microdata; this is the unit. */
  filledPosts: number;
  /** Share of those posts on each ladder step. Absent means unknown. */
  senioritySplit?: Readonly<Record<string, number>>;
}

export interface Headcount {
  id: string;
  asOf: IsoDate;
  rows: ReadonlyArray<HeadcountRow>;
}

export interface AggregateBucket {
  key: string;
  filledPosts: number;
  baseBill: Money;
  supplementBill: Money;
  grossBill: Money;
  employerCostBill: Money;
}

export interface Aggregate {
  regimeId: string;
  headcountId: string;
  currency: string;
  period: 'month' | 'year';
  total: AggregateBucket;
  byFamily: AggregateBucket[];
  byOrdonator: AggregateBucket[];
  /** Here the caps are real: 'ordonatorPrincipal' scope is computable. */
  capUtilisation: Array<CapUtilisation & { bucketKey: string }>;
  diagnostics: Diagnostic[];
}

function emptyBucket(key: string): AggregateBucket {
  return { key, filledPosts: 0, baseBill: 0, supplementBill: 0, grossBill: 0, employerCostBill: 0 };
}

function addTo(bucket: AggregateBucket, slip: Payslip, posts: number) {
  const supplements = slip.supplements.reduce((s, l) => s + l.amount, 0);
  bucket.filledPosts += posts;
  bucket.baseBill += slip.base * posts;
  bucket.supplementBill += supplements * posts;
  bucket.grossBill += slip.gross * posts;
  bucket.employerCostBill += slip.employerCost * posts;
}

export function aggregate(
  headcount: Headcount,
  regime: Regime,
  opts?: { asOf?: IsoDate },
): Aggregate {
  const diagnostics: Diagnostic[] = [
    note('filled-posts-only', 'blocking',
      'Agregarea ruleaza pe posturi ocupate, nu pe persoane: Romania nu publica date individuale de salarizare. Fiecare post primeste profilul mediu declarat, nu unul real.',
      'aggregate'),
  ];

  const total = emptyBucket('total');
  const families = new Map<string, AggregateBucket>();
  const ordonatori = new Map<string, AggregateBucket>();
  // Cap numerators and denominators accumulate per ordonator, which is the scope the
  // statute actually names.
  const capAcc = new Map<string, { numerator: number; denominator: number }>();

  for (const row of headcount.rows) {
    const position = regime.positions.find((p) => p.code === row.positionCode);
    if (!position) {
      diagnostics.push(
        note('headcount-position-missing', 'material',
          `Codul ${row.positionCode} din statul de functii nu exista in acest regim; cele ${row.filledPosts} posturi au fost ignorate.`,
          'aggregate'),
      );
      continue;
    }

    // Without a seniority distribution every post would sit at step 0 and understate
    // the bill. Say so rather than quietly assuming it.
    const split = row.senioritySplit ?? { __unknown: 1 };
    if (!row.senioritySplit) {
      diagnostics.push(
        note('seniority-unknown', 'material',
          `${row.positionCode}: nu se cunoaste distributia pe gradatii, deci toate posturile sunt calculate la gradatia 0. Factura reala este mai mare.`,
          'aggregate'),
      );
    }

    for (const [stepId, share] of Object.entries(split)) {
      const posts = row.filledPosts * share;
      if (posts <= 0) continue;
      const slip = payslip(
        {
          positionCode: row.positionCode,
          dims: row.dims,
          seniorityYears: 0,
          ladderStepId: stepId === '__unknown' ? undefined : stepId,
          ordonator: row.ordonator,
          fundingSource: row.fundingSource,
        },
        regime,
        opts,
      );

      const family = row.family ?? position.family;
      if (!families.has(family)) families.set(family, emptyBucket(family));
      if (!ordonatori.has(row.ordonator)) ordonatori.set(row.ordonator, emptyBucket(row.ordonator));
      addTo(total, slip, posts);
      addTo(families.get(family)!, slip, posts);
      addTo(ordonatori.get(row.ordonator)!, slip, posts);

      const key = row.fundingSource ? `${row.ordonator}|${row.fundingSource}` : row.ordonator;
      const acc = capAcc.get(key) ?? { numerator: 0, denominator: 0 };
      acc.numerator += slip.supplements.reduce((s, l) => s + l.capCountingAmount, 0) * posts;
      acc.denominator += slip.base * posts;
      capAcc.set(key, acc);
    }
  }

  const asOf = opts?.asOf ?? regime.effectiveFrom;
  const capUtilisation: Aggregate['capUtilisation'] = [];
  for (const cap of regime.caps) {
    if (cap.kind !== 'shareOfBase' || cap.scope.level !== 'ordonatorPrincipal') continue;
    const limit = cap.pct !== undefined ? resolveSeries(cap.pct, asOf) : 0;
    for (const [key, acc] of capAcc) {
      capUtilisation.push({
        bucketKey: key,
        capId: cap.id,
        numerator: acc.numerator,
        denominator: acc.denominator,
        ratio: acc.denominator > 0 ? acc.numerator / acc.denominator : 0,
        limit,
        authoritative: true,
        scopeNote: `Plafon pe ordonator principal${cap.scope.partitionBy?.includes('fundingSource') ? ' si sursa de finantare' : ''} — nivelul la care legea il masoara.`,
      });
    }
  }

  return {
    regimeId: regime.id,
    headcountId: headcount.id,
    currency: regime.currency,
    period: regime.reference.period,
    total,
    byFamily: [...families.values()].sort((a, b) => b.grossBill - a.grossBill),
    byOrdonator: [...ordonatori.values()].sort((a, b) => b.grossBill - a.grossBill),
    capUtilisation,
    diagnostics,
  };
}

/**
 * Engine contract. Signatures only - no implementation, no dependencies.
 *
 * Rules this file commits to:
 *  - All money is integer minor units (bani, oere). No floats in money arithmetic.
 *  - Coefficients stay float, because the source data is float garbage and hiding
 *    that would defeat view 2.
 *  - Every function is pure. Same (input, asOf) -> same output, always.
 *  - Nothing here knows the word "Romania" or "Denmark".
 */

// ---------------------------------------------------------------- primitives

/** Integer minor units. 1234 = 12.34 RON. */
export type Money = number;

/** ISO date, YYYY-MM-DD. Every read of a ValueSeries is resolved against one. */
export type IsoDate = string;

export type ValueSeries = number | ReadonlyArray<{ from: IsoDate; value: number; provenance?: Provenance }>;

export interface Provenance {
  source: string;
  locator: string;
  confidence: 'verbatim' | 'derived' | 'assumed';
  note?: string;
}

/**
 * The fields a caveat can attach to. Shared by engine diagnostics and by the
 * `limitations` a regime document carries, so the two use one vocabulary and the UI can
 * render either beside the number it affects. Mirrors the enum in regime.schema.json.
 */
export type OutputField =
  | 'base'
  | 'seniority'
  | 'supplements'
  | 'gross'
  | 'net'
  | 'employerCost'
  | 'pensionSplit'
  | 'capUtilisation'
  | 'aggregate'
  | 'structure'
  | 'regime';

/** Anything the engine wants the UI to say out loud next to a number. */
export interface Diagnostic {
  code: string;
  severity: 'blocking' | 'material' | 'note';
  message: string;
  /** Which output field the caveat is attached to, so the UI can render it in place. */
  affects: OutputField;
  provenance?: Provenance;
}

/** A number the engine computed, together with why you may not trust it. */
export interface Traced<T> {
  value: T;
  provenance: Provenance[];
  diagnostics: Diagnostic[];
}

// ---------------------------------------------------------------- the regime

// Mirrors schema/regime.schema.json exactly. Generated from it at build time;
// hand-written here only to show the shape.
export interface Regime {
  id: string;
  name: string;
  jurisdiction: string;
  status: 'in-force' | 'draft' | 'proposal' | 'comparator';
  effectiveFrom?: IsoDate;
  currency: string;
  minorUnits: number;
  provenance: Provenance;

  reference: Reference;
  grades: ReadonlyArray<Grade>;
  ladders: Readonly<Record<string, Ladder>>;
  positions: ReadonlyArray<Position>;
  supplements: ReadonlyArray<Supplement>;
  caps: ReadonlyArray<Cap>;
  levies: ReadonlyArray<Levy>;
  limitations: ReadonlyArray<Limitation>;
}

export interface Reference {
  amount: ValueSeries;
  factor: ValueSeries;
  baseDate: IsoDate;
  unit: 'coefficient' | 'absolute';
  /** The period a position value resolves to. RO coefficients are monthly; the Danish
   *  basic amounts are annual. Never add across a period boundary. */
  period: 'month' | 'year';
  rounding: Rounding;
  growthCapId?: string;
  provenance: Provenance;
}

export interface Rounding {
  /** In minor units. 100 = whole currency unit. */
  step: number;
  mode: 'ceil' | 'floor' | 'halfUp' | 'halfEven' | 'none';
  provenance?: Provenance;
}

export interface Grade {
  id: string;
  label?: string;
  min: ValueSeries;
  max: ValueSeries;
  description?: string;
  provenance: Provenance;
}

export type PositionKind = 'execution' | 'management' | 'dignitary' | 'uniformed' | 'academic';

export interface Ladder {
  id: string;
  label?: string;
  kind: 'compoundingUplift' | 'absoluteSteps';
  /** Position kinds whose published value already contains the top step. */
  bakedInto?: ReadonlyArray<PositionKind>;
  steps: ReadonlyArray<LadderStep>;
  provenance: Provenance;
}

export interface LadderStep {
  id: string;
  label?: string;
  fromYears?: number;
  toYears?: number | null;
  /** compoundingUplift: 0.075 = +7.5% on the running salary. */
  pct?: ValueSeries;
  /** absoluteSteps: a position value in the same unit as Position variants. */
  value?: ValueSeries;
  provenance: Provenance;
}

export interface PositionTitle {
  name: string;
  canonical?: boolean;
  /** Trailing qualifier that applies to every title in the row. */
  qualifier?: string;
  note?: string;
}

export interface Assimilation {
  /** The source cell verbatim. Never regenerated from titles. */
  rawTitleCell: string;
  parse: 'single' | 'semicolon' | 'comma' | 'slash' | 'mixed' | 'needsReview';
  fanIn?: number;
  reviewedBy?: string;
  provenance?: Provenance;
}

export interface Position {
  code: string;
  name: string;
  /** Every former title the source merged onto this one position. */
  titles?: ReadonlyArray<PositionTitle>;
  assimilation?: Assimilation;
  family: string;
  chapter?: string;
  kind: PositionKind;
  studyLevel?: string;
  ordonator?: string;
  dims?: ReadonlyArray<string>;
  ladder?: string | null;
  /** Ordered step ids, repeats allowed. Omit to walk the ladder's own order. */
  ladderPath?: ReadonlyArray<string>;
  variants: ReadonlyArray<PositionVariant>;
  /**
   * Pay that varies with the kind of institution rather than with the job. Expressed as
   * one multiplier on one position, instead of several positions sharing a title.
   */
  institutionFactor?: { min: number; max: number; reason: string };
  /**
   * Codes this position absorbed when a proposal merged names that described the same
   * job. Kept so a merged row can still be traced back to every cell it came from.
   */
  mergedFrom?: ReadonlyArray<string>;
  provenance: Provenance;
}

export interface PositionVariant {
  dims?: Readonly<Record<string, string>>;
  value?: ValueSeries;
  range?: { min: ValueSeries; max: ValueSeries };
  gradeId?: string;
  modifier?: { pct: ValueSeries; reason: string };
  provenance: Provenance;
}

export interface Supplement {
  id: string;
  name: string;
  mode: 'fixed' | 'upTo' | 'range';
  rate?: ValueSeries;
  rateMin?: ValueSeries;
  amount?: ValueSeries;
  base: 'baseSalary' | 'referenceValue' | 'hourlyRate' | 'gross' | 'absolute';
  countsToCap: boolean | 'partial';
  capId?: string;
  capSplit?: { countsWhen: string; provenance?: Provenance };
  /** Overrides reference.rounding for this supplement. */
  rounding?: Rounding;
  /** A supplement may escalate along its own seniority ladder. */
  ladder?: string;
  /** Per-component levy rates, e.g. a different pension rate on this supplement. */
  levyOverrides?: ReadonlyArray<{ levyId: string; rate: ValueSeries; provenance?: Provenance }>;
  excludes?: ReadonlyArray<string>;
  requires?: ReadonlyArray<string>;
  eligibility?: {
    families?: ReadonlyArray<string>;
    positionKinds?: ReadonlyArray<PositionKind>;
    maxStaffShare?: ValueSeries;
    condition?: string;
  };
  provenance: Provenance;
}

export interface Cap {
  id: string;
  label?: string;
  kind: 'shareOfBase' | 'shareOfHeadcount' | 'growth' | 'shareOfGdp';
  pct?: ValueSeries;
  scope: {
    level: 'person' | 'institution' | 'ordonatorPrincipal' | 'system';
    partitionBy?: ReadonlyArray<'fundingSource' | 'family' | 'positionKind'>;
    period: 'month' | 'year';
  };
  numerator?: { include?: ReadonlyArray<string>; exclude?: ReadonlyArray<string> };
  denominator?: { include?: ReadonlyArray<string> };
  /** The external fiscal series this cap is measured against. */
  boundTo?: {
    dataset: string;
    seriesId: string;
    baselinePeriod?: string;
    targetPeriod?: string;
    deltaPp?: number;
    provenance?: Provenance;
  };
  penalty?: string;
  provenance: Provenance;
}

export interface Levy {
  id: string;
  label?: string;
  kind: 'socialInsurance' | 'health' | 'incomeTax' | 'employerContribution' | 'pension' | 'other';
  payer: 'employee' | 'employer' | 'split';
  split?: { employee: number; employer: number };
  rate?: ValueSeries;
  bands?: ReadonlyArray<{ upTo: number | null; rate: ValueSeries }>;
  base: 'gross' | 'grossLessDeductions' | 'baseSalary' | 'netSalary' | 'taxable';
  deducts?: ReadonlyArray<string>;
  order: number;
  inGross?: boolean;
  provenance: Provenance;
}

export interface Limitation {
  id: string;
  text: string;
  affects: ReadonlyArray<OutputField>;
  severity?: 'blocking' | 'material' | 'note';
}

// ---------------------------------------------------------------- the person

/**
 * A scenario subject. Deliberately regime-agnostic: it says what is true about
 * a person, not what any one law calls it. The same Person is priced under
 * every regime in a diff.
 */
export interface Person {
  positionCode: string;
  /** Picks the variant. { gradProfesional: 'superior' }, { institutionLevel: 'II' }. */
  dims?: Readonly<Record<string, string>>;
  /** Total years of work seniority. Resolves to a ladder step. */
  seniorityYears: number;
  /** Overrides the seniority lookup when a scenario wants a specific rung. */
  ladderStepId?: string;
  fte?: number;
  /** Where a variant gives a range, the point chosen inside it (0..1). */
  rangePoint?: number;
  claims: ReadonlyArray<SupplementClaim>;
  ordonator?: string;
  fundingSource?: string;
}

export interface SupplementClaim {
  supplementId: string;
  /** For 'upTo' supplements: the rate actually granted. Defaults to the ceiling. */
  rate?: number;
  /** For countsToCap = 'partial': share funded from outside title I, hence exempt. */
  externallyFundedShare?: number;
  hours?: number;
}

// ---------------------------------------------------------------- the outputs

export interface SupplementLine {
  id: string;
  name: string;
  /** What the claim asked for. */
  requestedRate: number;
  /** What the regime's own ceiling allows. */
  allowedRate: number;
  amount: Money;
  base: Supplement['base'];
  countsToCap: boolean | 'partial';
  /** The part of `amount` that enters the cap numerator. */
  capCountingAmount: Money;
  suppressedBy?: string;
  provenance: Provenance;
}

export interface CapUtilisation {
  capId: string;
  numerator: Money;
  denominator: Money;
  ratio: number;
  limit: number;
  /**
   * true only when the cap's own scope is 'person'. For Art. 21(2) this is
   * always false and the UI must label the ratio as notional: one payslip
   * cannot breach a cap that is measured per ordonator principal.
   */
  authoritative: boolean;
  scopeNote: string;
}

export interface Payslip {
  regimeId: string;
  asOf: IsoDate;
  currency: string;

  base: Money;
  seniority: {
    stepId: string | null;
    /** Cumulative factor for compoundingUplift ladders; 1 otherwise. */
    factor: number;
    /** Difference between base at this step and base at step 0. */
    amount: Money;
    bakedIn: boolean;
  };
  supplements: ReadonlyArray<SupplementLine>;
  gross: Money;
  employerCost: Money;
  /** null when the regime has no provenanced tax schedule. DK is null today. */
  net: Money | null;
  pensionSplit: { employee: Money; employer: Money; total: Money } | null;
  capUtilisation: ReadonlyArray<CapUtilisation>;

  diagnostics: ReadonlyArray<Diagnostic>;
  provenance: ReadonlyArray<Provenance>;
}

export interface HeadcountRow {
  positionCode: string;
  dims?: Readonly<Record<string, string>>;
  family: string;
  ordonator: string;
  fundingSource?: string;
  /** Filled posts. Romania publishes no per-person microdata; this is the unit. */
  filledPosts: number;
  /** Distribution across ladder steps, if known. Absent = the assumption below fires. */
  senioritySplit?: Readonly<Record<string, number>>;
  provenance: Provenance;
}

export interface Headcount {
  id: string;
  asOf: IsoDate;
  rows: ReadonlyArray<HeadcountRow>;
  provenance: Provenance;
  limitations: ReadonlyArray<Limitation>;
}

export interface AggregateBucket {
  key: string;
  filledPosts: number;
  baseBill: Money;
  seniorityBill: Money;
  supplementBill: Money;
  grossBill: Money;
  employerCostBill: Money;
}

export interface Aggregate {
  regimeId: string;
  headcountId: string;
  asOf: IsoDate;
  currency: string;
  total: AggregateBucket;
  byFamily: ReadonlyArray<AggregateBucket>;
  byOrdonator: ReadonlyArray<AggregateBucket>;
  /** Here the caps are real: scope 'ordonatorPrincipal' is computable. */
  capUtilisation: ReadonlyArray<CapUtilisation & { bucketKey: string }>;
  diagnostics: ReadonlyArray<Diagnostic>;
}

// ------------------------------------------------------- structural metrics


// ------------------------------------------------------------- crosswalks

export type CrosswalkRelation = 'identity' | 'rename' | 'merge' | 'split' | 'regrade' | 'new' | 'abolished';

export interface CrosswalkEndpoint {
  positionCode: string;
  title?: string;
  dims?: Readonly<Record<string, string>>;
  /** Share of filled posts on this endpoint. Absent means unknown. */
  weight?: number;
}

export interface CrosswalkLink {
  id?: string;
  relation: CrosswalkRelation;
  from: ReadonlyArray<CrosswalkEndpoint>;
  to: ReadonlyArray<CrosswalkEndpoint>;
  confidence: Provenance['confidence'];
  evidence?: ReadonlyArray<string>;
  /** The labour-market name, where the two naming logics genuinely differ. */
  proposedName?: string;
  disputed?: boolean;
  note?: string;
  provenance: Provenance;
}

export interface Crosswalk {
  id: string;
  kind: 'assimilation' | 'alignment';
  from: string;
  to: string;
  legalBasis?: string;
  authority: 'published' | 'reconstructed' | 'editorial';
  needs?: ReadonlyArray<{ document: string; url?: string; why: string; status?: 'missing' | 'partial' | 'held' }>;
  links: ReadonlyArray<CrosswalkLink>;
  provenance: Provenance;
}

/**
 * Price the same person under another regime. Returns candidates rather than an
 * answer: assimilation is many-to-one, so going forward is usually determinate
 * and going back usually is not. An ambiguous resolution must reach the UI as
 * several priced outcomes, never as one silently chosen winner.
 */
export interface Resolution {
  targets: ReadonlyArray<{ positionCode: string; dims?: Record<string, string>; weight?: number }>;
  relation: CrosswalkRelation | null;
  ambiguous: boolean;
  /** True when weights are missing and the caller asked to aggregate. */
  unweighted: boolean;
  diagnostics: ReadonlyArray<Diagnostic>;
}

export declare function resolvePosition(
  person: Person,
  from: Regime,
  to: Regime,
  crosswalk: Crosswalk,
): Resolution;

export declare function validateCrosswalk(
  crosswalk: Crosswalk,
  from: Regime,
  to: Regime,
): ReadonlyArray<Violation>;

// ------------------------------------------------------------- envelope mode

/**
 * View 3. A scenario is a base regime plus an ordered list of patches, which is
 * what goes in the URL hash. Patches are data, not code, so a scenario survives
 * a schema change and can be diffed and explained.
 */
export type Patch =
  | { op: 'setReferenceAmount'; value: number }
  | { op: 'setCoefficient'; positionCode: string; dims?: Record<string, string>; value: number }
  | { op: 'scaleFamily'; family: string; factor: number }
  | { op: 'setGradeBand'; gradeId: string; min?: number; max?: number }
  | { op: 'setSupplementRate'; supplementId: string; rate: number }
  | { op: 'setSupplementCounts'; supplementId: string; countsToCap: boolean | 'partial' }
  | { op: 'setCapPct'; capId: string; pct: number }
  | { op: 'setLadderStep'; ladderId: string; stepId: string; pct?: number; value?: number }
  | { op: 'setHeadcount'; ordonator?: string; family?: string; positionCode?: string; factor: number }
  | { op: 'setLevyRate'; levyId: string; rate: number };

export interface Move {
  patch: Patch;
  /** Cost if positive, saving if negative, against the unpatched baseline. */
  delta: Money;
  /** Free text the author must supply. Envelope mode refuses unnamed moves. */
  rationale: string;
}

export interface EnvelopeResult {
  target: Money;
  baseline: Money;
  proposed: Money;
  /** proposed - target. Must be <= 0 for the scenario to be fundable. */
  headroom: Money;
  balanced: boolean;
  moves: ReadonlyArray<Move>;
  /** Every increase, paired with the reductions that pay for it. */
  fundingLedger: ReadonlyArray<{ increase: Move; fundedBy: ReadonlyArray<{ move: Move; amount: Money }>; unfunded: Money }>;
  byOrdonator: ReadonlyArray<AggregateBucket>;
  diagnostics: ReadonlyArray<Diagnostic>;
}

// ---------------------------------------------------------------- the engine

export interface EngineOptions {
  /** Date every ValueSeries is resolved against. Defaults to regime.effectiveFrom. */
  asOf?: IsoDate;
}

/** Structural checks the data must survive. Run in CI over every regime file. */
export interface Violation {
  rule: string;
  severity: 'error' | 'warning';
  message: string;
  path: string;
}

export declare function validateRegime(regime: Regime, opts?: EngineOptions): ReadonlyArray<Violation>;

export declare function payslip(person: Person, regime: Regime, opts?: EngineOptions): Payslip;

export declare function aggregate(headcount: Headcount, regime: Regime, opts?: EngineOptions): Aggregate;

export declare function applyPatches(regime: Regime, patches: ReadonlyArray<Patch>): Regime;

export declare function envelope(
  headcount: Headcount,
  regime: Regime,
  target: Money,
  moves: ReadonlyArray<Move>,
  opts?: EngineOptions,
): EnvelopeResult;

/** URL hash codec. The only state store in the app. */
export declare function encodeScenario(s: Scenario): string;
export declare function decodeScenario(hash: string): Scenario;

export interface Scenario {
  regimeIds: ReadonlyArray<string>;
  person?: Person;
  patches?: Readonly<Record<string, ReadonlyArray<Patch>>>;
  headcountId?: string;
  target?: Money;
  asOf?: IsoDate;
  view: 'payslip' | 'structure' | 'envelope';
}

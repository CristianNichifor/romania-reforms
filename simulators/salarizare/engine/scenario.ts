/**
 * The scenario codec. The URL hash is the only state store in this app — there is no
 * backend, no database, and deliberately no client-side store either.
 *
 * The encoding is readable rather than compact. A shareable link for a public argument
 * should be legible in the address bar and editable by hand: someone disputing a
 * scenario should be able to see what was assumed without running the app. That rules
 * out base64 of a JSON blob, which is shorter and opaque.
 *
 *   #/payslip?r=ro-draft-2026-07-16&p=81.10104001.01&y=12&s=cfp,fonduri-externe:0.4:0.85
 *
 * Unknown keys survive a round trip untouched, so a link made by a later version does
 * not lose information when an older one reads it.
 */

import type { Person, SupplementClaim } from './payslip';

export type ViewId =
  | 'acasa'
  | 'compare'
  | 'meserii'
  | 'echivalente'
  | 'payslip'
  | 'structure'
  | 'envelope'
  | 'distributie';

export interface Scenario {
  view: ViewId;
  regimeIds: string[];
  positionCode?: string;
  seniorityYears?: number;
  dims?: Record<string, string>;
  claims?: SupplementClaim[];
  asOf?: string;
  /** Which occupational sector the meserii page is narrowed to, if any. */
  sector?: string;
  /** Envelope mode: the ceiling on total spend, as a proportion of today's bill. */
  envelopeTarget?: number;
  /** Envelope mode: a proportional change per occupational family, and its reason. */
  envelopeMoves?: EnvelopeMove[];
  /** Anything this version does not understand, preserved verbatim. */
  extra?: Record<string, string>;
}

const KNOWN = new Set(['r', 'p', 'y', 'd', 's', 'a', 't', 'm', 'f']);

export interface EnvelopeMove {
  family: string;
  /** Proportional change to that family's bill. +0.05 is five percent more. */
  pct: number;
  /**
   * Why. Envelope mode refuses to price an unnamed move, so the reason has to survive
   * the round trip or a shared link would arrive as an unusable scenario.
   */
  why: string;
}

/**
 * `familie:0.05:motivul%20scris%20aici`.
 *
 * The reason is free text and will contain the separators, so it is percent-encoded —
 * the one place this codec gives up readability, because the alternative is a link that
 * silently loses the justification and arrives looking like an unargued cut.
 */
function encodeMove(move: EnvelopeMove): string {
  return `${move.family}:${move.pct}:${encodeURIComponent(move.why)}`;
}

function decodeMove(text: string): EnvelopeMove | null {
  const [family, pct, ...rest] = text.split(':');
  const parsed = Number(pct);
  if (!family || !Number.isFinite(parsed)) return null;
  let why = '';
  try {
    why = decodeURIComponent(rest.join(':'));
  } catch {
    why = rest.join(':');
  }
  return { family, pct: parsed, why };
}

export const DEFAULT_SCENARIO: Scenario = {
  // A first visit lands on an explanation, not on a table of structural metrics. Links
  // already shared into #/compare keep working; only the bare URL changes.
  view: 'acasa',
  regimeIds: ['ro-draft-2026-07-16'],
};

/** `cfp` | `fonduri-externe:0.4` | `fonduri-externe:0.4:0.85` (rate, exempt share). */
function encodeClaim(claim: SupplementClaim): string {
  if (claim.externallyFundedShare !== undefined) {
    return `${claim.supplementId}:${claim.rate ?? ''}:${claim.externallyFundedShare}`;
  }
  if (claim.rate !== undefined) return `${claim.supplementId}:${claim.rate}`;
  return claim.supplementId;
}

function decodeClaim(text: string): SupplementClaim | null {
  const [id, rate, exempt] = text.split(':');
  if (!id) return null;
  const claim: SupplementClaim = { supplementId: id };
  if (rate) {
    const parsed = Number(rate);
    if (Number.isFinite(parsed)) claim.rate = parsed;
  }
  if (exempt) {
    const parsed = Number(exempt);
    if (Number.isFinite(parsed)) claim.externallyFundedShare = parsed;
  }
  return claim;
}

export function encodeScenario(scenario: Scenario): string {
  const params = new URLSearchParams();
  if (scenario.regimeIds.length) params.set('r', scenario.regimeIds.join(','));
  if (scenario.positionCode) params.set('p', scenario.positionCode);
  if (scenario.seniorityYears !== undefined) params.set('y', String(scenario.seniorityYears));
  if (scenario.dims && Object.keys(scenario.dims).length) {
    params.set(
      'd',
      Object.entries(scenario.dims).map(([k, v]) => `${k}:${v}`).join(','),
    );
  }
  if (scenario.claims?.length) params.set('s', scenario.claims.map(encodeClaim).join(','));
  if (scenario.asOf) params.set('a', scenario.asOf);
  if (scenario.sector) params.set('f', scenario.sector);
  if (scenario.envelopeTarget !== undefined) params.set('t', String(scenario.envelopeTarget));
  if (scenario.envelopeMoves?.length) {
    params.set('m', scenario.envelopeMoves.map(encodeMove).join(','));
  }
  for (const [key, value] of Object.entries(scenario.extra ?? {})) params.set(key, value);

  const query = params.toString();
  return `#/${scenario.view}${query ? `?${query}` : ''}`;
}

export function decodeScenario(hash: string): Scenario {
  const raw = hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const view: ViewId =
    path === 'payslip' ||
    path === 'envelope' ||
    path === 'structure' ||
    path === 'compare' ||
    path === 'meserii' ||
    path === 'echivalente' ||
    path === 'distributie' ||
    path === 'acasa'
      ? path
      : DEFAULT_SCENARIO.view;

  const params = new URLSearchParams(query);
  const regimeIds = (params.get('r') ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  const dims: Record<string, string> = {};
  for (const pair of (params.get('d') ?? '').split(',')) {
    const [k, v] = pair.split(':');
    if (k && v) dims[k] = v;
  }

  const claims = (params.get('s') ?? '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
    .map(decodeClaim)
    .filter((c): c is SupplementClaim => c !== null);

  const extra: Record<string, string> = {};
  for (const [key, value] of params) if (!KNOWN.has(key)) extra[key] = value;

  const years = Number(params.get('y'));
  const target = Number(params.get('t'));

  const moves = (params.get('m') ?? '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
    .map(decodeMove)
    .filter((m): m is EnvelopeMove => m !== null);

  return {
    view,
    regimeIds: regimeIds.length ? regimeIds : DEFAULT_SCENARIO.regimeIds,
    positionCode: params.get('p') ?? undefined,
    seniorityYears: Number.isFinite(years) && params.get('y') !== null ? years : undefined,
    dims: Object.keys(dims).length ? dims : undefined,
    claims: claims.length ? claims : undefined,
    asOf: params.get('a') ?? undefined,
    sector: params.get('f') ?? undefined,
    envelopeTarget:
      Number.isFinite(target) && params.get('t') !== null ? target : undefined,
    envelopeMoves: moves.length ? moves : undefined,
    extra: Object.keys(extra).length ? extra : undefined,
  };
}

/** The subject of a scenario, as the engine wants it. */
export function personFrom(scenario: Scenario): Person | null {
  if (!scenario.positionCode) return null;
  return {
    positionCode: scenario.positionCode,
    seniorityYears: scenario.seniorityYears ?? 0,
    dims: scenario.dims,
    claims: scenario.claims,
  };
}

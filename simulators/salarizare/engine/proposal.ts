/**
 * A proposal is a base regime plus a short list of named edits.
 *
 * Not a second copy of the grid. Copying 1176 positions to change five rules would
 * make the proposal impossible to audit — a reader could not tell an intended change
 * from a transcription slip — and it would drift the moment the ministry's data is
 * re-imported. As a patch list, the diff *is* the proposal.
 *
 * Every patch names the limitation it fixes, so a claim in the UI can be traced to a
 * defect, and the defect to the cell or article it was found in.
 *
 * Pure. applyProposal returns a new regime and never mutates its input.
 */

import { resolveSeries } from './structure';
import type { Grade, Position, PositionVariant, Regime, ValueSeries } from './types';

/**
 * A duty is something a person does, priced on its own.
 *
 * The draft prices the same trade differently by annex: a driver is paid for the ministry
 * that employs them, not for what they drive. Naming the duty is the alternative — it
 * survives a transfer, it can be argued about on its own, and it is the only version of
 * the question a labour market can answer.
 *
 * `rate` is authored, never read out of the workbook, because the source contains no such
 * figure. Every duty must carry `basis` saying where its number comes from, and the
 * supplements it produces are marked `assumed` so nothing downstream can mistake them for
 * something the ministry proposed.
 */
export interface TradeDuty {
  id: string;
  name: string;
  /** Share of the base salary. */
  rate: number;
  basis: string;
  /** Matched against the folded former title, to decide who performs the duty. */
  appliesTo: string;
}

export interface Trade {
  id: string;
  /** What the trade is called once it is no longer called after its annex. */
  name: string;
  matches: string;
  excludeMatches?: string;
  duties: TradeDuty[];
}

export interface Patch {
  id: string;
  title: string;
  /** id of a limitation in the base regime that this patch addresses. */
  fixes?: string;
  rationale: string;
  expectedEffect?: string;
  op:
    | 'roundCoefficients'
    | 'makeGradeBandsContiguous'
    | 'collapseSchedule'
    | 'setSupplementCounts'
    | 'setSupplementRate'
    | 'separateInstitutionFactor'
    | 'mergeDuplicateTitles'
    | 'unifyTradeByDuty'
    | 'unifySeniority';
  trades?: Trade[];
  decimals?: number;
  dimension?: string;
  keep?: 'first' | 'last';
  supplementIds?: string[];
  countsToCap?: boolean | 'partial';
  rate?: number;
  ladder?: string;
  /**
   * True when the patch moves money between people rather than repairing a defect. The
   * other patches deliberately leave distribution alone; one that does not must say so,
   * or the whole proposal loses the claim that it only fixes what is broken.
   */
  policyChange?: boolean;
}

export interface Proposal {
  id: string;
  name: string;
  base: string;
  summary?: string;
  notPolicy?: string;
  patches: Patch[];
}

export interface PatchEffect {
  patchId: string;
  title: string;
  /** Plain count of what the patch touched, for showing the diff honestly. */
  positionsTouched: number;
  variantsTouched: number;
  gradesTouched: number;
  supplementsTouched: number;
  /** Codes this patch changed, so the UI can show the diff rather than assert it. */
  touchedCodes: string[];
}

export interface AppliedProposal {
  regime: Regime;
  effects: PatchEffect[];
}

function firstOf(series: ValueSeries): number {
  return resolveSeries(series);
}

/**
 * Titles compared with the accents folded away and the punctuation dropped. The sheets
 * spell the same word several ways — ș and ş, ț and ţ — so anything that compares titles
 * has to fold, or it silently decides two spellings are two jobs.
 */
function normTitle(title: string): string {
  return title
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function canonicalTitle(p: Position): string {
  return p.titles?.find((t) => t.canonical)?.name ?? p.name;
}

/** The entry-level coefficient, which is what compares one employer to another. */
function entryValue(p: Position): number | null {
  const values = p.variants
    .map((v) => (v.value === undefined ? null : firstOf(v.value)))
    .filter((n): n is number => n !== null);
  return values.length ? Math.min(...values) : null;
}

/**
 * Dropping a dimension can leave two variants with the same signature, which would make
 * them unaddressable — the defect this codebase already fixed once in the importer. Keep
 * the lowest value: for a seniority ladder that is the step-0 rung the ladder builds on.
 */
function dedupeByDims(variants: PositionVariant[]): PositionVariant[] {
  const kept = new Map<string, PositionVariant>();
  for (const variant of variants) {
    const key = JSON.stringify(variant.dims ?? {});
    const existing = kept.get(key);
    if (!existing || firstOf(variant.value ?? 0) < firstOf(existing.value ?? 0)) {
      kept.set(key, variant);
    }
  }
  return [...kept.values()];
}

function mapVariants(
  position: Position,
  fn: (v: PositionVariant) => PositionVariant | null,
): { position: Position; touched: number } {
  let touched = 0;
  const variants = position.variants
    .map((v) => {
      const next = fn(v);
      if (next === null) {
        touched += 1;
        return null;
      }
      if (next !== v) touched += 1;
      return next;
    })
    .filter((v): v is PositionVariant => v !== null);
  return {
    position: touched ? { ...position, variants: variants.length ? variants : position.variants } : position,
    touched,
  };
}

export function applyProposal(base: Regime, proposal: Proposal): AppliedProposal {
  let regime: Regime = { ...base, id: proposal.id, name: proposal.name, status: 'proposal' };
  const effects: PatchEffect[] = [];

  for (const patch of proposal.patches) {
    const effect: PatchEffect = {
      patchId: patch.id,
      title: patch.title,
      positionsTouched: 0,
      variantsTouched: 0,
      gradesTouched: 0,
      supplementsTouched: 0,
      touchedCodes: [],
    };

    switch (patch.op) {
      case 'roundCoefficients': {
        const dp = patch.decimals ?? 2;
        const factor = 10 ** dp;
        const positions = regime.positions.map((p) => {
          const { position, touched } = mapVariants(p, (v) => {
            if (v.value === undefined) return v;
            const value = firstOf(v.value);
            const rounded = Math.round(value * factor) / factor;
            return rounded === value ? v : { ...v, value: rounded };
          });
          if (touched) {
            effect.positionsTouched += 1;
            effect.variantsTouched += touched;
            effect.touchedCodes.push(p.code);
          }
          return position;
        });
        regime = { ...regime, positions };
        break;
      }

      case 'makeGradeBandsContiguous': {
        // Each band starts where the previous one ended, so the 0,01-wide holes between
        // them close. Only the floors move; no ceiling and no coefficient changes.
        const sorted = [...regime.grades].sort((a, b) => firstOf(a.min) - firstOf(b.min));
        const grades: Grade[] = sorted.map((g, i) => {
          if (i === 0) return g;
          const previousMax = firstOf(sorted[i - 1].max);
          if (firstOf(g.min) <= previousMax) return g;
          effect.gradesTouched += 1;
          return { ...g, min: previousMax };
        });
        regime = { ...regime, grades };
        break;
      }

      case 'collapseSchedule': {
        // Positions phased across a dimension (Annex IX's calendar years) keep one step
        // and drop the rest, so the grid that takes effect is the grid the law declares.
        const dim = patch.dimension ?? 'an';
        const keep = patch.keep ?? 'first';
        const positions = regime.positions.map((p) => {
          const dated = p.variants.filter((v) => v.dims?.[dim] !== undefined);
          if (dated.length < 2) return p;
          const ordered = [...dated].sort((a, b) =>
            String(a.dims![dim]).localeCompare(String(b.dims![dim])),
          );
          const chosen = keep === 'first' ? ordered[0] : ordered[ordered.length - 1];
          const rest = p.variants.filter((v) => v.dims?.[dim] === undefined);
          effect.positionsTouched += 1;
          effect.variantsTouched += dated.length - 1;
          effect.touchedCodes.push(p.code);
          const { [dim]: _dropped, ...otherDims } = chosen.dims ?? {};
          const flattened: PositionVariant = Object.keys(otherDims).length
            ? { ...chosen, dims: otherDims }
            : { ...chosen, dims: undefined };
          return { ...p, variants: dedupeByDims([...rest, flattened]) };
        });
        regime = { ...regime, positions };
        break;
      }

      case 'setSupplementCounts': {
        const ids = new Set(patch.supplementIds ?? []);
        const supplements = regime.supplements.map((s) => {
          if (!ids.has(s.id)) return s;
          effect.supplementsTouched += 1;
          return { ...s, countsToCap: patch.countsToCap ?? true };
        });
        // Keep the cap's exclusion list in step with the flag, in both directions.
        // Stripping ids from the list unconditionally — as this did — silently pulled a
        // supplement into the ceiling even when the patch was declaring it exempt.
        const bringingIn = (patch.countsToCap ?? true) !== false;
        const caps = regime.caps.map((cap) => {
          if (!cap.numerator) return cap;
          const current = cap.numerator.exclude ?? [];
          const next = bringingIn
            ? current.filter((id) => !ids.has(id))
            : [...new Set([...current, ...ids])];
          if (next.length === current.length && next.every((id, i) => id === current[i])) return cap;
          return { ...cap, numerator: { ...cap.numerator, exclude: next } };
        });
        regime = { ...regime, supplements, caps };
        break;
      }

      case 'setSupplementRate': {
        const ids = new Set(patch.supplementIds ?? []);
        const supplements = regime.supplements.map((s) => {
          if (!ids.has(s.id) || patch.rate === undefined) return s;
          effect.supplementsTouched += 1;
          return { ...s, rate: patch.rate };
        });
        regime = { ...regime, supplements };
        break;
      }

      case 'separateInstitutionFactor': {
        // A job is what someone does; the institution is where they do it. The draft
        // fuses the two, so one title carries several coefficients and the reader cannot
        // tell a promotion from a transfer. Keep the job once, and make the institutional
        // effect an explicit multiplier that can be argued about on its own.
        //
        // `celula` is deliberately not in this set. It is not a claim about institutions —
        // it is the importer recording that two rows of the source could be told apart by
        // nothing but their place on the page. Reading it as context turned every such
        // ambiguity into a confident statement that the difference is institutional, which
        // is the one thing nobody knows. Where the distinction is unknown the patch
        // declines to act, and the regime carries `variante-fara-criteriu` to say so.
        const contextDims = new Set(['institutionLevel', 'sursa']);
        const positions = regime.positions.map((p) => {
          if (p.variants.length < 2) return p;
          const jobKeys = (v: PositionVariant) =>
            JSON.stringify(
              Object.entries(v.dims ?? {})
                .filter(([k]) => !contextDims.has(k))
                .sort(),
            );
          const distinctJobs = new Set(p.variants.map(jobKeys));
          const usesContext = p.variants.some((v) =>
            Object.keys(v.dims ?? {}).some((k) => contextDims.has(k)),
          );
          if (distinctJobs.size !== 1 || !usesContext) return p;

          const values = p.variants
            .map((v) => (v.value === undefined ? null : firstOf(v.value)))
            .filter((n): n is number => n !== null);
          if (values.length < 2) return p;
          const lo = Math.min(...values);
          const hi = Math.max(...values);
          if (lo <= 0) return p;

          const keep = p.variants.find((v) => v.value !== undefined && firstOf(v.value) === lo)!;
          // Strip exactly what the set calls context, so the two cannot drift apart.
          const rest = Object.fromEntries(
            Object.entries(keep.dims ?? {}).filter(([k]) => !contextDims.has(k)),
          );

          effect.positionsTouched += 1;
          effect.variantsTouched += p.variants.length - 1;
          effect.touchedCodes.push(p.code);
          return {
            ...p,
            variants: [Object.keys(rest).length ? { ...keep, dims: rest } : { ...keep, dims: undefined }],
            institutionFactor: {
              min: 1,
              max: Number((hi / lo).toFixed(4)),
              reason:
                'Diferența dintre categoriile de instituții, scoasă din denumirea funcției și făcută explicită.',
            },
          };
        });
        regime = { ...regime, positions };
        break;
      }

      case 'mergeDuplicateTitles': {
        // The grid names a job once per employer. "Director" is 25 separate codes across
        // six annex sheets, "Șef serviciu" 25 more — not because the work differs but
        // because the institution does. That is the same defect separateInstitutionFactor
        // fixes inside one position, one level up: there it is several coefficients under
        // one name, here it is several names for one job.
        //
        // Two positions are the same job only when the title, the occupational family,
        // the kind of post and the study level all agree. Title alone is not enough — a
        // director in education and a director in administration are genuinely different
        // posts, and the family keeps them apart.
        // Rows that name a rank rather than a job. The workbook writes them under the
        // occupation they belong to and marks them by indenting the cell — 'gradul I',
        // '    clasa a II-a', 'debutant' — and the importer keeps the indentation but not
        // the parent title, so 46 positions are called "debutant" and 30 "clasa a …".
        // They are not 46 jobs, and merging them would invent one. Both signals are used
        // because neither catches everything: only 59 rows are indented, while 8 of those
        // are also bare grade words and many bare labels are not indented at all.
        const QUALIFIER_WORDS = new Set([
          'debutant', 'principal', 'asistent', 'superior', 'specialist', 'practicant',
          'stagiar', 'definitiv', 'expert',
        ]);
        const QUALIFIER_PREFIX = /^(gradul|clasa|treapta|nivel|grad)\b/;
        const isRankLabel = (p: Position, title: string) => {
          const raw = p.assimilation?.rawTitleCell ?? '';
          return (
            QUALIFIER_WORDS.has(title) ||
            QUALIFIER_PREFIX.test(title) ||
            (raw.length > 0 && raw !== raw.replace(/^\s+/, ''))
          );
        };
        const norm = normTitle;
        const canonical = canonicalTitle;
        const entry = entryValue;

        const groups = new Map<string, Position[]>();
        for (const position of regime.positions) {
          const title = norm(canonical(position));
          // Rank labels keep their own code and are left exactly as they are.
          const key =
            !title || isRankLabel(position, title)
              ? `sine:${position.code}`
              : [title, position.family ?? '', position.kind ?? '', position.studyLevel ?? ''].join('|');
          const list = groups.get(key) ?? [];
          list.push(position);
          groups.set(key, list);
        }

        const positions: Position[] = [];
        for (const group of groups.values()) {
          const entries = group.map(entry);
          if (group.length < 2 || entries.some((e) => e === null || e <= 0)) {
            positions.push(...group);
            continue;
          }
          const values = entries as number[];
          const lo = Math.min(...values);
          const hi = Math.max(...values);
          const keep = group[values.indexOf(lo)];

          // Every name the merged rows carried, kept once, so nothing disappears.
          const seen = new Set<string>();
          const titles = group
            .flatMap((p) => p.titles ?? [{ name: p.name, canonical: true }])
            .filter((t) => (seen.has(norm(t.name)) ? false : (seen.add(norm(t.name)), true)));

          // The spread between employers becomes an explicit multiplier, the same shape
          // separateInstitutionFactor produces — and never smaller than one already there.
          const spread = Number((hi / lo).toFixed(4));
          const existing = keep.institutionFactor;
          effect.positionsTouched += group.length - 1;
          effect.touchedCodes.push(...group.map((p) => p.code));
          positions.push({
            ...keep,
            titles,
            mergedFrom: group.filter((p) => p.code !== keep.code).map((p) => p.code),
            institutionFactor:
              spread > 1 || existing
                ? {
                    min: existing?.min ?? 1,
                    max: Math.max(spread, existing?.max ?? 1),
                    reason:
                      existing?.reason ??
                      'Aceeași meserie apărea sub coduri diferite după instituție. Funcția e numită o dată, iar diferența dintre angajatori devine un multiplicator explicit.',
                  }
                : undefined,
          });
        }
        regime = { ...regime, positions };
        break;
      }

      case 'unifyTradeByDuty': {
        // mergeDuplicateTitles keeps the occupational family in its key on purpose: a
        // director in education and a director in administration are different posts. For
        // a trade that is exactly backwards. A driver drives. The annex says which
        // ministry employs them, not what they do, and the grid pays the annex: the same
        // licence is worth 1,1489 in a small town hall and 1,5714 in an ambulance
        // service, a 37% spread with no duty named anywhere in the law.
        //
        // So the trade is named once, at the lowest coefficient in the grid, and what the
        // higher-paying annexes were buying has to be stated as a duty or not paid for at
        // all. Driving an ambulance is a duty; driving for the health ministry is not.
        //
        // Nothing is inferred. The trades and their duties are declared in the patch, the
        // duty rates are authored against a stated basis, and the part of each former
        // coefficient the duties do NOT account for is kept as `residual` rather than
        // quietly absorbed — that residual is the finding this patch exists to produce.
        const trades = patch.trades ?? [];
        const supplements = [...regime.supplements];
        let positions = [...regime.positions];

        for (const trade of trades) {
          const matches = new RegExp(trade.matches);
          const excludes = trade.excludeMatches ? new RegExp(trade.excludeMatches) : null;
          const candidates = positions.filter((p) => {
            if (p.kind !== 'execution') return false;
            // A row whose title the importer could not split is several jobs on one
            // coefficient. Folding it would carry the other jobs along with the trade.
            if (p.assimilation?.parse === 'needsReview') return false;
            if ((p.assimilation?.fanIn ?? 1) > 1) return false;
            const title = normTitle(canonicalTitle(p));
            if (!matches.test(title)) return false;
            if (excludes?.test(title)) return false;
            return entryValue(p) !== null;
          });
          if (candidates.length < 2) continue;

          const floors = candidates.map((p) => entryValue(p) as number);
          const floor = Math.min(...floors);
          if (floor <= 0) continue;
          const keep = candidates[floors.indexOf(floor)];

          const fold = candidates
            .map((p, i) => ({ position: p, was: floors[i] }))
            .filter(({ position }) => position.code !== keep.code)
            .map(({ position: p, was }) => {
              const title = normTitle(canonicalTitle(p));
              const performed = trade.duties.filter((d) => new RegExp(d.appliesTo).test(title));
              const dutyRate = performed.reduce((sum, d) => sum + d.rate, 0);
              return {
                code: p.code,
                name: canonicalTitle(p),
                family: p.family,
                was,
                duties: performed.map((d) => d.id),
                dutyRate: Number(dutyRate.toFixed(4)),
                residual: Number((was / floor - 1 - dutyRate).toFixed(4)),
              };
            });

          // Every name the folded rows carried, kept once, so nothing disappears.
          const seen = new Set<string>();
          const titles = candidates
            .flatMap((p) => p.titles ?? [{ name: p.name, canonical: true }])
            .filter((t) => (seen.has(normTitle(t.name)) ? false : (seen.add(normTitle(t.name)), true)));

          const folded = new Set(fold.map((f) => f.code));
          effect.positionsTouched += fold.length;
          effect.touchedCodes.push(...candidates.map((p) => p.code));
          positions = positions
            .filter((p) => !folded.has(p.code))
            .map((p) =>
              p.code === keep.code
                ? {
                    ...p,
                    name: trade.name,
                    titles: [{ name: trade.name, canonical: true }, ...titles.filter((t) => normTitle(t.name) !== normTitle(trade.name))],
                    // Deliberately NOT mergedFrom. That field carries the promise that a
                    // merge stayed inside one occupational family — the guard that keeps
                    // a director in education apart from one in administration, and it is
                    // tested. This fold crosses families on purpose, so it records itself
                    // separately and in more detail rather than weakening that promise.
                    tradeFold: fold,
                  }
                : p,
            );

          for (const duty of trade.duties) {
            if (supplements.some((s) => s.id === duty.id)) continue;
            effect.supplementsTouched += 1;
            supplements.push({
              id: duty.id,
              name: duty.name,
              mode: 'fixed',
              rate: duty.rate,
              base: 'baseSalary',
              // A duty is paid for work actually done, and the whole point of naming it is
              // that it can be argued about — so it sits inside the ceiling like any other
              // supplement rather than beside it.
              countsToCap: true,
              eligibility: { condition: `Se plătește pentru ${duty.name.toLowerCase()}.` },
              provenance: {
                source: 'propunere-alternativa',
                locator: `data/proposals/${proposal.id}.json#${patch.id}/${trade.id}/${duty.id}`,
                confidence: 'assumed',
                note: duty.basis,
              },
            });
          }
        }
        regime = { ...regime, positions, supplements };
        break;
      }

      case 'unifySeniority': {
        // Annexes I and V publish a coefficient per seniority band. Keep the lowest band
        // as the gradatia-0 value and let the Art. 13 ladder do the rest, so one rule
        // governs seniority everywhere instead of two that contradict each other.
        const ladder = patch.ladder ?? 'gradatii';
        const positions = regime.positions.map((p) => {
          const banded = p.variants.filter((v) => v.dims?.vechime !== undefined);
          if (banded.length < 2 || p.ladder != null) return p;
          const lowest = banded.reduce((min, v) =>
            firstOf(v.value ?? 0) < firstOf(min.value ?? 0) ? v : min,
          );
          const others = p.variants.filter((v) => v.dims?.vechime === undefined);
          const { vechime: _v, ...rest } = lowest.dims ?? {};
          effect.positionsTouched += 1;
          effect.variantsTouched += banded.length - 1;
          effect.touchedCodes.push(p.code);
          return {
            ...p,
            ladder,
            variants: dedupeByDims([
              ...others,
              Object.keys(rest).length ? { ...lowest, dims: rest } : { ...lowest, dims: undefined },
            ]),
          };
        });
        regime = { ...regime, positions };
        break;
      }
    }

    effects.push(effect);
  }

  return { regime, effects };
}

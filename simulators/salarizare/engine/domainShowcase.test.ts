import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { resolveDomainShowcase } from './domainShowcase';
import type { DkOccupation, GroupsDocument } from './occupations';
import { applyProposal, type Proposal } from './proposal';
import type { Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const load = <T>(path: string): T =>
  JSON.parse(readFileSync(resolve(here, '..', path), 'utf8')) as T;

function dkOccupations(): DkOccupation[] {
  const doc = load<{ series: Array<{ dims: Record<string, string>; observations: Array<{ value: number }> }> }>(
    'data/fiscal/dk-occupations.json',
  );
  const byOcc = new Map<string, DkOccupation>();
  for (const series of doc.series) {
    const name = series.dims.occupation;
    if (!name) continue;
    const entry = byOcc.get(name) ?? { occupation: name, q1: 0, median: 0, q3: 0 };
    const value = series.observations.at(-1)?.value ?? 0;
    if (series.dims.kind === 'occupation') {
      (entry as unknown as Record<string, number>)[series.dims.quartile] = value;
    }
    byOcc.set(name, entry);
  }
  return [...byOcc.values()];
}

describe('domain showcase', () => {
  const draft = load<Regime>('data/regimes/ro-draft-2026-08-20.json');
  const inForce = load<Regime>('data/regimes/ro-153-2017.json');
  const proposal = applyProposal(draft, load<Proposal>('data/proposals/propunere-v1.json')).regime;
  const groups = load<GroupsDocument>('data/groups/ro-dk-occupations.json');
  const rows = resolveDomainShowcase({ inForce, draft, proposal }, groups, dkOccupations());

  it('covers the public-sector domains that need explicit showcase rows', () => {
    expect(rows.map((row) => row.group.id)).toEqual(
      expect.arrayContaining([
        'cercetatori',
        'judecatori-procurori',
        'grefieri',
        'armata',
        'politie',
        'penitenciare',
        'interventii-urgenta',
        'biblioteci-arhive',
      ]),
    );
  });

  it('keeps missing Romanian current-law data visible instead of inventing a value', () => {
    const probation = rows.find((row) => row.group.id === 'probatiune')!;
    expect(probation.sides.inForce.band).toBeNull();
    expect(probation.sides.inForce.missingReason).toMatch(/niciun post/);
    expect(probation.sides.draft.count).toBeGreaterThan(0);
  });

  it('computes comparable ratios against each system middle', () => {
    const police = rows.find((row) => row.group.id === 'politie')!;
    expect(police.sides.draft.band?.ratio.median).toBeGreaterThan(0);
    expect(police.sides.proposal.band?.ratio.median).toBeGreaterThan(0);
    expect(police.sides.denmark.band?.ratio.median).toBeGreaterThan(0);
  });

  it('leaves a missing Danish comparator missing', () => {
    const researchers = rows.find((row) => row.group.id === 'cercetatori')!;
    expect(researchers.sides.denmark.band).toBeNull();
    expect(researchers.sides.denmark.missingReason).toMatch(/nu există comparator danez/);
  });
});

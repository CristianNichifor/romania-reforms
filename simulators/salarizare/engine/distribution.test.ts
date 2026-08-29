import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { BANDS, bandFor, distribution } from './distribution';
import type { Crosswalk, Regime } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const read = (p: string) => JSON.parse(readFileSync(resolve(here, '..', p), 'utf8'));

const IN_FORCE: Regime = read('data/regimes/ro-153-2017.json');
const DRAFT: Regime = read('data/regimes/ro-draft-2026-07-16.json');
const CROSSWALK: Crosswalk = read('data/crosswalks/ro-153-2017--ro-draft-2026-07-16.json');

const d = distribution(IN_FORCE, DRAFT, CROSSWALK);

describe('who moves up and who moves down', () => {
  it('prices only the one-to-one links, and says how many it set aside', () => {
    // A link with several posts on a side has no single before-and-after; averaging them
    // would invent a move nobody made.
    expect(d.coverage.priced).toBeGreaterThan(80);
    expect(d.coverage.grouped).toBeGreaterThan(0);
    expect(d.coverage.priced + d.coverage.grouped).toBeLessThanOrEqual(d.coverage.links);
    expect(d.moves.every((m) => m.before > 0 && m.after > 0)).toBe(true);
  });

  it('keeps the reader honest about how much of the grid this is', () => {
    // A third of the old grid could be matched. The distribution describes that subset,
    // and the number has to be reachable so the page can say so.
    expect(d.coverage.oldPositions).toBeGreaterThan(1000);
    expect(d.coverage.priced / d.coverage.oldPositions).toBeLessThan(0.2);
  });

  it('bands cover every ratio without a gap or an overlap', () => {
    // A gap would silently drop posts out of the chart; an overlap would double-count.
    for (let i = 1; i < BANDS.length; i += 1) {
      expect(BANDS[i].from).toBe(BANDS[i - 1].to);
    }
    expect(BANDS[0].from).toBe(0);
    expect(BANDS[BANDS.length - 1].to).toBe(Infinity);
    expect(d.bands.reduce((sum, b) => sum + b.count, 0)).toBe(d.moves.length);
    expect(d.bands.reduce((sum, b) => sum + b.share, 0)).toBeCloseTo(1, 10);
  });

  it('puts a ratio in the band a reader would put it in', () => {
    expect(bandFor(0.5).id).toBe('down-hard');
    expect(bandFor(1).id).toBe('flat');
    expect(bandFor(1.0).direction).toBe(0);
    expect(bandFor(1.5).id).toBe('up-hard');
    // The boundaries belong to the band above, consistently.
    expect(bandFor(0.98).id).toBe('flat');
    expect(bandFor(1.02).id).toBe('up-soft');
  });

  it('finds the middle post roughly where it was', () => {
    // The headline: the reform moves the median post hardly at all, while the tails move
    // a lot. A page that reported only the median would miss the story, and one that
    // reported only the tails would invent one.
    expect(d.median).toBeGreaterThan(0.95);
    expect(d.median).toBeLessThan(1.1);
    expect(d.losing).toBeGreaterThan(0);
    expect(d.losing).toBeLessThan(1);
  });

  it('summarises families most-affected first', () => {
    expect(d.byFamily.length).toBeGreaterThan(2);
    for (let i = 1; i < d.byFamily.length; i += 1) {
      expect(d.byFamily[i].median).toBeGreaterThanOrEqual(d.byFamily[i - 1].median);
    }
    expect(d.byFamily.reduce((sum, f) => sum + f.moves, 0)).toBe(d.moves.length);
  });

  it('returns an empty distribution rather than throwing on an empty crosswalk', () => {
    const empty = distribution(IN_FORCE, DRAFT, { ...CROSSWALK, links: [] });
    expect(empty.moves).toEqual([]);
    expect(empty.median).toBe(0);
    expect(empty.losing).toBe(0);
    expect(empty.bands.every((b) => b.share === 0)).toBe(true);
  });
});

describe('how far the Art. 33 transitional difference could reach', () => {
  it('settles the half of the question the data can settle', () => {
    // The reference rises 2500 -> 4100, so a post keeps a smaller base only if it falls
    // further in standing than that rise makes up. Nothing observed comes close.
    const t = d.transition;
    expect(t.oldReference).toBe(2500);
    expect(t.newReference).toBe(4100);
    expect(t.breakeven).toBeCloseTo(0.6098, 3);
    expect(t.worstRatio).toBeGreaterThan(t.breakeven);
    expect(t.below).toBe(0);
  });

  it('does not let that be read as "nobody loses"', () => {
    // The bound is against the 2022 grid printed in the annexes, not against November
    // 2026 income, which includes supplements and every increase granted since. This test
    // exists so the distinction cannot quietly disappear: if a future change starts
    // pricing the old regime at something other than its own published reference, the
    // breakeven moves and this fails.
    expect(d.transition.breakeven).toBeLessThan(1);
    expect(d.coverage.priced).toBeLessThan(d.coverage.oldPositions);
  });
});

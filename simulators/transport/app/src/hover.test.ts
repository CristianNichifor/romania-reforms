/**
 * Guards the one-popup contract.
 *
 * Each layer used to own a `Popup` and a per-layer `mousemove`. The layers overlap — the speed
 * lines and the three investment layers are all drawn over the commune fill — so hovering a
 * road inside a commune fired two handlers, which anchored two boxes at the same coordinate.
 * The second painted over the first and neither could be read. Every layer added was another
 * way to collide.
 *
 * Catching that in the DOM would need a rendered map and real hit-testing. This catches the
 * cause: one popup, and hover answered in one handler rather than one per layer.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(import.meta.dirname, '..');
const main = readFileSync(join(root, 'src/main.ts'), 'utf8');
const css = readFileSync(join(root, 'src/style.css'), 'utf8');

describe('map hover', () => {
  it('constructs exactly one popup', () => {
    const popups = main.match(/new maplibregl\.Popup\(/g) ?? [];
    expect(popups, 'a second Popup is a second box at the same lngLat').toHaveLength(1);
  });

  it('binds no per-layer hover handlers', () => {
    // `map.on('mousemove', 'some-layer', ...)` is the three-argument form. It is the shape that
    // caused this: one per overlapping layer, each unaware of the others.
    const scoped = [...main.matchAll(/map\.on\(\s*'(?:mousemove|mouseleave)'\s*,\s*'/g)];
    expect(scoped.map((m) => m[0])).toEqual([]);
  });

  it('queries every hoverable layer from one list, commune last', () => {
    const list = main.match(/HOVER_LAYERS: readonly string\[\] = \[([^\]]*)\]/)?.[1];
    expect(list).toBeDefined();
    const ids = [...list!.matchAll(/'([\w-]+)'/g)].map((m) => m[1]);
    expect(ids).toContain('speeds-line');
    expect(ids).toContain('inv-ocolire');
    // The commune under the cursor is context for the road on top of it, never its replacement.
    expect(ids.at(-1)).toBe('uat-fill');
  });

  it('separates stacked sections', () => {
    expect(main).toContain('pop-sep');
    expect(css).toContain('hr.pop-sep');
  });
});

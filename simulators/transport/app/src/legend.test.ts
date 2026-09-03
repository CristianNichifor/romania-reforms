/**
 * Guards the legend markup contract.
 *
 * The swatch rules were written as `#legend i`, so when two more legends were added they
 * inherited the `ul` reset and nothing else: an `<i>` with a background colour, no width, and
 * therefore no visible swatch — while the text beside it still read like a legend, which is
 * why it survived several sessions. Measured 0x17 against the working legend's 15x15.
 *
 * A DOM test would need a CSS engine to catch it again. This catches the cause instead: the
 * rules are now class-scoped, so what must hold is that every legend carries the class and
 * that nothing goes back to styling them inline.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(import.meta.dirname, '..');
const html = readFileSync(join(root, 'index.html'), 'utf8');
const css = readFileSync(join(root, 'src/style.css'), 'utf8');
const main = readFileSync(join(root, 'src/main.ts'), 'utf8');

describe('legend markup', () => {
  it('every legend list carries the class the swatch rules are scoped to', () => {
    const lists = [...html.matchAll(/<ul\s+id="([\w-]*legend[\w-]*)"([^>]*)>/g)];
    expect(lists.length).toBeGreaterThanOrEqual(3);
    for (const [, id, attrs] of lists) {
      expect(attrs, `#${id} must have class="legend" or its swatches are 0px wide`).toContain(
        'class="legend"',
      );
    }
  });

  it('the swatch rules are class-scoped, not id-scoped', () => {
    expect(css).toContain('.legend i');
    expect(css).toContain('.legend li');
    expect(css).not.toMatch(/#legend\s+i\s*\{/);
  });

  it('legend sub-headings use the class rather than inline styles', () => {
    // Inline `style="..."` on a legend row is how the previous version faked a sub-heading,
    // and it drifts from the real rules the moment either changes.
    expect(main).toContain('<li class="group">');
    expect(main).not.toMatch(/<li style="[^"]*list-style/);
  });
});

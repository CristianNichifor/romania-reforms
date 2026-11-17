// The summary bar sat at a fixed 64 px and drew over the subtitle and the status badge once
// the header gained the back link and the data line (UX review, 1440 px). It and both side
// panels now hang off the header's measured height, which main.ts publishes.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8');
const main = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8');
const rule = (selector: string): string =>
  new RegExp(`\\n${selector.replace('.', '\\.')} \\{([^}]*)\\}`).exec(css)?.[1] ?? '';

describe('the header and what hangs below it', () => {
  it('publishes the header height from the taller of its two columns', () => {
    expect(main).toContain("'--topbar-h'");
    expect(main).toMatch(/observe\(brand\)/);
    expect(main).toMatch(/observe\(actions\)/);
  });

  it('places the summary bar and both panels from that height, not a constant', () => {
    expect(rule('.summary')).toMatch(/top: calc\(var\(--topbar-h/);
    expect(rule('.controls')).toMatch(/max-height: calc\([^;]*var\(--topbar-h/);
    expect(rule('.detail')).toMatch(/top: calc\(var\(--topbar-h/);
  });

  it('wraps the header controls instead of clipping them', () => {
    expect(rule('.topbar-actions')).toContain('flex-wrap: wrap;');
    expect(css).toMatch(/#methodology-btn \{\s*white-space: nowrap;/);
  });

  it('gives the back link a 24 px target', () => {
    expect(rule('.up')).toContain('min-height: 24px;');
  });
});

// The chrome follows the family (UX-14): civic-ui neutral roles for background, surfaces,
// text and action; only the series colours are the app's own (ux-guidelines § 6).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = resolve(dirname(fileURLToPath(import.meta.url)), '../src');
const styles = readFileSync(resolve(src, 'styles.css'), 'utf8');
const pilot = readFileSync(resolve(src, 'civic-pilot.css'), 'utf8');

const firstRoot = /:root\s*\{([^}]*)\}/.exec(styles)?.[1] ?? '';
const darkBlocks = [...styles.matchAll(/(?:data-theme='dark'\]|:not\(\[data-theme='light'\]\)\))\s*\{([^}]*)\}/g)]
  .map((m) => m[1])
  .filter((b) => b.includes('--surface-0'));

describe('the chrome tokens', () => {
  it('are the civic-ui light roles by default, with the blue series kept', () => {
    expect(firstRoot).toContain('color-scheme: light;');
    for (const line of [
      '--surface-0: #f4f6f6;',
      '--surface-1: #ffffff;',
      '--surface-2: #e7eeee;',
      '--border-strong: #718588;',
      '--text-primary: #182b2c;',
      '--text-secondary: #475d60;',
      '--action: #006b60;',
      '--series-1: #2a78d6;',
    ]) expect(firstRoot).toContain(line);
  });

  it('turn to the civic-ui dark roles under the system preference and the explicit theme', () => {
    expect(darkBlocks).toHaveLength(2);
    for (const block of darkBlocks) {
      for (const line of ['--surface-0: #142323;', '--surface-1: #203332;', '--text-primary: #f0f6f5;', '--action: #b5e8dc;'])
        expect(block).toContain(line);
    }
  });

  it('give civic-ui controls the family action colour, not the text colour', () => {
    expect(pilot).toContain('--civic-action: var(--action);');
    expect(pilot).toContain('--civic-border: var(--border-strong);');
    expect(pilot).not.toContain('--civic-action: var(--text-primary);');
  });
});

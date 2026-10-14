// The page is light first on civic-ui roles (UX-13, ux-guidelines § 6 and § 9.1): the plain
// `:root` block is the light palette; dark is the opt-in under prefers-color-scheme.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), 'style.css'), 'utf8');

const CIVIC_LIGHT: Record<string, string> = {
  '--bg': '#f4f6f6',
  '--fg': '#182b2c',
  '--muted': '#475d60',
  '--card': '#ffffff',
  '--line': '#718588',
  '--link': '#006b60',
};

describe('the palette', () => {
  const media = [...css.matchAll(/@media\s*\(prefers-color-scheme:\s*(\w+)\)\s*\{/g)];

  it('has only a dark override', () => {
    expect(media.map((m) => m[1])).toEqual(['dark']);
  });

  it('is the civic-ui light palette by default', () => {
    const base = css.slice(0, media[0].index);
    const root = /:root\s*\{([^}]*)\}/.exec(base)?.[1] ?? '';
    expect(root).toContain('color-scheme: light;');
    for (const [name, value] of Object.entries(CIVIC_LIGHT)) expect(root).toContain(`${name}: ${value};`);
  });

  it('turns dark only when the system asks', () => {
    const dark = css.slice(media[0].index);
    expect(dark).toContain('--bg: #142323;');
    expect(dark).toContain('--fg: #f0f6f5;');
  });
});

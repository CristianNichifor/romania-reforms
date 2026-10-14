// UX-19 (ux-guidelines § 5, design criterion 7): the loader turns into its slow stage after
// two seconds, a failed load names the failure and offers to try again, and main.ts wires both.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { LOADING_SLOW, RETRY, SLOW_AFTER_MS, loadErrorMarkup, messageOf } from '../src/states';

const main = readFileSync(join(import.meta.dirname, '../src/main.ts'), 'utf8');

describe('the page states', () => {
  it('stage the loader after two seconds', () => {
    expect(SLOW_AFTER_MS).toBe(2000);
    expect(LOADING_SLOW).toMatch(/durează mai mult/);
    expect(main).toContain('stageLoader(');
  });

  it('name the failure and offer a retry, escaped', () => {
    const html = loadErrorMarkup('<b>404</b> & gone');
    expect(html).toContain('Nu s-au putut încărca datele: &lt;b&gt;404&lt;/b&gt; &amp; gone');
    expect(html).toContain(`<button type="button" class="retry">${RETRY}</button>`);
    expect(messageOf(new Error('x'))).toBe('x');
    expect(messageOf(7)).toBe('7');
    expect(main).toContain('loadErrorMarkup(');
    expect(main).toMatch(/\.retry[^\n]*location\.reload/);
  });
});

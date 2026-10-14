// The error and empty states say what happened and what to do next (UX-12).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { noHit } from '../src/HomeView';
import LoadError from '../src/LoadError';
import ViewSource from '../src/ViewSource';
import { STRINGS } from '../src/i18n';

describe('the error state', () => {
  it.each(['ro', 'en'] as const)('in %s names the failure and offers to try again', (lang) => {
    const t = STRINGS[lang];
    const html = renderToStaticMarkup(<LoadError message={t.loadError('regimes')} retry={t.retry} />);
    expect(html).toContain('role="alert"');
    expect(html).toContain(t.loadError('regimes'));
    expect(html).toMatch(new RegExp(`<button type="button"[^>]*>${t.retry}</button>`));
  });

  it('calls the action Reîncearcă in Romanian and Try again in English', () => {
    expect(STRINGS.ro.retry).toBe('Reîncearcă');
    expect(STRINGS.en.retry).toBe('Try again');
  });
});

describe('the empty search', () => {
  it('names what was typed and says what to try', () => {
    const text = noHit(' farmacist primr ');
    expect(text).toContain('„farmacist primr"');
    expect(text).toMatch(/caută/);
  });
});

describe('the source line of a secondary view', () => {
  it('prints the short data line', () => {
    const html = renderToStaticMarkup(<ViewSource text={STRINGS.ro.dataLine} />);
    expect(html).toBe(`<p class="view-source">${STRINGS.ro.dataLine}</p>`);
  });

  it('closes every secondary view once it has drawn (UX-35)', () => {
    const app = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../src/App.tsx'), 'utf8');
    // One line for all views, after the last of them and before the footer: a view added later
    // cannot forget it, and the first screen keeps its own line under the H1.
    const lines = app.split('<ViewSource ');
    expect(lines).toHaveLength(2);
    const [before, after] = lines;
    expect(after.indexOf('<footer>')).toBeGreaterThan(0);
    expect(before.lastIndexOf("scenario.view === '")).toBeLessThan(before.length);
    expect(before.slice(before.lastIndexOf('\n'))).toContain("scenario.view !== 'acasa' && !error && loaded.length > 0 &&");
    for (const view of ['compare', 'propunere', 'distributie', 'functii', 'domenii', 'meserii', 'echivalente', 'structure', 'envelope', 'payslip']) {
      expect(before).toContain(`scenario.view === '${view}'`);
    }
  });
});

describe('the loader', () => {
  it.each(['ro', 'en'] as const)('in %s has a second stage that begins like the first', (lang) => {
    const t = STRINGS[lang];
    expect(t.loadingSlow).not.toBe(t.loading);
    expect(t.loadingSlow.startsWith(t.loading)).toBe(true);
  });

  it('switches stages after two seconds', () => {
    const app = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../src/App.tsx'), 'utf8');
    expect(app).toContain('setSlow(true), 2000)');
    expect(app).toContain('{slow ? t.loadingSlow : t.loading}');
  });
});

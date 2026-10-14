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

  it('closes the distribution and domains views, which draw figures without one', () => {
    const app = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../src/App.tsx'), 'utf8');
    for (const view of ['DistributionView', 'DomainsView']) {
      const after = app.slice(app.indexOf(`<${view}\n`));
      expect(after.indexOf('<ViewSource text={t.dataLine} />')).toBeLessThan(after.indexOf('</>'));
    }
  });
});

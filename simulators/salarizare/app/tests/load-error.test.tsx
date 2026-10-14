// The error state carries a retry button (design screen 03, criterion 7), in both languages.
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import LoadError from '../src/LoadError';
import { STRINGS } from '../src/i18n';

describe('the error state', () => {
  it('names the failure and offers to try again', () => {
    const html = renderToStaticMarkup(
      <LoadError message={STRINGS.ro.loadError('HTTP 500')} retryLabel={STRINGS.ro.retry} onRetry={() => undefined} />,
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain('Nu s-au putut încărca datele: HTTP 500');
    expect(html).toMatch(/<button[^>]*type="button"[^>]*>Reîncearcă<\/button>/);
  });

  it('is translated', () => {
    expect(STRINGS.en.retry).toBe('Try again');
  });
});

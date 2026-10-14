// The loader says "loading" at once and "computing" after two seconds (screen 03, criterion 7).
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import Loader, { LOADER_STAGE_MS, loaderText } from '../src/Loader';
import { STRINGS } from '../src/i18n';

describe('the loader', () => {
  it('changes its text after two seconds', () => {
    expect(LOADER_STAGE_MS).toBe(2000);
    expect(loaderText(0, 'a', 'b')).toBe('a');
    expect(loaderText(1999, 'a', 'b')).toBe('a');
    expect(loaderText(2000, 'a', 'b')).toBe('b');
  });

  it('renders the first text at once as a live status', () => {
    const html = renderToStaticMarkup(<Loader first={STRINGS.ro.loading} later={STRINGS.ro.loadingLater} />);
    expect(html).toMatch(/<p class="loading" role="status" aria-live="polite">Se încarcă grila…<\/p>/);
  });

  it('has both texts in both languages', () => {
    expect(STRINGS.ro.loadingLater).toBe('Se calculează…');
    expect(STRINGS.en.loadingLater).toBe('Computing…');
  });
});

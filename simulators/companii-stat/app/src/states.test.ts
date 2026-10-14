// Loading and error states (design screens, criterion 7).
import { describe, expect, it } from 'vitest';

import { LOADER_STAGE_MS, RETRY_LABEL, errorStateHtml, loaderText } from './states';

describe('the loader', () => {
  it('changes its text after two seconds', () => {
    expect(LOADER_STAGE_MS).toBe(2000);
    expect(loaderText(0, 'a', 'b')).toBe('a');
    expect(loaderText(1999, 'a', 'b')).toBe('a');
    expect(loaderText(2000, 'a', 'b')).toBe('b');
  });
});

describe('the error state', () => {
  it('names the failure and offers to try again', () => {
    const html = errorStateHtml('HTTP 500 pentru data/x.json');
    expect(html).toContain('Nu s-au putut încărca datele: HTTP 500 pentru data/x.json');
    expect(html).toMatch(/<button type="button" class="civic-button retry">Reîncearcă<\/button>/);
    expect(RETRY_LABEL).toBe('Reîncearcă');
  });

  it('escapes the message', () => {
    expect(errorStateHtml('<b>')).toContain('&lt;b&gt;');
  });
});

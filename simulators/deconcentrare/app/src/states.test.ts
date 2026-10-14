import { describe, expect, it } from 'vitest';

import { LOADING, LOADING_SLOW, RETRY, SLOW_AFTER_MS, loadErrorMarkup, messageOf } from './states';

describe('the error state', () => {
  it('names the failure and offers to try again', () => {
    const html = loadErrorMarkup('HTTP 404 pentru data/x.json');
    expect(html).toContain('Nu s-au putut încărca datele: HTTP 404 pentru data/x.json');
    expect(html).toContain(`<button type="button" class="retry">${RETRY}</button>`);
    expect(RETRY).toBe('Reîncearcă');
  });

  it('escapes the message, which may quote a URL or a server page', () => {
    expect(loadErrorMarkup('<b>&"')).toContain('&lt;b&gt;&amp;&quot;');
  });

  it('reads the message of anything thrown', () => {
    expect(messageOf(new Error('x'))).toBe('x');
    expect(messageOf('y')).toBe('y');
  });
});

describe('the loader', () => {
  it('has a second stage after two seconds that begins like the first', () => {
    expect(SLOW_AFTER_MS).toBe(2000);
    expect(LOADING_SLOW).not.toBe(LOADING);
    expect(LOADING_SLOW.startsWith(LOADING)).toBe(true);
  });
});

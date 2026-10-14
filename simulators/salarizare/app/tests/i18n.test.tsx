// The salary simulator in English (RR-10): the language comes from `lang=` in the hash, as in
// the administrative simulator, defaults to Romanian, and survives the scenario round trip.
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it } from 'vitest';

import { decodeScenario, encodeScenario } from '../../engine/scenario';
import type { ViewId } from '../../engine/scenario';
import App from '../src/App';
import { STRINGS, langOf, withLang } from '../src/i18n';

const at = (hash: string) =>
  Object.defineProperty(globalThis, 'location', { value: { hash }, configurable: true, writable: true });

afterEach(() => {
  Reflect.deleteProperty(globalThis, 'location');
});

describe('the language', () => {
  it('is Romanian unless the link says English', () => {
    expect(langOf(decodeScenario(''))).toBe('ro');
    expect(langOf(decodeScenario('#/compare?lang=en'))).toBe('en');
    expect(langOf(decodeScenario('#/compare?lang=xx'))).toBe('ro');
  });

  it('survives the scenario round trip', () => {
    const scenario = withLang(decodeScenario('#/payslip?p=X'), 'en');
    expect(langOf(decodeScenario(encodeScenario(scenario)))).toBe('en');
    expect(encodeScenario(withLang(scenario, 'ro'))).not.toContain('lang=');
  });

  it('labels every view in both languages', () => {
    const views = Object.keys(STRINGS.ro.views) as ViewId[];
    expect(Object.keys(STRINGS.en.views).sort()).toEqual([...views].sort());
    for (const id of views) expect(STRINGS.en.views[id].label).not.toBe(STRINGS.ro.views[id].label);
  });
});

describe('the app shell', () => {
  it('renders in Romanian by default', () => {
    at('#/acasa');
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('lang="ro"');
    expect(html).toContain('Ce se schimbă');
    expect(html).toContain('>English<');
  });

  it('renders in English from the link', () => {
    at('#/acasa?lang=en');
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('lang="en"');
    expect(html).toContain('What changes');
    expect(html).toContain('Sections of the tool');
    expect(html).toContain('>Română<');
    const nav = /<nav class="tabs".*?<\/nav>/s.exec(html)?.[0] ?? '';
    expect(nav).not.toContain('Ce se schimbă');
    expect(html).toContain('the views themselves are in Romanian for now');
  });
});

describe('severities', () => {
  it('are printed in Romanian, not as the engine keys', async () => {
    const { SEVERITY_LABELS } = await import('../src/i18n');
    expect(SEVERITY_LABELS).toEqual({ blocking: 'blocant', material: 'important', note: 'de reținut' });
  });
});

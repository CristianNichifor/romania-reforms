// The public-pay layout after the UX review (UX-7): the H1 and its lead come first, the
// function search follows the lead, and the eleven-card menu sits below them. Codes and
// footnote markers from the source sheets are shown as what they are, never alone.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it } from 'vitest';

import type { Regime } from '../../engine/types';
import App from '../src/App';
import NoHit from '../src/NoHit';
import StructureView from '../src/StructureView';
import { PositionName, regimeLabel, splitFootnotes } from '../src/names';

const data = resolve(dirname(fileURLToPath(import.meta.url)), '../../data');
const inForce = JSON.parse(readFileSync(resolve(data, 'regimes/ro-153-2017.json'), 'utf8')) as Regime;

const at = (hash: string) =>
  Object.defineProperty(globalThis, 'location', { value: { hash }, configurable: true, writable: true });

afterEach(() => {
  Reflect.deleteProperty(globalThis, 'location');
});

const order = (html: string, ...needles: string[]) => needles.map((n) => html.indexOf(n));

describe('the first screen', () => {
  it('leads with the title, then the search, then the menu', () => {
    at('#/acasa');
    const html = renderToStaticMarkup(<App />);
    const [h1, search, nav] = order(html, '<h1', 'id="home-search"', '<nav class="tabs"');
    expect(h1).toBeGreaterThan(-1);
    expect(search).toBeGreaterThan(h1);
    expect(nav).toBeGreaterThan(search);
    expect(html.match(/<nav class="tabs"/g)).toHaveLength(1);
  });

  it('puts the menu under the title of every other view', () => {
    const html = renderToStaticMarkup(
      <StructureView regime={inForce} period={null} menu={<nav className="tabs" />} />,
    );
    const [h1, nav] = order(html, '<h1', '<nav class="tabs"');
    expect(h1).toBeGreaterThan(-1);
    expect(nav).toBeGreaterThan(h1);
  });
});

describe('names from the source sheets', () => {
  it('separates the footnote markers from the name', () => {
    expect(splitFootnotes('Farmacist primar*1)')).toEqual({ base: 'Farmacist primar', markers: ['*1)'] });
    expect(splitFootnotes('Director unitate de învățământ*) **)')).toEqual({
      base: 'Director unitate de învățământ',
      markers: ['*)', '**)'],
    });
    expect(splitFootnotes('Contabil-șef*) - nivel maxim')).toEqual({
      base: 'Contabil-șef - nivel maxim',
      markers: ['*)'],
    });
    expect(splitFootnotes('Consilier')).toEqual({ base: 'Consilier', markers: [] });
  });

  it('renders a marker as a labelled superscript, never as bare punctuation', () => {
    const html = renderToStaticMarkup(<PositionName name="Farmacist primar*1)" />);
    expect(html).toContain('Farmacist primar');
    expect(html).toMatch(/<sup[^>]*aria-label="[^"]*tabelul sursă[^"]*"[^>]*>\*1\)<\/sup>/);
    expect(html).not.toContain('primar*1)');
  });

  it('shows the code only as a secondary detail next to the name', () => {
    const html = renderToStaticMarkup(<PositionName name="Rector*)" code="153.I.1.1" />);
    expect(order(html, 'Rector', '153.I.1.1')[0]).toBeLessThan(order(html, 'Rector', '153.I.1.1')[1]);
    expect(html).toMatch(/<code[^>]*>153\.I\.1\.1<\/code>/);
  });

  it('names a regime by its law, not its file id', () => {
    expect(regimeLabel('ro-153-2017', { 'ro-153-2017': inForce })).toBe('Legea-cadru 153/2017');
    expect(regimeLabel('dk-stat-2026', {})).toBe('dk-stat-2026');
  });
});

describe('the empty state of the search', () => {
  it('names the query and suggests what to try (screen 03, criterion 7)', () => {
    const html = renderToStaticMarkup(<NoHit query=" farmacist primr " />);
    expect(html).toContain('role="status"');
    expect(html).toContain('„farmacist primr”');
    expect(html).toMatch(/încearcă .*sau alege o secțiune din meniu/);
  });
});

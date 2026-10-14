// Every page of this simulator links home and all seven simulators, and carries the site's
// Content Security Policy once built (RR-3, RR-9). Runs this app's own Vite config, so a
// simulator that stops registering the shared shell fails here.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import config from '../vite.config';

type Shell = { name: string; transformIndexHtml(html: string, ctx: { server?: unknown }): string };

const isShell = (plugin: unknown): plugin is Shell =>
  typeof plugin === 'object' && plugin !== null && (plugin as Shell).name === 'romania-reforms-site-shell';

const shell = [config.plugins ?? []].flat(3).find(isShell);

describe.each(['index.html', 'statistici.html'])('%s', (page) => {
  const html = readFileSync(new URL(`../${page}`, import.meta.url), 'utf8');

  it('links home and all seven simulators, marking this one', () => {
    expect(shell).toBeDefined();
    const built = shell!.transformIndexHtml(html, {});
    const nav = /<nav class="rr-nav" aria-label="Simulatoare">.*?<\/nav>/.exec(built)?.[0] ?? '';
    expect(nav.match(/<a /g)).toHaveLength(8);
    expect(nav).toContain('<a href="../">Toate simulatoarele</a>');
    expect(nav).toContain('<a href="../justitie/" aria-current="page">');
  });

  it('carries the Content Security Policy in the built page only', () => {
    expect(shell!.transformIndexHtml(html, {})).toContain('http-equiv="Content-Security-Policy"');
    expect(shell!.transformIndexHtml(html, { server: {} })).not.toContain('Content-Security-Policy');
  });
});

it('index.html reads title, purpose, then the data line with the one status badge (UX-5, screen criteria 3-4)', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  expect(html).toMatch(
    /<h1[^>]*>[^<]*<\/h1>\s*<p class="sub" id="sub"><\/p>\s*<p class="data-line"><span id="data-line"><\/span> <span class="badge status">Date reale<\/span><\/p>/,
  );
  expect(html.match(/class="badge[ "]/g)).toHaveLength(1);
});

it('statistici.html reads title, purpose, then the data line with the one status badge (screen criteria 3-4)', () => {
  const html = readFileSync(new URL('../statistici.html', import.meta.url), 'utf8');
  expect(html).toMatch(
    /<h1>[^<]*<\/h1>\s*<p>[^]*?<\/p>\s*<p class="data-line"><span id="data-line"><\/span> <span class="badge status">Date reale<\/span><\/p>/,
  );
  expect(html.match(/class="badge[ "]/g)).toHaveLength(1);
});

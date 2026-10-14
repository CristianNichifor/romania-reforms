// Page-level checks the ux guideline asks for (§9 item 9; design screens, criteria 1 and 8),
// on every view, not only the first screen (UX-33): at phone width no view scrolls sideways,
// axe reports no serious or critical issue on the whole page, and no view raises a JS error.
// Same harness as the other check-*.mjs scripts: one preview server, one browser engine per
// run, results written to a temp folder whose path is printed as JSON for check-ui-browsers.mjs.
// Every view is measured before anything is asserted, so one run reports every problem.
import { chromium, firefox, webkit, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

/** Every view the hash router knows (engine/scenario.ts `ViewId`), first screen first. */
const VIEWS = [
  'acasa', 'compare', 'propunere', 'structure', 'distributie', 'domenii',
  'meserii', 'payslip', 'echivalente', 'envelope', 'functii',
];

const browserName = process.env.CIVIC_BROWSER || 'chromium';
const output = await mkdtemp(join(tmpdir(), 'pay-civic-ui-page-'));
const port = process.env.DEMO_PORT || '5201';
const origin = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', port, '--strictPort'], {
  cwd: fileURLToPath(new URL('../', import.meta.url)), stdio: 'ignore',
});
const exit = new Promise(resolve => server.once('exit', resolve));
let browser;
try {
  for (let i = 0; i < 60; i++) {
    if (server.exitCode !== null) throw new Error('Server exited');
    try { if ((await fetch(origin)).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  browser = await { chromium, firefox, webkit }[browserName].launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('http') && new URL(url).origin !== origin) return route.abort();
    return route.continue();
  });

  const results = [];
  for (const view of VIEWS) {
    const before = errors.length;
    await page.goto(`${origin}/#/${view}`);
    await expect(page.locator(`nav button.on[data-view="${view}"]`)).toHaveCount(1);
    // Data files load once and are then cached; a view that is still computing says so.
    await expect(page.locator('p.loading')).toHaveCount(0, { timeout: 30_000 });
    await page.waitForLoadState('networkidle');

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    const serious = violations
      .filter(v => v.impact === 'serious' || v.impact === 'critical')
      .map(({ id, impact, nodes }) => ({ id, impact, targets: nodes.slice(0, 5).map(node => node.target) }));
    await page.screenshot({ path: join(output, `${view}-390.png`), fullPage: true });
    results.push({ view, overflow, serious, errors: errors.slice(before) });
  }
  await writeFile(join(output, 'results.json'), JSON.stringify({ browserName, results }, null, 2));

  const sideways = results.filter(r => r.overflow.scrollWidth > r.overflow.clientWidth + 1).map(r => `${r.view}: ${JSON.stringify(r.overflow)}`);
  const issues = results.filter(r => r.serious.length).map(r => `${r.view}: ${JSON.stringify(r.serious)}`);
  const thrown = results.filter(r => r.errors.length).map(r => `${r.view}: ${r.errors.join(' | ')}`);
  assert.deepEqual(sideways, [], 'views scroll sideways at 390 px');
  assert.deepEqual(issues, [], 'axe reports serious or critical issues');
  assert.deepEqual(thrown, [], 'page errors');
  console.log(JSON.stringify({ browserName, output, views: results.length, serious: 0, overflow: false }));
} finally {
  if (browser) await browser.close();
  server.kill();
  await exit;
}

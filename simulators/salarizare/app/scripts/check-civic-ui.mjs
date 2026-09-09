import { chromium, firefox, webkit } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { mkdir, mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const stage = 'after';
const browserName = process.env.CIVIC_BROWSER || 'chromium';
const browserType = { chromium, firefox, webkit }[browserName];
assert.ok(browserType, `Unsupported CIVIC_BROWSER: ${browserName}`);
const app = fileURLToPath(new URL('../', import.meta.url));
const out = (await mkdtemp(join(tmpdir(), 'pay-civic-ui-'))) + '/';
const port = process.env.DEMO_PORT || '5200';
await mkdir(out, { recursive: true });
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', port, '--strictPort'], { cwd: app, stdio: 'ignore' });
const exit = new Promise(resolve => server.once('exit', resolve));
const url = `http://127.0.0.1:${port}/#/echivalente`;
let browser;
const results = [];
try {
  for (let i = 0; i < 60; i++) {
    if (server.exitCode !== null) throw new Error('Server exited');
    try { if ((await fetch(url)).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  browser = await browserType.launch({ executablePath: browserName === 'chromium' ? process.env.DEMO_CHROMIUM : undefined });
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  const external = [];
  page.on('pageerror', e => errors.push(e.message));
  await context.route('**/*', route => {
    const request = route.request().url();
    if (request.startsWith('http') && new URL(request).origin !== new URL(url).origin) { external.push(request); return route.abort(); }
    return route.continue();
  });
  for (const mode of ['light', 'dark']) {
    await page.emulateMedia({ colorScheme: mode });
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(url);
      // Reload a ready screen, not a document whose initial data requests are still starting.
      await page.locator('.ratio-list > *').first().waitFor();
      await page.reload();
      await page.locator('.ratio-list > *').first().waitFor();
      await page.screenshot({ path: `${out}${mode}-${width}.png`, fullPage: true });
      const dimensions = await page.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth }));
      assert.ok(dimensions.document <= width, JSON.stringify(dimensions));
      if (stage === 'after') {
        const select = page.getByLabel('Raportat la', { exact: true });
        assert.equal(await select.evaluate(el => getComputedStyle(el).paddingRight), '44px');
        await select.focus();
        await page.keyboard.press('Tab');
        assert.equal(await page.locator('.anchor-controls input[type=range]').evaluate(el => el === document.activeElement), true);
        await page.keyboard.press('Shift+Tab');
        assert.equal(await select.evaluate(el => el === document.activeElement && getComputedStyle(el).outlineStyle === 'solid'), true);
        const scan = await new AxeBuilder({ page }).include('.civic-pay .civic-field').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        assert.deepEqual(scan.violations, []);
      }
      results.push({ mode, width, dimensions });
    }
  }
  const scenarios = [];
  for (const anchor of ['avg', 'gov', 'floor']) {
    await page.locator('.anchor-controls select').selectOption(anchor);
    assert.equal(await page.locator('.anchor-controls select').inputValue(), anchor);
    for (const years of [0, 35]) {
      await page.locator('.anchor-controls input[type=range]').focus();
      await page.keyboard.press(years === 0 ? 'Home' : 'End');
      assert.equal(await page.locator('.anchor-controls input[type=range]').inputValue(), String(years));
      scenarios.push({ anchor, years, values: await page.locator('.ratio-list').innerText(), benchmarks: await page.locator('.anchors').innerText(), hash: new URL(page.url()).hash });
    }
  }
  if (stage === 'after') {
    if (process.env.CIVIC_BASELINE) {
      const before = JSON.parse(await readFile(process.env.CIVIC_BASELINE, 'utf8'));
      assert.deepEqual(scenarios, before.scenarios, 'Calculated outputs or route changed');
    }
    await context.setOffline(true);
    await page.locator('.anchor-controls select').selectOption('avg');
    assert.equal(await page.locator('.ratio-list').innerText(), scenarios.find(s => s.anchor === 'avg' && s.years === 35).values);
    await context.setOffline(false);
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  await writeFile(out + 'results.json', JSON.stringify({ stage, browserName, results, scenarios, errors, external }, null, 2));
  console.log(JSON.stringify({ browserName, output: out, layouts: results.length, scenarios: scenarios.length, errors, external, matchesBaseline: Boolean(process.env.CIVIC_BASELINE) }));
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) server.kill('SIGTERM');
  await exit;
}

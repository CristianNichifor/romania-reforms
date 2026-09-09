import { chromium, firefox, webkit, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const before = process.env.CIVIC_STAGE === 'before';
const browserName = process.env.CIVIC_BROWSER || 'chromium';
const browserType = { chromium, firefox, webkit }[browserName];
assert.ok(browserType, `Unsupported CIVIC_BROWSER: ${browserName}`);
const output = await mkdtemp(join(tmpdir(), 'pay-civic-ui-merges-'));
const port = process.env.DEMO_PORT || '5200';
const url = `http://127.0.0.1:${port}/#/functii?r=ro-draft-2026-08-20`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', port, '--strictPort'], {
  cwd: fileURLToPath(new URL('../', import.meta.url)), stdio: 'ignore',
});
const exit = new Promise(resolve => server.once('exit', resolve));
let browser;
try {
  for (let i = 0; i < 60; i++) {
    if (server.exitCode !== null) throw new Error('Server exited');
    try { if ((await fetch(url)).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  browser = await browserType.launch({ executablePath: browserName === 'chromium' ? process.env.DEMO_CHROMIUM : undefined });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  const errors = [];
  const external = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', route => {
    const request = route.request().url();
    if (request.startsWith('http') && new URL(request).origin !== new URL(url).origin) {
      external.push(request);
      return route.abort();
    }
    return route.continue();
  });
  const search = page.getByLabel('Caută o denumire', { exact: true });
  const family = before ? page.locator('.merges-controls select') : page.getByLabel('Familia ocupațională', { exact: true });
  const merged = page.getByLabel('doar funcțiile care chiar comasează', { exact: true });
  const cards = page.locator('.merge-card');
  await page.goto(url);
  await page.waitForLoadState('networkidle');
  await cards.first().waitFor();
  const scenarios = [];
  const snapshot = async name => {
    scenarios.push({ name, hash: new URL(page.url()).hash, cards: await cards.allInnerTexts(), note: await page.locator('.merges-controls + .note').innerText() });
  };
  await snapshot('initial');
  await search.fill('asistent');
  await snapshot('search');
  assert.ok(scenarios[1].cards.length > 0 && scenarios[1].cards.length < scenarios[0].cards.length);
  const matchingFamily = (await cards.first().locator('.merge-meta').innerText()).split(' · ')[0];
  await family.selectOption(matchingFamily);
  await snapshot('combined');
  assert.ok(scenarios[2].cards.length > 0 && scenarios[2].cards.length < scenarios[1].cards.length);
  assert.ok((await cards.locator('.merge-meta').allInnerTexts()).every(text => text.startsWith(`${matchingFamily} · `)));
  await merged.check();
  await snapshot('merged');
  assert.ok(scenarios[3].cards.length > 0 && scenarios[3].cards.length < scenarios[2].cards.length);
  assert.equal(await cards.locator('.badge').count(), scenarios[3].cards.length);
  const bookmarked = page.url();
  await page.reload();
  await page.waitForLoadState('networkidle');
  await search.waitFor();
  assert.equal(await search.inputValue(), 'asistent');
  assert.equal(await family.inputValue(), matchingFamily);
  assert.equal(await merged.isChecked(), true);
  assert.equal(page.url(), bookmarked);
  await expect.poll(() => cards.allInnerTexts()).toEqual(scenarios.at(-1).cards);
  await snapshot('reloaded');
  await search.fill('zzzz-no-matching-function');
  assert.equal(await cards.count(), 0);
  assert.match(await page.locator('.merges-controls + .note').innerText(), /^0 funcții găsite/);
  await snapshot('empty');
  await search.fill('');
  await family.selectOption('');
  await merged.uncheck();
  await snapshot('reset');
  assert.deepEqual(scenarios.at(-1).cards, scenarios[0].cards);
  assert.equal(scenarios.at(-1).hash, scenarios[0].hash);
  await context.setOffline(true);
  await search.fill('asistent');
  assert.deepEqual(await cards.allInnerTexts(), scenarios[1].cards);
  await context.setOffline(false);
  const longestFamily = await family.locator('option').evaluateAll(options =>
    options.filter(option => option.value).sort((a, b) => b.text.length - a.text.length)[0].value,
  );
  await family.selectOption(longestFamily);
  const layouts = [];
  for (const mode of ['light', 'dark']) {
    await page.emulateMedia({ colorScheme: mode });
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await search.fill('');
      const dimensions = await page.locator('.merges-controls').evaluate(el => {
        const box = el.getBoundingClientRect();
        return { left: box.left, right: box.right, scroll: el.scrollWidth, width: el.clientWidth };
      });
      assert.ok(dimensions.left >= 0 && dimensions.right <= width && dimensions.scroll <= dimensions.width, JSON.stringify(dimensions));
      for (const control of [search, family]) {
        const box = await control.boundingBox();
        assert.ok(box && box.x >= 0 && box.x + box.width <= width);
      }
      if (!before) {
        assert.equal(await family.evaluate(el => getComputedStyle(el).paddingRight), '44px');
        await search.focus();
        await page.keyboard.press('Tab');
        assert.equal(await family.evaluate(el => el === document.activeElement && getComputedStyle(el).outlineStyle === 'solid'), true);
        await page.keyboard.press('Tab');
        assert.equal(await merged.evaluate(el => el === document.activeElement), true);
        await page.keyboard.press('Shift+Tab');
        await page.keyboard.press('Shift+Tab');
        assert.equal(await search.evaluate(el => el === document.activeElement && getComputedStyle(el).outlineStyle === 'solid'), true);
        const scan = await new AxeBuilder({ page }).include('.merges-controls .civic-field').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        assert.deepEqual(scan.violations, []);
      }
      await page.locator('.merges-controls').screenshot({ path: join(output, `${mode}-${width}.png`) });
      layouts.push({ mode, width, dimensions });
    }
  }
  if (process.env.CIVIC_MERGES_BASELINE) {
    const baseline = JSON.parse(await readFile(process.env.CIVIC_MERGES_BASELINE, 'utf8'));
    // Engines insert different tabs/newlines around table cells; retain all text and amounts.
    const normalize = items => items.map(item => ({
      ...item,
      cards: item.cards.map(text => text.replace(/\s+/g, ' ').trim()),
      note: item.note.replace(/\s+/g, ' ').trim(),
    }));
    assert.deepEqual(normalize(scenarios), normalize(baseline.scenarios), 'Filter results, amounts or URL state changed');
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  await writeFile(join(output, 'results.json'), JSON.stringify({ browserName, scenarios, layouts, errors, external }, null, 2));
  console.log(JSON.stringify({ browserName, output, layouts: layouts.length, scenarios: scenarios.length, matchesBaseline: Boolean(process.env.CIVIC_MERGES_BASELINE) }));
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) server.kill('SIGTERM');
  await exit;
}

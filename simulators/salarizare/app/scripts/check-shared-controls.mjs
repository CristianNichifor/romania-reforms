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
const output = await mkdtemp(join(tmpdir(), 'pay-civic-ui-controls-'));
const port = process.env.DEMO_PORT || '5200';
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
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [], external = [], scenarios = [], layouts = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('http') && new URL(url).origin !== origin) {
      external.push(url);
      return route.abort();
    }
    return route.continue();
  });
  const open = async route => {
    await context.setOffline(false);
    await page.goto(`${origin}/#/${route}`);
    await page.locator('.masthead h1').waitFor();
    await page.waitForLoadState('networkidle');
  };
  const snapshot = async name => {
    if (!before) {
      const uncomposed = await page.locator('.civic-input, .civic-select').evaluateAll(els => els
        .filter(el => !el.closest('.civic-field') || !el.closest('.civic-scope') || !el.labels?.length)
        .map(el => el.outerHTML));
      assert.deepEqual(uncomposed, [], 'Shared inputs/selects require scoped Field composition and a label');
    }
    scenarios.push({ name, hash: new URL(page.url()).hash,
      // Preserve every rendered value and table row, including collapsed detail data.
      text: await page.locator('.wrap > :not(nav)').evaluateAll(els => els.map(el => {
        const copy = el.cloneNode(true);
        // These two formerly placeholder-only fields gain visible labels; data/copy otherwise match.
        copy.querySelectorAll('label[for="home-search"], label[for^="move-why-"]').forEach(label => label.remove());
        return copy.textContent;
      })),
      tables: await page.locator('table').allTextContents(),
      checked: await page.locator('input[type=checkbox]').evaluateAll(els => els.map(el => [el.checked, el.disabled])),
    });
  };
  const layout = async (name, selector) => {
    for (const mode of ['light', 'dark']) {
      await page.emulateMedia({ colorScheme: mode });
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        if (!before) {
          const scope = name.startsWith('proposal') ? selector : `${selector} .civic-choice, ${selector} .civic-field`;
          const violations = (await new AxeBuilder({ page }).include(scope).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
          assert.deepEqual(violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) })), []);
          const controls = page.locator(`${selector} input:not([type=range]), ${selector} select, ${selector} button`);
          for (const el of await controls.all()) {
            const box = await el.boundingBox();
            if (box) assert.ok(box.x >= 0 && box.x + box.width <= width + 1, `${name}: ${JSON.stringify(box)}`);
          }
        }
        await page.locator(selector).screenshot({ path: join(output, `${name}-${mode}-${width}.png`) });
        layouts.push({ name, mode, width });
      }
    }
  };
  const tableLayouts = async name => {
    if (before) return;
    await page.locator('details:has(table)').evaluateAll(els => els.forEach(el => { el.open = true; }));
    const semantics = await new AxeBuilder({ page }).include('.civic-table-scroll').withTags(['wcag2a']).analyze();
    assert.deepEqual(semantics.violations.map(({ id, nodes }) => ({ id, targets: nodes.map(node => node.target) })), [], 'Table accessibility semantics');
    for (const mode of ['light', 'dark']) {
      await page.emulateMedia({ colorScheme: mode });
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        const tables = page.locator('.civic-table-scroll:visible');
        assert.ok(await tables.count() > 0, `${name} must render shared tables`);
        await page.keyboard.press('Tab');
        for (const region of await tables.all()) {
          await expect(region).toHaveAttribute('role', 'region');
          assert.ok(await region.getAttribute('aria-label'));
          await region.focus();
          await expect(region).toHaveCSS('outline-style', 'solid');
          const dimensions = await region.evaluate(el => {
            const box = el.getBoundingClientRect();
            return { left: box.left, right: box.right, nested: Boolean(el.parentElement.closest('.civic-table-scroll, .chart-scroll, .table-scroll')) };
          });
          assert.ok(dimensions.left >= 0 && dimensions.right <= width + 1 && !dimensions.nested, `${name}: ${JSON.stringify(dimensions)}`);
          if (await region.evaluate(el => el.scrollWidth > el.clientWidth)) {
            await region.evaluate(el => { el.scrollLeft = 0; });
            await page.keyboard.press('ArrowRight');
            await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
            await region.evaluate(el => { el.scrollLeft = 0; });
          }
          assert.equal(await region.locator('.num').evaluateAll(cells => cells.every(cell => getComputedStyle(cell).textAlign === 'right')), true);
        }
        await tables.first().screenshot({ path: join(output, `${name}-table-${mode}-${width}.png`) });
        layouts.push({ name: `${name}-table`, mode, width });
      }
    }
  };
  await open('acasa');
  await page.locator('input[type=search]').fill('auditor');
  await snapshot('home-search');
  await open('propunere');
  await snapshot('proposal-initial');
  await page.getByRole('button', { name: 'stinge tot', exact: true }).click();
  await snapshot('proposal-off');
  await page.getByRole('button', { name: 'doar reparațiile', exact: true }).click();
  await snapshot('proposal-repairs');
  const patch = page.locator('.patch input[type=checkbox]').first();
  await page.keyboard.press('Tab');
  await expect(patch).toBeFocused();
  await page.keyboard.press('Space');
  if (!before) await expect(patch).toHaveCSS('outline-style', 'solid');
  await snapshot('proposal-toggle');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await snapshot('proposal-reloaded');
  await page.getByRole('button', { name: 'pornește tot', exact: true }).click();
  await snapshot('proposal-reset');
  await layout('proposal', '.patches');
  await page.getByRole('button', { name: 'stinge tot', exact: true }).click();
  await page.locator('.patch details').evaluateAll(els => els.forEach(el => { el.open = true; }));
  await layout('proposal-off-expanded', '.patches');

  await open('meserii');
  await snapshot('occupations-initial');
  const occupationChecks = page.locator('.occ-controls input[type=checkbox]');
  for (let i = 0; i < 2; i++) {
    await occupationChecks.nth(i).focus();
    await page.keyboard.press('Space');
    await snapshot(`occupations-toggle-${i}`);
  }
  await page.locator('.sector-filter button').nth(1).click();
  await snapshot('occupations-sector');
  await layout('occupations', '.occ-controls');
  await tableLayouts('occupations');

  await open('envelope');
  await snapshot('envelope-initial');
  await page.locator('.move-row input[type=range]').first().fill('5');
  await page.locator('.move-row input[type=text]').fill('Exemplu de justificare');
  await snapshot('envelope-move');
  const capChecks = page.locator('.occ-controls input[type=checkbox]');
  for (let i = 0; i < 2; i++) {
    await capChecks.nth(i).focus();
    await page.keyboard.press('Space');
    await snapshot(`cap-toggle-${i}`);
  }
  await layout('cap', '.occ-controls');
  await tableLayouts('cap');

  await open('payslip?r=ro-draft-2026-08-20');
  await page.locator('input[type=search]').fill('Părinte social');
  const positions = page.locator('select[size]');
  const code = '21.00303045.04';
  const position = positions.locator(`option[value="${code}"]`);
  await expect(position).toHaveCount(1);
  await positions.selectOption(code);
  await snapshot('payslip-position');
  await page.locator('input[type=range]').last().fill('35');
  await snapshot('payslip-seniority');
  const variants = page.locator('select:not([size])');
  if (await variants.count()) {
    await variants.selectOption({ index: 1 });
    await snapshot('payslip-variant');
  }
  const claims = page.locator('.claims input:not(:disabled)');
  assert.ok(await claims.count() > 0);
  await claims.first().focus();
  await page.keyboard.press('Space');
  await snapshot('payslip-claim');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await snapshot('payslip-reloaded');
  await context.setOffline(true);
  await page.locator('.claims input:not(:disabled)').first().uncheck();
  await snapshot('payslip-offline-unclaim');
  if (!before) {
    const regimes = page.locator('.regimes input[type=checkbox]');
    const initialRegimes = await regimes.evaluateAll(els => els.map(el => el.checked));
    const originalHash = new URL(page.url()).hash;
    assert.equal(initialRegimes.filter(Boolean).length, 1);
    const current = page.locator('.regimes input:checked');
    await current.click();
    await expect(page.locator('.regimes input:checked')).toHaveCount(1);
    const guardedRegimes = await regimes.evaluateAll(els => els.map(el => el.checked));
    assert.equal(guardedRegimes[0], true, 'The final-regime guard selects the first available regime');
    const guardedHash = new URL(page.url()).hash;
    const additional = page.locator('.regimes input:not(:checked)').first();
    await additional.check();
    await expect(page.locator('.regimes input:checked')).toHaveCount(2);
    assert.notEqual(new URL(page.url()).hash, guardedHash);
    const checked = page.locator('.regimes input[type=checkbox]');
    const addedIndex = guardedRegimes.findIndex(value => !value);
    await checked.nth(addedIndex).uncheck();
    assert.equal(new URL(page.url()).hash, guardedHash);
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {
      configurable: true, value: { writeText: async text => { window.__copiedScenario = text; } },
    }));
    await page.getByRole('button', { name: 'copiază linkul scenariului', exact: true }).click();
    await expect(page.getByRole('button', { name: 'link copiat', exact: true })).toBeVisible();
    assert.equal(await page.evaluate(() => window.__copiedScenario), page.url());
    await regimes.nth(initialRegimes.indexOf(true)).check();
    for (let i = 0; i < initialRegimes.length; i++) if (!initialRegimes[i]) await regimes.nth(i).uncheck();
    assert.equal(new URL(page.url()).hash, originalHash);
  }
  await layout('payslip', '.card.controls');
  await tableLayouts('payslip');
  await context.setOffline(false);
  for (const route of ['structure', 'distributie', 'compare', 'functii']) {
    await open(route);
    await snapshot(`tables-${route}`);
    await tableLayouts(route);
  }
  if (process.env.CIVIC_CONTROLS_BASELINE) {
    const baseline = JSON.parse(await readFile(process.env.CIVIC_CONTROLS_BASELINE, 'utf8'));
    const normalize = items => items.map(item => ({ ...item,
      text: item.text.map(text => text.replace(/\s+/g, ' ').trim()),
      tables: item.tables.map(text => text.replace(/\s+/g, ' ').trim()),
    }));
    assert.deepEqual(normalize(scenarios), normalize(baseline.scenarios), 'Values, table order or scenario URLs changed');
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  await writeFile(join(output, 'results.json'), JSON.stringify({ browserName, scenarios, layouts }, null, 2));
  console.log(JSON.stringify({ browserName, output, layouts: layouts.length, scenarios: scenarios.length, matchesBaseline: Boolean(process.env.CIVIC_CONTROLS_BASELINE) }));
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) server.kill('SIGTERM');
  await exit;
}

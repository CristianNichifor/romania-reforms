import { expect, test } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { checkMap } from './map-check';
const baseline = process.env.NATIVE_UI_BASELINE;
test('selected locality native pin field preserves URL and reset', async ({ page }) => {
  await page.goto('/#lang=en&sel=1');
  await expect(page.locator('#loading')).toBeHidden();
  const pin = page.locator('#pin-select');
  await expect(pin).toBeVisible();
  expect(await pin.evaluate(el => !!el.closest('.civic-field') && !!(el as HTMLSelectElement).labels?.length)).toBe(true);
  const targets = await pin.locator('option').evaluateAll(options => options.map(o => (o as HTMLOptionElement).value).filter(Boolean));
  expect(targets.length).toBeGreaterThan(0);
  await pin.selectOption(targets[0]!);
  await expect(page).toHaveURL(/pin=1\./);
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden();
  await expect(pin).toHaveValue(targets[0]!);
  await pin.selectOption('');
  await expect(page).not.toHaveURL(/pin=/);
  const violations = (await new AxeBuilder({ page }).include('.pin-control').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
  expect(violations.map(v => v.id)).toEqual([]);
});
test('filters, saved scenario, reload and language preserve output', async ({ page }, info) => {
  await page.goto('/#lang=en');
  await expect(page.locator('#loading')).toBeHidden();
  await page.locator('#candidates-details > summary').click();
  await expect(page.locator('#candidate-search')).toBeVisible();
  const states: unknown[] = [];
  const record = async () => states.push({
    hash: new URL(page.url()).hash,
    summary: await page.locator('#summary .stat:not(:has(.recompute))').allTextContents(),
    rows: await page.locator('.candidate-showing').textContent(),
    options: await page.locator('#candidate-county option').allTextContents(),
  });
  await record();
  await page.locator('#candidate-search').fill('Alba');
  await record();
  await page.locator('#candidate-search').fill('');
  await page.locator('#candidate-county').selectOption({ index: 1 });
  await record();
  await page.locator('#candidate-county').selectOption('');
  page.once('dialog', dialog => dialog.accept('Browser scenario'));
  await page.locator('#save-version').click();
  await expect(page.locator('[data-open-version]')).toHaveText('Browser scenario');
  const savedHash = new URL(page.url()).hash;
  await page.locator('[data-mode="cost"]').click();
  await expect(page).toHaveURL(/mode=cost/);
  await page.locator('[data-open-version]').click();
  await expect.poll(() => new URL(page.url()).hash).toBe(savedHash);
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden();
  await expect(page.locator('[data-open-version]')).toHaveText('Browser scenario');
  await page.locator('#candidates-details > summary').click();
  await expect(page.locator('#candidate-search')).toBeVisible();
  await record();
  await page.locator('[data-lang="ro"]').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'ro');
  await record();
  await page.locator('[data-drop-version]').click();
  await expect(page.locator('[data-open-version]')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden();
  await expect(page.locator('[data-open-version]')).toHaveCount(0);
  if (baseline) {
    const path = `${baseline}/administrativ-${info.project.name}.json`;
    if (process.env.NATIVE_UI_CAPTURE) { await mkdir(baseline, { recursive: true }); await writeFile(path, JSON.stringify(states)); }
    else expect(states).toEqual(JSON.parse(await readFile(path, 'utf8')));
  }
});

for (const width of [320, 390, 1440]) test(`native controls and map at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 1000 });
  const external: string[] = [];
  await page.route('**/*', route => {
    if (!route.request().url().startsWith('http://127.0.0.1:5194/')) { external.push(route.request().url()); return route.abort(); }
    return route.continue();
  });
  await page.goto('/#lang=en');
  await expect(page.locator('#loading')).toBeHidden();
  await checkMap(page, info);
  if (width < 900) await page.locator('#controls-handle').click();
  const overlay = page.locator('input[data-overlay="regions"]');
  await overlay.focus(); await page.keyboard.press('Space'); await expect(overlay).toBeChecked();
  await page.keyboard.press('Space'); await expect(overlay).not.toBeChecked();
  await page.locator('#candidates-details > summary').click();
  await expect(page.locator('#candidate-search')).toBeVisible();
  for (const id of ['candidate-search', 'candidate-county']) {
    const control = page.locator(`#${id}`);
    expect(await control.evaluate(el => !!el.closest('.civic-field') && !!el.getAttribute('aria-label'))).toBe(true);
    expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    expect(await control.evaluate(el => el.getBoundingClientRect().width >= el.parentElement!.getBoundingClientRect().width - 2)).toBe(true);
    await control.focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    await expect(control).toBeFocused();
    await expect(control).toHaveCSS('outline-style', 'solid');
  }
  await page.locator('#candidate-search').fill('Alba');
  await expect(page.locator('#candidate-search')).toHaveValue('Alba');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const violations = (await new AxeBuilder({ page }).include('.civic-field, .civic-choice, .civic-button').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
  expect(violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  await page.locator('.candidate-filters').screenshot({ path: info.outputPath('filters.png') });
  await page.screenshot({ path: info.outputPath('page.png') });
  expect(external).toEqual([]);
});

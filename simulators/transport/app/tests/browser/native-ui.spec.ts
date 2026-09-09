import { expect, test } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { checkMap } from './map-check';
const baseline = process.env.NATIVE_UI_BASELINE;
test('service levels and scenario URL preserve domain output', async ({ page }, info) => {
  await page.goto('/#s=uncoordinated');
  await expect(page.locator('#levels tbody tr').first()).toBeVisible();
  const states: unknown[] = [];
  const record = async () => states.push({
    hash: new URL(page.url()).hash,
    text: await page.locator('#stats, #cost, #fares, #levels, #rail').allTextContents(),
    options: await page.locator('#level option').allTextContents(),
  });
  await record();
  await page.locator('[data-scenario="pulsed"]').click();
  await expect(page).toHaveURL(/s=pulsed/);
  await record();
  const values = await page.locator('#level option').evaluateAll(options => options.map(o => (o as HTMLOptionElement).value));
  for (const value of values) { await page.locator('#level').selectOption(value); await record(); }
  await page.reload();
  await expect(page.locator('[data-scenario="pulsed"]')).toHaveClass(/on/);
  await expect(page.locator('#levels tbody tr').first()).toBeVisible();
  await record();
  if (baseline) {
    const path = `${baseline}/transport-${info.project.name}.json`;
    if (process.env.NATIVE_UI_CAPTURE) { await mkdir(baseline, { recursive: true }); await writeFile(path, JSON.stringify(states)); }
    else expect(states).toEqual(JSON.parse(await readFile(path, 'utf8')));
  }
});

for (const width of [320, 390, 1440]) test(`native controls and map at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 1000 });
  const external: string[] = [];
  await page.route('**/*', route => {
    if (!route.request().url().startsWith('http://127.0.0.1:5193/')) { external.push(route.request().url()); return route.abort(); }
    return route.continue();
  });
  await page.goto('/');
  await expect(page.locator('#levels tbody tr').first()).toBeVisible();
  await checkMap(page, info);
  const select = page.locator('#level');
  expect(await select.evaluate(el => !!el.closest('.civic-field') && !!(el as HTMLSelectElement).labels?.length)).toBe(true);
  expect((await select.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await select.focus();
  await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
  await expect(select).toBeFocused();
  await expect(select).toHaveCSS('outline-style', 'solid');
  const rail = page.locator('#rail-toggle');
  await rail.focus(); await page.keyboard.press('Space'); await expect(rail).toBeChecked();
  await expect(rail).toBeEnabled();
  await rail.focus();
  await page.keyboard.press('Space'); await expect(rail).not.toBeChecked();
  const region = page.getByRole('region', { name: 'Costul pe niveluri' });
  await expect(region.getByRole('columnheader')).toHaveCount(5);
  await region.focus(); await expect(region).toHaveCSS('outline-style', 'solid');
  if (await region.evaluate(el => el.scrollWidth > el.clientWidth)) {
    await page.keyboard.press('ArrowRight'); await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const violations = (await new AxeBuilder({ page }).include('.civic-field, .civic-choice, .civic-table-scroll').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
  expect(violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  await region.screenshot({ path: info.outputPath('table.png') });
  await select.screenshot({ path: info.outputPath('select.png') });
  expect(external).toEqual([]);
});

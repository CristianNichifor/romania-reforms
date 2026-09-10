import { test, expect } from '@playwright/test';
import { localOnly, mapPixels, settledPixels, jsonEvidence, publicData, formatCount } from './helpers';

test('map modes, real pixels, zoom/pan, ranges, optional layers and reader', async ({ page }, info) => {
  const audit = await localOnly(page);
  await page.route('**/data/roads.geojson', route => route.fulfill({ status: 404, body: 'missing optional roads' }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.locator('#summary')).toContainText('instanțe');
  await expect(page.locator('#summary strong').first()).toHaveText(formatCount(publicData('instante.json').courts.length));
  const initialSummary = await page.locator('#summary').innerText();
  const initial = await mapPixels(page, info, 'today');
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.mouse.move(0, 0);
  expect((await settledPixels(initial.capture)).equals(initial.png)).toBe(false);
  await mapPixels(page, info, 'zoomed');
  const beforePan = await initial.capture();
  await page.mouse.move(1050, 500);
  await page.mouse.down();
  await page.mouse.move(1170, 560, { steps: 12 });
  await page.mouse.up();
  await page.mouse.move(0, 0);
  expect((await settledPixels(initial.capture)).equals(beforePan)).toBe(false);
  await page.locator('[data-mode="proposed"]').click();
  await expect(page.locator('#staffing')).toBeVisible();
  await expect(page.locator('#ceiling')).toBeHidden();
  await expect(page.locator('#summary')).toContainText('instanțe de nivel 1');
  const proposalSummary = await page.locator('#summary').innerText();
  await page.locator('#target').fill('1000');
  await expect(page.locator('#target-value')).toContainText(formatCount(1000));
  await expect(page.locator('#summary')).not.toHaveText(proposalSummary, { useInnerText: true });
  await page.locator('#target').fill('1325');
  await expect(page.locator('#summary')).toHaveText(proposalSummary, { useInnerText: true });
  await mapPixels(page, info, 'proposed');
  // The failure path immediately clears the check; do not ask Playwright to keep it checked.
  await page.locator('#roads-toggle').click();
  await expect(page.locator('#roads-toggle')).toBeDisabled();
  await expect(page.locator('#roads-toggle')).not.toBeChecked();
  await page.locator('#outline-toggle').check();
  await expect.poll(() => audit.requests.some(url => url.endsWith('/data/uats.geojson'))).toBe(true);
  await mapPixels(page, info, 'outlines');
  await page.locator('[data-mode="acces"]').click();
  await expect(page.locator('#ceiling')).toBeVisible();
  await expect(page.locator('#staffing')).toBeHidden();
  await expect.poll(() => audit.requests.some(url => url.endsWith('/data/acces.json'))).toBe(true);
  const accessSummary = await page.locator('#summary').innerText();
  await page.locator('#ceiling-input').fill('0');
  await expect(page.locator('#summary')).not.toHaveText(accessSummary, { useInnerText: true });
  const adjustedAccessSummary = await page.locator('#summary').innerText();
  await mapPixels(page, info, 'access');
  await page.locator('[data-mode="arondare"]').click();
  await expect(page.locator('#summary')).not.toContainText('Se încarcă');
  await expect.poll(() => audit.requests.some(url => url.endsWith('/data/court-distance.bin'))).toBe(true);
  await expect(page.locator('#catchment-note')).toBeVisible();
  await mapPixels(page, info, 'catchments');
  await jsonEvidence(info, 'map-summaries', {
    today: initialSummary, proposed: proposalSummary, access: adjustedAccessSummary,
    catchments: await page.locator('#summary').innerText(),
  });
  await page.locator('[data-mode="today"]').click();
  await expect(page.locator('#summary')).toHaveText(initialSummary, { useInnerText: true });
  await page.context().setOffline(true);
  await page.locator('#reader-open').click();
  await expect(page.locator('#reader')).toBeVisible();
  expect(await page.locator('#reader details').count()).toBeGreaterThan(10);
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => document.querySelector('#reader')!.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(page.locator('#reader')).not.toBeVisible();
  await expect(page.locator('#reader-open')).toBeFocused();
  await page.locator('#reader-open').click();
  await page.locator('#reader-close').click();
  await expect(page.locator('#reader-open')).toBeFocused();
  expect(audit.external).toEqual([]);
  expect(audit.errors).toEqual([]);
});

test('mobile map controls and reading dialog remain within the viewport', async ({ page }, info) => {
  const audit = await localOnly(page);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    await expect(page.locator('#summary')).toContainText('instanțe');
    for (const mode of ['today', 'proposed', 'acces', 'arondare']) {
      await page.locator(`[data-mode="${mode}"]`).click();
      await expect(page.locator(`#panel [data-mode="${mode}"]`)).toHaveClass('on');
      await expect(page.locator('#summary')).not.toContainText('Se încarcă');
      await mapPixels(page, info, `mobile-${mode}-${width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`map-${mode}-${width}.png`) });
    }
    await page.locator('#reader-open').click();
    const reader = page.locator('#reader');
    await expect(reader).toBeVisible();
    const box = (await reader.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    await page.screenshot({ path: info.outputPath(`reader-${width}.png`) });
    await page.keyboard.press('Escape');
  }
  expect(audit.external).toEqual([]);
  expect(audit.errors).toEqual([]);
});

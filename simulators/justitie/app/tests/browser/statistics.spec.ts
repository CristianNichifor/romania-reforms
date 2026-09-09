import { test, expect } from '@playwright/test';
import { pool, type CourtsFile } from '../../src/aggregate';
import { localOnly, publicData, scopeFacts, recordStatistics, formatCount } from './helpers';

const stats = publicData('portal-stats.json');
const courts: CourtsFile = publicData('portal-instante.json');
const county = courts.instante.filter(court => court.judet === 'TM');
const sum = (selection: typeof county) => {
  const pooled = pool(selection, courts.praguriZile);
  return [pooled.dosare, pooled.instante, pooled.amanari.termeneCuSolutie];
};

test('national source, cohort filters, disabled tier and hash round trips', async ({ page }, info) => {
  const audit = await localOnly(page);
  // Deliberately distinguish the authoritative national total from per-court sums.
  const national = structuredClone(stats);
  national.snapshot.dosare = 1234567;
  await page.route('**/data/portal-stats.json', route => route.fulfill({ json: national }));
  await page.goto('/statistici.html#x=9000&keep=baseline');
  await scopeFacts(page, [1234567, stats.snapshot.instante, stats.amanari.termeneCuSolutie]);
  expect(audit.requests.some(url => /admin-|court-distance|maplibre|assets\/main-/.test(url))).toBe(false);
  await recordStatistics(page, info, 'national');
  const historyLength = await page.evaluate(() => history.length);
  await page.locator('#scope').selectOption('j:TM');
  await scopeFacts(page, sum(county));
  await expect(page.locator('[data-national]').first()).toBeVisible();
  await page.locator('#tier').selectOption('judecătorie');
  await scopeFacts(page, sum(county.filter(court => court.level === 'judecătorie')));
  expect(await page.evaluate(() => history.length)).toBe(historyLength);
  expect(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('x')).toBe('9000');
  expect(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('keep')).toBe('baseline');
  const selected = await recordStatistics(page, info, 'county-tier');
  await page.reload();
  await expect(page.locator('#scope')).toHaveValue('j:TM');
  await expect(page.locator('#tier')).toHaveValue('judecătorie');
  expect(await recordStatistics(page, info, 'county-tier-reload')).toEqual(selected);
  const court = county.find(row => row.level === 'judecătorie' && !row.acoperire.trunchiat)!;
  await page.locator('#scope').selectOption(`i:${court.institutie}`);
  await expect(page.locator('#tier')).toBeDisabled();
  await scopeFacts(page, sum([court]));
  await page.evaluate(() => { location.hash = 'loc=j%3ATM&grad=toate&x=9000&keep=baseline'; });
  await expect(page.locator('#tier')).toBeEnabled();
  await scopeFacts(page, sum(county));
  await page.locator('#scope').selectOption('tara');
  await scopeFacts(page, [1234567, stats.snapshot.instante, stats.amanari.termeneCuSolutie]);
  await expect(page.locator('[data-national]').first()).toBeHidden();
  expect(audit.external).toEqual([]);
  expect(audit.errors).toEqual([]);
});

test('proposal lazy load failure, button retry and cached offline selection', async ({ page }, info) => {
  const audit = await localOnly(page);
  let fail = true;
  let release: () => void;
  const loading = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/data/court-distance.bin', async route => {
    await loading;
    return fail ? route.fulfill({ status: 503, body: 'unavailable' }) : route.continue();
  });
  await page.goto('/statistici.html#x=9000&keep=baseline');
  await expect(page.locator('#filtre')).toBeVisible();
  expect(audit.requests.some(url => url.includes('court-distance'))).toBe(false);
  const button = page.locator('#load-proposal');
  await button.click();
  await expect(button).toBeDisabled();
  release!();
  await expect(page.locator('#filter-state')).toContainText('nu a putut fi calculată');
  await expect(button).toBeEnabled();
  await expect(page.locator('#scope option[value^="p:"]')).toHaveCount(0);
  fail = false;
  await button.click();
  await expect(button).toBeHidden();
  const proposed = page.locator('#scope option[value^="p:"]').first();
  const value = await proposed.getAttribute('value');
  expect(value).toMatch(/^p:/);
  await page.locator('#scope').selectOption(value!);
  await expect(page.locator('#tier')).toBeDisabled();
  await expect(page.locator('#acoperire h2')).toContainText('(propusă)');
  const baseline = await recordStatistics(page, info, 'proposed');
  const hash = new URL(page.url()).hash;
  await page.reload();
  await expect(page.locator('#scope')).toHaveValue(value!);
  await expect(page.locator('#tier')).toBeDisabled();
  expect(await recordStatistics(page, info, 'proposed-direct-reload')).toEqual(baseline);
  await page.context().setOffline(true);
  await page.locator('#scope').selectOption('j:TM');
  await scopeFacts(page, sum(county));
  await page.evaluate(next => { location.hash = next; }, hash);
  await expect(page.locator('#acoperire h2')).toContainText('(propusă)');
  expect(await recordStatistics(page, info, 'proposed-cached-offline')).toEqual(baseline);
  expect(audit.external).toEqual([]);
  expect(audit.errors).toEqual([]);
});

test('direct proposed URL retains selection after failed load and retry', async ({ page }) => {
  const audit = await localOnly(page);
  let fail = true;
  await page.route('**/data/court-distance.bin', route => fail
    ? route.fulfill({ status: 503, body: 'unavailable' }) : route.continue());
  await page.goto('/statistici.html#loc=p%3A0&x=9000&keep=baseline');
  await expect(page.locator('#scope option[value^="p:"]')).toHaveCount(0);
  // Wait for the initial national fallback rather than racing its pending model load.
  await expect(page.locator('#filter-state')).toContainText('instanțe colectate');
  fail = false;
  await page.locator('#load-proposal').click();
  await expect(page.locator('#load-proposal')).toBeHidden();
  await expect(page.locator('#scope')).toHaveValue('p:0');
  await expect(page.locator('#tier')).toBeDisabled();
  await expect(page.locator('#acoperire h2')).toContainText('(propusă)');
  expect(new URLSearchParams(new URL(page.url()).hash.slice(1)).get('keep')).toBe('baseline');
  expect(audit.external).toEqual([]);
  expect(audit.errors).toEqual([]);
});

test('optional court data failure preserves authoritative national statistics', async ({ page }) => {
  const audit = await localOnly(page);
  await page.route('**/data/portal-instante.json', route => route.fulfill({ status: 404, body: 'missing' }));
  await page.goto('/statistici.html');
  await expect(page.locator('#filtre')).toBeHidden();
  await scopeFacts(page, [stats.snapshot.dosare, stats.snapshot.instante, stats.amanari.termeneCuSolutie]);
  expect(audit.errors).toEqual([]);
});

test('statistics keyboard, chart values and responsive light/dark layouts', async ({ page }, info) => {
  const audit = await localOnly(page);
  await page.goto('/statistici.html');
  await expect(page.locator('#filtre')).toBeVisible();
  await page.locator('#scope').focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Tab');
  await expect(page.locator('#scope')).not.toHaveValue('tara');
  await expect(page.locator('#tier')).toBeFocused();
  await page.locator('#scope').selectOption('tara');
  const national = await recordStatistics(page, info, 'responsive-reference');
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      for (const id of ['scope', 'tier', 'load-proposal']) {
        const control = page.locator(`#${id}`);
        const box = (await control.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
        if (id !== 'load-proposal') expect(await control.evaluate(node => (node as HTMLSelectElement).labels?.length)).toBeGreaterThan(0);
      }
      await page.screenshot({ path: info.outputPath(`statistics-${colorScheme}-${width}.png`), fullPage: true });
      // Layout may change percentage widths; the chart labels, values and caveats must not.
      expect((await recordStatistics(page, info, `${colorScheme}-${width}`)).text).toEqual(national.text);
      await expect(page.locator('#acoperire .facts b').first()).toHaveText(formatCount(stats.snapshot.dosare));
    }
  }
  expect(audit.external).toEqual([]);
  expect(audit.errors).toEqual([]);
});

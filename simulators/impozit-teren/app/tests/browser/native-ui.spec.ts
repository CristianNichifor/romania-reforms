import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const baseline = process.env.LAND_UI_BASELINE;
const capture = process.env.LAND_UI_CAPTURE === '1';

async function ready(page: Page) {
  await expect(page.locator('#rows td').first()).toBeVisible();
  await expect(page.locator('#county option')).toHaveCount(43);
  await page.waitForLoadState('networkidle');
}

test('county, year, pagination and scenario values survive the native CSS pilot', async ({ page }, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#j=bc&cota=0.01&randament=0.025');
  await ready(page);
  const states: unknown[] = [];
  async function snapshot(name: string) {
    const state = { name, hash: new URL(page.url()).hash,
      text: await page.locator('#headline, #national, #rows, #gdp-value, #pager').allTextContents(),
      county: await page.locator('#county').inputValue(),
      year: await page.locator('#gdp-year').inputValue(),
      options: await page.locator('#county option, #gdp-year option').allTextContents(),
    };
    states.push(state);
    return state;
  }
  await snapshot('county-initial');
  const years = await page.locator('#gdp-year option').evaluateAll(options => options.map(option => (option as HTMLOptionElement).value));
  expect(years.length).toBeGreaterThan(1);
  await page.locator('#gdp-year').selectOption(years[0]);
  await snapshot('year');
  await page.locator('#county').selectOption('toate');
  await expect(page.locator('#pager button')).toHaveCount(2);
  await expect(page.locator('#pager button').first()).toBeDisabled();
  await snapshot('national-first');
  const firstRows = await page.locator('#rows').textContent();
  await page.locator('#pager button').last().click();
  await expect(page).toHaveURL(/pag=2/);
  const second = await snapshot('national-second');
  await expect(page.locator('#rows')).not.toHaveText(firstRows!);
  await page.reload();
  await ready(page);
  const reloaded = await snapshot('reload-second');
  expect({ ...reloaded, name: second.name }).toEqual(second);
  await page.locator('#sort button[data-sort="name"]').click();
  await expect(page.locator('#pager button').first()).toBeDisabled();
  await snapshot('sort-resets-page');
  await page.locator('#county').selectOption('b');
  await expect(page.locator('#pager button')).toHaveCount(0);
  await snapshot('single-page-county');
  const initialYear = await page.locator('#gdp-year').inputValue();
  const initialOutput = await page.locator('#gdp-note').textContent();
  const anotherYear = years.find(year => year !== initialYear)!;
  await page.locator('#gdp-year').selectOption(anotherYear);
  await expect(page).toHaveURL(new RegExp(`pib=${anotherYear}`));
  await expect(page.locator('#gdp-note')).not.toHaveText(initialOutput!);
  const changedOutput = await page.locator('#gdp-note').textContent();
  await page.reload();
  await ready(page);
  await expect(page.locator('#gdp-year')).toHaveValue(anotherYear);
  await expect(page.locator('#gdp-note')).toHaveText(changedOutput!);
  await page.locator('#gdp-year').selectOption(initialYear);
  await expect(page.locator('#gdp-note')).toHaveText(initialOutput!);
  expect(errors).toEqual([]);
  if (baseline) {
    const path = join(baseline, `${info.project.name}.json`);
    if (capture) {
      await mkdir(baseline, { recursive: true });
      await writeFile(path, JSON.stringify(states, null, 2));
    } else {
      expect(states).toEqual(JSON.parse(await readFile(path, 'utf8')));
    }
  }
});

for (const width of [320, 390, 1440]) {
  test(`native controls, table and map at ${width}px`, async ({ page }, info) => {
    test.skip(capture, 'Baseline captures domain behavior before changing markup.');
    await page.setViewportSize({ width, height: 1000 });
    const external: string[] = [];
    await page.context().route('**/*', route => {
      if (!route.request().url().startsWith('http://127.0.0.1:5192/')) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    await page.goto('/#j=toate&cota=0.01&randament=0.025');
    await ready(page);
    await expect(page.locator('#pager button')).toHaveCount(2);
    for (const selector of ['#county', '#gdp-year']) {
      const field = page.locator(selector);
      expect(await field.evaluate(el => !!el.closest('.civic-field') && !!el.closest('.civic-scope') && !!(el as HTMLSelectElement).labels?.length)).toBe(true);
      expect((await field.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await field.focus();
      await expect(field).toHaveCSS('outline-style', 'solid');
    }
    const region = page.getByRole('region', { name: 'Localități: comparația impozitelor' });
    await expect(region.locator('thead').getByRole('columnheader')).toHaveCount(6);
    await region.focus();
    await expect(region).toBeFocused();
    await expect(region).toHaveCSS('outline-style', 'solid');
    if (width < 500) {
      expect(await region.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
      await page.keyboard.press('ArrowRight');
      await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const violations = (await new AxeBuilder({ page })
      .include('#counties, #gdp-control, #pager, .civic-table-scroll')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
    expect(violations.map(({ id, nodes }) => ({ id, targets: nodes.map(node => node.target) }))).toEqual([]);
    await page.locator('#counties').screenshot({ path: info.outputPath('county.png') });
    await region.screenshot({ path: info.outputPath('table.png') });
    await page.locator('#panel').screenshot({ path: info.outputPath('panel.png') });
    const canvas = page.locator('#map canvas');
    expect(await canvas.evaluate(element => !!(element as HTMLCanvasElement).getContext('webgl2')), 'Map requires a working WebGL2 context').toBe(true);
    await canvas.scrollIntoViewIfNeeded();
    const pixels = async () => {
      const png = await canvas.screenshot();
      return page.evaluate(async data => {
        const bitmap = await createImageBitmap(await (await fetch(`data:image/png;base64,${data}`)).blob());
        const surface = document.createElement('canvas');
        surface.width = bitmap.width; surface.height = bitmap.height;
        const ctx = surface.getContext('2d')!;
        ctx.drawImage(bitmap, 0, 0);
        const rgba = ctx.getImageData(0, 0, surface.width, surface.height).data;
        const colors = new Set<number>();
        for (let i = 0; i < rgba.length; i += 16) colors.add((rgba[i] << 16) | (rgba[i + 1] << 8) | rgba[i + 2]);
        return colors.size;
      }, png.toString('base64'));
    };
    await expect.poll(pixels, { timeout: 30_000 }).toBeGreaterThan(20);
    await canvas.screenshot({ path: info.outputPath('map-initial.png') });
    const before = await canvas.screenshot();
    await canvas.hover();
    await page.mouse.wheel(0, -400);
    await page.mouse.move(0, 0);
    await expect(page.locator('.maplibregl-popup')).toHaveCount(0);
    await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false);
    await canvas.screenshot({ path: info.outputPath('map.png') });
    expect(external).toEqual([]);
  });
}

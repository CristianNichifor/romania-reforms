import { expect, type Page, type TestInfo } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';
import { basename, join } from 'node:path';

export const publicData = (name: string) => JSON.parse(readFileSync(new URL(`../../public/data/${name}`, import.meta.url), 'utf8'));
export const formatCount = (value: number) => Math.round(value).toLocaleString('ro-RO');

export async function localOnly(page: Page) {
  const external: string[] = [];
  const errors: string[] = [];
  const requests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  await page.route('**/*', route => {
    const url = route.request().url();
    if (/^https?:/.test(url) && new URL(url).origin !== 'http://127.0.0.1:5196') {
      external.push(url);
      return route.abort();
    }
    return route.continue();
  });
  return { external, errors, requests };
}

export async function scopeFacts(page: Page, values: number[]) {
  await expect(page.locator('#acoperire .facts b')).toHaveText(values.map(formatCount));
}

export async function recordStatistics(page: Page, info: TestInfo, name: string) {
  const snapshot = await page.locator('#app').evaluate(element => ({
    text: element.textContent,
    charts: [...element.querySelectorAll('[style], [data-tip]')].map(node => ({
      text: node.textContent, style: node.getAttribute('style'), tip: node.getAttribute('data-tip'),
    })),
    hash: location.hash,
  }));
  await jsonEvidence(info, name, snapshot);
  if (process.env.JUSTICE_BASELINE) {
    const before = JSON.parse(readFileSync(join(process.env.JUSTICE_BASELINE, basename(info.outputDir), `${name}.json`), 'utf8'));
    const normalize = (value: typeof snapshot) => ({
      ...value, text: value.text?.replace(/\s+/g, ' ').trim(),
      charts: value.charts.map(chart => ({ ...chart, text: chart.text?.replace(/\s+/g, ' ').trim() })),
    });
    expect(normalize(snapshot)).toEqual(normalize(before));
  }
  return snapshot;
}

export async function jsonEvidence(info: TestInfo, name: string, value: unknown) {
  const path = info.outputPath(`${name}.json`);
  await writeFile(path, JSON.stringify(value, null, 2));
  await info.attach(`${name}.json`, { path, contentType: 'application/json' });
}

export async function mapPixels(page: Page, info: TestInfo, name: string) {
  const canvas = page.locator('#map canvas').first();
  expect(await canvas.evaluate(node => Boolean((node as HTMLCanvasElement).getContext('webgl2')))).toBe(true);
  // Sample the map's exposed right-hand area, excluding the sidebar and zoom buttons.
  const box = (await canvas.boundingBox())!;
  const panel = (await page.locator('#panel').boundingBox())!;
  const stacked = panel.y >= box.y + box.height - 1;
  const left = stacked ? box.x + box.width * 0.1 : Math.max(box.x + box.width * 0.55, panel.x + panel.width + 3);
  const clip = { x: left, y: box.y + box.height * 0.25,
    width: stacked ? box.width * 0.8 : box.x + box.width - left - 3, height: box.height * 0.6 };
  expect(clip.width).toBeGreaterThan(0);
  const capture = () => page.screenshot({ clip });
  await expect.poll(async () => {
    const png = await capture();
    return page.evaluate(async encoded => {
      const bitmap = await createImageBitmap(await (await fetch(`data:image/png;base64,${encoded}`)).blob());
      const surface = document.createElement('canvas');
      surface.width = bitmap.width; surface.height = bitmap.height;
      const context = surface.getContext('2d')!;
      context.drawImage(bitmap, 0, 0);
      const pixels = context.getImageData(0, 0, surface.width, surface.height).data;
      const palette = new Set<number>();
      for (let i = 0; i < pixels.length; i += 16) palette.add((pixels[i]! << 16) | (pixels[i + 1]! << 8) | pixels[i + 2]!);
      return palette.size;
    }, png.toString('base64'));
  }).toBeGreaterThan(20);
  const png = await capture();
  const path = info.outputPath(`${name}.png`);
  await writeFile(path, png);
  await info.attach(`${name}.png`, { path, contentType: 'image/png' });
  return { png, capture };
}

export async function settledPixels(capture: () => Promise<Buffer>) {
  let previous = await capture();
  let stable = 0;
  await expect.poll(async () => {
    const next = await capture();
    stable = next.equals(previous) ? stable + 1 : 0;
    previous = next;
    return stable;
  }, { intervals: [150, 250, 350] }).toBeGreaterThanOrEqual(2);
  return previous;
}

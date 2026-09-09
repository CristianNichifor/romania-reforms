import { expect, type Page, type TestInfo } from '@playwright/test';
import { readFileSync } from 'node:fs';

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
  await info.attach(`${name}.json`, { body: JSON.stringify(snapshot, null, 2), contentType: 'application/json' });
  return snapshot;
}

export async function mapPixels(page: Page, info: TestInfo, name: string) {
  const canvas = page.locator('#map canvas').first();
  expect(await canvas.evaluate(node => Boolean((node as HTMLCanvasElement).getContext('webgl2')))).toBe(true);
  // Sample the map's exposed right-hand area, excluding the sidebar and zoom buttons.
  const box = (await canvas.boundingBox())!;
  const panel = (await page.locator('#panel').boundingBox())!;
  const left = Math.max(box.x + box.width * 0.55, panel.x + panel.width + 3);
  const clip = { x: left, y: box.y + box.height * 0.25,
    width: box.x + box.width - left - 3, height: box.height * 0.6 };
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
  await info.attach(`${name}.png`, { body: png, contentType: 'image/png' });
  return { png, capture };
}

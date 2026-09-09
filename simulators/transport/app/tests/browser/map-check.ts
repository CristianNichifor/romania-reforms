import { expect, type Page, type TestInfo } from '@playwright/test';
export async function checkMap(page: Page, info: TestInfo) {
  const canvas = page.locator('#map canvas').first();
  await canvas.scrollIntoViewIfNeeded();
  expect(await canvas.evaluate(el => !!(el as HTMLCanvasElement).getContext('webgl2'))).toBe(true);
  const colors = async () => {
    const png = await canvas.screenshot();
    return page.evaluate(async data => {
      const bitmap = await createImageBitmap(await (await fetch(`data:image/png;base64,${data}`)).blob());
      const surface = document.createElement('canvas');
      surface.width = bitmap.width; surface.height = bitmap.height;
      const context = surface.getContext('2d')!;
      context.drawImage(bitmap, 0, 0);
      const rgba = context.getImageData(0, 0, surface.width, surface.height).data;
      const palette = new Set<number>();
      for (let i = 0; i < rgba.length; i += 16) palette.add((rgba[i]! << 16) | (rgba[i + 1]! << 8) | rgba[i + 2]!);
      return palette.size;
    }, png.toString('base64'));
  };
  await expect.poll(colors).toBeGreaterThan(20);
  await canvas.screenshot({ path: info.outputPath('map-before.png') });
  const before = await canvas.screenshot();
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.4);
  await page.mouse.wheel(0, -500);
  await page.mouse.move(0, 0);
  await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false);
  await canvas.screenshot({ path: info.outputPath('map-after.png') });
}


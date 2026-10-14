// Page-level checks the ux guideline asks for (§9 item 9; design screens, criteria 1 and 8):
// at phone width the document never scrolls sideways (the zone table scrolls inside itself),
// axe reports no serious or critical issue, and the page raises no JS error.
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('the page has no sideways scroll at 390 px and no serious axe issue', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#j=bc');
  await expect(page.locator('#rows td').first()).toBeVisible();
  await expect(page.locator('#county option')).toHaveCount(43);
  await page.waitForLoadState('networkidle');

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth, `document scrolls sideways: ${JSON.stringify(overflow)}`).toBeLessThanOrEqual(
    overflow.clientWidth + 1,
  );

  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  const serious = violations
    .filter(v => v.impact === 'serious' || v.impact === 'critical')
    .map(({ id, impact, nodes }) => ({ id, impact, targets: nodes.slice(0, 5).map(node => node.target) }));
  expect(serious).toEqual([]);
  expect(errors).toEqual([]);
});

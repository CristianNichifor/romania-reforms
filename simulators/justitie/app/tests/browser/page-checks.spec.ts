// Page-level checks the ux guideline asks for (§9 item 9; design screens, criteria 1 and 8):
// at phone width the document never scrolls sideways, and axe reports no serious or critical
// issue on either page. Scoped to the whole page rather than one region, so a regression
// anywhere on the page fails here.
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { localOnly } from './helpers';

const pages = [
  { path: '/', ready: '#summary' },
  { path: '/statistici.html', ready: '#sursa' },
];

for (const { path, ready } of pages) {
  test(`${path} has no sideways scroll at 390 px and no serious axe issue`, async ({ page }) => {
    const audit = await localOnly(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    await expect(page.locator(ready)).not.toBeEmpty();
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
    expect(audit.errors).toEqual([]);
  });
}

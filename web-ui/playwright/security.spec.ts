import { test, expect } from '@playwright/test';

test('security page renders', async ({ page }) => {
  await page.goto('/security');
  await expect(page.locator('text=Health Checks')).toBeVisible();
  await expect(page.locator('text=Audit Findings')).toBeVisible();
});

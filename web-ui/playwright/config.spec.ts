import { test, expect } from '@playwright/test';

test('config editor renders', async ({ page }) => {
  await page.goto('/config');
  await expect(page.locator('text=Configuration')).toBeVisible();
});

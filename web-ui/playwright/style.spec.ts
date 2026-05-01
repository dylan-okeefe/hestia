import { test, expect } from '@playwright/test';

test('style profile renders', async ({ page }) => {
  await page.goto('/style');
  await expect(page.locator('text=Style Profile')).toBeVisible();
});

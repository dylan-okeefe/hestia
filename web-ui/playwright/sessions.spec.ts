import { test, expect } from '@playwright/test';

test('session timeline renders', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('text=Sessions')).toBeVisible();
});

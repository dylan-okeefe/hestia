import { test, expect } from '@playwright/test';

test('scheduler table renders', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.locator('text=Scheduled Tasks')).toBeVisible();
});

import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('style profile renders', async ({ page }) => {
  await page.goto('/style');
  await expect(page.locator('text=Style Profile')).toBeVisible();
  await expect(page.locator('text=formality')).toBeVisible();
});

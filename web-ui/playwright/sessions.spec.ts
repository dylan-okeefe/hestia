import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('session timeline renders', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('text=Sessions')).toBeVisible();
  await expect(page.locator('[data-testid="session-row"]')).toHaveCount(1);
});

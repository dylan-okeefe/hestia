import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('dashboard loads', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('h1')).toHaveText('Sessions');
});

test('session row expands to show turns', async ({ page }) => {
  await page.goto('/');
  await page.locator('[data-testid="session-row"]').first().click();
  await expect(page.locator('text=turn_001')).toBeVisible();
});

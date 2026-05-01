import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('scheduler table renders', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.locator('text=Scheduled Tasks')).toBeVisible();
  await expect(page.locator('text=Daily summary')).toBeVisible();
});

test('run now button triggers task', async ({ page }) => {
  await page.goto('/scheduler');
  await page.locator('button:has-text("Run now")').click();
  await expect(page.locator('text=Running…')).toBeVisible();
});

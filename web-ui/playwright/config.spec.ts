import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('config editor renders', async ({ page }) => {
  await page.goto('/config');
  await expect(page.locator('text=Configuration')).toBeVisible();
  await expect(page.locator('text=Trust Preset')).toBeVisible();
});

test('save config shows not-implemented message', async ({ page }) => {
  await page.goto('/config');
  await page.locator('button:has-text("Save")').click();
  await expect(page.locator('text=Not implemented')).toBeVisible();
});

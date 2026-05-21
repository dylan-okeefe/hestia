import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('security page renders', async ({ page }) => {
  await page.goto('/security');
  await expect(page.locator('text=Health Checks')).toBeVisible();
  await expect(page.locator('text=Audit Findings')).toBeVisible();
  await expect(page.locator('text=Egress Log')).toBeVisible();
});

test('doctor checks load after re-run', async ({ page }) => {
  await page.goto('/security');
  await page.locator('button:has-text("Re-run checks")').click();
  await expect(page.locator('text=Database')).toBeVisible();
});

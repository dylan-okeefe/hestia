import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('navigate between pages', async ({ page }) => {
  await page.goto('/');

  await page.locator('a:has-text("Proposals")').click();
  await expect(page).toHaveURL(/.*\/proposals/);
  await expect(page.locator('h1')).toHaveText('Proposals');

  await page.locator('a:has-text("Scheduler")').click();
  await expect(page).toHaveURL(/.*\/scheduler/);
  await expect(page.locator('h1')).toHaveText('Scheduled Tasks');

  await page.locator('a:has-text("Security")').click();
  await expect(page).toHaveURL(/.*\/security/);
  await expect(page.locator('h1')).toHaveText('Security & Health');

  await page.locator('a:has-text("Config")').click();
  await expect(page).toHaveURL(/.*\/config/);
  await expect(page.locator('h1')).toHaveText('Configuration');

  await page.locator('a:has-text("Dashboard")').click();
  await expect(page).toHaveURL(/.*\/$/);
  await expect(page.locator('h1')).toHaveText('Sessions');
});

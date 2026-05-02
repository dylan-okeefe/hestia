import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('workflows list page renders', async ({ page }) => {
  await page.goto('/workflows');
  await expect(page.locator('h1')).toHaveText('Workflows');
  await expect(page.locator('text=Morning Greeting')).toBeVisible();
  await expect(page.locator('text=Daily Summary')).toBeVisible();
});

test('click workflow row navigates to editor', async ({ page }) => {
  await page.goto('/workflows');
  await page.locator('[data-testid="workflow-row"]').first().click();
  await expect(page.locator('text=Morning Greeting')).toBeVisible();
});

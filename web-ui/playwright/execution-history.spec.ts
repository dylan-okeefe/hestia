import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('execution history panel renders and shows executions', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await page.locator('button', { hasText: 'Execution History' }).click();

  await expect(page.locator('text=Execution History')).toBeVisible();
  await expect(page.locator('text=1234ms')).toBeVisible();
  await expect(page.locator('text=150 prompt + 80 completion')).toBeVisible();
});

test('clicking execution row expands node results', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await page.locator('button', { hasText: 'Execution History' }).click();

  // The first execution row should be visible; click it to expand
  const rows = page.locator('table tbody tr');
  await expect(rows.first()).toBeVisible();
  await rows.first().click();

  // Expanded node details should be visible - scope to nested table
  await expect(page.locator('table table').locator('text="Start" (default)').first()).toBeVisible();
  await expect(page.locator('table table').locator('text=hello').first()).toBeVisible();
});

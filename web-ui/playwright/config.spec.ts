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

test('trust preset renders as a dropdown', async ({ page }) => {
  await page.goto('/config');
  const select = page.locator('select');
  await expect(select).toBeVisible();
  const options = select.locator('option');
  await expect(options).toHaveCount(4);
  await expect(options.nth(0)).toHaveAttribute('value', 'paranoid');
  await expect(options.nth(1)).toHaveAttribute('value', 'prompt_on_mobile');
  await expect(options.nth(2)).toHaveAttribute('value', 'household');
  await expect(options.nth(3)).toHaveAttribute('value', 'developer');
});

test('changing trust preset dropdown updates value', async ({ page }) => {
  await page.goto('/config');
  const select = page.locator('select');
  await select.selectOption('household');
  await expect(select).toHaveValue('household');
});

test('save config shows not-implemented message', async ({ page }) => {
  await page.goto('/config');
  await page.locator('button:has-text("Save")').click();
  await expect(page.locator('text=Not implemented')).toBeVisible();
});

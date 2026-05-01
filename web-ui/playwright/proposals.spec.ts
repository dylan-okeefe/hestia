import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('accept a proposal', async ({ page }) => {
  await page.goto('/proposals');
  const card = page.locator('[data-testid="proposal-card"]').first();
  await expect(card).toBeVisible();
  await card.locator('button:has-text("Accept")').click();
  await expect(card.locator('text=accepted')).toBeVisible();
});

test('history tab shows resolved proposals without action buttons', async ({ page }) => {
  await page.goto('/proposals');
  await page.locator('button:has-text("History")').click();
  const card = page.locator('[data-testid="proposal-card"]').filter({ hasText: 'accepted' });
  await expect(card).toBeVisible();
  await expect(card.locator('button:has-text("Accept")')).not.toBeVisible();
});

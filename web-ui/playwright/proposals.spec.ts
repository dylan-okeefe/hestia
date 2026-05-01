import { test, expect } from '@playwright/test';

test('accept a proposal', async ({ page }) => {
  await page.goto('/proposals');
  const card = page.locator('[data-testid="proposal-card"]').first();
  await expect(card).toBeVisible();
  await card.locator('button:has-text("Accept")').click();
  await expect(page.locator('[data-testid="accepted-section"] [data-testid="proposal-card"]')).toHaveCount(1);
});

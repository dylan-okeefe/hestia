import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('webhook URL is shown and copyable', async ({ page }) => {
  await page.goto('/workflows/wf_001');

  // Wait for trigger type dropdown to be visible and select webhook
  const triggerSelect = page.locator('select[aria-label="Trigger type"]');
  await expect(triggerSelect).toBeVisible();
  await triggerSelect.selectOption('webhook');

  // Webhook URL should be visible
  await expect(page.getByText('/api/webhooks/wf_001')).toBeVisible();

  // Copy URL button should be visible
  const copyButton = page.locator('button:has-text("Copy URL")');
  await expect(copyButton).toBeVisible();

  // Note should be visible
  await expect(page.locator('text=Send POST requests to this URL')).toBeVisible();
});

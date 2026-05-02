import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('changing trigger type and config', async ({ page }) => {
  await page.goto('/workflows/wf_001');

  // Wait for trigger type dropdown to be visible
  const triggerSelect = page.locator('select[aria-label="Trigger type"]');
  await expect(triggerSelect).toBeVisible();

  // Change trigger type to schedule
  await triggerSelect.selectOption('schedule');

  // Cron input should appear
  const cronInput = page.locator('input[aria-label="Cron expression"]');
  await expect(cronInput).toBeVisible();
  await cronInput.fill('0 9 * * *');

  // Click Save Trigger
  await page.locator('button:has-text("Save Trigger")').click();

  // Change to chat_command
  await triggerSelect.selectOption('chat_command');
  const commandInput = page.locator('input[aria-label="Command"]');
  await expect(commandInput).toBeVisible();
  await commandInput.fill('status');

  // Change to message
  await triggerSelect.selectOption('message');
  const patternInput = page.locator('input[aria-label="Pattern"]');
  await expect(patternInput).toBeVisible();
  await patternInput.fill('ERROR');

  // Change to webhook
  await triggerSelect.selectOption('webhook');
  const endpointInput = page.locator('input[aria-label="Endpoint"]');
  await expect(endpointInput).toBeVisible();
  await endpointInput.fill('/deploy');
});

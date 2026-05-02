import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('adds an investigate node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('[aria-label="Workflow name"]')).toHaveValue('Morning Greeting');

  await page.locator('select[aria-label="Node type to add"]').selectOption('investigate');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="investigate"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Investigate');

  await node.click();
  await expect(page.locator('label:has-text("Topic")')).toBeVisible();
  await expect(page.locator('label:has-text("Depth")')).toBeVisible();
  await expect(page.locator('label:has-text("Tools (comma-separated)")')).toBeVisible();

  await page.locator('label:has-text("Topic") + textarea').fill('best Python frameworks');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("Topic") + textarea')).toHaveValue('best Python frameworks');
});

import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('adds a tool_call node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('text=Morning Greeting')).toBeVisible();

  await page.locator('select[aria-label="Node type to add"]').selectOption('tool_call');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="tool_call"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Tool Call');

  await node.click();
  await expect(page.locator('label:has-text("Tool Name")')).toBeVisible();
  await expect(page.locator('label:has-text("Args (JSON)")')).toBeVisible();

  await page.locator('label:has-text("Tool Name") + input').fill('my_tool');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("Tool Name") + input')).toHaveValue('my_tool');
});

test('adds a send_message node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('text=Morning Greeting')).toBeVisible();

  await page.locator('select[aria-label="Node type to add"]').selectOption('send_message');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="send_message"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Send Message');

  await node.click();
  await expect(page.locator('label:has-text("Platform")')).toBeVisible();
  await expect(page.locator('label:has-text("Message")')).toBeVisible();
  await expect(page.locator('label:has-text("Target User")')).toBeVisible();

  await page.locator('label:has-text("Platform") + input').fill('discord');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("Platform") + input')).toHaveValue('discord');
});

test('adds an http_request node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('text=Morning Greeting')).toBeVisible();

  await page.locator('select[aria-label="Node type to add"]').selectOption('http_request');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="http_request"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('HTTP Request');

  await node.click();
  await expect(page.locator('label:has-text("Method")')).toBeVisible();
  await expect(page.locator('label:has-text("URL")')).toBeVisible();
  await expect(page.locator('label:has-text("Headers (JSON)")')).toBeVisible();
  await expect(page.locator('label:has-text("Body")')).toBeVisible();

  await page.locator('label:has-text("URL") + input').fill('https://example.com');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("URL") + input')).toHaveValue('https://example.com');
});

test('adds an llm_decision node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('text=Morning Greeting')).toBeVisible();

  await page.locator('select[aria-label="Node type to add"]').selectOption('llm_decision');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="llm_decision"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('LLM Decision');

  await node.click();
  await expect(page.locator('label:has-text("Prompt")')).toBeVisible();
  await expect(page.locator('label:has-text("Branches (comma-separated)")')).toBeVisible();

  await page.locator('label:has-text("Prompt") + textarea').fill('Choose a path');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("Prompt") + textarea')).toHaveValue('Choose a path');
});

test('adds a condition node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('text=Morning Greeting')).toBeVisible();

  await page.locator('select[aria-label="Node type to add"]').selectOption('condition');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="condition"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Condition');

  await node.click();
  await expect(page.locator('label:has-text("Expression")')).toBeVisible();

  await page.locator('label:has-text("Expression") + input').fill('inputs.ok == true');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("Expression") + input')).toHaveValue('inputs.ok == true');
});

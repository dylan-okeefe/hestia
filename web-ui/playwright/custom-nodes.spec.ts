import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('adds a tool_call node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('[aria-label="Workflow name"]')).toHaveValue('Morning Greeting');

  await page.locator('select[aria-label="Node type to add"]').selectOption('tool_call');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="tool_call"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Tool Call');

  await node.click();
  await expect(page.locator('label:has-text("Tool Name")')).toBeVisible();
  await expect(page.locator('label:has-text("Args (JSON)")')).toBeVisible();

  await page.locator('select[aria-label="Tool name"]').selectOption('search_web');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('select[aria-label="Tool name"]')).toHaveValue('search_web');
});

test('adds a send_message node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('[aria-label="Workflow name"]')).toHaveValue('Morning Greeting');

  await page.locator('select[aria-label="Node type to add"]').selectOption('send_message');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="send_message"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Send Message');

  await node.click();
  await expect(page.locator('label:has-text("Platform")')).toBeVisible();
  await expect(page.locator('label:has-text("Message")')).toBeVisible();
  await expect(page.locator('label:has-text("Target User")')).toBeVisible();

  await page.locator('select[aria-label="Platform"]').selectOption('discord');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('select[aria-label="Platform"]')).toHaveValue('discord');
});

test('adds an http_request node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('[aria-label="Workflow name"]')).toHaveValue('Morning Greeting');

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
  await expect(page.locator('[aria-label="Workflow name"]')).toHaveValue('Morning Greeting');

  await page.locator('select[aria-label="Node type to add"]').selectOption('llm_decision');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="llm_decision"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('LLM Decision');

  await node.click();
  await expect(page.locator('label:has-text("Prompt")')).toBeVisible();
  await expect(page.locator('label:has-text("Branches")')).toBeVisible();

  await page.locator('label:has-text("Prompt") + textarea').fill('Choose a path');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('label:has-text("Prompt") + textarea')).toHaveValue('Choose a path');

  // Tag chips: add branch via Enter
  const addBranchInput = page.locator('input[aria-label="Add branch"]');
  await addBranchInput.fill('yes');
  await addBranchInput.press('Enter');
  await expect(page.locator('button[aria-label="Remove branch yes"]')).toBeVisible();

  // Add second branch
  await addBranchInput.fill('no');
  await addBranchInput.press('Enter');
  await expect(page.locator('button[aria-label="Remove branch no"]')).toBeVisible();

  // Remove branch
  await page.locator('button[aria-label="Remove branch yes"]').click();
  await expect(page.locator('button[aria-label="Remove branch yes"]')).not.toBeVisible();
  await expect(page.locator('button[aria-label="Remove branch no"]')).toBeVisible();
});

test('adds a condition node and shows its properties', async ({ page }) => {
  await page.goto('/workflows/wf_001');
  await expect(page.locator('[aria-label="Workflow name"]')).toHaveValue('Morning Greeting');

  await page.locator('select[aria-label="Node type to add"]').selectOption('condition');
  await page.locator('button:has-text("Add Node")').click();

  const node = page.locator('[data-testid="workflow-node"][data-node-type="condition"]').first();
  await expect(node).toBeVisible();
  await expect(node).toContainText('Condition');

  await node.click();
  await expect(page.locator('label:has-text("Expression")')).toBeVisible();

  await page.locator('textarea[aria-label="Expression"]').fill('inputs.ok == true');
  await page.locator('.react-flow__pane').click();
  await node.click();
  await expect(page.locator('textarea[aria-label="Expression"]')).toHaveValue('inputs.ok == true');
});

import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

const mockTestRunSuccess = {
  status: 'ok',
  total_elapsed_ms: 1234,
  total_prompt_tokens: 150,
  total_completion_tokens: 80,
  node_results: [
    {
      node_id: 'n1',
      status: 'ok',
      elapsed_ms: 500,
      prompt_tokens: 100,
      completion_tokens: 50,
      output: 'hello',
      error: null,
    },
  ],
  outputs: { trigger: {}, n1: 'hello' },
};

const mockTestRunFailure = {
  status: 'failed',
  total_elapsed_ms: 100,
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  node_results: [
    {
      node_id: 'n1',
      status: 'failed',
      elapsed_ms: 100,
      prompt_tokens: 0,
      completion_tokens: 0,
      output: null,
      error: 'Node failed',
    },
  ],
  outputs: { trigger: {} },
};

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('test run shows results panel with status and node results', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/test-run')) {
      await route.fulfill({ json: mockTestRunSuccess });
    } else if (url.includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes: [
                { id: 'n1', type: 'default', position: { x: 100, y: 100 }, data: { label: 'Start' } },
              ],
              edges: [],
              created_at: '2024-01-15T08:00:00Z',
              activated_at: '2024-01-15T08:05:00Z',
            },
          ],
        },
      });
    } else {
      await route.fulfill({
        json: {
          id: 'wf_001',
          name: 'Test Workflow',
          trigger_type: 'manual',
          last_edited_at: '2024-01-15T08:00:00Z',
          active_version_id: 'v_001',
        },
      });
    }
  });

  await page.goto('/workflows/wf_001');
  await page.locator('button', { hasText: 'Test Run' }).click();

  await expect(page.locator('text=Status:')).toBeVisible();
  await expect(page.locator('span', { hasText: /^ok$/ })).toBeVisible();
  await expect(page.locator('text=1234ms')).toBeVisible();
  await expect(page.locator('text=150 prompt + 80 completion')).toBeVisible();
  await expect(page.locator('text=n1')).toBeVisible();
});

test('test run shows error on failure', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/test-run')) {
      await route.fulfill({ status: 500, json: { detail: 'Server error' } });
    } else if (url.includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes: [
                { id: 'n1', type: 'default', position: { x: 100, y: 100 }, data: { label: 'Start' } },
              ],
              edges: [],
              created_at: '2024-01-15T08:00:00Z',
              activated_at: '2024-01-15T08:05:00Z',
            },
          ],
        },
      });
    } else {
      await route.fulfill({
        json: {
          id: 'wf_001',
          name: 'Test Workflow',
          trigger_type: 'manual',
          last_edited_at: '2024-01-15T08:00:00Z',
          active_version_id: 'v_001',
        },
      });
    }
  });

  await page.goto('/workflows/wf_001');
  await page.locator('button', { hasText: 'Test Run' }).click();

  await expect(page.locator('text=Test Run Failed:')).toBeVisible();
});

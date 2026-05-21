import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

async function gotoEditor(page: any, nodes: any[] = []) {
  await page.route('/api/workflows/**', async (route: any) => {
    if (route.request().url().includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes,
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
}

test('condition syntax help toggles', async ({ page }) => {
  await gotoEditor(page, [
    { id: 'n1', type: 'condition', position: { x: 100, y: 100 }, data: { label: 'Check', expression: 'input.status == "ok"' } },
  ]);

  await page.locator('.react-flow__node').click();
  const helpButton = page.locator('button:has-text("Show Syntax Help")');
  await expect(helpButton).toBeVisible();
  await helpButton.click();
  await expect(page.locator('text=Variables:')).toBeVisible();
  await expect(page.locator('text=input.field_name')).toBeVisible();
  await page.locator('button:has-text("Hide Syntax Help")').click();
});

test('LLM decision shows upstream variables', async ({ page }) => {
  await page.route('/api/workflows/**', async (route: any) => {
    if (route.request().url().includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes: [
                { id: 'start', type: 'default', position: { x: 0, y: 0 }, data: { label: 'Start' } },
                { id: 'decide', type: 'llm_decision', position: { x: 100, y: 100 }, data: { label: 'Decide', prompt: '', branches: [] } },
              ],
              edges: [{ id: 'e1', source: 'start', target: 'decide' }],
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

  await page.locator('[data-id="decide"]').click();
  await expect(page.locator('text=Available:')).toBeVisible();
  await expect(page.locator('code:has-text("start.output")')).toBeVisible();
});

test('HTTP request header validation shows error on invalid JSON', async ({ page }) => {
  await gotoEditor(page, [
    { id: 'n1', type: 'http_request', position: { x: 100, y: 100 }, data: { label: 'API', url: '', method: 'GET', headers: {}, body: '' } },
  ]);

  await page.locator('.react-flow__node').click();
  const headersArea = page.locator('textarea[aria-invalid]').first();
  await headersArea.fill('{invalid json');
  await headersArea.blur();
  await expect(page.locator('span:has-text("Invalid JSON — headers must be a JSON object")')).toBeVisible();
});

test('HTTP request PATCH and HEAD methods available', async ({ page }) => {
  await gotoEditor(page, [
    { id: 'n1', type: 'http_request', position: { x: 100, y: 100 }, data: { label: 'API', url: '', method: 'GET', headers: {}, body: '' } },
  ]);

  await page.locator('.react-flow__node').click();
  const methodSelect = page.locator('select').filter({ hasText: /GET/ }).first();
  await expect(methodSelect).toContainText('PATCH');
  await expect(methodSelect).toContainText('HEAD');
});

test('controlled textarea updates on node switch', async ({ page }) => {
  await gotoEditor(page, [
    { id: 'n1', type: 'llm_decision', position: { x: 100, y: 100 }, data: { label: 'A', prompt: 'foo', branches: [] } },
    { id: 'n2', type: 'llm_decision', position: { x: 200, y: 200 }, data: { label: 'B', prompt: 'bar', branches: [] } },
  ]);

  await page.locator('[data-id="n1"]').click();
  const prompt = page.locator('textarea').first();
  await expect(prompt).toHaveValue('foo');

  await page.locator('[data-id="n2"]').click();
  await expect(prompt).toHaveValue('bar');
});

test('execution history shows node labels', async ({ page }) => {
  await page.route('/api/workflows/**', async (route: any) => {
    const url = route.request().url();
    if (url.includes('/executions')) {
      await route.fulfill({
        json: {
          executions: [
            {
              id: 'ex1',
              workflow_id: 'wf_001',
              status: 'ok',
              total_elapsed_ms: 100,
              total_prompt_tokens: 10,
              total_completion_tokens: 5,
              created_at: '2024-01-15T08:00:00Z',
              node_results: [{ node_id: 'n1', status: 'ok', elapsed_ms: 50, output: 'done' }],
            },
          ],
        },
      });
    } else if (url.includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes: [{ id: 'n1', type: 'tool_call', position: { x: 100, y: 100 }, data: { label: 'My Tool' } }],
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

  await page.locator('button:has-text("Execution History")').click();
  await page.locator('td:has-text("1")').first().click();
  await expect(page.locator('text="My Tool" (tool_call)')).toBeVisible();
});

test('SendMessage shows template preview and character count', async ({ page }) => {
  await gotoEditor(page, [
    { id: 'n1', type: 'send_message', position: { x: 100, y: 100 }, data: { label: 'Notify', platform: '', message: 'Hello {{user.name}}', target_user: '' } },
  ]);

  await page.locator('.react-flow__node').click();
  await expect(page.locator('text=Preview')).toBeVisible();
  // Preview should show the variable pill
  await expect(page.locator('span:has-text("user.name")').first()).toBeVisible();
  await expect(page.locator('text=19 characters')).toBeVisible();
});

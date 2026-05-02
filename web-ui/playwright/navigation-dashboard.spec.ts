import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('breadcrumb navigation in editor', async ({ page }) => {
  await page.route('/api/workflows/**', async (route: any) => {
    if (route.request().url().includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes: [{ id: 'n1', type: 'default', position: { x: 100, y: 100 }, data: { label: 'Start' } }],
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
  await expect(page.locator('text=Workflows')).toBeVisible();
  await expect(page.locator('text=Test Workflow')).toBeVisible();
  await page.locator('a[href="/workflows"]').first().click();
  await expect(page).toHaveURL(/\/workflows$/);
});

test('dashboard shows aggregated data', async ({ page }) => {
  await page.route('/api/dashboard', async (route: any) => {
    await route.fulfill({
      json: {
        active_workflow_count: 3,
        recent_executions: [
          {
            id: 'ex1',
            workflow_id: 'wf_001',
            status: 'ok',
            total_elapsed_ms: 100,
            total_prompt_tokens: 10,
            total_completion_tokens: 5,
            created_at: '2024-01-15T08:00:00Z',
            node_results: [],
          },
        ],
        pending_proposal_count: 2,
        platforms_connected: ['telegram'],
      },
    });
  });

  await page.goto('/');
  await expect(page.locator('text=Active Workflows')).toBeVisible();
  await expect(page.locator('text=3').first()).toBeVisible();
  await expect(page.locator('text=Pending Proposals')).toBeVisible();
  await expect(page.locator('text=2').first()).toBeVisible();
  await expect(page.locator('text=Telegram')).toBeVisible();
});

test('workflow list shows trigger badges and execution status', async ({ page }) => {
  await page.route('/api/workflows', async (route: any) => {
    await route.fulfill({
      json: {
        workflows: [
          {
            id: 'wf_001',
            name: 'Scheduled Task',
            trigger_type: 'schedule',
            trigger_config: {},
            last_edited_at: '2024-01-15T08:00:00Z',
            active_version_id: 'v_001',
            last_execution_status: 'ok',
            last_execution_at: '2024-01-15T08:00:00Z',
          },
        ],
      },
    });
  });

  await page.goto('/workflows');
  await expect(page.locator('text=📅schedule')).toBeVisible();
});

test('execution history detail has back navigation', async ({ page }) => {
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
              nodes: [{ id: 'n1', type: 'default', position: { x: 100, y: 100 }, data: { label: 'Start' } }],
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
  await expect(page.locator('button:has-text("← Back to history")')).toBeVisible();
  await page.locator('button:has-text("← Back to history")').click();
  await expect(page.locator('button:has-text("← Back to history")')).not.toBeVisible();
});

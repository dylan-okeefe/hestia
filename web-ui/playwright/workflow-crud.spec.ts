import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('rename workflow on blur', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
    const method = route.request().method();
    if (method === 'PUT') {
      const body = await route.request().postDataJSON();
      await route.fulfill({
        json: {
          id: 'wf_001',
          name: body.name || 'Morning Greeting',
          trigger_type: 'cron',
          last_edited_at: '2024-01-15T08:00:00Z',
          active_version_id: 'v_001',
        },
      });
    } else if (route.request().url().includes('/versions')) {
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
          name: 'Morning Greeting',
          trigger_type: 'cron',
          last_edited_at: '2024-01-15T08:00:00Z',
          active_version_id: 'v_001',
        },
      });
    }
  });

  await page.goto('/workflows/wf_001');
  const nameInput = page.locator('[aria-label="Workflow name"]');
  await expect(nameInput).toHaveValue('Morning Greeting');

  await nameInput.fill('Evening Greeting');
  await nameInput.blur();

  await expect(nameInput).toHaveValue('Evening Greeting');
});

test('version panel renders versions with active badge', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
    if (route.request().url().includes('/versions')) {
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
            {
              id: 'v_002',
              workflow_id: 'wf_001',
              version_number: 2,
              nodes: [],
              edges: [],
              created_at: '2024-01-16T08:00:00Z',
              activated_at: null,
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
  await page.locator('button:has-text("Versions")').click();

  await expect(page.getByRole('cell', { name: '1', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: '2', exact: true })).toBeVisible();
  await expect(page.locator('text=Active').first()).toBeVisible();
});

test('save does not auto-activate version', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/versions') && method === 'POST') {
      await route.fulfill({
        json: {
          id: 'v_003',
          workflow_id: 'wf_001',
          version_number: 3,
          nodes: [],
          edges: [],
          created_at: new Date().toISOString(),
          activated_at: null,
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
  await page.locator('button:has-text("Versions")').click();

  // Save Version should add v_003 but not activate it
  await page.locator('button:has-text("Save Version")').click();

  await expect(page.getByRole('cell', { name: '3', exact: true })).toBeVisible();
  // Active badge should still be on version 1, not version 3
  const rows = page.locator('table tbody tr');
  await expect(rows.nth(0).locator('text=Active')).toBeVisible();
  await expect(rows.nth(1).locator('text=Active')).not.toBeVisible();
});

test('delete node with Delete key removes node', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
    if (route.request().url().includes('/versions')) {
      await route.fulfill({
        json: {
          versions: [
            {
              id: 'v_001',
              workflow_id: 'wf_001',
              version_number: 1,
              nodes: [
                { id: 'n1', type: 'default', position: { x: 100, y: 100 }, data: { label: 'Start' } },
                { id: 'n2', type: 'default', position: { x: 250, y: 100 }, data: { label: 'End' } },
              ],
              edges: [{ id: 'e1', source: 'n1', target: 'n2' }],
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
  const nodes = page.locator('.react-flow__node');
  await expect(nodes).toHaveCount(2);

  // Click the first node to select it
  await nodes.first().click();

  // Press Delete key (bubbles to ReactFlow container handler)
  await page.keyboard.press('Delete');

  await expect(nodes).toHaveCount(1);
});

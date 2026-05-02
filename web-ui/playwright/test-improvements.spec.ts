import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('deterministic node placement below last node', async ({ page }) => {
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
  const nodes = page.locator('.react-flow__node');
  await expect(nodes).toHaveCount(1);

  // Add three nodes
  for (let i = 0; i < 3; i++) {
    await page.locator('button:has-text("Add Node")').click();
  }
  await expect(nodes).toHaveCount(4);

  // Verify y positions increase monotonically
  const positions = await page.evaluate(() => {
    const nodeElements = document.querySelectorAll('.react-flow__node');
    return Array.from(nodeElements).map((el) => {
      const transform = (el as HTMLElement).style.transform;
      const match = transform.match(/translate\(([^,]+)px,\s*([^)]+)px\)/);
      return match ? { x: parseFloat(match[1]), y: parseFloat(match[2]) } : { x: 0, y: 0 };
    });
  });

  // Sort by y to get the order they appear vertically
  const sorted = [...positions].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) {
    expect(sorted[i].y).toBeGreaterThan(sorted[i - 1].y);
  }
});

test('error state on network failure during save', async ({ page }) => {
  await page.route('/api/workflows/**', async (route: any) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/versions') && method === 'POST') {
      await route.abort('failed');
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
  await page.locator('button:has-text("Add Node")').click();
  await page.locator('button:has-text("Save Version")').click();
  await expect(page.locator('text=Failed to fetch')).toBeVisible();
});

test('error state on invalid workflow ID', async ({ page }) => {
  await page.route('/api/workflows/**', async (route: any) => {
    await route.fulfill({ status: 404, json: { detail: 'Workflow not found' } });
  });

  await page.goto('/workflows/nonexistent-id');
  await expect(page.locator('text=Failed to fetch workflow')).toBeVisible();
});

test('error state on test run failure', async ({ page }) => {
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'confirm') dialog.accept().catch(() => {});
  });
  await page.route('/api/workflows/**', async (route: any) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/test-run')) {
      await route.fulfill({ status: 500, json: { detail: 'Test run failed' } });
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
  await page.locator('button:has-text("Test Run")').click();
  await expect(page.locator('text=Test run failed')).toBeVisible();
});

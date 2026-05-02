import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('undo removes added node and redo restores it', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
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

  await page.locator('button:has-text("Add Node")').click();
  await expect(nodes).toHaveCount(2);

  // Undo
  await page.keyboard.press('Control+z');
  await expect(nodes).toHaveCount(1);

  // Redo
  await page.keyboard.press('Control+Shift+z');
  await expect(nodes).toHaveCount(2);
});

test('keyboard shortcuts trigger actions', async ({ page }) => {
  let saveCalled = false;
  await page.route('/api/workflows/**', async (route) => {
    const method = route.request().method();
    const url = route.request().url();
    if (url.includes('/versions') && method === 'POST') {
      saveCalled = true;
      await route.fulfill({
        json: {
          id: 'v_002',
          workflow_id: 'wf_001',
          version_number: 2,
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

  // Focus the page body first
  await page.locator('body').click();

  // Ctrl+S should trigger save
  await page.keyboard.press('Control+s');
  await page.waitForTimeout(500);
  expect(saveCalled).toBe(true);
});

test('dirty state indicator and beforeunload', async ({ page }) => {
  await page.route('/api/workflows/**', async (route) => {
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

  // Initially not dirty
  await expect(page.locator('[aria-label="Unsaved changes"]')).not.toBeVisible();

  // Add node → dirty
  await page.locator('button:has-text("Add Node")').click();
  await expect(page.locator('[aria-label="Unsaved changes"]')).toBeVisible();

  // Save → not dirty
  await page.locator('button:has-text("Save Version")').click();
  await expect(page.locator('[aria-label="Unsaved changes"]')).not.toBeVisible();

  // Add node again → dirty
  await page.locator('button:has-text("Add Node")').click();
  await expect(page.locator('[aria-label="Unsaved changes"]')).toBeVisible();

  // beforeunload should fire when dirty
  const beforeunloadResult = await page.evaluate(() => {
    const event = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    window.dispatchEvent(event);
    return event.defaultPrevented;
  });
  expect(beforeunloadResult).toBe(true);
});

test('confirmation dialogs for activate and test run', async ({ page }) => {
  let testRunCalled = false;
  let activateCalled = false;

  await page.route('/api/workflows/**', async (route) => {
    const method = route.request().method();
    const url = route.request().url();
    if (url.includes('/test-run')) {
      testRunCalled = true;
      await route.fulfill({ json: { status: 'ok', total_elapsed_ms: 0, total_prompt_tokens: 0, total_completion_tokens: 0, node_results: [], outputs: {} } });
    } else if (url.includes('/activate')) {
      activateCalled = true;
      await route.fulfill({ json: { activated: true } });
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

  // Test Run — cancel
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'confirm') {
      dialog.dismiss().catch(() => {});
    }
  });
  await page.locator('button:has-text("Test Run")').click();
  await page.waitForTimeout(200);
  expect(testRunCalled).toBe(false);

  // Test Run — confirm
  page.removeAllListeners('dialog');
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'confirm') {
      dialog.accept().catch(() => {});
    }
  });
  await page.locator('button:has-text("Test Run")').click();
  await page.waitForTimeout(200);
  expect(testRunCalled).toBe(true);

  // Activate Version — cancel
  activateCalled = false;
  page.removeAllListeners('dialog');
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'confirm') {
      dialog.dismiss().catch(() => {});
    }
  });
  await page.locator('button:has-text("Activate Version")').click();
  await page.waitForTimeout(200);
  expect(activateCalled).toBe(false);

  // Activate Version — confirm
  page.removeAllListeners('dialog');
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'confirm') {
      dialog.accept().catch(() => {});
    }
  });
  await page.locator('button:has-text("Activate Version")').click();
  await page.waitForTimeout(200);
  expect(activateCalled).toBe(true);
});

test('component decomposition renders subcomponents', async ({ page }) => {
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
                { id: 'n1', type: 'tool_call', position: { x: 100, y: 100 }, data: { label: 'Tool', tool_name: '' } },
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

  // EditorToolbar buttons
  await expect(page.locator('button:has-text("Save Version")')).toBeVisible();
  await expect(page.locator('button:has-text("Activate Version")')).toBeVisible();
  await expect(page.locator('button:has-text("Test Run")')).toBeVisible();
  await expect(page.locator('button:has-text("Undo")')).toBeVisible();
  await expect(page.locator('button:has-text("Redo")')).toBeVisible();

  // Click node to open NodePropertiesPanel
  const nodes = page.locator('.react-flow__node');
  await nodes.first().click();

  // NodePropertiesPanel config fields for tool_call node
  await expect(page.locator('h3:has-text("Properties")')).toBeVisible();
  await expect(page.locator('[aria-label="Tool name"]')).toBeVisible();
});

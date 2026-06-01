import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('browser stream start mode is visible', async ({ page }) => {
  await page.goto('/browser-sessions/stream');
  await expect(page.locator('h1')).toHaveText('New Browser Session');
  await expect(page.locator('input#stream-url')).toBeVisible();
  await expect(page.locator('button:has-text("Start Session")')).toBeVisible();
});

test('browser stream can start and show canvas', async ({ page }) => {
  await page.goto('/browser-sessions/stream');
  await page.fill('input#stream-url', 'https://example.com/login');

  // Mock the WebSocket connection so the page can connect
  await page.route('/api/browser-session/stream/test-session-001**', async (route) => {
    await route.fulfill({ status: 200 });
  });

  await page.click('button:has-text("Start Session")');

  // Canvas should become visible after start
  await expect(page.locator('canvas.browser-stream-canvas')).toBeVisible();

  // Status bar should show domain and timer
  await expect(page.locator('.browser-stream-domain')).toHaveText('example.com');
  await expect(page.locator('.browser-stream-timer').first()).toContainText('Elapsed:');
});

test('cancel button navigates back to browser sessions list', async ({ page }) => {
  await page.goto('/browser-sessions/stream');
  await page.fill('input#stream-url', 'https://example.com/login');

  await page.route('/api/browser-session/stream/test-session-001**', async (route) => {
    await route.fulfill({ status: 200 });
  });

  await page.click('button:has-text("Start Session")');
  await expect(page.locator('canvas.browser-stream-canvas')).toBeVisible();

  await page.click('button:has-text("Cancel")');
  await expect(page).toHaveURL(/\/browser-sessions$/);
});

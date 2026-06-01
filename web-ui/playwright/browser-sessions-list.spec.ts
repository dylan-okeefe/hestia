import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('browser sessions list renders empty state', async ({ page }) => {
  await page.goto('/browser-sessions');
  await expect(page.locator('h1')).toHaveText('Browser Sessions');
  await expect(page.locator('text=No saved browser sessions')).toBeVisible();
  await expect(page.locator('text=Click New Session to authenticate with a site.')).toBeVisible();
});

test('browser sessions list renders table with data', async ({ page }) => {
  await page.route('/api/browser-sessions', async (route) => {
    await route.fulfill({
      json: {
        sessions: [
          {
            domain: 'linkedin.com',
            has_cookies: true,
            has_storage_state: true,
            cookie_count: 14,
            last_saved: '2026-05-30T14:22:00+00:00',
            last_used: '2026-05-31T08:15:00+00:00',
            last_health_check: '2026-05-31T06:00:00+00:00',
            health_status: 'healthy',
            health_check_url: 'https://linkedin.com/feed',
          },
          {
            domain: 'example.com',
            has_cookies: false,
            has_storage_state: false,
            cookie_count: 0,
            last_saved: null,
            last_used: null,
            last_health_check: null,
            health_status: 'unknown',
            health_check_url: 'https://example.com',
          },
        ],
      },
    });
  });

  await page.goto('/browser-sessions');
  await expect(page.locator('text=linkedin.com')).toBeVisible();
  await expect(page.locator('text=example.com')).toBeVisible();
  await expect(page.locator('text=Healthy')).toBeVisible();
  await expect(page.locator('text=14')).toBeVisible();
});

test('new session button navigates to stream page', async ({ page }) => {
  await page.goto('/browser-sessions');
  await page.locator('button:has-text("New Session")').first().click();
  await expect(page).toHaveURL(/\/browser-sessions\/stream/);
});

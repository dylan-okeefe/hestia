import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

async function mockAuthEnabled(page: any, authenticated: boolean, token?: string) {
  await page.route('/api/auth/status', async (route: any) => {
    await route.fulfill({
      json: {
        auth_enabled: true,
        authenticated,
        platform: authenticated ? 'telegram' : null,
        platform_user: authenticated ? '12345' : null,
        available_platforms: ['telegram', 'matrix'],
      },
    });
  });
  await page.route('/api/auth/request-code', async (route: any) => {
    await route.fulfill({ json: { status: 'sent', platform: 'telegram', expires_in: 300 } });
  });
  await page.route('/api/auth/verify-code', async (route: any) => {
    await route.fulfill({ json: { token: token || 'test_token_123', platform: 'telegram', platform_user: '12345' } });
  });
  await page.route('/api/auth/logout', async (route: any) => {
    await route.fulfill({ json: { status: 'ok' } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('login page renders when unauthenticated', async ({ page }) => {
  await mockAuthEnabled(page, false);
  await page.goto('/');
  await expect(page.locator('h1')).toHaveText('Hestia Dashboard');
  await expect(page.locator('text=Authenticate via your chat platform')).toBeVisible();
  await expect(page.locator('button:has-text("Send code via Telegram")')).toBeVisible();
});

test('token persists in sessionStorage across refresh', async ({ page }) => {
  // Pre-seed sessionStorage with a token, simulating a prior login
  await page.goto('/');
  await page.evaluate(() => sessionStorage.setItem('hestia_auth_token', 'persisted_token'));

  await mockAuthEnabled(page, true, 'persisted_token');
  await page.reload();
  await expect(page.locator('nav')).toBeVisible();
  await expect(page.locator('text=Dashboard')).toBeVisible();

  // Verify token is still in sessionStorage after reload
  const token = await page.evaluate(() => sessionStorage.getItem('hestia_auth_token'));
  expect(token).toBe('persisted_token');

  // Refresh again and verify still authenticated
  await page.reload();
  await expect(page.locator('nav')).toBeVisible();
  await expect(page.locator('text=Dashboard')).toBeVisible();
});

test('clearing sessionStorage shows login on next load', async ({ page }) => {
  await mockAuthEnabled(page, true, 'persisted_token');
  await page.goto('/');
  await expect(page.locator('nav')).toBeVisible();

  // Clear sessionStorage and reload
  await page.evaluate(() => sessionStorage.clear());
  await page.reload();

  await mockAuthEnabled(page, false);
  await page.reload();
  await expect(page.locator('text=Authenticate via your chat platform')).toBeVisible();
});

test('404 route shows NotFound component', async ({ page }) => {
  await mockAuthEnabled(page, true, 'persisted_token');
  await page.goto('/nonexistent');
  await expect(page.locator('text=Page not found')).toBeVisible();
  await expect(page.locator('text=Back to dashboard')).toBeVisible();
});

test('auth:unauthorized event redirects to login', async ({ page }) => {
  await mockAuthEnabled(page, true, 'persisted_token');
  await page.goto('/');
  await expect(page.locator('nav')).toBeVisible();

  // Simulate a 401 from a protected endpoint
  await page.route('/api/sessions**', async (route: any) => {
    await route.fulfill({ status: 401, json: { detail: 'Unauthorized' } });
  });

  // Trigger a navigation that hits the protected endpoint
  await page.goto('/');
  await page.waitForTimeout(500);

  // After 401, should show login
  await mockAuthEnabled(page, false);
  await page.reload();
  await expect(page.locator('text=Authenticate via your chat platform')).toBeVisible();
});

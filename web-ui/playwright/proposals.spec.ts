import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('accept a proposal', async ({ page }) => {
  await page.route('/api/proposals**', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      await route.fulfill({ json: { id: 'prop_001', status: 'accepted' } });
    } else {
      await route.fulfill({
        json: {
          proposals: [
            {
              id: 'prop_001',
              type: 'identity_update',
              summary: 'Add greeting preference',
              confidence: 0.9,
              evidence: ['turn_1'],
              action: { file: 'SOUL.md', append: '- Greeting: casual' },
              status: 'accepted',
              created_at: '2024-01-15T10:00:00Z',
              expires_at: '2024-01-29T10:00:00Z',
              reviewed_at: null,
              review_note: null,
            },
          ],
        },
      });
    }
  });

  await page.goto('/proposals');
  const card = page.locator('[data-testid="proposal-card"]').first();
  await expect(card).toBeVisible();
  await card.locator('button:has-text("Accept")').click();
  await expect(card.locator('text=accepted')).toBeVisible();
});

test('history tab shows resolved proposals without action buttons', async ({ page }) => {
  await page.goto('/proposals');
  await page.locator('button:has-text("History")').click();
  const card = page.locator('[data-testid="proposal-card"]').filter({ hasText: 'accepted' });
  await expect(card).toBeVisible();
  await expect(card.locator('button:has-text("Accept")')).not.toBeVisible();
});

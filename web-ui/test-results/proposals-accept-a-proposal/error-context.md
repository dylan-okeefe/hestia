# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: proposals.spec.ts >> accept a proposal
- Location: playwright/proposals.spec.ts:8:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('[data-testid="proposal-card"]').first().locator('button:has-text("Accept")')

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - navigation [ref=e3]:
    - link "Dashboard" [ref=e4] [cursor=pointer]:
      - /url: /
    - link "Proposals" [ref=e5] [cursor=pointer]:
      - /url: /proposals
    - link "Style" [ref=e6] [cursor=pointer]:
      - /url: /style
    - link "Scheduler" [ref=e7] [cursor=pointer]:
      - /url: /scheduler
    - link "Security" [ref=e8] [cursor=pointer]:
      - /url: /security
    - link "Config" [ref=e9] [cursor=pointer]:
      - /url: /config
    - link "Workflows" [ref=e10] [cursor=pointer]:
      - /url: /workflows
  - generic [ref=e11]:
    - heading "Proposals 1" [level=1] [ref=e12]
    - generic [ref=e13]:
      - button "Pending" [ref=e14]
      - button "History" [ref=e15]
    - generic [ref=e16]:
      - generic [ref=e17]:
        - heading "identity_update" [level=3] [ref=e18]
        - generic [ref=e19]: accepted
      - paragraph [ref=e20]: Add greeting preference
      - paragraph [ref=e21]: "Confidence: 90%"
      - list [ref=e22]:
        - listitem [ref=e23]: turn_1
      - generic [ref=e24]: "{ \"file\": \"SOUL.md\", \"append\": \"- Greeting: casual\" }"
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | import { mockApis } from './fixtures';
  3  | 
  4  | test.beforeEach(async ({ page }) => {
  5  |   await mockApis(page);
  6  | });
  7  | 
  8  | test('accept a proposal', async ({ page }) => {
  9  |   await page.route('/api/proposals**', async (route) => {
  10 |     const method = route.request().method();
  11 |     if (method === 'POST') {
  12 |       await route.fulfill({ json: { id: 'prop_001', status: 'accepted' } });
  13 |     } else {
  14 |       await route.fulfill({
  15 |         json: {
  16 |           proposals: [
  17 |             {
  18 |               id: 'prop_001',
  19 |               type: 'identity_update',
  20 |               summary: 'Add greeting preference',
  21 |               confidence: 0.9,
  22 |               evidence: ['turn_1'],
  23 |               action: { file: 'SOUL.md', append: '- Greeting: casual' },
  24 |               status: 'accepted',
  25 |               created_at: '2024-01-15T10:00:00Z',
  26 |               expires_at: '2024-01-29T10:00:00Z',
  27 |               reviewed_at: null,
  28 |               review_note: null,
  29 |             },
  30 |           ],
  31 |         },
  32 |       });
  33 |     }
  34 |   });
  35 | 
  36 |   await page.goto('/proposals');
  37 |   const card = page.locator('[data-testid="proposal-card"]').first();
  38 |   await expect(card).toBeVisible();
> 39 |   await card.locator('button:has-text("Accept")').click();
     |                                                   ^ Error: locator.click: Test timeout of 30000ms exceeded.
  40 |   await expect(card.locator('text=accepted')).toBeVisible();
  41 | });
  42 | 
  43 | test('history tab shows resolved proposals without action buttons', async ({ page }) => {
  44 |   await page.goto('/proposals');
  45 |   await page.locator('button:has-text("History")').click();
  46 |   const card = page.locator('[data-testid="proposal-card"]').filter({ hasText: 'accepted' });
  47 |   await expect(card).toBeVisible();
  48 |   await expect(card.locator('button:has-text("Accept")')).not.toBeVisible();
  49 | });
  50 | 
```
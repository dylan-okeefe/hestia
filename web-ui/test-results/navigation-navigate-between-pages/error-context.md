# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: navigation.spec.ts >> navigate between pages
- Location: playwright/navigation.spec.ts:8:1

# Error details

```
Error: expect(locator).toHaveText(expected) failed

Locator:  locator('h1')
Expected: "Proposals"
Received: "Proposals 2"
Timeout:  5000ms

Call log:
  - Expect "toHaveText" with timeout 5000ms
  - waiting for locator('h1')
    9 × locator resolved to <h1>…</h1>
      - unexpected value "Proposals 2"

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - navigation [ref=e3]:
    - link "Dashboard" [ref=e4] [cursor=pointer]:
      - /url: /
    - link "Proposals" [active] [ref=e5] [cursor=pointer]:
      - /url: /proposals
    - link "Style" [ref=e6] [cursor=pointer]:
      - /url: /style
    - link "Scheduler" [ref=e7] [cursor=pointer]:
      - /url: /scheduler
    - link "Security" [ref=e8] [cursor=pointer]:
      - /url: /security
    - link "Config" [ref=e9] [cursor=pointer]:
      - /url: /config
  - generic [ref=e10]:
    - heading "Proposals 2" [level=1] [ref=e11]
    - generic [ref=e12]:
      - button "Pending" [ref=e13]
      - button "History" [ref=e14]
    - generic [ref=e15]:
      - generic [ref=e16]:
        - heading "identity_update" [level=3] [ref=e17]
        - generic [ref=e18]: pending
      - paragraph [ref=e19]: Add greeting preference
      - paragraph [ref=e20]: "Confidence: 90%"
      - list [ref=e21]:
        - listitem [ref=e22]: turn_1
      - generic [ref=e23]: "{ \"file\": \"SOUL.md\", \"append\": \"- Greeting: casual\" }"
      - generic [ref=e24]:
        - button "Accept" [ref=e25]
        - button "Reject" [ref=e26]
        - button "Defer" [ref=e27]
    - generic [ref=e28]:
      - generic [ref=e29]:
        - heading "style_update" [level=3] [ref=e30]
        - generic [ref=e31]: accepted
      - paragraph [ref=e32]: Increase formality
      - paragraph [ref=e33]: "Confidence: 75%"
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
  8  | test('navigate between pages', async ({ page }) => {
  9  |   await page.goto('/');
  10 | 
  11 |   await page.locator('a:has-text("Proposals")').click();
  12 |   await expect(page).toHaveURL(/.*\/proposals/);
> 13 |   await expect(page.locator('h1')).toHaveText('Proposals');
     |                                    ^ Error: expect(locator).toHaveText(expected) failed
  14 | 
  15 |   await page.locator('a:has-text("Scheduler")').click();
  16 |   await expect(page).toHaveURL(/.*\/scheduler/);
  17 |   await expect(page.locator('h1')).toHaveText('Scheduled Tasks');
  18 | 
  19 |   await page.locator('a:has-text("Security")').click();
  20 |   await expect(page).toHaveURL(/.*\/security/);
  21 |   await expect(page.locator('h1')).toHaveText('Security & Health');
  22 | 
  23 |   await page.locator('a:has-text("Config")').click();
  24 |   await expect(page).toHaveURL(/.*\/config/);
  25 |   await expect(page.locator('h1')).toHaveText('Configuration');
  26 | 
  27 |   await page.locator('a:has-text("Dashboard")').click();
  28 |   await expect(page).toHaveURL(/.*\/$/);
  29 |   await expect(page.locator('h1')).toHaveText('Sessions');
  30 | });
  31 | 
```
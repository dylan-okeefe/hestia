# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: config.spec.ts >> clicking a card changes the active highlight
- Location: playwright/config.spec.ts:50:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('div:has(> h3:has-text("Household"))')

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
  - generic [ref=e10]:
    - heading "Configuration" [level=1] [ref=e11]
    - generic [ref=e12]:
      - generic [ref=e13]:
        - strong [ref=e14]: Trust Preset
        - generic [ref=e15]:
          - button "paranoid" [ref=e16]
          - button "prompt_on_mobile" [ref=e17]
          - button "household" [ref=e18]
          - button "developer" [ref=e19]
      - generic [ref=e20]:
        - generic [ref=e21] [cursor=pointer]:
          - strong [ref=e22]: inference
          - generic [ref=e23]:
            - button "Reset to initial" [ref=e24]
            - generic [ref=e25]: ▼
        - generic [ref=e26]:
          - generic [ref=e29]:
            - generic [ref=e30]: base_url
            - textbox "base_url" [ref=e31]: http://127.0.0.1:8001
          - generic [ref=e34]:
            - generic [ref=e35]: model_name
            - textbox "model_name" [ref=e36]: test
      - generic [ref=e37]:
        - generic [ref=e38] [cursor=pointer]:
          - strong [ref=e39]: trust
          - generic [ref=e40]:
            - button "Reset to initial" [ref=e41]
            - generic [ref=e42]: ▼
        - generic [ref=e46]:
          - generic [ref=e47]: preset
          - textbox "preset" [ref=e48]: developer
      - generic [ref=e49]:
        - generic [ref=e50] [cursor=pointer]:
          - strong [ref=e51]: web
          - generic [ref=e52]:
            - button "Reset to initial" [ref=e53]
            - generic [ref=e54]: ▼
        - generic [ref=e55]:
          - generic [ref=e58] [cursor=pointer]:
            - checkbox "enabled" [checked] [ref=e59]
            - generic [ref=e60]: enabled
          - generic [ref=e63]:
            - generic [ref=e64]: host
            - textbox "host" [ref=e65]: 127.0.0.1
          - generic [ref=e68]:
            - generic [ref=e69]: port
            - spinbutton "port" [ref=e70]: "8765"
      - button "Save" [ref=e72]
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
  8  | test('config editor renders', async ({ page }) => {
  9  |   await page.goto('/config');
  10 |   await expect(page.locator('text=Configuration')).toBeVisible();
  11 |   await expect(page.locator('text=Trust Preset')).toBeVisible();
  12 | });
  13 | 
  14 | test('trust preset renders four cards', async ({ page }) => {
  15 |   await page.goto('/config');
  16 |   await expect(page.locator('h3:has-text("Paranoid")')).toBeVisible();
  17 |   await expect(page.locator('h3:has-text("Prompt on Mobile")')).toBeVisible();
  18 |   await expect(page.locator('h3:has-text("Household")')).toBeVisible();
  19 |   await expect(page.locator('h3:has-text("Developer")')).toBeVisible();
  20 | });
  21 | 
  22 | test('each trust preset card shows description and bullets', async ({ page }) => {
  23 |   await page.goto('/config');
  24 |   await expect(page.locator('text=Maximum safety. Every tool requires explicit confirmation.')).toBeVisible();
  25 |   await expect(page.locator('text=No tools auto-approved').first()).toBeVisible();
  26 | });
  27 | 
  28 | test('currently active preset is visually highlighted', async ({ page }) => {
  29 |   await page.goto('/config');
  30 |   // mockConfig has preset: 'developer', so Developer should be highlighted
  31 |   const developerCard = page.locator('div:has(> h3:has-text("Developer"))');
  32 |   await expect(developerCard).toHaveCSS('border-color', 'rgb(25, 118, 210)');
  33 |   await expect(developerCard).toHaveCSS('background-color', 'rgb(227, 242, 253)');
  34 | 
  35 |   const householdCard = page.locator('div:has(> h3:has-text("Household"))');
  36 |   await expect(householdCard).toHaveCSS('border-color', 'rgb(221, 221, 221)');
  37 | });
  38 | 
  39 | test('clicking a card updates the trust config section', async ({ page }) => {
  40 |   await page.goto('/config');
  41 |   const householdCard = page.locator('div:has(> h3:has-text("Household"))');
  42 |   await householdCard.click();
  43 | 
  44 |   // The trust section should now show updated household values
  45 |   await expect(page.locator('text=auto_approve_tools').first()).toBeVisible();
  46 |   const autoApproveInput = page.locator('input[value="terminal, write_file"]');
  47 |   await expect(autoApproveInput).toBeVisible();
  48 | });
  49 | 
  50 | test('clicking a card changes the active highlight', async ({ page }) => {
  51 |   await page.goto('/config');
  52 |   const householdCard = page.locator('div:has(> h3:has-text("Household"))');
> 53 |   await householdCard.click();
     |                       ^ Error: locator.click: Test timeout of 30000ms exceeded.
  54 | 
  55 |   await expect(householdCard).toHaveCSS('border-color', 'rgb(25, 118, 210)');
  56 | 
  57 |   const developerCard = page.locator('div:has(> h3:has-text("Developer"))');
  58 |   await expect(developerCard).toHaveCSS('border-color', 'rgb(221, 221, 221)');
  59 | });
  60 | 
  61 | test('save config shows not-implemented message', async ({ page }) => {
  62 |   await page.goto('/config');
  63 |   await page.locator('button:has-text("Save")').click();
  64 |   await expect(page.locator('text=Not implemented')).toBeVisible();
  65 | });
  66 | 
```
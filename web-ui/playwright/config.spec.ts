import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
});

test('config editor renders', async ({ page }) => {
  await page.goto('/config');
  await expect(page.locator('h1:has-text("Configuration")')).toBeVisible();
  await expect(page.locator('text=Trust Preset')).toBeVisible();
});

test('trust preset renders four cards', async ({ page }) => {
  await page.goto('/config');
  await expect(page.locator('h3:has-text("Paranoid")')).toBeVisible();
  await expect(page.locator('h3:has-text("Prompt on Mobile")')).toBeVisible();
  await expect(page.locator('h3:has-text("Household")')).toBeVisible();
  await expect(page.locator('h3:has-text("Developer")')).toBeVisible();
});

test('each trust preset card shows description and bullets', async ({ page }) => {
  await page.goto('/config');
  await expect(page.locator('text=Maximum safety. Every tool requires explicit confirmation.')).toBeVisible();
  await expect(page.locator('text=No tools auto-approved').first()).toBeVisible();
});

test('currently active preset is visually highlighted', async ({ page }) => {
  await page.goto('/config');
  // mockConfig has preset: 'developer', so Developer should be highlighted
  const developerCard = page.locator('div:has(> h3:has-text("Developer"))');
  await expect(developerCard).toHaveCSS('border-color', 'rgb(25, 118, 210)');
  await expect(developerCard).toHaveCSS('background-color', 'rgb(227, 242, 253)');

  const householdCard = page.locator('div:has(> h3:has-text("Household"))');
  await expect(householdCard).toHaveCSS('border-color', 'rgb(221, 221, 221)');
});

test('clicking a card updates the trust config section', async ({ page }) => {
  await page.goto('/config');
  const householdCard = page.locator('div:has(> h3:has-text("Household"))');
  await householdCard.click();

  // The trust section should now show updated household values
  await expect(page.locator('text=auto_approve_tools').first()).toBeVisible();
  const autoApproveInput = page.locator('input[value="terminal, write_file"]');
  await expect(autoApproveInput).toBeVisible();
});

test('clicking a card changes the active highlight', async ({ page }) => {
  await page.goto('/config');
  const householdCard = page.locator('div:has(> h3:has-text("Household"))');
  await householdCard.click();

  await expect(householdCard).toHaveCSS('border-color', 'rgb(25, 118, 210)');

  const developerCard = page.locator('div:has(> h3:has-text("Developer"))');
  await expect(developerCard).toHaveCSS('border-color', 'rgb(221, 221, 221)');
});

test('save config shows not-implemented message', async ({ page }) => {
  await page.goto('/config');
  await page.locator('button:has-text("Save")').click();
  await expect(page.locator('text=Not implemented')).toBeVisible();
});

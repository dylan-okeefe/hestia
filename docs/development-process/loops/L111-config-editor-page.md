# L111 — Config Editor Page

**Status:** Spec only
**Branch:** `feature/l111-config-editor` (from `feature/web-dashboard`)
**Depends on:** L105, L106

## Intent

Build a form-based config editor so operators can modify HestiaConfig through the UI instead of editing Python config files directly.

## Scope

### §1 — API client additions

```ts
export async function fetchConfig() {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json();
}

export async function saveConfig(config: object) {
  return fetch(`${API_BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}
```

### §2 — Config form component

`web-ui/src/components/ConfigForm.tsx`:
- Render each config section as a collapsible panel (Inference, Telegram, Matrix, Trust, Reflection, Style, RateLimit, etc.)
- Each field rendered as appropriate input type: text, number, boolean toggle, dropdown for enums
- Credential fields (bot_token, access_token, password) shown as masked inputs with reveal toggle
- Trust preset quick-select: buttons for paranoid / prompt_on_mobile / household / developer
- Validation: red borders for invalid values
- "Requires restart" badge on fields that need daemon restart
- "Save" button calls `saveConfig`
- "Reset to defaults" button per section

### §3 — Config page

`web-ui/src/pages/Config.tsx`:
- Wraps `ConfigForm`
- Shows save success/error messages

### §4 — Navigation

Add Config link to nav bar.

### §5 — Playwright test

`playwright/config.spec.ts`:
```ts
test('config editor renders', async ({ page }) => {
  await page.goto('/config');
  await expect(page.locator('text=Configuration')).toBeVisible();
});
```

## Evaluation

- Config page loads with current values pre-populated
- Changing a value and saving persists it
- Trust preset buttons fill in all TrustConfig fields
- Invalid values show red borders

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `npm run build` succeeds
- Playwright `config.spec.ts` passes
- `.kimi-done` includes `LOOP=L111`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
- Next: L112 (Flip to opt-out)

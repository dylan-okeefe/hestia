# L110 — Security & Health Page

**Status:** Spec only
**Branch:** `feature/l110-security-health` (from `feature/web-dashboard`)
**Depends on:** L105, L106

## Intent

Build the security and health dashboard: doctor checks with traffic-light indicators, audit findings table, and egress log.

## Scope

### §1 — API client additions

```ts
export async function runDoctor() {
  const res = await fetch(`${API_BASE}/doctor`);
  if (!res.ok) throw new Error('Doctor check failed');
  return res.json();
}

export async function runAudit() {
  const res = await fetch(`${API_BASE}/audit`);
  if (!res.ok) throw new Error('Audit failed');
  return res.json();
}

export async function fetchEgress(domain?: string, since?: string) {
  const params = new URLSearchParams();
  if (domain) params.set('domain', domain);
  if (since) params.set('since', since);
  const res = await fetch(`${API_BASE}/egress?${params}`);
  if (!res.ok) throw new Error('Failed to fetch egress');
  return res.json();
}
```

### §2 — Doctor panel

`web-ui/src/components/DoctorCheckList.tsx`:
- Traffic-light indicators (green/yellow/red) for each check
- Expandable detail on click
- "Re-run checks" button that calls `runDoctor` and refreshes

### §3 — Audit panel

`web-ui/src/components/AuditFindings.tsx`:
- Findings grouped by severity (critical → warning → info)
- Category, message, expandable details
- "Run audit" button

### §4 — Egress log panel

`web-ui/src/components/EgressLog.tsx`:
- Table: URL (query-stripped), status code, response size, timestamp
- Filter inputs for domain and time range

### §5 — Security page

`web-ui/src/pages/Security.tsx`:
- Combines Doctor, Audit, and Egress panels in sections

### §6 — Playwright test

`playwright/security.spec.ts`:
```ts
test('security page renders', async ({ page }) => {
  await page.goto('/security');
  await expect(page.locator('text=Health Checks')).toBeVisible();
  await expect(page.locator('text=Audit Findings')).toBeVisible();
});
```

## Evaluation

- Doctor panel shows traffic-light indicators
- Audit panel shows findings by severity
- Egress log is filterable
- Playwright test passes

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `npm run build` succeeds
- Playwright `security.spec.ts` passes
- `.kimi-done` includes `LOOP=L110`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
- Next: L111 (Config editor page)

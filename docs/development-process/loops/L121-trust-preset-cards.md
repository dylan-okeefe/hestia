# L121 — Trust Preset Cards with Descriptions

**Status:** Spec only
**Branch:** `feature/l121-trust-preset-cards` (from `develop`)
**Depends on:** L111 (config editor page)

## Intent

The trust preset selector in the config editor currently shows four plain buttons with preset names only. Users have no way to know what each preset does without trial and error. Each preset should be presented as a card with a title, short description, and a bulleted list of what it enables/disables.

## Scope

### §1 — Expand preset metadata

In `web-ui/src/components/ConfigForm.tsx`, replace the flat `trustPresets` object with richer metadata:

```typescript
interface TrustPreset {
  name: string;
  description: string;
  bullets: string[];
  values: Record<string, unknown>;
}

const trustPresets: Record<string, TrustPreset> = {
  paranoid: {
    name: 'Paranoid',
    description: 'Maximum safety. Every tool requires explicit confirmation.',
    bullets: [
      'No tools auto-approved',
      'Scheduler and subagent shell access disabled',
      'Self-management tools disabled',
      'No email sending from autonomous agents',
    ],
    values: {
      auto_approve_tools: [],
      scheduler_shell_exec: false,
      subagent_shell_exec: false,
      subagent_write_local: false,
      subagent_email_send: false,
      scheduler_email_send: false,
      self_management: false,
      blocked_shell_patterns: [],
      preset: 'paranoid',
    },
  },
  prompt_on_mobile: {
    name: 'Prompt on Mobile',
    description: 'Safe for phone use. Destructive tools show ✅/❌ buttons on Telegram.',
    bullets: [
      'No tools auto-approved',
      'Scheduler and subagent shell access disabled',
      'Self-management tools disabled',
      'Blocks dangerous patterns like rm -rf /',
    ],
    values: {
      auto_approve_tools: [],
      scheduler_shell_exec: false,
      subagent_shell_exec: false,
      subagent_write_local: false,
      subagent_email_send: false,
      scheduler_email_send: false,
      self_management: false,
      blocked_shell_patterns: ['rm -rf /'],
      preset: 'prompt_on_mobile',
    },
  },
  household: {
    name: 'Household',
    description: 'Balanced for daily use. Common file tools work without prompts.',
    bullets: [
      'Terminal and write_file auto-approved',
      'Subagent local file writes enabled',
      'Self-management tools enabled (proposals, style)',
      'Blocks dangerous shell patterns',
    ],
    values: {
      auto_approve_tools: ['terminal', 'write_file'],
      scheduler_shell_exec: false,
      subagent_shell_exec: false,
      subagent_write_local: true,
      subagent_email_send: false,
      scheduler_email_send: false,
      self_management: true,
      blocked_shell_patterns: ['rm -rf /', 'dd if=/dev/zero'],
      preset: 'household',
    },
  },
  developer: {
    name: 'Developer',
    description: 'Full access. All tools auto-approved, autonomous agents can send email.',
    bullets: [
      'All common tools auto-approved',
      'Scheduler and subagent shell access enabled',
      'Self-management tools enabled',
      'Email sending from autonomous agents enabled',
    ],
    values: {
      auto_approve_tools: ['terminal', 'write_file', 'read_file', 'shell'],
      scheduler_shell_exec: true,
      subagent_shell_exec: true,
      subagent_write_local: true,
      subagent_email_send: true,
      scheduler_email_send: true,
      self_management: true,
      blocked_shell_patterns: [],
      preset: 'developer',
    },
  },
};
```

**Commit:** `feat(web-ui): expand trust preset metadata with descriptions and bullets`

### §2 — Render cards

Replace the current button row in `ConfigForm.tsx` with a card grid:

```tsx
<div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
  {Object.entries(trustPresets).map(([key, preset]) => (
    <div
      key={key}
      onClick={() => applyTrustPreset(key)}
      style={{
        border: `2px solid ${currentPreset === key ? '#1976d2' : '#ddd'}`,
        borderRadius: '8px',
        padding: '1rem',
        cursor: 'pointer',
        background: currentPreset === key ? '#e3f2fd' : '#fff',
      }}
    >
      <h3 style={{ margin: '0 0 0.5rem' }}>{preset.name}</h3>
      <p style={{ margin: '0 0 0.75rem', fontSize: '0.9rem', color: '#555' }}>
        {preset.description}
      </p>
      <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#444' }}>
        {preset.bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>
    </div>
  ))}
</div>
```

- Highlight the currently active preset with a blue border and background
- Clicking a card applies that preset
- Cards are responsive (grid wraps on narrow screens)

**Commit:** `feat(web-ui): render trust presets as selectable cards with descriptions`

### §3 — Update applyTrustPreset

Update `applyTrustPreset` to use the new metadata structure:

```typescript
const applyTrustPreset = (presetKey: string) => {
  const preset = trustPresets[presetKey];
  if (!preset) return;
  setConfig((prev) => ({
    ...prev,
    trust: { ...(prev.trust as Record<string, unknown> || {}), ...preset.values },
  }));
};
```

**Commit:** `refactor(web-ui): update applyTrustPreset for new preset structure`

### §4 — Tests

1. Playwright test: config page shows 4 trust preset cards
2. Playwright test: clicking a card updates the trust config section
3. Playwright test: currently active preset is visually highlighted
4. Verify no regression: saving config still works

**Commit:** `test(web-ui): trust preset card selection and highlighting`

## Evaluation

- **Spec check:** Rich preset metadata, card grid rendering, active preset highlighting
- **Intent check:** User opens config editor, sees 4 clearly labeled cards. "Paranoid" says "Maximum safety. Every tool requires explicit confirmation." with bullets listing what is disabled. Clicking "Household" highlights that card and updates the trust config fields.
- **Regression check:** Config save still works. Existing tests pass.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green (backend unchanged, should pass)
- `npm run build` in `web-ui/` succeeds
- `ruff check src/ tests/` clean on changed files
- 4 trust preset cards visible on config page
- Each card has title, description, and bullet list
- Active preset visually highlighted
- Clicking a card applies the preset values
- `.kimi-done` includes `LOOP=L121`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`

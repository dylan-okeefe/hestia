# L176 — Quick Fixes & Polish

**Status:** Spec only  
**Branch:** `feature/l176-quick-fixes-and-polish` (from `feature/user-registry-ui-rewrite`)  
**Depends on:** L172–L175 (UI rewrite)

## Intent

The V2 review identified a cluster of small but high-impact polish issues that make the UI feel unfinished. Config keys still display in snake_case. The scheduler uses a single-line input for multi-line prompts. The nav bar says "Security" but the page says "Security & Health". Trust preset display is confusing because Profile shows per-user overrides without explaining they differ from global config. Error handling in Profile silently swallows failures. Health check re-runs give no visual feedback, and passing checks show concerning detail text in red.

These are all "last mile" issues — the infrastructure exists, it just hasn't been wired consistently. Fixing them makes the UI feel complete and trustworthy.

## Scope

### §0 — Config key labels

**Why:** The Config page is one of the most-visited pages, and it still renders raw snake_case keys like `auto_approve_tools`, `scheduler_shell_exec`, `subagent_write_local`. The `labels.ts` infrastructure exists but has no `CONFIG_KEY_LABELS` map.

In `web-ui/src/lib/labels.ts`:

1. Add `CONFIG_KEY_LABELS: Record<string, string>` covering at least:
   - Trust-related: `trust_preset`, `auto_approve_tools`, `prompt_on_mobile`
   - Core: `model_path`, `inference_url`, `context_window`, `max_tokens`
   - Platforms: `bot_token`, `allowed_users`, `allowed_rooms`, `access_token`
   - Scheduler: `scheduler_shell_exec`, `blocked_shell_patterns`
   - Features: `subagent_write_local`, `web_search_enabled`, `voice_enabled`
   - Any other keys visible in the current config form
2. Export it alongside the other label maps.

In `web-ui/src/components/ConfigForm.tsx`:

3. Import `CONFIG_KEY_LABELS` and `label` from `labels.ts`.
4. In `renderField`, replace all raw `{key}` displays with `{label(CONFIG_KEY_LABELS, key)}`.
5. Keep the raw key in a `title` attribute or small monospace sub-label for power users.

**Commit:** `feat(web-ui): human-readable labels for config keys`

### §1 — Scheduler prompt/URL textarea

**Why:** `Scheduler.tsx` line 242 uses a single-line `<input>` for prompt/URL. Prompts can be multi-line instructions. This is inconsistent with the workflow editor's textarea pattern.

In `web-ui/src/pages/Scheduler.tsx`:

1. Replace the prompt/URL `<input>` with `<textarea rows={4}>` in both the create and edit modals.
2. Keep the same placeholder text.
3. Ensure the value binds correctly to the task's `prompt` field.

**Commit:** `fix(web-ui): scheduler prompt field uses textarea for multi-line input`

### §2 — Nav label consistency

**Why:** `App.tsx` says `navLink('Security', '/security')` but the page heading says `Security & Health`. The page heading is more accurate.

In `web-ui/src/App.tsx`:

1. Change `navLink('Security', '/security')` to `navLink('Security & Health', '/security')`.

**Commit:** `fix(web-ui): match nav label to page heading`

### §3 — Trust preset clarity on Profile

**Why:** Config shows the global trust preset while Profile shows the per-user override. A user seeing "Developer" on Config and "Paranoid" on Profile would reasonably think something is broken.

In `web-ui/src/pages/Profile.tsx`:

1. Fetch the global config's trust preset via `fetchConfig()` (or add a lightweight `GET /api/config/trust-preset` endpoint if fetchConfig is too heavy).
2. Update the trust preset field label to: "Personal trust override".
3. Add helper text below the dropdown:
   - If a per-user override is set: "Overrides the global trust level (currently: {globalPreset})."
   - If no override is set: "Using global trust level: {globalPreset}. Select a preset to override it for this user only."
4. Display the effective trust level prominently: a badge showing the resolved preset (global if no override, override if set).

**Commit:** `fix(web-ui): clarify per-user trust override vs global preset on Profile`

### §4 — Profile error handling

**Why:** Multiple `catch { // swallow to match prior behavior }` blocks mean name save, notes save, identity add/remove, and room member operations fail silently. The user gets no feedback.

In `web-ui/src/pages/Profile.tsx`:

1. Remove all `catch { // swallow }` blocks.
2. In each catch, call `setError(err.message)` so the error renders in the existing error banner.
3. Clear the error banner before starting a new operation.
4. Ensure the error banner is visible (not hidden by other layout).

**Commit:** `fix(web-ui): surface errors in Profile instead of swallowing`

### §5 — Health check re-run feedback

**Why:** Clicking "Re-run checks" can feel like nothing happened if results don't visually change. The backend may not return `cached_at`.

In `src/hestia/web/routes/doctor.py`:

1. Ensure the response includes `cached_at: datetime.now(UTC).isoformat()` when checks are run.

In `web-ui/src/components/DoctorCheckList.tsx`:

2. If `cached_at` is present, show "Last checked: {formatRelativeDate(cached_at)}" prominently.
3. Add a brief pulsing animation or spinner during the re-run, even if results don't change.
4. After re-run completes, briefly flash the check list border to indicate refresh.

**Commit:** `feat(web-ui+api): health check re-run with timestamp and visual feedback`

### §6 — Health check detail coloring

**Why:** Passing checks show green dots but the detail text can be concerning (e.g., "memory.epoch_path not configured"). This is confusing.

In `web-ui/src/components/DoctorCheckList.tsx`:

1. For passing checks (`ok: true`), render detail text in neutral gray (`#666`).
2. For failing checks (`ok: false`), render detail text in warning red (`#ef4444`).
3. Keep the status dot colors unchanged.

**Commit:** `fix(web-ui): neutral detail text for passing health checks, warning for failures`

### §7 — Tests

1. **Config labels test:** Mount ConfigForm. Assert `auto_approve_tools` renders as a human-readable label.
2. **Scheduler textarea test:** Mount Scheduler create modal. Assert prompt field is `<textarea>` not `<input>`.
3. **Nav label test:** Assert nav link text is "Security & Health".
4. **Trust preset test:** Mock global preset as "Developer". Mock user override as "Paranoid". Assert helper text mentions global preset.
5. **Profile error test:** Mock save failure. Assert error banner renders with failure message.
6. **Health check color test:** Mock passing check with detail text. Assert detail rendered in gray. Mock failing check. Assert detail in red.

**Commit:** `test(web-ui): quick fixes and polish tests`

## Evaluation

- Config page shows human-readable labels for all visible keys
- Scheduler uses `<textarea rows={4}>` for prompt/URL input
- Nav label matches page heading: "Security & Health"
- Profile trust preset shows effective level and explains global vs override
- Profile surfaces all save/add/remove errors in the UI
- Health check re-run shows timestamp and visual feedback
- Passing health checks show detail in neutral gray, failing in red

## Acceptance

- `npm run build` in `web-ui/` passes
- Frontend tests pass
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L176`

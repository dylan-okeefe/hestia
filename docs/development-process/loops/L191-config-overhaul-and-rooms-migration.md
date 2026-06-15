# L191 — Config Overhaul & Rooms Migration

**Status:** Spec only  
**Branch:** `feature/l191-config-overhaul-and-rooms-migration` (from `develop`)  
**Depends on:** L176 (config key labels), L179 (rooms migration)

## Intent

Two long-standing items from the V2 review remain unaddressed: the config page is still a rendered config file (labels fixed, but structure unchanged), and pre-existing Telegram groups still need a migration path to the rooms system.

## Scope

### §1 — Config page structural overhaul

**Why:** The config page displays every key as a flat list of form fields. There's no grouping, no descriptions, no visual hierarchy. 109 keys are overwhelming.

**In `web-ui/src/pages/ConfigPage.tsx` + `ConfigPage.css`:**

1. **Group keys by category.** Add a `CONFIG_KEY_GROUPS` mapping:
   ```typescript
   const CONFIG_GROUPS = [
     { id: 'inference', label: TEXT.configGroupInference, keys: ['base_url', 'model_name', 'context_length', ...] },
     { id: 'storage', label: TEXT.configGroupStorage, keys: ['database_url', 'artifacts_dir', ...] },
     { id: 'trust', label: TEXT.configGroupTrust, keys: ['auto_approve_tools', ...] },
     // ... etc
   ];
   ```
   - Start with the most commonly changed groups: Inference, Storage, Trust, Voice, Matrix, Telegram, Web
   - Ungrouped keys fall into an "Advanced" section at the bottom

2. **Add descriptions.** Extend `CONFIG_KEY_LABELS` (or create `CONFIG_KEY_DESCRIPTIONS`) with one-sentence help text per key:
   ```typescript
   const CONFIG_KEY_DESCRIPTIONS: Record<string, string> = {
     context_length: 'Per-slot token budget. Must match llama-server --ctx-size / --parallel.',
     // ...
   };
   ```
   - Show descriptions below each field label in a smaller, muted font

3. **Improve spacing.** Add section headers with `h2` styling, vertical padding between groups, and a subtle divider line.

4. **Add search/filter.** A simple text input that filters keys by label or description. Useful for finding one key in 109.

5. **Read-only indicators.** Keys that are set via environment variables (not editable in the form) should show a lock icon or "Set via env" badge.

**Commit:** `feat(web-ui): group, describe, and search config page`

---

### §2 — Rooms migration for pre-existing Telegram groups

**Why:** Room auto-registration exists in `runners.py`, but Telegram groups that existed *before* the rooms system was added never get registered until someone sends a new message. Admins need a way to migrate existing groups.

**In `src/hestia/platforms/telegram.py` or a new CLI command:**

Option A — **CLI command:**
```bash
hestia telegram migrate-rooms
```
- Fetches all chats the bot is a member of via Telegram Bot API (`getUpdates` or `getChat`)
- For each chat not already in the `rooms` table, inserts a room record
- Maps the chat ID to `room_id`, sets `platform = 'telegram'`
- Optionally sets `allowed = false` for unknown chats so the admin can review

Option B — **Startup auto-scan:**
- On bot startup, scan known chats and auto-register any missing ones
- Log a warning for each new room so the admin notices

**Recommended: Option A (CLI command).** It's explicit, safer, and gives the admin control.

**In `src/hestia/commands/admin.py` (or create `telegram.py` CLI):**

```python
async def cmd_telegram_migrate_rooms(app: AppContext) -> None:
    """Register all existing Telegram chats as rooms."""
```

- Use the Telegram bot token from config
- Call `getUpdates` with `offset=-1` or use `getChat` for known chat IDs from message history
- Insert into `rooms` table via `RoomStore`
- Print a table of migrated rooms

**Commit:** `feat(telegram): add migrate-rooms CLI command`

## Quality gates

```bash
# Backend
cd /home/<user>/Hestia && uv run pytest tests/unit/ tests/integration/ -q
cd /home/<user>/Hestia && uv run mypy src/hestia
cd /home/<user>/Hestia && uv run ruff check src/ tests/

# Frontend
cd web-ui && npm run build
cd web-ui && npx vitest run
```

All must pass.

## Handoff

- Verify config page is navigable with 109 keys (grouping + search)
- Verify Telegram migrate-rooms registers existing chats correctly
- Verify unknown chats default to disallowed if using Option A

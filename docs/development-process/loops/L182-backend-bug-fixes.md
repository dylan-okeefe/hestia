# L182 — Backend Bug Fixes & Cleanup

**Status:** Spec only  
**Branch:** `feature/l182-backend-bug-fixes` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L176–L179

## Intent

The audit surfaced a cluster of backend bugs that are small in scope but significant in impact: the `update_user` null guard prevents clearing fields, the error dashboard performs raw SQL against a private attribute, the scheduler API accepts raw dicts, and the session messages endpoint returns turn metadata instead of actual messages. These are correctness and maintainability issues that should be fixed before merge.

## Scope

### §0 — Fix `update_user` null guard

**Why:** `updates = {k: v for k, v in fields.items() if k in allowed and v is not None}` means `trust_preset=None` and `notes=""` are silently ignored. A user cannot clear their trust override or notes.

In `src/hestia/persistence/users.py`:

1. Change line 138 from:
   ```python
   updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
   ```
   To:
   ```python
   updates = {k: v for k, v in fields.items() if k in allowed}
   ```
2. Same fix for `update_room` (line 280).
3. Add tests that verify clearing `trust_preset` to `None` and `notes` to `""` works.

**Commit:** `fix(persistence): allow clearing fields to None/empty in update_user`

### §1 — Fix error dashboard raw SQL

**Why:** `errors.py:178` reaches into `ctx.session_store._db.engine` and executes raw SQL against the `turns` table. This breaks encapsulation.

In `src/hestia/persistence/sessions.py`:

1. Add `async def get_turn_messages(self, turn_id: str) -> dict[str, str] | None`:
   ```python
   query = sa.select(turns.c.user_message, turns.c.final_response).where(turns.c.id == turn_id)
   async with self._db.engine.connect() as conn:
       result = await conn.execute(query)
       row = result.mappings().first()
       if row:
           return {"user_message": row.user_message, "final_response": row.final_response}
       return None
   ```

In `src/hestia/web/routes/errors.py`:

2. Replace the raw SQL block with:
   ```python
   messages = await ctx.session_store.get_turn_messages(turn_id)
   if messages:
       user_msg = messages["user_message"]
       assistant_msg = messages["final_response"]
   ```
3. Remove the inline sqlalchemy import.

**Commit:** `refactor(api): remove raw SQL from error dashboard`

### §2 — Fix session messages endpoint

**Why:** `GET /api/sessions/{id}/messages` returns turn metadata (state, iterations, error) but no actual message content. The endpoint name promises messages.

In `src/hestia/web/routes/sessions.py`:

1. Rename the endpoint to `/api/sessions/{id}/turns` to match what it actually returns, OR
2. Actually fetch messages and include them:
   ```python
   session = await ctx.session_store.get_session(session_id)
   turns = await ctx.session_store.list_turns_for_session(session_id)
   messages = await ctx.session_store.get_messages(session_id)  # if available
   return {
       "session": {...},
       "turns": [...],
       "messages": [serialize(m) for m in messages],
   }
   ```

If `get_messages` doesn't exist, add it to `SessionStore`.

**Commit:** `feat(api): session messages endpoint returns actual message content`

### §3 — Cap in-memory error state

**Why:** `_resolved_ids` and `_ignored_ids` are unbounded sets. An attacker can grow them indefinitely.

In `src/hestia/web/routes/errors.py`:

1. Add a max size check:
   ```python
   _MAX_RESOLVED = 10_000
   
   def _mark_resolved(error_id: str) -> None:
       _resolved_ids.add(error_id)
       if len(_resolved_ids) > _MAX_RESOLVED:
           _resolved_ids.pop()  # Remove arbitrary oldest
   ```
2. Document the in-memory nature of resolution state in the route docstrings.

**Commit:** `fix(api): cap in-memory error resolution state size`

### §4 — Fix `send_message` node platform_user cast crash

**Why:** `PlatformNotifier.send_interactive` does `chat_id=int(platform_user)`. If `platform_user` is a Matrix room ID or non-numeric string, this crashes with `ValueError`.

In `src/hestia/workflows/nodes/send_message.py`:

1. Validate `platform_user` before calling `send_interactive`:
   ```python
   if platform == "telegram":
       try:
           int(platform_user)
       except ValueError:
           raise ValueError(f"Invalid Telegram chat ID: {platform_user}")
   ```

In `src/hestia/platforms/notifier.py`:

2. Handle the cast gracefully:
   ```python
   try:
       chat_id = int(platform_user)
   except ValueError:
       raise ValueError(f"Cannot send interactive message to non-numeric Telegram ID: {platform_user}")
   ```

**Commit:** `fix(workflows): validate platform_user before interactive send`

### §5 — Fix `send_message` timeout coercion

**Why:** `(value as number) || 300` means `0` becomes `300`. A user cannot set a 0-second timeout.

In `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx`:

1. Change to:
   ```typescript
   value={selectedNode.data.timeout_seconds ?? 300}
   ```

In `src/hestia/workflows/nodes/send_message.py`:

2. Validate `timeout_seconds` is a non-negative number:
   ```python
   timeout_seconds = node.config.get("timeout_seconds", 300)
   if not isinstance(timeout_seconds, (int, float)) or timeout_seconds < 0:
       timeout_seconds = 300
   ```

**Commit:** `fix(workflows): allow zero-second timeout and validate input`

### §6 — Tests

1. **update_user clear test:** Update user with `trust_preset=None`. Assert field is cleared.
2. **Error dashboard SQL removal test:** Mock `get_turn_messages`. Assert no raw SQL executed.
3. **Session messages content test:** Create session with messages. Assert endpoint returns message content.
4. **Error state cap test:** Add 10,001 resolved IDs. Assert size stays at 10,000.
5. **Interactive send validation test:** Pass Matrix room ID to Telegram interactive send. Assert `ValueError`.

**Commit:** `test: backend bug fix tests`

## Evaluation

- `update_user` allows clearing fields to `None` and empty string
- Error dashboard uses `SessionStore` interface, not raw SQL
- Session messages endpoint returns actual message content
- Error resolution state is bounded
- Interactive send validates platform_user format
- Timeout accepts 0 and rejects negative values

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L182`

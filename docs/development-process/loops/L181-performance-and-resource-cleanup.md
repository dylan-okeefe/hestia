# L181 — Performance & Resource Cleanup

**Status:** Spec only  
**Branch:** `feature/l181-performance-cleanup` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L176–L179

## Intent

The audit identified three performance/resource issues that will degrade the system as data grows: N+1 queries in list endpoints, memory leaks in the workflow response store, and connection leaks in platform notifiers. These are not immediately visible in a low-data environment, but they are ticking time bombs for any real deployment.

## Scope

### §0 — Fix N+1 query in `list_users`

**Why:** `users.py:list_users` calls `get_identities(u.id)` and `get_user_rooms(u.id)` once per user. With 100 users, that's 201 queries.

In `src/hestia/persistence/users.py`:

1. Add `async def get_identities_for_users(self, user_ids: list[str]) -> dict[str, list[Identity]]`:
   ```python
   query = sa.select(user_identities).where(user_identities.c.user_id.in_(user_ids))
   async with self._db.engine.connect() as conn:
       result = await conn.execute(query)
       rows = result.mappings().all()
   # Group by user_id
   ```
2. Add `async def get_rooms_for_users(self, user_ids: list[str]) -> dict[str, list[Room]]`.
3. In `users.py:list_users` (the route), use batch queries:
   ```python
   user_ids = [u.id for u in users]
   identities_map = await ctx.user_store.get_identities_for_users(user_ids)
   rooms_map = await ctx.user_store.get_rooms_for_users(user_ids)
   for u in users:
       identities = identities_map.get(u.id, [])
       rooms = rooms_map.get(u.id, [])
   ```

**Commit:** `perf(api): batch identities and rooms queries in list_users`

### §1 — Fix N+1 query in `list_sessions`

**Why:** `sessions.py:list_sessions` calls `count_turns_for_session(s.id)` once per session.

In `src/hestia/persistence/sessions.py`:

1. Add `async def count_turns_for_sessions(self, session_ids: list[str]) -> dict[str, int]`:
   ```python
   query = (
       sa.select(turns.c.session_id, sa.func.count(turns.c.id))
       .where(turns.c.session_id.in_(session_ids))
       .group_by(turns.c.session_id)
   )
   ```
2. In the route, use the batch method instead of looping.

**Commit:** `perf(api): batch turn count query in list_sessions`

### §2 — Add TTL cleanup to WorkflowResponseStore

**Why:** Pending workflow responses leak memory if the user never responds. The store grows unbounded.

In `src/hestia/workflows/response_store.py`:

1. Add `_sweep_stale` method:
   ```python
   async def _sweep_stale(self, interval: float = 60.0) -> None:
       while True:
           await asyncio.sleep(interval)
           now = datetime.now(UTC)
           stale = [
               rid for rid, req in self._pending.items()
               if now - req.created_at > timedelta(seconds=req.timeout_seconds * 2)
           ]
           for rid in stale:
               self.cancel(rid)
   ```
2. Start the sweep task in the constructor or when the first request is created.
3. Add a `stop()` method to cancel the sweep task for clean shutdown.

**Commit:** `fix(workflows): add TTL cleanup to WorkflowResponseStore`

### §3 — Fix Telegram Bot connection leak

**Why:** `PlatformNotifier._send_telegram_interactive` creates a new `telegram.Bot` on every call without closing it.

In `src/hestia/platforms/notifier.py`:

1. Cache a single `telegram.Bot` instance:
   ```python
   self._telegram_bot: telegram.Bot | None = None
   
   def _get_telegram_bot(self) -> telegram.Bot:
       if self._telegram_bot is None:
           self._telegram_bot = telegram.Bot(token=self.telegram_config.bot_token)
       return self._telegram_bot
   ```
2. Use the cached instance in both `_send_telegram` and `_send_telegram_interactive`.
3. Add `async def close(self)` to close the bot on shutdown.

**Commit:** `fix(platforms): cache Telegram Bot instance to prevent connection leaks`

### §4 — Fix Matrix txn_id collision

**Why:** `_send_matrix` uses `txn_id = hash(text) & 0xFFFFFFFF`. Duplicate text gets the same txn_id, and Matrix may deduplicate the second send.

In `src/hestia/platforms/notifier.py`:

1. Replace `hash(text)` with a random or monotonic ID:
   ```python
   import uuid
   txn_id = uuid.uuid4().hex[:16]
   ```

**Commit:** `fix(platforms): use random txn_id for Matrix notifications`

### §5 — Add session/task ownership to error aggregation

**Why:** The error dashboard currently aggregates errors from all sessions/tasks. After L180 adds auth restrictions, the error API needs to filter by the caller's resources.

In `src/hestia/web/routes/errors.py`:

1. Update `list_errors` to only aggregate errors from workflows/tasks/sessions owned by the caller (or all if admin).
2. This is coupled with L180 §3; implement together or ensure compatibility.

**Commit:** `fix(api): filter error aggregation by caller ownership`

### §6 — Tests

1. **Batch query test:** Create 10 users with identities. Call `list_users`. Assert exactly 3 DB queries (users, identities, rooms).
2. **Batch session test:** Create 10 sessions with turns. Call `list_sessions`. Assert exactly 2 DB queries (sessions, turn counts).
3. **Response store TTL test:** Create a pending request with 1-second timeout. Wait 3 seconds. Assert the request is removed from the store.
4. **Telegram bot cache test:** Send two interactive messages. Assert the same Bot instance is reused.

**Commit:** `test: performance and resource cleanup tests`

## Evaluation

- `list_users` makes 3 queries total regardless of user count
- `list_sessions` makes 2 queries total regardless of session count
- WorkflowResponseStore removes stale requests automatically
- Telegram Bot is cached and reused
- Matrix notifications use unique txn_ids

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L181`

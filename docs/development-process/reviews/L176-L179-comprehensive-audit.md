# Comprehensive Audit: L176–L179 (V2 Follow-up Work)

**Branch:** `feature/l179-rooms-interactive-nodes`  
**Auditor:** Kimi (orchestrator)  
**Date:** 2026-05-18  
**Scope:** All changes from L170 through L179 (~46,000 lines across backend + frontend)

---

## Executive Summary

**Overall Score: 6.5/10**

This is genuinely good work. The L169 review feedback was taken seriously: wrong-user bugs are fixed, dropdowns replaced text inputs, the scheduler is a real CRUD interface, and new Admin Users + Error Dashboard pages make Hestia feel like a product rather than a developer tool. The interactive workflow node feature is implemented with proper async primitives and tests.

**But it's not production-ready.** There are **authorization gaps** (any authenticated user can read anyone's sessions, memories, and errors), **N+1 query patterns** that will degrade as data grows, **memory leaks** in the workflow response store, **resource leaks** in platform notifiers, and **680 inline style objects** across the frontend that make global changes nearly impossible. The `NodePropertiesPanel` component has grown to 749 lines and contains 103 inline style objects.

The codebase shows clear signs of being built by someone who cares about correctness (session upsert comments, retry logic, comprehensive tests) and usability (trust preset cards, cron builder, variable insertion). With the security and performance gaps closed, this is a solid foundation.

---

## 1. Comparison to Review Findings

### L169 V1 Review Issues

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 1 | Profile.tsx `users[0]` bug | **Fixed** | `useCurrentUser()` fetches by `auth.userId` |
| 2 | Login identity passthrough | **Fixed** | `handleRequestCode` resolves `platformUser` from selected user identities |
| 3 | Migration creates rooms as users | **Fixed** | `!`-prefixed Matrix IDs become Room records |
| 4 | `child` role missing | **Fixed** | `_ROLES` includes `"child"` |
| 5 | `resolved_user: Any` | **Fixed** | `User \| None` in both `types.py` and `engine.py` |
| 6 | Knowledge hardcoded style fetch | **Partially fixed** | Uses first identity, still falls back to `('cli', 'default')` |
| 7 | `delete_user` no room_members cascade | **Fixed** | Explicit `DELETE FROM room_members` before user delete |
| 8 | No OpenUI integration | **Not fixed** | Still inline styles throughout; tech debt at 680 objects |
| 9 | Handoff summaries placeholder | **Fixed** | Real data from `GET /api/users/{id}/handoffs` |

### L169 V2 Review Issues

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 1 | Config key labels | **Fixed** | `CONFIG_KEY_LABELS` (~100 entries) applied in `ConfigForm.tsx` |
| 2 | Scheduler textarea | **Fixed** | `<textarea rows={4}>` in create/edit modals |
| 3 | Nav "Security" mismatch | **Fixed** | Both nav and heading say "Security & Health" |
| 4 | Trust preset confusion | **Fixed** | Profile shows "Personal trust override" with global context |
| 5 | Memory tags not clickable | **Fixed** | Toggle filter chips with "Showing X of Y" and Clear |
| 6 | Memory description misleading | **Partially fixed** | Description updated, but content is still session summaries |
| 7 | Session history null data | **Partially fixed** | `started_at` formats correctly; `message_count` works via `count_turns` |
| 8 | Sessions not reviewable | **Fixed** | `SessionDetail.tsx` at `/sessions/:id` |
| 9 | Rooms empty for Telegram | **Partially fixed** | `migrate-rooms` CLI exists; auto-registration on new messages |
| 10 | No admin Users page | **Fixed** | `AdminUsers.tsx` with full CRUD |
| 11 | No errors/failures page | **Fixed** | `ErrorDashboard.tsx` with resolve/ignore/debug |
| 12 | Health check re-run feedback | **Fixed** | Flash animation + `cachedAt` timestamp |
| 13 | Health check detail coloring | **Fixed** | Gray for passing, red for failing |
| 14 | `resolved_user` still `Any` | **Fixed** | (see above) |
| 15 | `room_members` cascade | **Fixed** | (see above) |
| 16 | Profile error swallowing | **Fixed** | All catches call `setError(err.message)` |

---

## 2. Backend Audit

### Critical Security Issues

#### 2.1 No Per-User Authorization on Personal Data Routes

**Severity: HIGH**

The global `AuthMiddleware` enforces Bearer token auth on all `/api/*` routes (except `/api/auth/*` and `/api/webhooks/*`). However, **none of the new routes enforce that the caller can only access their own data.** Any authenticated user can:

- `GET /api/sessions` → list **all** sessions in the system
- `GET /api/sessions/{id}/messages` → read **any** conversation transcript
- `GET /api/memory` → list **all** memories (including other users')
- `DELETE /api/memory/{id}` → delete **any** memory
- `GET /api/errors` → view **all** system errors (may contain stack traces, user data)
- `POST /api/scheduler/tasks` → create tasks in **any** session
- `DELETE /api/scheduler/tasks/{id}` → delete **any** scheduled task

**Fix:** Each route that returns personal data should filter by the authenticated user's `platform_user` or `user_id` from `request.state`. Admin-only routes (like user management) already enforce this via `_require_admin` — the same pattern should apply to personal data routes.

```python
# Example fix for sessions
@router.get("")
async def list_sessions(
    request: Request,
    platform: str | None = Query(None),
    platform_user: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    # Enforce caller can only see their own sessions
    caller = request.state.platform_user
    sessions = await ctx.session_store.list_sessions(
        limit=limit,
        platform=request.state.platform,
        platform_user=caller,
    )
    ...
```

#### 2.2 Scheduler CRUD Has No Ownership Checks

**Severity: HIGH**

`POST /api/scheduler/tasks` accepts `session_id` from the payload with no validation. An attacker could attach tasks to arbitrary sessions. `DELETE` and `PUT` similarly don't check ownership.

**Fix:** Derive `session_id` from the authenticated user, or validate that the provided `session_id` belongs to the caller.

### Performance Issues

#### 2.3 N+1 Queries in List Endpoints

**Severity: MEDIUM (will become HIGH as data grows)**

**`users.py:list_users`** (lines 33–51):
```python
for u in users:
    identities = await ctx.user_store.get_identities(u.id)   # +1 query per user
    rooms = await ctx.user_store.get_user_rooms(u.id)        # +1 query per user
```
With 100 users, this is 201 queries. With 1,000 users, it's 2,001 queries.

**`sessions.py:list_sessions`** (lines 28–41):
```python
for s in sessions:
    message_count = await ctx.session_store.count_turns_for_session(s.id)  # +1 per session
```

**Fix:** Use batch queries. For users: `get_identities_for_users([u.id for u in users])` returning a `dict[user_id, list[Identity]]`. For sessions: add `COUNT(turns.id)` as a subquery in the main session SELECT.

#### 2.4 Memory Leak in WorkflowResponseStore

**Severity: MEDIUM**

`src/hestia/workflows/response_store.py` stores pending requests in a module-level `dict[str, WorkflowResponseRequest]` with **no TTL or cleanup**. If a workflow creates an interactive node and the user never responds (or the platform message fails), the entry leaks forever.

**Fix:** Add a periodic cleanup task:
```python
async def _sweep_stale(self) -> None:
    now = datetime.now(UTC)
    stale = [
        rid for rid, req in self._pending.items()
        if now - req.created_at > timedelta(seconds=req.timeout_seconds * 2)
    ]
    for rid in stale:
        self.cancel(rid)
```
Call this every 60 seconds via `asyncio.create_task`.

#### 2.5 Resource Leak in PlatformNotifier

**Severity: MEDIUM**

`PlatformNotifier._send_telegram_interactive` creates a new `telegram.Bot` instance on every call without closing it. Over time, this leaks httpx client connections.

**Fix:** Cache a single `telegram.Bot` instance as an instance variable, or use `async with bot:` context manager.

### Code Quality Issues

#### 2.6 `update_user` Null Guard Bug

**`src/hestia/persistence/users.py:138`**:
```python
updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
```
This means you **cannot clear a field to `None`** or an empty string. Setting `trust_preset=None` or `notes=""` is silently ignored. The same bug exists in `update_room` (line 280).

**Fix:** Remove `and v is not None`. If the caller wants to preserve existing values, they simply shouldn't pass the key.

#### 2.7 Error Dashboard Abstraction Violation

**`src/hestia/web/routes/errors.py:178`**:
```python
async with ctx.session_store._db.engine.connect() as conn:
    result = await conn.execute(
        sa.text("SELECT user_message, final_response FROM turns WHERE id = :id"),
        {"id": turn_id},
    )
```
This reaches into a private `_db.engine` attribute and executes raw SQL against a table that belongs to the session store. This breaks encapsulation. If the session store changes its connection strategy or table schema, this route breaks silently.

**Fix:** Add a `get_turn_messages(turn_id)` method to `SessionStore` and call it.

#### 2.8 `errors.py` In-Memory State Issues

`_resolved_ids` and `_ignored_ids` are module-level sets with:
- **No size limit** — an attacker can resolve arbitrary IDs to grow memory unbounded
- **No persistence** — server restart wipes all resolution state
- **No validation** — resolving a non-existent ID still adds it to the set

These are acceptable for a v1 dashboard, but should be documented as known limitations.

#### 2.9 Session Messages Endpoint Name Mismatch

`GET /api/sessions/{id}/messages` returns turn **metadata** (state, iterations, error) but **not actual message content**. The endpoint name promises messages; it delivers turn summaries. `SessionDetail.tsx` shows a "conversation transcript" that is actually just a list of turn states with no content.

**Fix:** Either rename the endpoint to `/turns` and update the UI copy, or actually fetch and return message content via `session_store.get_messages(session_id)`.

#### 2.10 Scheduler API Uses Raw Dicts

`POST /api/scheduler/tasks` and `PUT /api/scheduler/tasks/{id}` accept `payload: dict[str, Any]` with no Pydantic model. This means:
- No automatic validation
- No OpenAPI docs for the request body
- No IDE autocomplete
- `cron_expression` is stored without validation (will fail at runtime, not API time)
- `notify` is not read from the payload on create

**Fix:** Define a Pydantic model:
```python
class TaskCreate(BaseModel):
    prompt: str
    description: str | None = None
    cron_expression: str | None = None
    enabled: bool = True
    notify: bool = False
```

---

## 3. Frontend Audit

### Structural Concerns

#### 3.1 Inline Style Proliferation

**680 inline `style={{...}}` objects** across the frontend. Every component invents its own colors, spacing, and border-radius. This makes global changes (e.g., "make our primary color slightly darker") nearly impossible.

**Worst offenders:**
- `NodePropertiesPanel.tsx`: 103 inline styles
- `AdminUsers.tsx`: 53 inline styles
- `ErrorDashboard.tsx`: 44 inline styles
- `Knowledge.tsx`: 46 inline styles
- `Profile.tsx`: 37 inline styles

**Impact:** The review called for OpenUI adoption to solve this. It didn't happen. Each new page adds ~40–60 more inline styles. At this rate, a design system migration will require touching every single component.

**Fix:** At minimum, extract a `theme.ts` with design tokens:
```typescript
export const theme = {
  colors: { primary: '#2563eb', danger: '#ef4444', surface: '#fff', text: '#333', muted: '#666' },
  spacing: { xs: '0.25rem', sm: '0.5rem', md: '1rem', lg: '1.5rem', xl: '2rem' },
  radius: { sm: '4px', md: '8px', lg: '12px' },
  fontSize: { sm: '0.875rem', md: '1rem', lg: '1.25rem' },
};
```
Then replace `style={{ color: '#666' }}` with `style={{ color: theme.colors.muted }}`.

#### 3.2 `NodePropertiesPanel.tsx` is Unmaintainable

**749 lines, 103 inline styles, 6 co-located helper components.** This single file handles configuration panels for 6 node types (`send_message`, `tool_call`, `llm_decision`, `condition`, `investigate`, `http_request`).

**Specific issues:**
- `JsonTextarea` manages its own state independently of the parent — a controlled/uncontrolled hybrid bug (lines 111–170). If the parent passes a new `value` prop, the textarea won't update until blur.
- `InsertVariableDropdown` mutates DOM directly via refs (lines 235–258), bypassing React state.
- Uses item **values** as React keys (lines 396, 435, 448, 542), causing incorrect diffing if duplicates exist.
- `timeout_seconds` coercion: `(value as number) || 300` means `0` becomes `300` (line 607).
- `Number(e.target.value)` can store `NaN` in node data (line 611).

**Fix:** Split into `components/workflow-editor/node-config-panels/` with one file per node type. Extract shared primitives (`JsonEditor`, `VariablePicker`, `TemplatePreview`) into reusable components.

#### 3.3 Frontend Constants Out of Sync with Backend

`TRIGGER_LABELS`, `NODE_TYPE_LABELS`, `STATIC_PLATFORMS`, and `TRIGGER_VARIABLES` are all hardcoded in the frontend. If the backend adds a new trigger type or node type, the UI shows raw snake_case until someone updates the TypeScript file.

**Fix:** Expose `/api/schema` or `/api/workflows/schema` that returns trigger types, node types, and their variable schemas. Have the frontend fetch this on app load.

### Component-Specific Issues

#### 3.4 `ErrorDashboard.tsx` Unhandled Async Errors

Lines 67–80: `handleResolve`, `handleIgnore`, and `handleDebug` are async but not wrapped in try/catch. If the API call fails, the promise rejection is unhandled and the UI shows no feedback.

**Fix:**
```typescript
const handleResolve = async (id: string) => {
  try {
    await resolveError(id);
    refetch();
  } catch (err: any) {
    setError(err.message);
  }
};
```

#### 3.5 `AdminUsers.tsx` Client-Side Access Control Illusion

Line 133: `if (currentUser?.role !== 'admin')` is client-side only. An attacker can bypass this by tampering with local state. The backend DOES enforce admin via `_require_admin`, so the API is safe, but the frontend "security" is misleading.

**Fix:** This is actually fine as defense-in-depth, but add a comment explaining that the real protection is server-side.

#### 3.6 `CronBuilder` Potential Update Loop

Lines 30–45: `useEffect` with `[value]` dependency calls `onChange(cron)` when frequency/time changes. If `onChange` updates parent state which updates `value`, this could loop. The `cron !== value` check short-circuits in practice, but this is fragile.

**Fix:** Use `useCallback` for the build logic and ensure `onChange` is stable via `useCallback` in the parent.

### Accessibility Issues

Multiple modals across `AdminUsers.tsx`, `ErrorDashboard.tsx`, and `Scheduler.tsx` lack:
- `role="dialog"` and `aria-modal="true"`
- Focus traps
- Escape key handlers
- `aria-label` or `aria-labelledby`

Form inputs in modals are not wrapped in `<form>` elements, so Enter key does not submit.

---

## 4. Architecture & Structural Concerns

### Where the Structure is Straining

#### 4.1 `UserStore` is a God Class

**398 lines** handling users, identities, rooms, and room members. It's approaching unmaintainable. Consider splitting:
- `UserStore`: users + identities
- `RoomStore`: rooms + room_members

#### 4.2 `SessionStore` is Too Large

**963 lines** mixing session CRUD, message CRUD, turn CRUD, handoff CRUD, and slot management. The file has grown beyond the cognitive load a developer can hold in working memory.

#### 4.3 Frontend Has No Shared Style System

680 inline style objects mean:
- No consistent spacing scale
- No consistent color palette
- No way to implement dark mode
- No way to rebrand
- Every new component re-invents button/input/card styling

This is the most expensive technical debt on the frontend. It compounds with every new page.

#### 4.4 `PlatformNotifier` Handles Too Many Platforms

Telegram, Matrix, and generic fallback in one class. Adding Discord or Email will push it over the edge.

#### 4.5 Test Files Out of Sync

`tests/unit/persistence/test_sessions.py` instantiates `SessionStore(db, memory_store=..., session_summarizer=...)` but the current `__init__` only accepts `(db, event_bus=None)`. The test file is testing stale code.

---

## 5. Top 10 Recommendations (Prioritized)

### 1. 🔒 Add Per-User Authorization to Personal Data Routes
**Files:** `sessions.py`, `memory.py`, `scheduler.py`, `errors.py`  
**Effort:** Small  
**Impact:** Critical security fix. Filter queries by `request.state.platform_user` or `request.state.user_id`.

### 2. 🔒 Add Input Validation to Scheduler API
**Files:** `scheduler.py`  
**Effort:** Small  
**Impact:** Prevents invalid cron expressions and missing fields from being stored.

### 3. 🔧 Fix N+1 Queries in List Endpoints
**Files:** `users.py`, `sessions.py`  
**Effort:** Medium  
**Impact:** Prevents performance degradation as data scales. Use batch queries or JOINs.

### 4. 🔧 Extract `NodePropertiesPanel` into Sub-Components
**Files:** `NodePropertiesPanel.tsx`  
**Effort:** Medium  
**Impact:** Makes the workflow editor maintainable. One file per node type.

### 5. 🔧 Add TTL/Cleanup to `WorkflowResponseStore`
**Files:** `response_store.py`  
**Effort:** Small  
**Impact:** Prevents memory leaks from stale pending requests.

### 6. 🔧 Fix `update_user` Null Guard Bug
**Files:** `users.py`  
**Effort:** Tiny (1 line)  
**Impact:** Allows clearing fields like `trust_preset` and `notes`.

### 7. 🔧 Close Telegram Bot Instances
**Files:** `notifier.py`  
**Effort:** Small  
**Impact:** Prevents httpx connection leaks over time.

### 8. 🔧 Introduce Minimal Design Tokens
**Files:** New `theme.ts`, then incremental migration  
**Effort:** Medium  
**Impact:** Makes the UI maintainable. Start with colors and spacing constants.

### 9. 🔧 Return Actual Messages in Session Detail
**Files:** `sessions.py`, `SessionDetail.tsx`  
**Effort:** Small  
**Impact:** The session detail page currently shows turn metadata, not conversation content. Rename endpoint or add messages.

### 10. 🔧 Fix Raw SQL in Error Dashboard
**Files:** `errors.py`  
**Effort:** Small  
**Impact:** Removes abstraction violation. Add `get_turn_messages()` to `SessionStore`.

---

## 6. Honest Overall Opinion

**This is good work that needs a security and performance pass before merge.**

The L169 review feedback was absorbed and acted upon. The migration bug is fixed. The login flow works. Dropdowns replaced free-text inputs. The scheduler is a real CRUD interface. Health checks have remediation guidance. New pages (Admin Users, Error Dashboard, Session Detail) fill genuine functional gaps. The interactive workflow node feature is implemented with solid async primitives.

**What's genuinely well done:**
- The `labels.ts` / `format.ts` infrastructure solves systemic UI problems
- The session upsert logic with dialect-aware SQL and retry loops shows care for correctness
- The cron builder with validation and natural-language preview is polished
- Tool schema rendering in the workflow editor is genuinely excellent UX
- Comprehensive test coverage (115 frontend tests across 21 files)

**What blocks merge:**
- Any authenticated user can read any other user's sessions, memories, and conversation history
- N+1 queries will cause timeouts as usage scales
- Memory leaks in the workflow response store
- Resource leaks in platform notifiers

**What is accumulating dangerous tech debt:**
- 680 inline style objects and growing
- `NodePropertiesPanel.tsx` at 749 lines
- Frontend constants (trigger types, node types) out of sync with backend

## 7. Remediation Loop Specifications

All findings have been specced as standalone loops. See the individual loop files for full implementation plans.

| Finding | Loop | Section |
|---------|------|---------|
| Authorization gaps on sessions, memory, scheduler, errors | **L180** | §0–§5 |
| N+1 queries in `list_users`, `list_sessions` | **L181** | §0–§1 |
| Memory leak in `WorkflowResponseStore` | **L181** | §2 |
| Telegram Bot connection leak | **L181** | §3 |
| Matrix `txn_id` collision | **L181** | §4 |
| `update_user` null guard bug | **L182** | §0 |
| Raw SQL in error dashboard | **L182** | §1 |
| Session messages endpoint returns turns | **L182** | §2 |
| Unbounded in-memory error state | **L182** | §3 |
| `send_message` `platform_user` crash | **L182** | §4 |
| `timeout_seconds` coercion bug | **L182** | §5 |
| 680 inline style objects | **L184** | §0–§7 |
| Login page right-edge padding bug | **L184** | §3 |
| No shared CSS / design tokens | **L184** | §0–§1 |
| No mobile layout | **L185** | §0–§7 |
| No dark mode | **L186** | §0–§7 |
| Scattered user-facing text | **L183** | §0–§5 |

### Execution Order

```
Phase 1 (parallel):
  L180 — Security & Authorization Hardening
  L181 — Performance & Resource Cleanup
  L182 — Backend Bug Fixes & Cleanup

Phase 2 (sequential, depends on L184):
  L184 — Shared CSS System
  L185 — Responsive Design
  L186 — Dark Mode

Phase 3 (independent):
  L183 — User-Facing Text Extraction
```

Phase 1 and Phase 3 can run concurrently. Phase 2 must run in order because each builds on the previous CSS foundation.

---

## 8. Honest Overall Opinion

**This is good work that needs a security and performance pass before merge.**

The L169 review feedback was absorbed and acted upon. The migration bug is fixed. The login flow works. Dropdowns replaced free-text inputs. The scheduler is a real CRUD interface. Health checks have remediation guidance. New pages (Admin Users, Error Dashboard, Session Detail) fill genuine functional gaps. The interactive workflow node feature is implemented with solid async primitives.

**What's genuinely well done:**
- The `labels.ts` / `format.ts` infrastructure solves systemic UI problems
- The session upsert logic with dialect-aware SQL and retry loops shows care for correctness
- The cron builder with validation and natural-language preview is polished
- Tool schema rendering in the workflow editor is genuinely excellent UX
- Comprehensive test coverage (115 frontend tests across 21 files)

**What blocks merge:**
- Any authenticated user can read any other user's sessions, memories, and conversation history
- N+1 queries will cause timeouts as usage scales
- Memory leaks in the workflow response store
- Resource leaks in platform notifiers

**What is accumulating dangerous tech debt:**
- 680 inline style objects and growing
- `NodePropertiesPanel.tsx` at 749 lines
- Frontend constants (trigger types, node types) out of sync with backend

**My recommendation:**
1. Run L180 (security) and L181 (performance) first — these are blockers
2. Run L182 (bug fixes) in parallel
3. Merge to develop
4. Run L184 → L185 → L186 (style overhaul) and L183 (text extraction) next

The codebase is functional, well-tested, and shows clear craftsmanship in the details that matter (retry logic, type safety, error handling). The gaps are identifiable and fixable. This is a solid foundation for the next phase.

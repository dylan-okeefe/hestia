# L211 — Browser Session Integration, Auth, and Polish

**Branch:** `feature/l207-l211-browser-session-dashboard` (shared with L207–L210)
**Depends on:** L207–L210 (all backend and frontend components must exist)
**Goal:** Lock down auth, integrate with existing tools, port runtime patches, and finalize.

---

## §0 Cleanup from L210

*(To be filled by orchestrator after L210 review)*

---

## §1 Auth Guards

### REST endpoints

In `src/hestia/web/routes/browser_sessions.py`, add admin-only guards to all endpoints:

```python
from hestia.web.dependencies import require_admin

@router.get("/browser-sessions")
async def list_sessions(request: Request):
    await require_admin(request, ctx)
    ...

@router.delete("/browser-sessions/{domain}")
async def delete_session(request: Request, domain: str):
    await require_admin(request, ctx)
    ...

@router.post("/browser-sessions/{domain}/check")
async def check_session(request: Request, domain: str):
    await require_admin(request, ctx)
    ...

@router.post("/browser-sessions/start")
async def start_stream(request: Request, ...):
    await require_admin(request, ctx)
    ...

@router.post("/browser-sessions/stop")
async def stop_stream(request: Request):
    await require_admin(request, ctx)
    ...
```

### WebSocket auth

The WebSocket endpoint already validates the token. Ensure it also checks the user's role is `"admin"` before accepting the connection. If not admin, close with code `4003` (forbidden).

### Dashboard nav guard

In `StickyNav`, only show the "Browser" link if `isAdmin` is true (same pattern as the "Users" link).

In `App.tsx`, guard the browser routes:
```tsx
<Route path="/browser-sessions" element={isAdmin ? <BrowserSessions /> : <Navigate to="/" />} />
<Route path="/browser-sessions/stream" element={isAdmin ? <BrowserStream /> : <Navigate to="/" />} />
```

---

## §2 browser_login Integration

In `src/hestia/tools/builtin/browser_login.py`, update the tool's return message to mention the dashboard:

After successfully saving the session, append a note:
```
You can also manage this session (and re-authenticate later) from the Browser Sessions page on the Hestia dashboard.
```

If the tool is called and the user is interacting via Telegram/Matrix, this nudges them toward the dashboard for future logins.

---

## §3 Port Runtime Patches

Port the two verified runtime patches to the primary worktree (`~/Hestia`):

### Patch 1: inference.py

In `src/hestia/core/inference.py`, remove `reasoning_format` and `reasoning_budget` from the request bodies in both `chat()` and `chat_stream()`.

**Rationale:** `reasoning_format: "deepseek"` combined with `enable_thinking: false` in the llama-server Jinja template causes garbage output (`?????`) in streaming mode on Qwen3.6. Without these fields, llama-server uses its default behavior, which is clean.

### Patch 2: finalization.py

In `src/hestia/orchestrator/finalization.py`:
1. Add `InferenceServerError` to the top-level import: `from hestia.errors import ...`
2. In `finalize_turn()`, change the except clause from `(OSError, PersistenceError)` to `(OSError, PersistenceError, InferenceServerError)`

**Rationale:** The slot save endpoint returns 501 for multimodal models. Without catching `InferenceServerError`, the exception escapes and surfaces to the user.

---

## §4 Quality Gates

Run the full quality gate suite:

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

All three must pass. Note the pre-existing baseline issue count and ensure no new issues were introduced.

Also run the web UI style audit:
```bash
cd web-ui && grep -r "style={{" src/ | grep -v "node_modules" | wc -l
```
Must stay under 20.

---

## §5 Integration Testing

### Backend integration test

New file: `tests/integration/test_browser_session_end_to_end.py`

1. Start a test FastAPI app with the browser session routes
2. Create a mock Playwright session (or use a real one if Playwright is installed in CI)
3. Start a stream, verify WebSocket connection, send input, stop stream
4. Verify metadata was saved

### Frontend E2E test

Extend `web-ui/tests/browser-sessions-list.spec.ts` and `web-ui/tests/browser-stream.spec.ts` from L208/L210.

If Playwright E2E tests are not feasible for the stream (requires live backend), mark them as `@pytest.mark.skip` with a reason.

---

## §6 Documentation

Update `docs/handoffs/L207-L211-browser-session-dashboard-handoff.md` with:
- What was built
- How to use the feature
- Known limitations (single session at a time, admin-only, no mobile-optimized stream)

Update `docs/development-process/kimi-loop-log.md` with a narrative entry at the top.

---

## §7 Commit

```
feat: browser session dashboard — auth, integration, and polish

- Admin-only guards on all browser session endpoints
- WebSocket auth validates admin role
- browser_login tool mentions dashboard
- Port runtime patches: inference.py reasoning_format removal, finalization.py InferenceServerError catch
- Quality gates pass
```

---

## Handoff

**Completed:**
- Full browser session management via dashboard
- Metadata tracking and health checks
- CDP screencast streaming with WebSocket
- Admin-only auth guards
- Runtime patches ported to primary worktree

**Known limitations:**
- Only one streaming session at a time
- No mobile-optimized stream (text fallback works)
- Health checks require Playwright installed on server

**Next steps:**
- Deploy to runtime worktree when user is ready

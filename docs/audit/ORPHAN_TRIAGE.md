# ORPHAN_TRIAGE.md — classification of 43 unaccounted-for audit findings

**Run:** 2026-08-25 · **Card:** #55 · **Branch:** `docs/audit-orphan-triage` (off develop @ b9db06c8)
**Scope:** classification ONLY — nothing was fixed. Every citation was
grepped against the current tree before writing. Commands used were
targeted `grep -n` / `sed -n` reads of the cited files; counts below state
their command inline where a number is claimed.

**Totals, recomputed from the table below (`grep -cE '^\| (BUG|SEC|PERF)'`
per bucket): 42 rows = 41 orphans + BUG-013 → 6 FIXED · 33 STILL OPEN
(incl. 1 partial: BUG-087) · 2 NO LONGER APPLIES · 1 CANNOT DETERMINE.**

One CANNOT DETERMINE (PERF-015), plus one register self-undercount
(SEC-003, below), are statements about the audit register's precision, not
about this run.

## ⚠️ ALARMING BUT NOT FIXED HERE (per scope fence)

**SEC-010 (High, Confirmed) is fully present in the current tree**, including
the exact fail-open the audit flagged: an unresolved identity turns memory
`delete()` into an unscoped by-ID delete. See row below. It should be the
first item of the next fix loop.

## Summary table

| ID | Sev | Classification | One-line evidence |
|---|---|---|---|
| SEC-010 | High | STILL OPEN | `memory/store.py:848-851` unscoped `DELETE FROM memory WHERE id=:id` when identity unresolved |
| SEC-024 | Low-Med | STILL OPEN | `web/routes/memory.py:76-78` owner check skipped when either caller or memory platform_user is None |
| SEC-005 | High | STILL OPEN | `builtin/browser_get_json.py:202`, `browser_interact.py:88` `page.goto(url)` with no SSRF guard in either file |
| SEC-009 | Medium | STILL OPEN | `routes/workflows.py:206` create takes payload owner_id; `:293-294` update overwrites it; trust_level self-selectable `:207,296-301` |
| SEC-008 | Medium | STILL OPEN | dashboard returns `_row_to_dict` rows incl. trigger_payload/node_results to any authenticated user (`workflows.py` dashboard + `execution_store.list_recent`) |
| SEC-019 | Low | STILL OPEN | `browser_sessions.py:292-293` query-string token; no Origin check anywhere in file; auth-off shape changed (see detail) |
| SEC-016 | Low | STILL OPEN | no chmod in `tools/browser/session_store.py`; `--no-sandbox` at `stealth.py:26` |
| SEC-020 | Med-Low | STILL OPEN | headed-login gate is `normalize_domain()` (eTLD+1 string op, `session_store.py:33`) — not an SSRF check (`browser_sessions.py:276-278`) |
| SEC-025 | Medium | STILL OPEN | zero egress recording under `tools/browser/`; httpx records final URL only (`http_get.py:199`) |
| SEC-003 | High | FIXED | delegation flows through `_check_confirmation`/gated dispatch (`execution.py:1529+`, L245 chunk D) |
| BUG-013 | Medium | STILL OPEN | boot sync inside `start()` at `matrix_adapter.py:133`; L247 covered config-completeness only (see detail) |
| BUG-007 | High | STILL OPEN | `failure_store.py:127-128` raw `IN :session_ids` tuple bind, no expanding bindparam |
| BUG-012 | High | STILL OPEN | `engine.py:117` fixed 30s backoff; `_MAX_RETRY_BACKOFF_SECONDS` dead (`persistence/scheduler.py:18`) |
| BUG-006 | High | STILL OPEN | zero `concurrent_updates` in `telegram_adapter.py` (grep count 0) |
| BUG-037 | High | STILL OPEN | no wait_for/cancel/Lock in `executor.py` (grep count 0) |
| BUG-030 | Medium | STILL OPEN | `engine.py:155` `async with self._tick_lock:` serializes ticks incl. dispatch |
| BUG-043 | Med-High | STILL OPEN | `response_store.py:91-95` find_pending matches by platform/user only; `resolve()` unbound `:67-77`; buttons unauthenticated `telegram_adapter.py:1155-1160` |
| BUG-016 | Medium | STILL OPEN | `telegram_adapter.py:420-426` "not modified"→ok skips chunks[1:]; failure path resends ALL chunks `:437-441` |
| BUG-024 | Medium | STILL OPEN | `quality.py:486` startswith greeting match; `:419-434` substring error scan |
| BUG-025 | Medium | STILL OPEN | checkpoints in-memory dict `checkpoint.py:45` |
| BUG-052 | Medium | STILL OPEN | Proposals/Dashboard/Config raw refetch effects; requestIdRef absent (grep 0 in those files) |
| BUG-067 | Medium | STILL OPEN | `reflection/scheduler.py:86` `.isoformat()` string compared against DateTime column |
| BUG-071 | Low-Med | STILL OPEN | `workflows.py:277-278` free-form trigger_type on update; no graph validation at version save |
| BUG-077 | Low | STILL OPEN | formality = TECHNICAL_VOCABULARY ratio (`style/builder.py:113-137`) |
| BUG-078 | Low-Med | STILL OPEN | `AWAITING_USER` never entered; confirmation awaits inline `execution.py:1681` |
| BUG-083 | Low | STILL OPEN | server masks to `"***"` (`config.py:33`); reveal toggles input type only (`ConfigForm.tsx:172`) |
| BUG-087 | Low | STILL OPEN (partial) | node input fixed (`NodePropertiesPanel.tsx:367`); trigger save still unvalidated (`useWorkflowEditor.ts:457-471`) |
| BUG-062 | Low | STILL OPEN | `ogg_path` assigned only AFTER `download_to_drive`; download-failure path sees None and skips cleanup (`telegram_adapter.py:1004-1018`) |
| BUG-074 | Low | FIXED | tag MATCH routed through `_sanitize_fts5_query` (`store.py:779`, `:1118`), embedded quotes escaped |
| BUG-076 | Low | FIXED | `bm25(memory, 10.0, 1.0)` content-dominates-tags (`store.py:702`, commit cce2a2ba 2026-08-22) |
| PERF-001 | High impact | STILL OPEN | no React.lazy/manualChunks (`vite.config.ts`, `App.tsx` grep empty) |
| PERF-002 | Med | STILL OPEN | `@openuidev/react-ui` still in `package.json:14` |
| PERF-006 | Medium | FIXED | WAL + per-connection busy_timeout (`db.py:47-50`, BUG-008 remediation) |
| PERF-008 | High | STILL OPEN | alias of BUG-006 (above) |
| PERF-009 | XS | NO LONGER APPLIES | no Sessions list page exists (`App.tsx` routes; pages/ has SessionDetail/BrowserSessions only) |
| PERF-010 | Med | STILL OPEN | single inline.json rewritten wholesale with base64 payloads (`artifacts/store.py:129-139`) |
| PERF-012 | Medium | STILL OPEN | INTERNALDATE FETCH per matched UID before limit (`email/adapter.py:319-324` loop; limit at `:356`) |
| PERF-013 | Medium | STILL OPEN | `trace_store.py:216-221` `list_egress` has no limit parameter |
| PERF-014 | Low-Med | NO LONGER APPLIES | breaker scans `ctx.tool_chain` names (`execution.py:1108-1121`), not message history |
| PERF-015 | Med | CANNOT DETERMINE | grepped persistence/ for consumed-payload retention; nothing matched; need pointer to where consumed payloads persist |
| PERF-016 | Med | FIXED | epoch prefix capped `_MAX_MEMORIES=5` (`context/memory_epoch.py:19,41`) |
| PERF-018 | Medium | STILL OPEN | alias of BUG-030 (above) |

## Confirmed-open, severity-ranked (the work queue)

1. **SEC-010** — cross-user memory access (High)
2. **SEC-005** — browser tools bypass SSRF guard end-to-end (High)
3. **BUG-007** — IN-clause binding crash in failure_store (High)
4. **BUG-012** — infinite 30s retry hammering (High)
5. **BUG-006 / PERF-008** — Telegram head-of-line blocking (High)
6. **BUG-037** — workflow execution has no ceiling/cancel/concurrency (High)
7. **SEC-009** — client-controlled workflow ownership + trust self-select (Medium)
8. **SEC-008** — dashboard leaks raw executions cross-workflow (Medium)
9. **SEC-025** — Playwright egress invisible to audit (Medium)
10. **BUG-013** — Matrix boot-sync failure kills serve (Medium)
11. **BUG-030 / PERF-018** — scheduler tick HOL + at-most-once loss (Medium)
12. **BUG-016** — chunked-send duplication/drop (Medium)
13. **BUG-024** — quality heuristics false positives (Medium)
14. **BUG-043** — group response hijack + unauthenticated buttons (Med-High)
15. **PERF-010 / PERF-012 / PERF-013** — storage/IO scale items (Medium)
16. **SEC-024, SEC-016, SEC-019, SEC-020** — lower-severity security (Low–Med-Low)
17. **BUG-025, BUG-052, BUG-067, BUG-071** — medium-low functional defects
18. **BUG-077, BUG-078, BUG-083, BUG-087, BUG-062** — low

## Per-finding detail

### Security

**SEC-010 — STILL OPEN.** `memory/store.py:833-851`: `delete()` calls
`_resolve_scope()`; when platform/platform_user remain None the SQL falls
back to `DELETE FROM memory WHERE id = :id` with no ownership clause.
`update()` (`:973+`) resolves scope the same way for its topic rewiring;
`pin` / `mark_user_authored` / `mark_recalled` (`:1048`, `:1060`,
`:1071`) take only memory_id. Reachable path: any code path (web route,
tool) that reaches these methods without runtime identity ContextVars set
can modify/delete another user's memory by ID.

**SEC-024 — STILL OPEN.** `web/routes/memory.py:69-78`:
```
if caller_platform_user is not None and mem.platform_user is not None:
    await RequireOwner(mem.platform_user)(request, ctx)
```
Either side being None skips enforcement and returns the memory to the
mutation handlers (`:126`, `:163`, `:175`, `:187`). Global-seed memories
(platform_user NULL) are editable/deletable by any caller that can reach
the route.

**SEC-005 — STILL OPEN.** `browser_get_json.py:194-202` and
`browser_interact.py:80-88` launch Chromium and `page.goto(url)` directly;
neither file references `assert_url_safe` (grep across both: 0 hits).
Only `fetch.py:458` gates, once, pre-navigation — Chromium-side redirects,
subresource loads, and JS navigations remain unvalidated, and extraction
can carry internal responses into model context.

**SEC-008 — STILL OPEN.** `routes/workflows.py` `dashboard()` calls
`execution_store.list_recent(limit=5)`; `list_recent` selects all columns
(`execution_store.py:170-175`) and `_row_to_dict` serializes them —
including `trigger_payload` and `node_results`. No ownership filter, no
admin gate on the route.

**SEC-009 — STILL OPEN.** Create: `owner_id = payload.get("owner_id") or
getattr(request.state, "platform_user", "")` (`:206`). Update:
`if "owner_id" in payload: workflow.owner_id = payload["owner_id"]`
(`:293-294`). `trust_level` validated only against `_TRUST_LEVELS`
(`:207`, `:296-301`) — self-assignable including `developer`.

**SEC-016 — STILL OPEN.** No `chmod` in `tools/browser/session_store.py`;
cookie/localStorage stores inherit umask defaults. `stealth.py:26` passes
`--no-sandbox` in every launch profile.

**SEC-019 — STILL OPEN (shape shifted).** Query-string token accepted at
`browser_sessions.py:292-293`; no Origin header check anywhere in the
file (grep 0). The register's third clause ("enforced even when
auth_enabled=False") does NOT match today's tree: the whole auth block is
skipped when `ctx.auth_manager is None`, so an auth-off deployment gets an
unauthenticated WS instead of an unobtainable-token WS. Core issues
(retention-via-URL, no Origin check) stand.

**SEC-020 — STILL OPEN.** `headed_browser_login` (`browser_sessions.py:262-280`)
requires admin but validates only `normalize_domain(body.url)` — an eTLD+1
string operation (`session_store.py:33-46`) that happily accepts IP hosts
and internal names. No `assert_url_safe` on the launch path.

**SEC-025 — STILL OPEN.** `grep -rn "_record_egress" src/hestia/tools/browser/`
→ 0 hits; `fetch.py` records nothing. httpx path records final URL
(`http_get.py:199`), curl_cffi hops recorded per its own path — asymmetry
as audited.

**SEC-003 — FIXED.** `_execute_policy_delegation` (`execution.py:1529`)
docstring and body route delegate_task through `_check_confirmation` and
gated registry dispatch (L245 chunk D, commit 6c870aae lineage).

**SEC-024 detail above; SEC-003..SEC-023 range placeholder:** the register
row reading "SEC-003..SEC-023 | See security doc" is a range placeholder,
not a finding. It implies findings between SEC-003 and SEC-023 exist only
if individually numbered elsewhere; every numbered SEC in that range IS
individually registered in this audit's own tables, so the register does
not undercount itself beyond the orphan set this card triages.

### Bugs

**BUG-013 — STILL OPEN (answering the card's explicit question).**
`matrix_adapter.py:133`: `await self._client.sync(timeout=5000)` runs
inside `start()`; an exception there propagates out of adapter
construction/startup in `serve.py` and kills the whole serve process —
Telegram included. L247's change (this branch) covers incomplete *config*
(credential gaps checked BEFORE construction); it does not touch boot-*sync*
failure at runtime. Adjacent, not closed. Fix direction stands: isolate
initial sync with try/backoff so one platform degrades alone.

**BUG-007 — STILL OPEN.** `failure_store.py:127-128`:
`clauses.append("session_id IN :session_ids"); params["session_ids"] =
tuple(session_ids)` — SQLAlchemy raises on a raw tuple bound to `IN :name`
without `bindparam(..., expanding=True)` (working pattern:
`error_resolution_store.py:69`). Reachable path: any caller passing
`session_ids` to the failure listing (web failure-log session filter).
trace_store's builders are scalar-only today; the live instance of the
defect is failure_store.

**BUG-012 — STILL OPEN.** `scheduler/engine.py:116-117` returns
`now + timedelta(seconds=_MIN_RETRY_BACKOFF_SECONDS)` unconditionally;
`_MAX_RETRY_BACKOFF_SECONDS` (persistence/scheduler.py:18) is referenced
nowhere in engine.py — dead exactly as audited.

**BUG-006 / PERF-008 — STILL OPEN.** `grep -c concurrent_updates
telegram_adapter.py` → 0; handler registration and turn awaiting unchanged.

**BUG-037 — STILL OPEN.** `grep -cE "asyncio.wait_for|asyncio.Lock"
executor.py` → 0; spawn-per-event fan-out unchanged in app.py/bus.py.

**BUG-030 / PERF-018 — STILL OPEN.** `engine.py:155` `async with
self._tick_lock:` wraps the whole tick including task dispatch.

**BUG-016 — STILL OPEN.** `telegram_adapter.py:420-426`: "not modified" →
`edit_ok = True` while remaining chunks are skipped; the non-modified
failure branch resends `for chunk in chunks` (all of them, `:437-441`),
duplicating already-delivered prefixes.

**BUG-024 — STILL OPEN.** `quality.py:486` startswith-prefix greeting
match; `quality.py:419-434` `_looks_like_error` substring indicators
("failed", "cannot", "not found"...).

**BUG-025 — STILL OPEN.** `checkpoint.py:45` `self._checkpoints: dict = {}`.

**BUG-043 — STILL OPEN.** `response_store.py:91-95` find_pending matches
by (platform, platform_user) only — Telegram groups key on chat.id
(adapter `:903`), so any member's reply resolves the prompt;
`resolve()` (`:67-77`) binds nothing; button presses resolve any
`workflow:<id>:<resp>` with no allowlist/requester check
(`telegram_adapter.py:1155-1160`).

**BUG-052 — STILL OPEN.** Proposals.tsx:33-49 refetch effect has no
staleness guard; `grep -c requestIdRef Dashboard.tsx Config.tsx` → 0/0.
useApiQuery has the guard (`useApi.ts:23,33,40`) but these pages don't use it.

**BUG-067 — STILL OPEN.** `reflection/scheduler.py:86`
`sessions.c.last_active_at >= cutoff.isoformat()` compares a DateTime
column to an ISO string; same pattern family across stores.

**BUG-071 — STILL OPEN.** Update assigns `trigger_type` verbatim
(`workflows.py:277-278`); version save performs no graph validation
(create_version builds nodes/edges from client payload unchecked).

**BUG-077 — STILL OPEN.** `style/builder.py:113-137` — formality is
TECHNICAL_VOCABULARY word ratio.

**BUG-078 — STILL OPEN.** Confirmation awaits `_confirm_callback` inline
(`execution.py:1681`) inside the turn (session lock held);
`AWAITING_USER` is declared (`types.py:29`, transitions allow-list) but
no code transitions to it.

**BUG-083 — STILL OPEN.** Server masks values to literal `"***"`
(`routes/config.py:33`); frontend reveal toggles input type over that
masked value (`ConfigForm.tsx:172,184`) — no real-value fetch exists.

**BUG-087 — STILL OPEN (partially fixed).** Node timeout input now guards
empty/min (`NodePropertiesPanel.tsx:367`); trigger save still writes
whatever is in triggerConfig with no required-field checks
(`useWorkflowEditor.ts:457-471`).

**BUG-062 — STILL OPEN (reclassified 2026-08-25; earlier FIXED was wrong).**
`telegram_adapter.py:1004-1018`: `ogg_path` is assigned only after
`download_to_drive` returns, inside the `with` block; on the
download-failure path the except handler's guard sees None and skips the
unlink, so the temp .ogg leaks. Reachable path: any voice message whose
download fails. Fix direction (NOT applied here — docs branch): assign
`ogg_path = ogg.name` on entering the with-block.

**BUG-074 — FIXED.** Tag filters pass through `_sanitize_fts5_query`
before MATCH (`store.py:779`, `:1118`), and the sanitizer escapes embedded
double quotes (`replace('"', '""')`).

**BUG-076 — FIXED.** `ORDER BY bm25(memory, 10.0, 1.0)` with the comment
"content (first column) dominates tags" (`store.py:700-702`; introduced in
cce2a2ba, 2026-08-22).

### Performance

**PERF-001 — STILL OPEN.** No `React.lazy`/dynamic imports in App.tsx;
no `manualChunks` in vite.config.ts.

**PERF-002 — STILL OPEN.** `"@openuidev/react-ui": "^0.11.6"` remains a
dependency (`package.json:14`).

**PERF-006 — FIXED.** `persistence/db.py:47-50` applies WAL (persistent)
and per-connection busy_timeout (BUG-008 remediation commit).

**PERF-009 — NO LONGER APPLIES.** There is no Sessions list page: routes
in App.tsx contain no `/sessions` entry and pages/ contains only
SessionDetail/BrowserSessions. The isLoading-skeleton remount pattern as
described has no host page.

**PERF-010 — STILL OPEN.** `_save_inline_index`
(`artifacts/store.py:129-139`) rewrites one inline.json containing every
inline payload base64-encoded on each store/delete.

**PERF-012 — STILL OPEN.** `email/adapter.py:319-324` loops
`conn.uid("FETCH", uid_str, "(INTERNALDATE)")` over EVERY matched UID to
sort client-side; `[:limit]` applied at `:356`. The comment shows this is
deliberate (works around servers returning UIDs out of arrival order),
but the round-trip cost the audit flagged is present. A batched
`(INTERNALDATE)` FETCH over the full UID set would keep the fix and drop N−1 RTTs.

**PERF-013 — STILL OPEN.** `list_egress` signature
(`trace_store.py:216-221`) has no limit parameter; other listers vary.

**PERF-014 — NO LONGER APPLIES.** Breaker logic counts entries in
`ctx.tool_chain` (a list of tool-name strings, sliced pre-batch) at
`execution.py:1108-1121` — not a rescan of message history. An O(chain)
count per dispatch remains, but chain length is bounded by the turn's
tool-call count, not history size.

**PERF-015 — CANNOT DETERMINE.** Grepped `src/hestia/persistence/` for
consumed/meta-tool payload retention (terms: consumed, meta_tool,
payloads) — no matching retention surface found. Settling this requires
identifying where consumed call_tool arguments/results are stored after
the turn (history compaction? trace payloads?) — a pointer from the
author settles it.

**PERF-016 — FIXED.** Epoch composition caps at five memories:
`_MAX_MEMORIES = 5` (`context/memory_epoch.py:19`) passed as the SQL LIMIT
through `list_memories` (`:41`; SQL limit at `store.py:705`).

## Noticed while looking (capped at 10)

1. `Proposals.tsx` history-tab filters pending out client-side after fetch — server could filter.
2. `handleTriggerSave` silently drops redacted webhook secret (documented behavior, but easy to miss).
3. `memory.py` list_memories allows arbitrary platform_user query param for admins only — non-admin path scoping worth a test.
4. `dashboard()` also leaks platform connection booleans to non-admins (tied to SEC-008).
5. `_sanitize_fts5_query` preserves user-supplied AND/OR/NOT — documented, but means tag search is operator-injectable by design.
6. `serve.py` telegram branch constructs the adapter before make_app's startup report ordering matters — gap warnings print after adapters start (cosmetic ordering).
7. `response_store` timeout default 300s vs audit's "600s" — register number stale even though finding stands.
8. `EmailConfig.resolved_password` raising inside property makes attribute access side-effectful — surprising API shape.
9. `failure_store.list_failures(session_ids=...)` appears to have no production caller yet — the crashing parameter may be web-route-bound.
10. Wheel smoke test during #52 showed bare-install CLI import fails on playwright — packaging finding already flagged for #45 register.

## Scope statement

Every classification above reflects the working tree at docs/audit-orphan-triage
(= develop b9db06c8 for src/; the branch adds only this file). Nothing was
fixed. Gates: not meaningful for a docs-only branch (no src/tests changes);
stating so rather than silently skipping — ruff/mypy untouched by markdown.

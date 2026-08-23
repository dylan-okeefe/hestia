# Security & Privacy Audit — Hestia

**Audit date:** 2026-08-22 · Scope: trust boundaries, tool/policy enforcement, web auth, SSRF/injection defenses, secrets handling, LLM-output-to-action paths, privacy of stored/derived data.
Method: every tool-invocation path traced end-to-end (gate-enforcement map below); auth routes read line-by-line; findings prioritized by **realistic impact × exploitability** for Hestia's actual posture (single-operator household assistant; dashboard on LAN/Tailscale with auth enabled; chat platforms allowlisted).

Related: register `07_BUGS_RELIABILITY.md`; architecture root-cause discussion `01_ARCHITECTURE.md` §ARCH-001.

---

## 1. Trust model as-built

**Boundaries that exist:** platform allowlists (empty = deny-all ✓); per-session confirmation with requester binding for tool approvals ✓; CapabilityGate with trust presets, channel classes, killswitch, injection escalation ✓; webhook HMAC ✓; SSRFSafeTransport for http_get/browser_get/browser_get_links ✓; path sandbox via allowed_roots (fail-closed empty default ✓); startup hard-fail guards for exposed+authless and destructive-auto-approve configs ✓; secret masking in config reprs and capability-event scrubbing ✓.

**Boundaries that are claimed but not enforced:** see §2 — this is the audit's most important section.

## 2. Gate enforcement map (primary deliverable)

`CapabilityGate.check` is invoked from exactly two places: the orchestrator's `_dispatch_tool_call`/`_meta_call_tool` chain, and the workflow executor's *fallback* branch (unknown node types only). Every actual tool-handler invocation path:

| # | Path | Gated? | Evidence |
|---|------|--------|----------|
| 1 | Orchestrator loop (CLI/TG/MX/scheduler/subagent turns) | ✅ gate before confirmation/auto-approve; meta-tool unwrapping prevents `call_tool(name="terminal")` dodge | `execution.py:1458→1538→1687`, `_meta_call_tool:1620-1638` |
| 2 | Policy-triggered delegation ("research…") | ❌ calls destructive-classified `delegate_task` directly — no killswitch/injection-escalation/audit | `execution.py:694-709 → :1410` → **SEC-003** |
| 3 | Explicit delegate_task tool call | ✅ via #1; subagent inner turns re-gated (Channel.SUBAGENT) | `delegate_task.py:173` |
| 4 | Scheduler tasks | ✅ #1 + filter_tools strips shell/write/email + auto_approve fail-closed blocklist | `default.py:225-244,297-305` |
| 5 | Workflow fallback nodes | ✅ synthetic actor, WORKFLOW channel, workflow allow_list | `executor.py:413-434` |
| 6 | Workflow `tool_call` node | ❌ **SEC-001 (Critical)** | `nodes/tool_call.py:54`; NODE_TYPES dispatch returns at `executor.py:378`, gate block unreachable |
| 7 | Workflow `investigate` node | ❌ same, tools list from interpolated inputs | `nodes/investigate.py:68-70` |
| 8 | Truncated-write recovery | ❌ raw handler call; writes even while context injection-flagged; skips killswitch/confirmation/audit (path sandbox still applies incidentally) | `quality.py:199-201` → **SEC-004** |

**Dead controls:** `workflow.trust_level` never read by executor; orchestrator passes no allow_list so `TrustConfig.scheduler_shell_exec` etc. always deny while filter_tools advertises the tools (confusing denials + digest noise); `Channel.SUBAGENT` in neither trusted nor unattended set (destructive approved unless capability-stripped; `browser_login` unlabeled so never stripped; developer preset `auto_approve=["*"]` lets a subagent open a headed browser + persist credentials); gate's `auto_approved` verdict computed then discarded, re-derived divergently.

### SEC-001 (Critical · Confirmed · verified by direct inspection)
Workflow `{type:"tool_call"}` / `investigate` nodes execute arbitrary registered tools ungated. Reachable from: HMAC-signed webhooks (secrets are optional per-workflow? No — webhook ingestion fails closed when no secret exists, but any activated chat-command/message/proposal/email/workflow_completed trigger also reaches nodes), owner test-run endpoint (no check when `web.auth_enabled=False`), and any authenticated dashboard user via run endpoints. A workflow containing `{"type":"tool_call","config":{"tool_name":"terminal"}}` runs shell commands unattended.
**Fix:** route both nodes through the gate (owner identity, Channel.WORKFLOW, allow_list); structurally, move enforcement into/wrapping `ToolRegistry.call` so bypasses cannot be reconstructed. Regression-test: paranoid workflow invoking `terminal` denied. Scope M.

### SEC-003 (High · Confirmed)
Policy-delegation path invokes `delegate_task` outside the gate. Blast radius limited (subagent's inner calls gated) but killswitch, injection escalation, and audit trail are all skipped on the delegation decision itself.
**Fix:** route through `_check_confirmation`. Scope S.

### SEC-004 (Medium-High · Confirmed)
Truncated-write recovery executes `write_file` handlers directly from model-emitted XML (`quality.py:253-256` supplies path). Path sandbox holds; everything else (killswitch, injection-flagged refusal, confirmation, audit) does not — a page that injects an oversized unclosed write block gets its content written even while the context is flagged.
**Fix:** route recovery through dispatch gating; refuse when injection_flagged. Scope S.

## 3. Web authentication

### SEC-002 (High · Confirmed) — Login-code dispatch trusts a client-supplied recipient
`routes/auth.py:44-45` accepts `platform_user` in the unauthenticated request body; `auth.py:198-199` only falls back to the configured user when the param is absent — so no allowlist check applies — and `:213` delivers the code to that recipient. Any anonymous caller who can reach the API can (a) harass arbitrary Telegram chat IDs with login codes, (b) if combined with any code-leak vector, attempt takeover; practically it's primarily a spam/enumeration primitive today because codes stay on Dylan's devices.
**Fix:** ignore client-supplied recipients entirely; resolve target from server-side user records. Scope S.

### SEC-026 (Medium · Confirmed) — Unauthenticated identity roster
> ID note: originally mis-numbered as a second SEC-004 (colliding with
> truncated-write recovery above). Renumbered 2026-08-23; card #44's
> adjudication caught the resulting citation ambiguity. Cite audit IDs as
> file-qualified when multiple finding schemes exist in-repo
> (docs/reviews uses C/H/M, docs/audit uses SEC/BUG/...).
`GET /api/auth/available-users` (middleware-exempt `/api/auth/*`) returns user_ids, display names, roles, platforms, and every platform_user binding; `/api/auth/status` adds available_platforms + debug_login flag. Precise targeting data synergistic with SEC-002 and household contact enumeration.
**Fix:** require authentication or return minimal booleans. Scope XS–S.

### SEC-006 (Medium · Confirmed) — debug_login outside the startup guard
`_validate_web_security_posture` hard-fails auth-disabled-on-exposed and warns on destructive auto-approve, but never checks `config.debug_login`, which mints sessions for arbitrary user_ids (`routes/auth.py:111-146`). Exposed deployment with debug_login=true boots silently.
**Fix:** add to guard (hard-fail unless allow_insecure). Scope XS.

Other auth notes (good): 10⁶ code space rate-limited single-use with expiry ✓; 256-bit tokens memory-only ✓; logout invalidates ✓; loopback detection handles IPv4-mapped forms ✓ (tested). Non-constant-time dict lookups for codes/tokens are acceptable given entropy/rate limits (Informational). Verbose `detail=str(exc)` on auth routes discloses which platforms are configured/viable to anonymous callers (SEC-023, Informational-Med). Rate limiting exists only on auth endpoints (Medium operational gap: doctor/audit heavy jobs re-triggerable by any authenticated user — DoS-ish).

## 4. Multi-user authorization gaps

Dashboard supports admin/user roles; these routes predate full role wiring:

| ID | Finding | Evidence | Severity |
|----|---------|----------|----------|
| SEC-007 | Topic rename/delete/read IDOR — zero ownership/admin checks vs scoped siblings | `memory.py:267-287,290-303,306-317` | Medium |
| SEC-008 | `/api/workflows/dashboard` returns all workflows' counts + recent executions incl. raw trigger payloads/node outputs/errors to any authenticated user | `workflows.py:505-524`; store selects all columns | Medium |
| SEC-009 | Workflow create/update accepts client-supplied `owner_id`; current owner can transfer to anyone; creators self-select `trust_level="developer"` (dead today, escalates the moment SEC-001 is fixed unless server-derived) | `workflows.py:174,260-261,175-180` | Medium |
| BUG-082 | Scheduler routes: inverse privilege — admins locked out of managing others' tasks (no role check anywhere in module) | `scheduler.py:143-205` | Low functional |
| SEC-024 | Memory owner check skipped when `mem.platform_user is None` or caller unauthenticated — global-seed memories editable by any user | `memory.py:46-54` | Low-Med |

**Fix direction:** derive owner from session; scope dashboard aggregates by caller unless admin; admin-bypass everywhere consistent. Scope M total.

## 5. Memory scoping (cross-user data exposure)

### SEC-010 (High · Confirmed)
`MemoryStore.search()` fails closed without identity (verified claim), but sibling methods **fail open**: scope clause added only when both platform AND platform_user present (`store.py:735`); `delete()` by-ID `:797-799`, `soft_delete()` `:862-865`, `update(topic_ids)` rewires topics with no ownership check `:978-986`; pin/mark_user_authored/mark_recalled have zero scoping `:991-1024`. Legacy `MemoryEpochBuilder.build_prefix` feeds `list_memories` directly (`context/memory_epoch.py:40-44`) — unset identity would inject other users' memories into context under "Relevant memories:".
**Fix:** extend fail-closed to all scoped methods; delete/deprecate legacy epoch builder; regression tests asserting unscoped calls raise. Scope S–M.

## 6. SSRF & egress

Strong core where applied: scheme locked http(s), all resolved addresses checked (IPv4-mapped normalized, CGNAT/metadata/ULA covered), redirect hops validated on transport path, honest DNS-rebinding TOCTOU docstring. Deepest-tested area (dedicated suites incl. rebinding + redirect-to-metadata).

Gaps:

| ID | Finding | Evidence | Severity |
|----|---------|----------|----------|
| SEC-005 | `browser_get_json`, `browser_interact`, health checks launch Chromium with **no** `assert_url_safe`; even guarded fetch_url validates once pre-navigation — Chromium-side redirects/subresource loads/JS navigations unvalidated → attacker page can bounce to metadata endpoints and extraction may carry response into model context | `browser_get_json.py:170-235,300`; `browser_interact.py:54-176`; `session_store.py:280-373`; guarded-only-at-entry `fetch.py:457-468` | High |
| SEC-011 | `use_curl_cffi` is model-selectable — choosing it downgrades SSRF enforcement from transport-guaranteed to best-effort pre-flight, silently | `http_get.py:245-256,318`; docstring admission :137-142 | Medium |
| SEC-025 | Egress audit asymmetric: httpx records final URL only (redirect hops invisible); curl_cffi records hops; Playwright records nothing | `http_get.py:209-213,157-160`; no trace_store usage in tools/browser | Medium |
| SEC-020 | Headed-login flow (admin-gated) lacks SSRF check — can point real Chromium at internal services and persist resulting cookie stores | `browser_sessions.py:274` route; login-save flow | Med-Low |

**Fix direction:** validate post-goto `page.url` + Playwright route interception for blocked ranges; pre-flight on the two unchecked tools; record browser navigations to egress log; pin resolved IPs where transport allows or document loudly. Scope M.

## 7. Injection scanner & escalation wiring

### SEC-012 (Medium · Confirmed)
Escalation is detected via substring `"[SECURITY NOTE:" in m.content` over running history (`execution.py:1524-1529`). Any fetched page containing that literal flips subsequent destructive calls into confirmation/deny — content-driven fail-closed DoS weaponizable mid-task. Annotation survives truncation (prepended), but registry artifact promotion happens before scanning, so payloads past char 4000 escape scanning until chunked re-reads.
Scanner false-negative surface: four regex families; ≥40-char role-prefix requirement exempts short overrides; entropy check skipped entirely for structured-looking content >500 chars (`injection.py:96-103`) — base64 instructions inside JSON/CSS evade the only statistical detector.
**Fix:** propagate structured `InjectionScanResult` on results/contextvar instead of string matching; nonce-wrap genuine annotations; document FN limits; scan full text at promotion time. Scope M.

## 8. Secrets handling

Good discipline overall: masked reprs on credential configs; reveal-once webhook secrets with sentinel round-trip; recursive scrubbing before capability-event persistence; tokens never logged across audited surfaces. Gaps:

| ID | Finding | Evidence | Severity |
|----|---------|----------|----------|
| SEC-013 | Dashboard renders webhook secret plaintext beside Copy button | `TriggerConfigPanel.tsx:194` | Med-High (shoulder-surf/screen-share) |
| SEC-014 | Node-config secrets unredacted in versions API — API key pasted into http headers exposed verbatim to anyone with read access | `routes/workflows.py:105-117`; redaction covers only trigger_config.secret | Low-Med |
| SEC-015 | Terminal tool inherits full environment — model-emitted `printenv`/`env` pulls host API keys into model context and thence traces/artifacts | `terminal.py` (no env= scrubbing) | Medium |
| SEC-016 | Browser session stores write cookies/localStorage world-readable (no chmod); Chromium launched `--no-sandbox` while rendering untrusted pages | `session_store.py:174-197`; `stealth.py:26` | Low |
| SEC-017 | Webhook replay dedup process-local, evictable (>1000 hits/5 min), wiped on restart | `webhooks.py:24-26,92-97` | Low-Med |
| SEC-019 | WS bearer token accepted via query string (log/proxy retention); enforced even when auth_enabled=False (functional inconsistency); no Origin check (token possession mitigates hijack) | `browser_sessions.py:291-315` | Low |

## 9. LLM-output-to-action paths (prompt-injection surface review)

The strongest structural defense is requester-bound confirmations plus channel gating on the orchestrator path. Residual surfaces, in priority order:

1. **Workflow nodes as injection amplifiers (SEC-001/SEC-021/SEC-022):** chat-command match-all fires workflows on any user's slash-command with raw text interpolated into prompts; send_message destinations resolvable from inputs; combined with ungated tool nodes, a single injected message can steer automation end-to-end.
2. **Truncated-write recovery (SEC-004)** writes injected content despite flagged context.
3. **Escalation forgery (SEC-012)** — inverted risk: forged markers paralyze; genuine markers forgeable is prevented only by convention.
4. **curl_cffi downgrade (SEC-011)** — the model chooses its own weaker SSRF boundary.
5. **Subagent summary trusted verbatim** into parent context (re-scanned next dispatch; acceptable but annotate as derived).
6. **Structured-content scanner bypass** documented above.

## 10. Privacy

- **Reflection ships raw user-input summaries to the LLM unscrubbed and persists them in proposals indefinitely:** first-200-chars summaries concatenated verbatim into trace_text prompts (`reflection/runner.py:92-96` via `trace_store.py:36`); mined observations persisted in proposal evidence JSON rendered in the UI. The dedicated redaction module (`diagnostics/scrub.py`: emails, IPs, tokens, cookies, high-entropy strings) exists but is unused on this path. **(SEC-018, Med-Low privacy.)**
- Auth-code filter drops digit-shaped messages globally (BUG-044) — minor confidentiality-of-history quirk.
- Maintenance digests correctly use SILENT sentinel; soft-delete+undo+trace honors stated reversibility promises.
- No telemetry/third-party calls found anywhere in src (local-first claim verified: outbound calls are platforms, inference localhost, Tavily/email/IMAP when configured).
- Logs: runtime logs contain message content by design (operator's own data, local disk); `.log` files properly gitignored; no token values observed in audited log statements.

## 11. What's done well (preserve)

1. Fail-closed defaults throughout (empty allowlists deny; unknown preset→paranoid; missing webhook secret→401; missing identity blocks search).
2. Confirmation requester-binding with double-submission safety and dual timeout coverage.
3. Meta-tool unwrapping preventing the `call_tool` dodge.
4. Startup posture hard-fail with explicit, documented escape hatch.
5. Secret scrubbing before audit persistence; masked reprs; reveal-once webhook secrets.
6. SSRF transport validating every hop where used; deepest security test coverage in repo.

## 12. Remediation priority

1. SEC-001 (+structural registry chokepoint) — Critical.
2. SEC-010 memory fail-open family — High, small diff.
3. SEC-002/026 login surface — High/Medium, small diffs.
4. SEC-005 browser SSRF completion — High.
5. SEC-003/004 remaining bypasses — ride along with #1's chokepoint work.
6. SEC-006 debug_login guard; SEC-013 secret display; SEC-015 env scrubbing; multi-user gap batch (§4).

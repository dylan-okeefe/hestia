# L222 — Unified trust/capability boundary

**Status:** Spec ready. Decisions resolved in `docs/reviews/decisions-trust-capability-boundary.md` (the "Decisions needed" section below is now answered there; note additions #3 generalized injection escalation and #8 audit emit). Feature branch work; can run independently of L220/L221; do not merge to develop until release-prep merge sequence.  
**Branch:** `feature/l222-trust-capability-boundary` (from `develop`; can be independent of L220/L221)  
**Spec source:** `docs/reviews/spec-trust-capability-boundary.md`  

## Goal

Create a single `CapabilityGate` that every tool-execution path must pass, enforce per-user trust presets, bind confirmations to the requester, redact webhook secrets, harden admin routes, and add SSRF protection to the browser front door.

## Review carry-forward

- *(none — this is a new spec-driven arc)*

## Decisions needed before implementation

1. **Workflow confirmation delivery (blocking decision).** A webhook- or scheduler-triggered workflow has no human in a chat to approve a confirmation, yet §2 makes destructive workflow nodes "require confirmation" and §4 binds confirmation to a requester. Decide what a destructive tool does on an unattended channel: (a) hard-deny, with explicit per-workflow allow-listing as the only escape hatch; (b) require pre-authorization configured on the trigger; (c) deliver an out-of-band approval to the owner and block/timeout. Recommend (a): do not attempt to deliver interactive confirmations to an unattended trigger; deny by default and allow-list per workflow. This must be settled before any of §2 is coded.
2. **The channel-by-capability trust matrix.** §1 step 5 ("untrusted channels require confirmation for destructive capabilities") must be made explicit, not inferred. Enumerate which channels are trusted (CLI/Telegram/Matrix operator) vs untrusted (email/webhook/workflow/scheduler), where SUBAGENT sits (acts for a trusted operator but unattended), and which capabilities count as destructive (terminal, write_local, email_send, browser_login, delegate_task). Recommend: write it as an explicit table in the decision doc; this is the core security logic.
3. **`trust_overrides` migration.** Existing overrides are keyed `platform:platform_user`, and group sessions were historically keyed by room/chat id. §3 changes the trust actor to the sender, so room-keyed overrides may stop matching. Decide the key precedence and how existing overrides are interpreted; do not silently change which overrides apply.
4. **Admin route treatment, per route (§6).** For each of doctor/audit/config/tools/egress/traces/memory, decide `require_admin` (global data) vs scope-by-identity (caller data). traces/egress/memory are arguably caller-scoped, so locking them admin-only could hide a user's own data while leaving them global leaks it. Recommend a per-route line: config/tools/doctor/audit to admin; traces/egress/memory to caller-scoped with admin-sees-all.
5. **Confirmation delegation (§4).** Decide whether an admin may approve another user's pending tool, or only the original requester.

## Scope

### §1 — `CapabilityGate` core

Create `src/hestia/policy/gate.py`, `src/hestia/policy/channel.py`, and `src/hestia/policy/identity.py`.

**Types:**

```python
class Channel(Enum):
    CLI = "cli"
    TELEGRAM = "telegram"
    MATRIX = "matrix"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SCHEDULER = "scheduler"
    WORKFLOW = "workflow"
    SUBAGENT = "subagent"
    API = "api"

@dataclass
class CapabilityRequest:
    actor: Identity
    channel: Channel
    tool_name: str
    inputs: dict[str, Any]
    session_id: str | None = None

@dataclass
class CapabilityResult:
    allowed: bool
    auto_approved: bool
    requires_confirmation: bool
    reason: str
    request_token: str | None = None
```

**Decision order inside `CapabilityGate.check`:**
1. Global deny-list / emergency killswitch.
2. Identity resolution via `UserStore`.
3. Effective trust from `trust_overrides[sender]` → `User.trust_preset` → `HestiaConfig.trust.preset` → `auto_approve_tools` (decision #5).
4. Tool capability label from `tools/capabilities.py`.
5. Channel factor (decision #4): unattended channels (email/webhook/workflow/scheduler) gate the destructive subset regardless of preset; trusted channels (CLI/Telegram/Matrix) auto-approve under the developer preset.
6. Injection escalation (decision #3): if any message in the current context carries the injection annotation and the tool is in the destructive subset, escalate. Require confirmation on attended channels; deny on unattended channels.
7. Confirmation binding with stable `request_token`, bound to the original requester (decision #7).
8. Emit a structured audit entry on every deny or escalation (decision #8); this feeds the L223 blocked-actions digest.

**Tests:**
- `tests/unit/policy/test_gate.py`:
  - Unknown actor on untrusted channel is restricted.
  - `User.trust_preset="child"` overrides config preset.
  - `trust_overrides` still win.
  - Developer preset keeps CLI/Telegram/Matrix auto-approve for safe tools.
  - Destructive tools in workflows require confirmation.

**Commit:** `feat(policy): add CapabilityGate with identity, channel, and trust-preset resolution`

### §2 — Route execution paths through the gate

Update every tool-execution entry point to call `CapabilityGate.check()` before `tool_registry.call()`.

**Files:**
- `src/hestia/orchestrator/execution.py` — `CapabilityRequest(channel=Channel.TELEGRAM/MATRIX/CLI/SCHEDULER/SUBAGENT, ...)`.
- `src/hestia/workflows/executor.py` — remove `_TRUST_CAPS`; construct `CapabilityRequest(channel=Channel.WORKFLOW, ...)`.
- `src/hestia/scheduler/engine.py` — scheduler-initiated turns use `Channel.SCHEDULER`.
- `src/hestia/tools/builtin/delegate_task.py` — subagent delegation uses `Channel.SUBAGENT`.

**Tests:**
- `tests/unit/workflows/test_executor_trust.py`:
  - A workflow node calling `terminal` or `email_send` hits the gate and requires confirmation.
  - Safe workflow nodes still execute.
- `tests/unit/orchestrator/test_execution_gate.py`:
  - Tool calls blocked by gate do not execute.
  - Auto-approved tool calls execute normally.

**Commit:** `refactor(orchestrator,workflows): route all tool execution through CapabilityGate`

### §3 — Identity model for group/room sessions

Update platform adapters so the actor for trust decisions is the human sender, not the room/chat id.

**Files:**
- `src/hestia/platforms/matrix_adapter.py` — set `sender_platform_user` from event sender; reject non-allow-listed senders before creating a session.
- `src/hestia/platforms/telegram_adapter.py` — for groups, use the individual sender's id for trust, not `chat.id`.
- `src/hestia/platforms/runners.py` — pass sender identity through to `Orchestrator.process_turn` and `CapabilityGate`.

**Tests:**
- `tests/unit/platforms/test_identity_resolution.py`:
  - Group chat actor is the sender, not the room.
  - Unknown sender in untrusted channel is rejected.

**Commit:** `fix(platforms): resolve trust actor to human sender in group/room sessions`

### §4 — Confirmation binding

Update `src/hestia/platforms/confirmation.py` and callbacks.

**Implementation:**
- Pending confirmation records include `requester_platform_user`.
- Approval callback checks that the approving user's `platform_user` matches `requester_platform_user`, or the approver is admin if policy allows delegation.
- Group/room members cannot approve another member's pending tool.

**Tests:**
- `tests/unit/platforms/test_confirmation_binding.py`:
  - Approval by a different user in the same room is rejected.
  - Approval by the requester succeeds.

**Commit:** `fix(platforms): bind confirmations to the original requester`

### §5 — Webhook secret redaction

Update `src/hestia/web/routes/workflows.py`.

**Implementation:**
- `GET /api/workflows` filters by ownership/admin.
- Redact `trigger_config.secret` for non-owner/non-admin callers.
- Keep full config for owners/admins.

**Tests:**
- `tests/unit/test_web_routes.py`:
  - `list_workflows` response does not contain `trigger_config.secret` for non-owner/non-admin.
  - Owner/admin responses still contain the secret.

**Commit:** `fix(web): redact workflow webhook secrets for non-owners`

### §6 — Admin route hardening

Update web routes to require admin or scope by identity.

**Files:**
- `src/hestia/web/routes/doctor.py`
- `src/hestia/web/routes/audit.py`
- `src/hestia/web/routes/config.py`
- `src/hestia/web/routes/tools.py`
- `src/hestia/web/routes/egress.py`
- `src/hestia/web/routes/traces.py`
- `src/hestia/web/routes/memory.py`

**Implementation:**
- Add `require_admin` where the route returns global/diagnostic data.
- For routes that can legitimately return caller-scoped data, scope by resolved identity instead.

**Tests:**
- `tests/unit/test_web_routes.py`:
  - Non-admin requests to admin-only routes return 403.
  - Admin requests succeed.

**Commit:** `fix(web): require admin on diagnostic and global-data routes`

### §7 — Browser SSRF protection

Move SSRF guards into a shared helper and apply them before any browser fetch.

**Files:**
- New: `src/hestia/security/ssrf.py` — shared `_assert_ip_allowed` and `_BLOCKED_RANGES`.
- `src/hestia/tools/builtin/http_get.py` — use the shared helper.
- `src/hestia/tools/browser/fetch.py` — resolve hostname and reject blocked ranges before `page.goto()`.
- `src/hestia/web/browser_stream.py` — apply the same helper in `SessionStreamManager.start` if it remains a separate entry point.

**Implementation:**
- Reject loopback, link-local, cloud-metadata (`169.254.169.254`), and RFC1918/private ranges.
- Return a structured failure prefixed with `[CATEGORY: BLOCKED]`.

**Tests:**
- `tests/unit/tools/test_browser_ssrf.py`:
  - `fetch_url("http://127.0.0.1:8001")` returns `[CATEGORY: BLOCKED]` without launching a browser.
  - `fetch_url("http://169.254.169.254")` returns `[CATEGORY: BLOCKED]`.
  - Public URLs still fetch normally.

**Commit:** `fix(tools): add SSRF guard to browser fetch and share helper with http_get`

### §8 — Tool-result category markers

Update gate/retry logic to lean on `[CATEGORY: ...]` markers.

**Implementation:**
- `CapabilityGate` categorizes previous tool result by parsing its marker (or defaulting to `SUCCESS` for unmarked legacy content).
- Retry/deny decisions in orchestrator and workflow executor use the parsed category directly.
- Ensure new tool implementations emit markers for `TIMEOUT`, `TRANSIENT_OTHER`, `BLOCKED`, and `NOT_FOUND`.

**Tests:**
- `tests/unit/tools/test_tool_result_category.py`:
  - `[CATEGORY: TIMEOUT]` is treated as retryable.
  - Bare "Timeout" string is not retryable.
  - `[CATEGORY: BLOCKED]` is not retryable.

**Commit:** `refactor(tools): use parsed category markers for retry and gate decisions`

## Tests

- New unit tests:
  - `tests/unit/policy/test_gate.py`
  - `tests/unit/workflows/test_executor_trust.py`
  - `tests/unit/test_web_routes.py`
  - `tests/unit/platforms/test_identity_resolution.py`
  - `tests/unit/platforms/test_confirmation_binding.py`
  - `tests/unit/tools/test_browser_ssrf.py`
  - `tests/unit/tools/test_tool_result_category.py`
- Updated tests: trust/orchestrator/workflow tests that assert on old `_TRUST_CAPS` behavior.
- Keep existing tests green.

## Acceptance

- `uv run pytest tests/unit/ tests/integration/ -q` green
- `uv run mypy src/hestia` reports 0 errors
- `uv run ruff check src/ tests/` remains at baseline or better (project line-length is 120)
- `.kimi-done` includes `LOOP=L222`
- Developer preset on the runtime box still auto-approves CLI/Telegram/Matrix safe tools.

## Handoff

- Write `docs/handoffs/L222-trust-capability-boundary-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to next queued item (or idle if no more)

## Critical rules recap

- Do not merge or push without Dylan's okay.
- The developer preset must remain functional on the runtime box.
- Every tool-execution path must pass `CapabilityGate.check()`.
- SSRF guard runs before any browser `page.goto()`.

# Spec — Unified trust/capability boundary

**Status:** HOLD-FOR-REVIEW  
**Review source:** docs/reviews/develop-review-2026-06-12.md (Security / Architecture sections)  
**Scope:** One coherent spec for all trust-related findings. Do NOT split into independent loops.

## Problem statement

Hestia currently has three parallel trust mechanisms that do not agree:

1. `TrustConfig` + `policy/default.py` — the orchestrator checks `_trust_for()` which reads `HestiaConfig.trust` and `trust_overrides` keyed by `"platform:platform_user"`.
2. `User.trust_preset` / `role` — stored in the users table and exposed in the AdminUsers UI, but **never read by the policy engine**.
3. `workflows/executor.py` `_TRUST_CAPS` — a separate allow-list that bypasses the policy engine entirely; workflow tool nodes call `tool_registry.call()` directly.

The runtime config on this box deliberately uses `TrustConfig(..., auto_approve_tools=["*"], preset="developer")`. That is a legitimate developer setting and must not be neutered. The real gap is that there is no single gate that every tool-execution path must pass, and per-user trust is stored but ignored.

## Findings this spec covers

- `User.trust_preset` / `role` stored but not enforced in `policy/default.py`.
- Workflow executor bypasses confirmation (`workflows/executor.py:549` calls `tool_registry.call` directly).
- Workflow tool nodes can run `email_send`, `terminal`, `write_file` unattended.
- `tools/browser/fetch.py` is the single front door for all browser access (`browser_get`, `browser_get_links`, and the recovery path all route through `fetch_url`), but it has **no SSRF guard** — it hands arbitrary URLs directly to Playwright.
- Per-user trust keyed on room/chat, not sender (Matrix `sender_platform_user=None`; Telegram groups key on `chat.id`).
- Confirmation buttons not bound to requester in groups.
- Webhook secrets leak via `GET /api/workflows` (`list_workflows` returns full `trigger_config`).
- Several diagnostic routes (`/api/doctor`, `/api/audit`, `/api/config`, `/api/tools`, `/api/egress`, traces/egress/memory) lack `require_admin` or return unscoped global data.

## Design

### 1. Single `CapabilityGate`

Introduce `src/hestia/policy/gate.py`:

```python
class CapabilityRequest:
    actor: Identity          # platform + platform_user + user_id (if resolved)
    channel: Channel         # telegram | matrix | email | webhook | scheduler | workflow | browser | cli
    tool_name: str
    inputs: dict[str, Any]
    session_id: str | None

class CapabilityGate:
    def __init__(self, config: HestiaConfig, user_store: UserStore | None):
        ...

    async def check(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Returns:
          - allowed: bool
          - auto_approved: bool
          - requires_confirmation: bool
          - reason: str
        """
```

Decision order inside `check()`:

1. **Deny-list / emergency killswitch.**  If `tool_name` is globally denied, reject.
2. **Identity resolution.**  Resolve `actor.platform_user` to a `User` row if possible. If the actor is unknown and the channel is untrusted (email/webhook/workflow), default to the most restrictive preset unless explicitly allow-listed.
3. **Effective trust.**  Compute effective trust from, in order of precedence:
   - `trust_overrides[actor]` if present (legacy, still supported).
   - `User.trust_preset` if user is resolved.
   - `HestiaConfig.trust.preset`.
   - `HestiaConfig.trust.auto_approve_tools`.
4. **Tool capability label.**  Map the tool to a capability (`SHELL_EXEC`, `EMAIL_SEND`, `WRITE_LOCAL`, etc.) using the existing `tools/capabilities.py` registry.
5. **Channel factor.**  Untrusted channels (email, webhook, workflow) should require confirmation for destructive capabilities even when the preset would auto-approve them in chat. The developer preset on the runtime box keeps CLI/Telegram/Matrix auto-approve, but an email-triggered workflow node must still gate.
6. **Confirmation binding.**  If confirmation is required, return `requires_confirmation=True` and a stable `request_token`. The confirmation record is bound to `(session_id, requester_platform_user)`.

### 2. Routing every execution path through the gate

- **Orchestrator tool dispatch** (`orchestrator/execution.py`) calls `CapabilityGate.check()` before `tool_registry.call()`.
- **Workflow executor** (`workflows/executor.py`) removes `_TRUST_CAPS`. Tool-call nodes construct a `CapabilityRequest(channel=Channel.WORKFLOW, ...)` and call the gate.
- **Scheduler-initiated turns** use `Channel.SCHEDULER`.
- **Subagent delegation** uses `Channel.SUBAGENT`.
- **Direct API tool calls** (if any) use `Channel.API`.

### 3. Identity model for group/room sessions

- A session may be keyed on a room/chat id, but the **actor** for trust decisions must be the sender.
- `MatrixAdapter.on_message`: set `sender_platform_user` from the event sender; if the sender is not allow-listed, reject before creating a session.
- `TelegramAdapter.on_message`: for groups, use the individual sender's id for trust, not `chat.id`.
- Update `PlatformUser` / `Identity` representations so that `actor.platform_user` is always the human sender.

### 4. Confirmation binding

- Pending confirmation records include `requester_platform_user`.
- The confirmation callback checks that the approving user's `platform_user` matches `requester_platform_user` (or the approver is an admin if the policy allows delegation).
- Group/room members cannot approve another member's pending tool.

### 5. Webhook secret redaction

- `GET /api/workflows` filters by ownership/admin and redacts `trigger_config.secret` for non-owner/non-admin callers.
- Add a test asserting the secret is absent in the list response.

### 6. Admin route hardening

- Add `require_admin` to `/api/doctor`, `/api/audit`, `/api/config`, `/api/tools`, `/api/egress`, and the traces/egress/memory routes.
- For routes that can legitimately return global data, require admin or scope by resolved identity.

### 7. Browser SSRF protection

`src/hestia/tools/browser/fetch.py` is now the single front door for browser access. It must share the SSRF boundary already implemented for `http_get`:

- Reuse the IP guard from `src/hestia/tools/builtin/http_get.py` (`_assert_ip_allowed` / `_BLOCKED_RANGES`), or move both into a shared `src/hestia/security/ssrf.py` helper.
- In `fetch_url`, resolve the hostname and reject loopback, link-local, cloud-metadata (`169.254.169.254`), and RFC1918/private ranges **before** calling `page.goto()`.
- Return a structured failure prefixed with `[CATEGORY: BLOCKED]` so downstream classification is deterministic and the model sees a clear, safe error.
- Apply the same helper to `web/browser_stream.py` (`SessionStreamManager.start`) if it is kept as a separate browser entry point.

### 8. Tool-result category markers

`classify_tool_result` was tightened to trust only `[CATEGORY: <NAME>]` markers. The gate and retry logic should lean on this instead of substring scanning:

- `CapabilityGate` categorizes the previous tool result by parsing its marker (or defaulting to `SUCCESS` for unmarked legacy content).
- Retry/deny decisions in the orchestrator and workflow executor use the parsed category directly.
- New tool implementations must emit markers for `TIMEOUT`, `TRANSIENT_OTHER`, `BLOCKED`, and `NOT_FOUND`; unmarked tool results are treated as successful.

## Tests that must pass before merging

1. A workflow node calling `terminal` or `email_send` hits the confirmation gate and requires approval.
2. A user with `trust_preset="child"` cannot auto-approve `terminal` even when `HestiaConfig.trust.preset="developer"`.
3. `list_workflows` response does not contain `trigger_config.secret` for non-owner/non-admin callers.
4. Confirmation approval by a different user in the same room is rejected.
5. An email-triggered workflow with a destructive tool requires confirmation; the same tool in a Telegram DM to the owner auto-approves (under developer preset).
6. `fetch_url("http://127.0.0.1:8001")` and `fetch_url("http://169.254.169.254")` return `[CATEGORY: BLOCKED]` without launching a browser.
7. A tool result containing `[CATEGORY: TIMEOUT]` is treated as retryable; a bare "Timeout" string is not.
8. All existing trust/orchestrator/workflow tests still pass.

## Files likely to change

- New: `src/hestia/policy/gate.py`, `src/hestia/policy/channel.py`, `src/hestia/policy/identity.py`
- Modify: `src/hestia/policy/default.py`, `src/hestia/orchestrator/execution.py`, `src/hestia/workflows/executor.py`, `src/hestia/tools/browser/fetch.py`, `src/hestia/tools/builtin/http_get.py` (or a shared SSRF helper), `src/hestia/platforms/matrix_adapter.py`, `src/hestia/platforms/telegram_adapter.py`, `src/hestia/platforms/runners.py`, `src/hestia/web/routes/workflows.py`, `src/hestia/web/routes/doctor.py`, `src/hestia/web/routes/audit.py`, `src/hestia/web/routes/config.py`, `src/hestia/web/routes/tools.py`, `src/hestia/web/routes/egress.py`, `src/hestia/web/routes/traces.py`, `src/hestia/web/routes/memory.py`
- Tests: `tests/unit/policy/test_gate.py`, `tests/unit/workflows/test_executor_trust.py`, `tests/unit/test_web_routes.py`, `tests/unit/tools/test_browser_ssrf.py`

## Risks & open questions

- **Backwards compatibility.**  `trust_overrides` keyed on room id will need a migration path.
- **Developer preset.**  Must remain functional on the runtime box; the gate should not silently neuter CLI/Telegram/Matrix auto-approve.
- **Workflow confirmation UX.**  If a workflow node requires confirmation, how is the prompt delivered and approved? Email/Matrix/Telegram? Need to decide before coding.
- **Performance.**  The gate is async and will be called for every tool call; keep it cheap (no DB round-trip on hot path if possible).

## Dependency

- Should land **after** the schema owner consolidation (Loop 9 / `error_resolutions` bootstrap) if the `User` table needs new indexes, but can otherwise be independent.

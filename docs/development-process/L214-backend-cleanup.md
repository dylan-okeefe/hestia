# L214 — Backend Cleanup & Correctness

## Goal
Fix policy inconsistencies, SSRF gaps, dead code, and minor correctness issues.

## §1 — M1: Auto-approve deny-list inconsistency
File: `src/hestia/policy/default.py:223-226`

The scheduler/tick fail-closed set is hardcoded `{"terminal", "write_file", "email_send"}`,
but `filter_tools` uses capability-based blocking. The two layers use different
keying (names vs capabilities), so the defense-in-depth layer in `auto_approve`
will silently rot if a new destructive tool is added. Also verify whether
`email_send` matches the registered tool name or if it's `send_email`.

Fix: Key the auto-approve fail-closed check on capabilities
(SHELL_EXEC, WRITE_LOCAL, EDIT_FILE, EMAIL_SEND) via the tool registry,
matching `filter_tools`.

## §2 — M2: SSRF misses IPv4-mapped IPv6
File: `src/hestia/tools/builtin/http_get.py:28-38, 62-75`

`_assert_ip_allowed` compares resolved IPs against IPv4 networks. An IPv4-mapped
IPv6 address (`::ffff:127.0.0.1`, `::ffff:169.254.169.254`) yields an
`IPv6Address` that is not contained in the IPv4 networks, bypassing the check.
Also missing: `100.64.0.0/10` (CGNAT).

Fix:
- Normalize IPv4-mapped IPv6 addresses via `ip.ipv4_mapped` before range checks.
- Reject IPv4-mapped/-compatible forms generally.
- Add `100.64.0.0/10` to blocked ranges.
- Consider using `not ip.is_global` as a broader guard instead of hand-rolled list.

## §3 — M3: Calibration file CWD-relative path
File: `src/hestia/context/builder.py:160-169`

`from_calibration_file` defaults to `Path("docs/calibration.json")` relative to
the process CWD. If launched from anywhere other than the repo root, calibration
is silently skipped (body_factor/meta_tool_overhead fall back to 1.0/0). No log
line on fallback. Also `body_factor == 0` causes ZeroDivision at `_apply_correction:446`.

Fix:
- Resolve calibration path from config (absolute path) or relative to the package.
- Log a warning when calibration is missing.
- Guard against `body_factor == 0`.

## §4 — M4: Dead code under web/routes/

Files to delete (confirmed not imported anywhere):
- `src/hestia/web/routes/execution_store.py`
- `src/hestia/web/routes/interpolation.py`
- `src/hestia/web/routes/models.py`
- `src/hestia/web/routes/response_store.py`
- `src/hestia/web/routes/nodes/` (if these are copies of workflow nodes)

Also check `src/hestia/web/routes/triggers.py` — it has diverged from
`workflows/triggers.py`. Verify which is canonical and delete or consolidate.

## §5 — M5: Duplicate web-search tools
File: `src/hestia/app.py:398-404`

Both `web_search` (factory) and `search_web` are registered. Decide which is
canonical and remove the other.

## §6 — M6: Unbounded reasoning text on done path
File: `src/hestia/orchestrator/execution.py:220-225`

Full `reasoning_content` is prepended to the reply with no length cap. The tool-call
path truncates to 2000 chars at :317-319. A model in reasoning mode can emit
thousands of tokens, blowing past Telegram's 4096-char limit.

Fix: Apply the same truncation cap on the done path. Optionally make "show
reasoning to user" a config toggle.

## §7 — Low: Injection scanner efficiency
File: `src/hestia/orchestrator/execution.py`

`_dispatch_tool_call` scans tool results (:834) and the reassembly loop scans
again (:604) — every result is entropy-scanned twice.

Fix: Scan once. Move the scan to a single point in the pipeline.

## Quality Gates
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff
Write `docs/handoffs/L214-backend-cleanup-handoff.md`.

# L248–L250: Error UX + stream-state guard + /thinking toggle

**Date:** 2026-11-03
**Cards:** #86 (L248), #87 (L249), #88 (L250)
**Branches (all pushed, all based on develop, none merged):**
- `feature/l248-descriptive-error-messages` @ `82799639`
- `feature/l249-stream-state-guard-scan` @ `3365534b` (includes cherry-picked `5cbce511` = hotfix `7023e801`)
- `feature/l250-thinking-toggle` @ `267b836e`

## Trigger

Production turn in a Telegram channel died at 2026-11-03 22:39 UTC with
`KeyError: 'message_id'` mid-tool-loop. The user-facing message was the fully
generic fallback ("Something went wrong. The operator has been notified."),
which exposed neither the bug class nor any lookup handle. The stream-state
root cause was hotfixed live as `7023e801` (runtime worktree) but had not
reached develop; the service was restarted to deploy the hotfix immediately.

## L248 — Descriptive unexpected-error messages (#86)

`sanitize_user_error` (`src/hestia/orchestrator/finalization.py`) unknown-error
fallback now returns `Unexpected error: <ClassName>: <sanitized detail>. The
operator has been notified.` — detail whitespace-collapsed to one line, URLs →
`[url]`, multi-segment absolute paths → `[path]`, 200-char cap. All existing
special cases (inference connection/busy/timeout, context-too-large,
tool-execution, max-iterations, policy, HestiaError) unchanged. The engine's
generic-error branch appends `(ref <turn.id[:8]>)` where the turn is already in
scope; runner/adapter call sites were left alone (threading turn ids out was
out of scope). 15 sanitize unit tests; two pre-existing assertions that pinned
the old text updated. Gates: 2536 passed, mypy/ruff clean.

## L249 — Stream-state guard: regression test + AST scan (#87)

- Cherry-picks `7023e801` onto develop (replaces `state.pop("message_id")`
  with `_reset_stream_segment`, which re-seeds keys instead of deleting them).
- Adapter-level regression test: stream callback survives a segment reset
  between streamed chunks (no KeyError; fresh `send_message`).
- `tests/unit/platforms/test_stream_state_deletion_scan.py`: AST scan over
  `src/hestia/platforms/` flags `del state[k]` / `state.pop(k` with an empty,
  comment-documented allowlist. Scan function takes a source path; a test runs
  it against `git show develop:src/hestia/platforms/runners.py` (pre-fix code)
  to prove the old shape is flagged. Gates: 2529 passed, mypy/ruff clean.

## L250 — `/thinking` per-chat reasoning toggle (#88)

- New `chat_settings` table (`src/hestia/persistence/schema.py` + idempotent
  runtime migration `m013`) backing `ChatSettingsStore` (write-through cache,
  SQLite source of truth).
- New `TelegramConfig.operator_user_id` (env `HESTIA_TELEGRAM_OPERATOR_USER_ID`,
  also in `deploy/example_config.py`). Operator chats default to **show**
  reasoning; everyone else (and group chats, and unconfigured operator)
  default to **hide**.
- `TurnExecution` accepts an optional `reasoning_gate`, resolved once per turn,
  fail-open. Both 💭 display paths in `execution.py` (final-answer prepend,
  pre-tool-call reasoning message) are gated; streaming still accumulates
  reasoning internally (transcript + tool-call XML fallback) but displays
  through the same gated sites. Non-Telegram platforms pass through as "show".
- `/thinking [on|off]` handler in the Telegram adapter (bare = toggle), keyed by
  chat id, allowlist-aware, silent-ignore for unauthorized group senders.
- `/tour` chat-and-session step now mentions `/thinking`.
- Runner wiring shares one store between command and gate (covers daemon and
  `hestia serve`). The coding-agent bridge runner has no orchestrator; `/thinking`
  there replies "not available right now" (acceptable — those chats talk to the
  coding agent). 33 new tests. Gates: 2558 passed (unit+integration), mypy/ruff
  clean.

## Deployment notes (for Dylan)

1. Merge the three branches to `develop` (L249 carries the stream-state fix;
   merge it even if only for `5cbce511`).
2. Runtime sync: `~/Hestia-runtime` is on `fix/65-tts-device-cpu` with working
   tree content equal to develop. After merging: `git checkout develop &&
   git merge --ff-only origin/develop` (or pull), then restart
   `hestia-serve.service`.
3. Set `operator_user_id` (or `HESTIA_TELEGRAM_OPERATOR_USER_ID`) in the runtime
   config so the operator default resolves; with it empty every chat defaults
   to hidden (conservative but not the intent).
4. The runtime worktree has an uncommitted 11-line telegram_adapter.py hunk
   (coder-bot non-routed-chat logging) that predates this work — review or drop
   it during the sync; it is NOT in develop.

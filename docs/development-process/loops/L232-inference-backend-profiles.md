# L232 — Inference backend profiles (llama.cpp slots vs Strata single-slot queue)

## Goal

Hestia's inference stack is llama.cpp-specific end to end (`slot_id` in request
bodies, `reasoning_budget` body field, `/tokenize` context budgeting, `/slots/*`
SlotManager with disk snapshots, `GET /health` probe). The Strata engine
(http://127.0.0.1:8080/v1, model `qwen3.8-flash-next-iq3_s`) is OpenAI-compatible
but has none of those endpoints/fields and runs a **single slot**: excess
requests queue server-side, so TTFT can sit in a queue for tens of seconds.
Flash-Next on 8002 is llama.cpp and must keep working unchanged.

Make Hestia backend-agnostic via a server-type profile with client-side
admission control, then point the runtime at Strata.

## §1 Config (`src/hestia/config.py`, `InferenceConfig`)

New fields (env names follow automatically via `HESTIA_INFERENCE_*`):

- `server_type: str = "llamacpp"` — `"llamacpp"` (default, current behavior) or
  `"openai-compat"` (Strata; llama.cpp-only machinery disabled).
- `max_inflight_requests: int = 0` — client-side admission limit; `0` =
  unlimited (llama.cpp default, unchanged behavior). When > 0, excess requests
  wait up to `queue_timeout` for a turn, then fail with a friendly busy error.
- `queue_timeout: float = 120.0` — seconds to wait for admission before
  `InferenceBusyError`.

Wire into the explicit `HestiaConfig.__init__` signature following the existing
deprecated-alias pattern. Defaults must reproduce today's behavior exactly.

## §2 InferenceClient (`src/hestia/core/inference.py`)

- Constructor accepts `server_type`; `AppContext.inference` (app.py:279-293)
  passes it from config.
- Request body (chat, inference.py:468-480): omit `slot_id` and
  `reasoning_budget` when `server_type != "llamacpp"`.
- `supports_tokenize: bool` property (`server_type == "llamacpp"`); `tokenize()`
  raises `InferenceServerError("tokenize unsupported for server_type ...")` when
  false (defense in depth; call sites must check first).
- `health()`: llamacpp → `GET /health` (unchanged); openai-compat →
  `GET {base_url}/v1/models`, healthy on 2xx with non-empty `data`.
- Admission: when `max_inflight_requests > 0`, wrap the HTTP call in an
  `asyncio.Semaphore`; acquire via `asyncio.wait_for(..., queue_timeout)`; on
  `asyncio.TimeoutError` raise `InferenceBusyError` (new class, same errors
  module as `InferenceTimeoutError`/`InferenceServerError`). Release in
  `finally`. Streaming path included. `0` → no semaphore at all (zero overhead
  for llamacpp).
- No auto-retry of 429/503 (server queue handles it); no new dependencies.

## §3 SlotManager (`src/hestia/inference/slot_manager.py`)

When `server_type != "llamacpp"`: `acquire()` returns `None` immediately (no
lock, no `/slots` HTTP, no disk snapshots); `release()`/eviction paths no-op.
Same public interface; pool_size ignored. Flash-Next (llamacpp type) path
untouched.

## §4 ContextBuilder token budgeting (`src/hestia/context/builder.py`)

All `client.tokenize(...)` call sites (builder.py:366,517,523,558,572): when
`not client.supports_tokenize`, estimate as `max(1, len(text) // 4)` — matches
the `FakeInferenceClient` convention used across the test suite. No other
behavior change.

## §5 Busy-path UX (`src/hestia/orchestrator/`)

`InferenceBusyError` caught alongside existing inference errors in the engine
catch-all (engine.py:303 area) → `TurnFinalization` sends: "I'm busy working on
another request right now — please try again in a moment." instead of the
generic "Error: ..." (finalization.py:217-255). No retry loop.

## §6 Tests

- `tests/unit/test_inference_client.py`: body gating per server_type; health()
  path per type (mock transport); tokenize gating; admission: with
  `max_inflight_requests=1`, two concurrent `chat()` calls → second waits;
  exceeding `queue_timeout` → `InferenceBusyError`; semaphore released on error.
- `tests/unit/test_slot_manager.py`: openai-compat mode returns None slot, no
  HTTP client slot calls recorded by FakeInferenceClient.
- Context builder: estimate fallback used when `supports_tokenize` is False;
  real tokenize when True.
- `tests/unit/test_config.py` + `test_config_env.py`: defaults; env coercion
  (`HESTIA_INFERENCE_SERVER_TYPE`, `_MAX_INFLIGHT_REQUESTS`, `_QUEUE_TIMEOUT`).
- Finalization: busy error message content.

## §7 Runtime deployment (after gates pass)

- `~/Hestia-runtime`: merge the feature branch (no cherry-pick), preserving
  untracked runtime files (`config.runtime.py`, `.env`, `runtime-data/`).
- `~/Hestia-runtime/config.runtime.py`: `base_url="http://127.0.0.1:8080"`,
  `model_name="qwen3.8-flash-next-iq3_s"`, `server_type="openai-compat"`,
  `max_inflight_requests=2`, `queue_timeout=120.0`, `request_timeout=600.0`
  (unchanged), `stream=True` (unchanged), `context_length=131072` (unchanged
  Hestia-side budget; Strata's own cap is 262144).
- Restart ONLY hestia-serve (Strata is the backend; hestia-llama stays
  stopped). Smoke locally: `hestia health` + a CLI chat turn (no Telegram/
  Matrix messages — Dylan is asleep).

## Quality gates

```
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff accounting

Every item §1-§7 implemented or explicitly deferred. Known follow-ups (not in
scope): multi-profile runtime switching UI; Strata parallel>1 re-test after
upstream fixes its silent crash; flash-next model file still parked on SATA
SSD (/mnt/storage) — must return to ~/models before hestia-flashnext.service
can run (documented in card #67/#68 notes, runtime-only concern).

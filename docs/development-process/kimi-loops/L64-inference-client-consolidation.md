# L64 — InferenceClient Consolidation & Resource Lifecycle

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l64-inference-client-consolidation` (from `develop`)

## Goal

Eliminate the two maintenance traps in `core/inference.py`: seven copy-pasted HTTP error-handling blocks, and a missing context-manager lifecycle that leaks `httpx.AsyncClient` connections.

---

## Intent & Meaning

The evaluation called the 7 duplicated try/except blocks a "maintenance trap" — a change in retry logic or error logging requires editing 7 places. But the deeper intent is **conceptual compression**: `InferenceClient` should express "make an HTTP request to llama-server" once, and the error translation (httpx exception → Hestia exception) should be a single policy. The duplicated code obscures the fact that all 7 methods share identical semantics.

The resource leak is subtler. `InferenceClient` creates an `httpx.AsyncClient` but never exposes `async with` support. In the current single-lifecycle usage this is fine, but it is fragile for tests, programmatic embedding, and any future multi-client paths. The intent is **daemon hygiene**: any object holding connections should be context-manager friendly and explicitly closable, so shutdown paths are obvious and test fixtures don't emit `ResourceWarning`.

---

## Scope

### §1 — Extract `_request()` helper

**File:** `src/hestia/core/inference.py`
**Evaluation:** `health()`, `tokenize()`, `chat()`, `slot_save()`, `slot_restore()`, `slot_erase()`, and `count_request()` all wrap the same try/except pattern.

**Change:**
Add a private `_request()` method:

```python
async def _request(
    self,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    try:
        response = await self._client.request(
            method, f"{self._base_url}{path}", json=json, timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as e:
        raise InferenceTimeoutError(f"{method} {path} timed out") from e
    except httpx.HTTPStatusError as e:
        raise InferenceServerError(
            f"{method} {path} returned {e.response.status_code}: {e.response.text}"
        ) from e
```

Replace all 7 methods with thin wrappers:
```python
async def health(self) -> dict[str, Any]:
    return await self._request("GET", "/health")
```

**Intent:** One place to change error handling. One place to add request/response logging. One place to add retries.

**Commit:** `refactor(inference): extract _request() helper for HTTP boilerplate`

---

### §2 — Context-manager support

**File:** `src/hestia/core/inference.py`
**Evaluation:** `close()` exists but is never called via `async with`. No `__aenter__`/`__aexit__`.

**Change:**
```python
async def __aenter__(self) -> "InferenceClient":
    return self

async def __aexit__(self, *_exc: object) -> None:
    await self.close()
```

**Intent:** `async with InferenceClient(...) as client:` should be the idiomatic way to use the client. This makes resource management automatic and explicit.

**Commit:** `feat(inference): add async context-manager support to InferenceClient`

---

### §3 — Wire lifecycle into app.py

**File:** `src/hestia/app.py`
**Evaluation:** `InferenceClient` is created in `make_app()` but `close()` is not in the shutdown path.

**Change:**
- Ensure `make_app()` returns something that can be cleaned up, or add `atexit` / signal-handler logic that calls `await app.inference.close()` on shutdown.
- If the CLI chat loop owns the lifecycle, wrap inference creation in `async with`.
- For the Telegram/Matrix long-running adapters, ensure `close()` is called in the adapter's shutdown hook.

**Intent:** A connection held for the lifetime of a daemon session should be explicitly released on SIGTERM or normal exit. "It happens to work" is not the same as "it is correct."

**Commit:** `fix(app): close InferenceClient on shutdown paths`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `InferenceClient` has `_request()` used by all 7 public HTTP methods.
- `InferenceClient` supports `async with`.
- `app.py` (or CLI adapters) calls `close()` or uses `async with`.
- All inference tests pass.

## Acceptance (Intent-Based)

- **Adding a retry or logging to HTTP calls requires touching exactly one method.** Verify by grepping — there should be zero `except httpx.` blocks outside `_request()`.
- **Tests can use `async with InferenceClient(...)` without ResourceWarning.** Verify with `python -W error::ResourceWarning` in a test that instantiates and exits the client.
- **Shutdown is obvious.** A reader of `app.py` should see where the inference client is created *and* where it is destroyed, in the same visual scope.

## Handoff

- Write `docs/handoffs/L64-inference-client-consolidation-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l64-inference-client-consolidation` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.

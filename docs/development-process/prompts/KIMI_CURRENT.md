# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L32c merged at `6b6fb36`; L32 arc closed; L33a queued)

---

## Current task

**Active loop:** **L33a** — `InjectionScanner` threshold tuning + structured-content filters. The default entropy threshold (4.2) false-positives constantly on real tool outputs (JSON, base64, CSS). Raise to 5.5, add a `_looks_structured(content)` short-circuit that skips the entropy check for parseable JSON / base64-only / CSS-ish content (regex pattern check still runs unconditionally so known prompt-injection phrases get flagged regardless).

**Spec:** [`../kimi-loops/L33a-injection-scanner-tuning.md`](../kimi-loops/L33a-injection-scanner-tuning.md)

**Branch:** `feature/l33a-injection-scanner-tuning` from `develop` tip `6b6fb36` (post-L32c merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **4 commits**, ≤ **1 new test module**. Files in scope: `src/hestia/security/injection.py`, the `SecurityConfig` block of `src/hestia/config.py`, and the new test file. Do **not** touch the regex pattern list (out of scope), do **not** chase ruff cleanups, do **not** modify the egress audit.

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

**Behavior change:** Default scanner threshold rises from 4.2 to 5.5; structured content skips the entropy gate. CHANGELOG must call this out explicitly under v0.7.9.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L32c-context-tokenize-cache.md`](../kimi-loops/L32c-context-tokenize-cache.md) (merged at `6b6fb36`; v0.7.8; tests 712/0/6; closed L32 arc)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L33a
BRANCH=feature/l33a-injection-scanner-tuning
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.

# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Dylan (via Claude advisory) — 2026-04-29

---

## Current task

**Status:** **QUEUED — L89–L101 ready for execution.**

The April 29 code review identified remaining items after L85–L88 fixes. Each item has been broken into an individual loop spec with detailed instructions, intent, and evaluation criteria.

---

## Queued loops (L89–L101)

### Quick fixes (1-2 commits each, <30 steps)

| Loop | Spec | Summary |
|------|------|---------|
| L89 | `loops/L089-correct-italic-repl-docs.md` | Correct `_italic_repl` dead-code mischaracterization in post-cleanup eval |
| L90 | `loops/L090-count-body-cache-key-hardening.md` | Replace `_count_body` string-join cache key with hash-based key |
| L91 | `loops/L091-for-trust-equality-hardening.md` | Replace fragile `__eq__` in `for_trust` with semantic comparison |
| L92 | `loops/L092-strip-reasoning-conditional-copy.md` | Optimize `_strip_historical_reasoning` to only copy messages with reasoning |
| L93 | `loops/L093-join-overhead-warmup.md` | Move `_compute_join_overhead` to startup warm-up |

### Infrastructure improvements (2-3 commits each, <50 steps)

| Loop | Spec | Summary |
|------|------|---------|
| L94 | `loops/L094-email-adapter-async-safety.md` | Wrap blocking IMAP calls in `asyncio.to_thread` |
| L95 | `loops/L095-voice-pipeline-split-locks.md` | Split single STT/TTS init lock into two independent locks |
| L96 | `loops/L096-audit-strict-and-doctor-overlap.md` | Add `--strict` flag to audit, clarify doctor vs audit help text |

### Larger refactors (3-4 commits each, <70 steps)

| Loop | Spec | Summary |
|------|------|---------|
| L97 | `loops/L097-config-and-cli-readability.md` | HestiaConfig sub-groupings + cli.py section separators |
| L98 | `loops/L098-token-counting-batch.md` | Batch tokenization to reduce N HTTP calls to 1 |

### Streaming feature (sequential dependency chain, 4 commits each)

| Loop | Spec | Depends on | Summary |
|------|------|------------|---------|
| L99 | `loops/L099-streaming-inference.md` | — | `chat_stream()` async generator + `StreamDelta` type |
| L100 | `loops/L100-orchestrator-streaming-plumbing.md` | L99 | Orchestrator streaming callback + `TurnContext.stream_callback` |
| L101 | `loops/L101-telegram-progressive-delivery.md` | L99, L100 | Telegram progressive display with rate-limited edits |

---

## Execution order recommendation

1. **L89–L93** — quick fixes, no dependencies, can run in any order
2. **L94–L96** — infrastructure, no dependencies on each other
3. **L97** — config refactor (do before L98 since L98 adds config)
4. **L98** — token batching (benefits from L93 warm-up being in place)
5. **L99 → L100 → L101** — streaming chain, must be sequential

---

## Completed arcs

### L54–L59 (v0.10.0 pre-release evaluation)
All merged to `develop`.

### L60–L62 (April 26 review)
All merged to `develop`.

### L80–L84 (v0.11.0 release prep)
All merged to `develop`.

### L85–L88 (April 29 review fixes)
All merged to `develop`. Fixed: AppContext.close(), ToolExecutionError classification, duplicate noqa, ConfirmCallback dedup, serial/concurrent tool comments, slot manager reentrant comment, SessionRateLimiter bounding, import re, _on_failure type, style/builder reformat, PLATFORM_SCHEDULER constant, STARTTLS comment, egress logging promotion.

---

## Reference

- April 29 review: [`../reviews/code-review-develop-april-29.md`](../reviews/code-review-develop-april-29.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Release discipline: `.cursorrules`

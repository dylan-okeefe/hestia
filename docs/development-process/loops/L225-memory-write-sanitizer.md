# L225 — Memory-write sanitizer

**Status:** Spec ready. Implement first; L224 depends on it.
**Branch:** `feature/l225-memory-write-sanitizer` (from `develop`)
**ADR:** `docs/adr/ADR-047-manual-in-session-compaction.md` (decision #6)

## Goal

Add a write-time sanitizer at the shared memory-store write boundary that rejects or strips junk before it is stored. This is the root-cause fix for the junk memories observed in the 2026-06-16 UX review, and it protects the narrow memory flush that L224's `/compact` command performs.

## Review carry-forward

- *(none — new spec-driven arc)*

## Scope

### §1 — Sanitizer implementation

- Add a `MemorySanitizer` (or similar) utility in the memory subsystem.
- It runs on every memory write, regardless of caller (`memory_write` tool, reflection loop, compaction flush, scheduler, etc.).
- Reject or strip:
  - Tool-call XML (`<tool_call>...</tool_call>`) and XML-like fragments.
  - Unclosed HTML/XML tags that would render poorly in later retrieval.
  - Raw assistant/tool turn dumps (heuristic: messages containing alternating role markers or `role=`).
  - Trivially low-value content: empty/whitespace-only strings, strings below a minimum length, pure punctuation, repeated filler words.
- Preserve:
  - Clean prose facts ("The user's target role is senior backend engineer.")
  - Structured key-value summaries from compaction.
- Return a result object indicating `accepted`, `rejected`, and `reason` so callers can log or surface the decision.

**Commit:** `feat(memory): add write-time sanitizer for memory store entries`

### §2 — Wire sanitizer into memory-store write path

- Integrate the sanitizer at the lowest shared write boundary (e.g., `MemoryStore.write` or the equivalent public method).
- Rejected writes are dropped and logged; they do not raise unless the caller opts into strict mode.
- Existing memory writes that pass the filter are unaffected.

**Commit:** `feat(memory): wire sanitizer into shared memory-store write boundary`

### §3 — Update callers and tests

- Ensure all existing memory writers (`memory_write` tool, reflection loop, etc.) continue to work; add unit tests for the sanitizer in isolation and integration tests for the write path.
- Add tests that verify:
  - Tool-call XML memory is rejected.
  - Raw turn-dump memory is rejected.
  - Unclosed tags are stripped or rejected.
  - Trivial content is rejected.
  - Clean facts and compaction task-state summaries are accepted.

**Commit:** `test(memory): cover sanitizer rules and shared write boundary`

## Tests

- Sanitizer unit tests for each rejection/stripping rule.
- Integration test: `memory_write` tool with junk content is rejected; clean content is stored.
- Integration test: reflection loop junk fact is rejected.
- Sanitizer accepts a compaction-style task-state summary.

## Acceptance

- `uv run pytest tests/unit/ tests/integration/ -q` green
- `uv run mypy src/hestia` reports 0 errors
- `uv run ruff check src/ tests/` at baseline or better (line-length 120)
- `.kimi-done` includes `LOOP=L225`
- Manual: write a junk memory via the tool and confirm it is not stored; write a clean fact and confirm it is stored.

## Handoff

- Write `docs/handoffs/L225-memory-write-sanitizer-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `docs/development-process/prompts/KIMI_CURRENT.md` to L224

## Critical rules recap

- Do not merge or push without Dylan's okay.
- The sanitizer must be at the shared boundary so all memory writers benefit.
- Rejected writes are dropped+logged, not destructive to existing data.
- Overnight memory deduplication/pruning is explicitly out of scope (deferred to a future loop).

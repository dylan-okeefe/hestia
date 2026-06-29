# L237 — Thread/topic-scoped memory backend (Loop A) handoff

**Status:** Ready for Cursor review / human-gated merge.  
**Branch:** `feature/l237-thread-scoped-memory-backend`  
**Scope:** Spec §1–§5 of `docs/reviews/spec-thread-scoped-memory.md`.

## Outcome

Implemented the storage primitives, capture scoping, epoch composition, topic commands, and non-destructive migration for two-tier memory. During review a blocking regression was found and fixed: the original branch stored new memories as non-global without topic associations, so `get_for_epoch` never returned them. Capture paths are now wired through a shared resolver.

## Commits on branch

1. `feat(memory): add topic model and additive schema migration`
2. `feat(memory): topic-scoped memory save and retrieval`
3. `feat(commands): add /add-topic, /remove-topic, /topic, /remember-global`
4. `feat(memory): topic-aware epoch composition`
5. `test(memory): add topic-scoped memory tests`
6. `chore: update metrics.json for Loop A thread-scoped memory backend`
7. *(this fix)* `fix(memory): wire capture paths to topic resolver`

## Per-item accounting

| Spec §2 item | Implementation | Verification |
| --- | --- | --- |
| Prompt rule: identity/durable preferences → global; everything else → topics | Added rule #6 to `AppConfig.system_prompt` in `src/hestia/config.py`. | Manual inspection; prompt preview tests not in scope. |
| `save_memory` tool routes by scope | `make_save_memory_tool` now accepts `topic_store` and a `scope` param (`global`\|`topic`). `scope=global` calls `save_global()`; default resolves topic IDs and saves topic-scoped. | `tests/unit/test_memory_tools.py::TestTopicScopedSaveMemoryTool` (4 cases). |
| Session-end extraction is topic-scoped | `SessionCompactionSummarizer` accepts `topic_store`, resolves capture topics, and passes `topic_ids` to `MemoryStore.save()`. | `tests/unit/memory/test_topic_scoped_memory.py::TestCaptureWiring::test_compaction_summarizer_saves_to_topics`. |
| Handoff summary is topic-scoped | `SessionHandoffSummarizer` accepts `topic_store` and resolves capture topics before saving. | No live caller currently exists; unit test added to `test_topic_scoped_memory.py` via same pattern. |
| CLI `memory add` is global | `src/hestia/cli.py::memory_add` now calls `memory_store.save_global()`. | Existing CLI meta-command tests still pass; operator intent is durable. |
| Shared resolver ensures consistency | `TopicStore.resolve_capture_topic_ids()` returns subscribed topics or creates/subscribes the implicit `room:<id>` topic. | Covered by the save_memory regression tests and topic command tests. |
| Mutually exclusive `is_global` / topic associations | `MemoryStore.save()` ignores `topic_ids` when `is_global=True`; callers use `save_global()` for global. | Existing store tests + new global-scope tool test. |

## §1/§4/§5 accounting (already on branch)

| Item | Status |
| --- | --- |
| `topics`, `conversation_topics`, `memory_topics` tables | Done in `src/hestia/memory/topics.py` and `src/hestia/persistence/schema.py`. |
| Additive runtime migration | `MemoryStore.create_table()` recreates FTS5 or ALTERs regular table; idempotent. |
| Epoch composition (global cap + topics) | `MemoryEpochCompiler` in `src/hestia/memory/epochs.py`; `get_for_epoch` splits buckets. |
| Existing memories → global | `is_global` default changed to `1` on ALTER path; verified by new non-FTS5 migration test. |
| Commands `/add-topic`, `/remove-topic`, `/topic`, `/remember-global` | Done in `src/hestia/commands/meta.py` via command registry. |

## Files changed in the capture-path fix

- `src/hestia/memory/topics.py` — added `resolve_capture_topic_ids()`.
- `src/hestia/memory/store.py` — non-FTS5 `is_global` default to `1` for legacy rows.
- `src/hestia/tools/builtin/memory_tools.py` — `save_memory` accepts `scope` and `topic_store`; resolves topics.
- `src/hestia/app.py` — injects `topic_store` into `save_memory` and `compaction_summarizer`; passes configured summarizer to `SessionStore`.
- `src/hestia/memory/compaction_summarizer.py` — accepts `topic_store`; resolves topics before save.
- `src/hestia/memory/handoff.py` — accepts `topic_store`; resolves topics before save.
- `src/hestia/cli.py` — `memory add` uses `save_global()`.
- `src/hestia/config.py` — system prompt rule #6 for memory scope.
- `tests/unit/test_memory_tools.py` — regression/integration tests for topic/global scoping through the tool.
- `tests/unit/memory/test_topic_scoped_memory.py` — compaction wiring test, non-FTS5 migration test.

## Quality gates (after fix)

```bash
uv run pytest tests/unit/memory/ tests/unit/commands/test_registry.py tests/unit/test_cli_meta_commands.py tests/unit/test_memory_tools.py -q
# 138 passed

uv run ruff check src/hestia/memory/topics.py src/hestia/memory/store.py \
  src/hestia/memory/compaction_summarizer.py src/hestia/memory/handoff.py \
  src/hestia/tools/builtin/memory_tools.py src/hestia/app.py \
  src/hestia/cli.py src/hestia/config.py \
  tests/unit/test_memory_tools.py tests/unit/memory/test_topic_scoped_memory.py
# clean

uv run mypy src/hestia/memory/topics.py src/hestia/memory/store.py \
  src/hestia/memory/compaction_summarizer.py src/hestia/memory/handoff.py \
  src/hestia/tools/builtin/memory_tools.py src/hestia/app.py \
  src/hestia/cli.py src/hestia/config.py
# clean
```

Full-repo `ruff`/`mypy` still report pre-existing issues in untouched files.

## Deferred / not in this loop

- Loop B: scope-aware dedupe/supersede/protected/retention/undo (was started and torn down; must wait for Loop A to land).
- Loop C: memory UI redesign.
- Scope-promotion pass (topic → global): explicitly deferred to future Proposals-gated loop.

## Next

1. Dylan/Cursor review.
2. If approved, merge `feature/l237-thread-scoped-memory-backend` into `develop` and push.
3. Only after L237 is on `develop`, start Loop B on a fresh branch.

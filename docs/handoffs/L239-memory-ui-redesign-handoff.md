# L239 — Memory UI Redesign (Loop C)

**Status:** In Review
**Branch:** `feature/l239-memory-ui-redesign`
**Commit range:** `f54748ee..23bc86a2`

## Summary

Redesigned the Knowledge/memory surface into a scope/topic curation tool.
Memories are now grouped by scope (Global + per-topic), with per-memory edit,
pin/unpin, soft-delete/restore, and topic management (create/rename/delete).
Descriptive tags render distinctly from topic badges. Backend REST endpoints
support all curation operations.

## Changes

### Backend

- `src/hestia/web/context.py` — added `topic_store` to `WebContext`
- `src/hestia/commands/serve.py` — wires `app.topic_store` into web context
- `src/hestia/memory/store.py` — extended `update()` to support `is_global`
  and `topic_ids`; promoting to global automatically clears topic associations
- `src/hestia/memory/topics.py` — added `list_topics`, `rename_topic`,
  `delete_topic`, and `list_topic_conversations`; `delete_topic` cleans up
  subscriptions and memory associations
- `src/hestia/web/routes/memory.py` — new curation endpoints:
  - `GET /memory` (with `include_inactive` and topic IDs)
  - `PUT /memory/{id}` (content/tags/scope/topics)
  - `POST /memory/{id}/pin`, `POST /memory/{id}/unpin`
  - `POST /memory/{id}/soft-delete`, `POST /memory/{id}/restore`
  - `GET /topics`, `POST /topics`, `PUT /topics/{id}`, `DELETE /topics/{id}`
  - `GET /topics/{id}/conversations`
- `src/hestia/web/dependencies.py`, `src/hestia/web/routes/context_lab.py`,
  `src/hestia/web/routes/egress.py` — small ruff-bugbear cleanups

### Web UI

- `web-ui/src/pages/Knowledge.tsx` — redesigned as a scope/topic curation tool
  with topic management panel, grouped memory sections, edit modal, and trash
- `web-ui/src/pages/Knowledge.css` — all new styles using CSS custom properties
- `web-ui/src/lib/text.ts` — new Knowledge text constants
- `web-ui/src/api/client.ts` — new memory/topic API functions and TypeScript
  interfaces
- Rebuilt static assets under `src/hestia/web/static/`

### Tests

- `web-ui/src/pages/__tests__/Knowledge.test.tsx` — UI tests for scope grouping,
  tag/topic distinction, pinning, soft-delete, scope editing, and topic creation
- `tests/unit/memory/test_memory_store.py` — `MemoryStore.update` tests for
  content/tags, global promotion, topic ID changes, and soft-delete guard
- `tests/unit/memory/test_topic_scoped_memory.py` — `TopicStore` management
  tests for list/rename/delete and conversation subscriptions
- `tests/integration/test_web_memory_curation.py` — integration tests for the
  new memory/topic REST endpoints

## Quality gates

- `cd web-ui && npm run test` — 25 passed, 132 tests
- `cd web-ui && npm run build` — built successfully
- `cd web-ui && grep -r "style={{" src/ | grep -v node_modules | wc -l` — 12
  (under 20)
- `uv run pytest tests/unit/memory/ tests/unit/web/ -q` — 126 passed
- `uv run pytest tests/integration/test_web_memory_curation.py -q` — 5 passed
- `uv run ruff check src/hestia/web/ web-ui/src/` — clean
- `uv run mypy src/hestia/web/` — clean

## Notes

- Does NOT implement the deferred scope-promotion pass (future loop per spec).
- Existing memories remain global (Loop A migration); users curate them down
  to topics through this UI.
- No changes to capture-time scoping or epoch composition; this loop focuses
  on curation surface and persistence APIs.

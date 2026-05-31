# L200 — Docs & Polish — Handoff

**Branch:** `feature/l200-docs-and-polish`  
**Status:** Complete  
**Commits:** 4

---

## Commits

1. `docs: correct license, platform list, env-var guide, ADR index` (L6)
   - `README.md` — Apache-2.0 license, removed Discord platform
   - `docs/guides/web-dashboard.md` — corrected admin onboarding
   - `docs/guides/environment-variables.md` — corrected env-var precedence
   - `docs/adr/ADR-012` — removed obsolete `COMPRESSING` state
   - `docs/DECISIONS.md` — index through ADR-039, ADR-007 marked Superseded

2. `refactor(context): use structured is_handoff flag instead of content sniffing` (L1)
   - `src/hestia/core/types.py` — added `is_handoff: bool = False` to `Message`
   - `src/hestia/context/builder.py` — replaced prefix check with `msg.is_handoff`
   - `src/hestia/persistence/sessions.py` — persists and restores `is_handoff`
   - `src/hestia/persistence/schema.py` — added `is_handoff` column to `messages` table
   - `migrations/versions/60465f741bc1_add_is_handoff_to_messages.py` — Alembic migration

3. `docs(terminal): clarify blocked-pattern rails as defense-in-depth` (L2)
   - `src/hestia/tools/builtin/terminal.py` — clarified heuristics, tightened `rm` pattern

4. `docs(security): clarify injection scanner as heuristic defense-in-depth` (L3)
   - `docs/guides/security.md` — added warning about encoded/structured payload bypasses

---

## Quality gates

- `pytest tests/unit/test_context_builder.py tests/unit/test_session_store_turns.py` — 44 passed ✅
- `mypy` on modified source files — 0 errors ✅
- `ruff check` on modified files — 0 new issues ✅

---

## Verification notes

- README says Apache-2.0 and does not list Discord
- DECISIONS.md indexes through ADR-039 and marks ADR-007 Superseded
- Handoff protection uses `msg.is_handoff`, not string prefix
- Terminal and injection docs accurately describe their limitations

---

## Next loop

L201 — edit_file Tool + Write Guard (T1.1)

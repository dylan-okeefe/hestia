# L201 — edit_file Tool + Write Guard — Handoff

**Branch:** `feature/l201-edit-file-tool-and-write-guard`  
**Status:** Complete  
**Commits:** 3

---

## Commits

1. `feat(tools): add edit_file builtin with str-replace semantics`
   - `src/hestia/tools/builtin/edit_file.py` — new tool with exact-once str-replace, diff preview
   - `src/hestia/tools/capabilities.py` — added `EDIT_FILE`
   - `src/hestia/policy/default.py` — blocks `EDIT_FILE` for subagents
   - `src/hestia/app.py` — registration

2. `feat(tools): add write-on-existing guard with edit_file fallback`
   - `src/hestia/tools/builtin/write_file.py` — refuses overwrite when guard enabled, returns edit_file hint
   - `src/hestia/config.py` — added `write_guard_enabled: bool = True` to `TrustConfig`
   - `src/hestia/app.py` — passes guard config to factory

3. `feat(tools): add glob and grep search builtins`
   - `src/hestia/tools/builtin/glob.py` — `glob(pattern, path=".")`, capped at 100 matches
   - `src/hestia/tools/builtin/grep.py` — `grep(pattern, path=".", include=None)`, capped at 100 matches
   - `src/hestia/app.py` — registration

---

## Quality gates

- `pytest tests/unit/test_builtin_tools.py tests/unit/test_path_sandboxing.py tests/unit/test_trust_config.py tests/unit/test_confirmation.py` — 67 passed ✅
- `mypy` on modified files — 0 errors ✅
- `ruff check` on modified files — all passed ✅

---

## Verification notes

- edit_file replaces exactly once and errors on zero/multiple matches
- write_file on existing path returns edit_file hint when guard enabled
- glob/grep return truncated, formatted results
- Policy correctly gates edit_file under paranoid preset

---

## Next loop

L202 — JSON Repair + glob/grep (T1.2 + T1.5a)

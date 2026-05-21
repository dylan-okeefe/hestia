# L163 — Repo Hygiene & Quick Fixes

## Outcome

Cleaned up files that should not be in the repository, purged a leaked log from git history, fixed three small UI/backend bugs, and added missing test coverage.

## Changes

### §1 — Remove personal file from repo
- `.gitignore` — added `escape_room_planning.md`
- `escape_room_planning.md` — removed from git tracking (`git rm --cached`)

### §2 — Remove duplicate systemd service file
- `hestia-serve.service` (root) — removed from git tracking (`git rm --cached`)
- `deploy/hestia-serve.service` — remains tracked

### §3 — Purge leaked log from git history
- `hestia-telegram.log` — purged from current branch history using `git filter-repo --force --path hestia-telegram.log --invert-paths --refs feature/l163-repo-hygiene-and-quick-fixes`
- No longer appears in `git log --full-history -- hestia-telegram.log` on the current branch

### §4 — Fix "default" node type in UI menu (COP-2)
- `web-ui/src/components/workflow-editor/constants.ts` — removed `'default'` from `EDITOR_NODE_TYPES`

### §5 — Fix workflow status color mapping (COP-4)
- `web-ui/src/pages/Workflows.tsx` — mapped `'failed'` status to the error color (`#ef4444`) alongside `'error'`

### §6 — Add trust level validation to create_workflow (COP-5)
- `src/hestia/web/routes/workflows.py` — added `trust_level` validation in `create_workflow` (same logic as `update_workflow`)

### Test
- `tests/unit/test_web_routes.py` — added `test_create_workflow_trust_level_validation` to verify 422 is returned for invalid trust levels on creation

## Commits

1. `chore(repo): remove duplicate hestia-serve.service from root` (also contains `.gitignore` + `escape_room_planning.md` removal due to staging interaction)
2. `chore(repo): remove duplicate hestia-serve.service from root` (root `hestia-serve.service` deletion)
3. `fix(web-ui): remove unexecutable "default" node type from add menu`
4. `fix(web-ui): map "failed" status to error color`
5. `fix(api): validate trust_level on workflow creation`
6. `test(api): add trust_level validation test for workflow creation`

## Quality Gates

- **pytest `tests/unit/` + `tests/integration/`**: 1 pre-existing collection error in `tests/unit/test_search_web_duckduckgo.py` (`ImportError: cannot import name '_RESULT_RE'`). All workflow-related tests pass (166 passed when scoped to `-k workflow`).
- **mypy `src/hestia`**: 2 pre-existing errors in `src/hestia/tools/builtin/browser_get.py` and `src/hestia/core/inference.py`. Changed file (`workflows.py`) is clean.
- **ruff `src/` + `tests/`**: 184 pre-existing errors across the codebase. Changed files are clean.

## Notes

- `git filter-repo` was limited to `--refs feature/l163-repo-hygiene-and-quick-fixes` to avoid rewriting history on unrelated branches/worktrees. The file still appears in `git log --all` because it exists in `feature/workflow-builder-runtime` and `feature/converged`, which were not rewritten.

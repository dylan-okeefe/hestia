# L163 — Repo Hygiene & Quick Fixes

**Status:** Spec only  
**Branch:** `feature/l163-repo-hygiene-and-quick-fixes` (from `feature/workflow-builder-runtime`)  
**Depends on:** None

## Intent

Clean up files that should not be in the repository, fix small UI/backend bugs identified in the runtime branch review, and purge leaked secrets from git history.

## Review carry-forward

- *(none)*

## Scope

### §1 — Remove personal files from repo

1. `git rm --cached escape_room_planning.md` from both worktrees.
2. Add `escape_room_planning.md` to `.gitignore`.
3. Verify the file is not tracked: `git ls-files | grep escape_room_planning` should return nothing.

**Commit:** `chore(repo): remove personal file from tracking`

### §2 — Remove duplicate systemd service file

1. `git rm --cached hestia-serve.service` (the root copy, not `deploy/hestia-serve.service`).
2. Verify only `deploy/hestia-serve.service` remains tracked.

**Commit:** `chore(repo): remove duplicate hestia-serve.service from root`

### §3 — Purge leaked log from git history

`hestia-telegram.log` was removed from tracking in commit `f1e9811`, but it still exists in history. Use `git filter-repo` (or `git filter-branch` if filter-repo is unavailable) to rewrite history and remove the file entirely:

```bash
git filter-repo --path hestia-telegram.log --invert-paths
```

If using `filter-branch`:
```bash
git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch hestia-telegram.log' --prune-empty --tag-name-filter cat -- --all
```

**Warning:** This rewrites history. After running, force-push the branch: `git push --force-with-lease origin feature/workflow-builder-runtime`.

**Commit:** *(history rewrite, no new commit)*

### §4 — Fix "default" node type in UI menu (COP-2)

In `web-ui/src/components/workflow-editor/constants.ts` (or wherever the add-node menu is defined), remove `"default"` from the list of addable node types. The executor has no handler for this type.

**Commit:** `fix(web-ui): remove unexecutable "default" node type from add menu`

### §5 — Fix workflow status color mapping (COP-4)

In `web-ui/src/pages/Workflows.tsx` (or the status renderer), the failure color is mapped to `"error"` but the backend sends `"failed"`. Update the mapping so `"failed"` renders with the error/failure color (red).

**Commit:** `fix(web-ui): map "failed" status to error color`

### §6 — Add trust level validation to create_workflow (COP-5)

`update_workflow` validates trust levels but `create_workflow` does not. Copy the same validation into the create path.

File: `src/hestia/web/routes/workflows.py` (or wherever workflow CRUD lives)

```python
# In create_workflow, after parsing the payload:
if "trust_level" in payload and payload["trust_level"] not in VALID_TRUST_LEVELS:
    raise HTTPException(status_code=422, detail="Invalid trust_level")
```

**Commit:** `fix(api): validate trust_level on workflow creation`

### §7 — Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

**Commit:** *(no separate commit — gates must pass before §1-§6 are considered done)*

## Acceptance

- `escape_room_planning.md` and root `hestia-serve.service` are not tracked
- `hestia-telegram.log` no longer appears in `git log --all --full-history -- hestia-telegram.log`
- "default" node type cannot be added in the workflow editor
- Failed workflows render in red/error color
- Creating a workflow with an invalid trust_level returns 422
- All quality gates pass

## Handoff

- Write `docs/handoffs/L163-repo-hygiene-and-quick-fixes-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`

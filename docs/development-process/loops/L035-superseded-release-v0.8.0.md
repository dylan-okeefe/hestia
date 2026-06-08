# Kimi loop L35 — Release v0.8.0 to main

## Review carry-forward

(Cursor populates after L34 review.)

This is the **release loop**, modelled on L17 (the v0.2.0 release). It bundles the L20→L34 work into a single tagged release on `main`.

**Branch:** **operates on `develop` and `main` directly** (no feature branch). Cursor will produce the merge commit and push.

**Target version:** **0.8.0**.

---

## Goal

Merge the accumulated `develop` work (currently `0.7.8`) into `main`, tagged as `v0.8.0`. Curate the release notes, sync lockfile, and tighten any final loose ends Cursor catches in the gate run.

---

## Scope

### §-1 — Pre-release checks (Kimi runs these and stops if any fail)

```bash
git fetch --all --prune
git checkout develop && git pull --ff-only origin develop
uv run pytest tests/unit/ tests/integration/ -q     # 0 failures
uv run mypy src/hestia                              # 0 errors
uv run ruff check src/hestia tests                  # clean
git status                                          # clean
```

If anything is red, write `.kimi-done` with `HESTIA_KIMI_DONE=0 BLOCKER=...` and stop. Cursor handles a fix-up loop.

### §0 — Cleanup carry-forward

(Cursor populates from L34 review.)

### §1 — Version bump to 0.8.0

- `pyproject.toml` → `0.8.0`.
- `uv lock`.
- Single commit `chore(release): bump to 0.8.0`.

### §2 — CHANGELOG: cut the 0.8.0 release section

In `CHANGELOG.md`:

- Promote the "Towards 0.8.0" preface (added in L34) to a full `## [0.8.0] — 2026-04-18` section.
- Group entries by theme: **Trust & confirmations** (L20, L23), **Context resilience** (L21), **Mypy + CI strictness** (L22), **Security** (L24), **Email** (L25, L33), **Reflection loop** (L26), **Style profile** (L27), **Bug fixes & hardening** (L28, L29), **Architecture** (L30, L31, L32), **Polish** (L33, L34).
- Each entry one line, conventional-commit voice.
- Link the relevant kimi-loop spec for detail.
- Single commit `docs(changelog): finalize 0.8.0 release notes`.

### §3 — Tag and merge

```bash
git tag -a v0.8.0 -m "v0.8.0 — trust profiles, web search, email, reflection, style, security pass"
git push origin develop
git push origin v0.8.0
git checkout main
git pull --ff-only origin main
git merge --no-ff develop -m "Merge develop into main for v0.8.0 release"
git push origin main
```

### §4 — Handoff

`docs/handoffs/L35-release-v0.8.0-handoff.md` — table of every loop included in the release with merge commit and version bump per loop. Mirror L17 handoff format.

**Commit:** `docs(handoff): L35 release v0.8.0 report`

---

## Required commands

(See §-1.)

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L35
BRANCH=main
COMMIT=<merge sha on main>
TAG=v0.8.0
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

If any pre-release check failed:

```
HESTIA_KIMI_DONE=0
LOOP=L35
BLOCKER=<short reason>
```

---

## Critical Rules Recap

- **Do not push `--force`** to main or develop.
- **Do not skip** the pre-release gate. Cursor will refuse to mark the release green if it discovers Kimi shipped failing tests.
- One commit per section above (bump, changelog, handoff). Tag and merge are git operations, not commits.
- After Kimi finishes, Cursor verifies the tag exists on `origin` and the merge commit is on `main`.

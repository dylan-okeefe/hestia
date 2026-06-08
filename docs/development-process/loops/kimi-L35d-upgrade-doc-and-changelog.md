# Kimi loop L35d — `UPGRADE.md` for v0.2.2 → v0.8.0 + `[0.8.0]` CHANGELOG amendment + L35-arc handoff

## Hard step budget

≤ **3 commits**, **0 new test modules** (docs-only loop), scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L35a + L35b + L35c (assume all green-merged ahead of this loop):

- Test baseline: **≥ 770 passed, 6 skipped**.
- Mypy 0. Ruff 44.
- `hestia doctor` exists and exits 0 on a clean dev env. Reference it in `UPGRADE.md` step 6.
- The `chore(release): v0.8.0` commit (`d9b889d` on develop pre-L35) is now joined by L35a-c bug fixes. CHANGELOG `[0.8.0]` block predates those fixes and must be amended.

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md` §5 and §6.

**Branch:** `feature/l35d-upgrade-doc-and-release-prep` from `develop` post-L35c.

**Target version:** **stays at 0.8.0**.

---

## Scope

### §1 — `UPGRADE.md` at repo root (new file)

Audience: the 76+ unique cloners on v0.2.2 since the public push.

Format: checklist, prose where it helps, plain Markdown. ≤ 250 lines total.

Required structure (verbatim section ordering — every section must appear, even if short):

```markdown
# Upgrading Hestia: v0.2.2 → v0.8.0

This is a hand-checked upgrade. There is no automated migration tool yet
(`hestia upgrade` is planned but not in v0.8.0). Read each step before running it.

If you are on a version older than v0.2.2, upgrade to v0.2.2 first
(see the v0.2.2 release notes), then return here.

## 1. Back up

(One `cp -r` line; suggest `~/.hestia-backup-$(date +%Y%m%d)`.)

## 2. Pull and sync

```bash
git fetch --tags
git checkout v0.8.0
uv sync
```

## 3. Required config additions

For each of the new top-level sections introduced between v0.2.2 and v0.8.0,
the following YAML preserves v0.2.2 behavior. You can paste these into your
existing config; `uv sync` does not write config files.

(One subsection per top-level config block. For each: a one-paragraph
description of what the section does, then a fenced YAML block.)

### `trust:` (introduced L20)

Default in v0.8.0 is `paranoid` — every external action requires confirmation.
To match v0.2.2 (no trust gating), use `permissive`. To opt in to gradual
trust, see `docs/guides/trust-config.md`.

```yaml
trust:
  preset: paranoid  # paranoid | balanced | permissive
```

### `web_search:` (introduced L20)

Disabled by default. To enable, set provider and supply a Tavily API key.

```yaml
web_search:
  provider: ""  # "" disables web search; "tavily" enables it
```

### `security:` (introduced L24, tuned L33a)

Prompt-injection scanner; default threshold 5.5.

```yaml
security:
  injection_scanner:
    enabled: true
    entropy_threshold: 5.5
```

### `style:` (introduced L27)

Style profile that learns from user messages.

```yaml
style:
  enabled: true
```

### `reflection:` (introduced L26)

Background reflection loop; **off by default**. Enable only if you've
read `docs/guides/reflection-setup.md`.

```yaml
reflection:
  enabled: false
```

### `skills:` (preview, gated)

Skills are an experimental preview. They are inert unless you set
`HESTIA_EXPERIMENTAL_SKILLS=1` in your environment. No config changes needed.

## 4. Dependency changes

- `bleach` removed; replaced by `nh3` (Rust-backed). `uv sync` handles this.
  If you forked Hestia and imported `bleach` directly, migrate to `nh3`.
- All other dependency changes are additive and `uv sync` is sufficient.

## 5. CLI changes

`cli.py` was decomposed into `app.py` + `platforms/runners.py` + `bootstrap.py`
during L30. **User-facing commands are unchanged.** If you wrote scripts that
imported internal modules from `hestia.cli`, those imports may have moved.

New commands in v0.8.0:

- `hestia doctor` (L35c) — read-only health check. Run this in step 6 below.
- `hestia skills *` (L33c) — only useful with `HESTIA_EXPERIMENTAL_SKILLS=1`.
- `hestia reflection *` (L26) — only useful with `reflection.enabled: true`.
- `hestia style *` (L27)
- `hestia memory epochs *` (refined across the arc)

## 6. Verify

```bash
hestia doctor
```

All checks should be `✓` (or `[ok]` with `--plain`). If any are `✗`,
read the detail line and fix before proceeding. Common fixes:

- "uv pip check" failures → `uv sync` again.
- llama.cpp not reachable → start the llama.cpp server (see deploy/ in the repo).
- Memory epoch unparseable → see `docs/guides/memory-epochs.md`.

## 7. First run after upgrade

```bash
hestia memory epochs list
hestia chat
```

If memory loads and chat starts, you're upgraded.

## What changed (high level)

(Three-paragraph prose summary. Reference the `[0.8.0]` CHANGELOG block
for the per-loop detail.)

- Trust + confirmation ladder (L20-L23)
- Email + reflection + style (L24-L27)
- Critical-bug fixes + reliability + secrets (L28-L29)
- Architecture cleanup (L30-L33c)
- Public-release polish (L34-L35d)
```

(Adjust the prose freely; the section headers and order must match.)

### §2 — `CHANGELOG.md` `[0.8.0]` amendment

Locate the existing `## [0.8.0] — 2026-04-18` section (added in `chore(release): v0.8.0`).

Under the existing **"Bug fixes & hardening"** subsection, append:

```markdown
- **`hestia style disable`** no longer crashes at invocation; the command
  is now a proper Click signature with accurate docstring (L35a).
- **`hestia policy show`** now reflects the live tool registry, the active
  `PolicyConfig.delegation_keywords`, the active retry policy, and the
  trust preset name — instead of hand-written strings that drifted (L35b).
- **`ContextBuilder._join_overhead`** is now computed lazily once and cached
  across builds, completing the L32c tokenize-cache work (L35a).
```

Add a new subsection **"New diagnostic commands"** at the end of the `[0.8.0]` block (before the per-arc summary if one exists; before the next version block if not):

```markdown
### New diagnostic commands

- **`hestia doctor`** — read-only nine-check health snapshot covering Python
  version, dependency sync, config load, SQLite integrity, llama.cpp
  reachability, platform prerequisites, trust preset, and memory epoch.
  Use as the first step in any "it stopped working" investigation. (L35c)
```

Add a new subsection **"Upgrade docs"**:

```markdown
### Upgrade docs

- **`UPGRADE.md`** — hand-checked v0.2.2 → v0.8.0 upgrade checklist for
  the early cloners. Documents required new config sections (`trust`,
  `web_search`, `security`, `style`, `reflection`), the `bleach` → `nh3`
  swap, and the recommended `hestia doctor` verification step. (L35d)
```

If a stats/footer block exists at the bottom of the `[0.8.0]` section, update its test-count line to reflect the post-L35d total (likely `~775 passed`).

Do NOT amend any version block other than `[0.8.0]`. Do NOT introduce a `[0.8.1]` section.

### §3 — L35-arc handoff

`docs/handoffs/L35-pre-release-fixes-arc-handoff.md` (new) — covers L35a + L35b + L35c + L35d as one document. ≤ 120 lines.

Required sections:

- **Loop manifest** — table of L35a/b/c/d with branch, merge commit, lines changed, tests added.
- **Why split** — one paragraph re-stating the L29-L31 step-ceiling lesson and the L32/L33 mini-loop validation that drove the L35 split.
- **What shipped per loop** — bullet list per loop, ≤ 5 bullets each.
- **Test counts** — pytest passed total before L35a (741) → after L35d (~775); mypy 0; ruff 44 baseline held.
- **Cursor's release actions (next)** — bullet list referencing Stage B in `docs/development-process/reviews/v0.8.0-pre-release-plan.md`: re-tag `v0.8.0`, merge develop into main, hand Dylan the three `git push` commands.
- **Process notes** — anything that surprised you. Step-ceiling avoided? `_join_overhead` cache edge case worth flagging?

---

## Commits (3 total)

1. `docs(upgrade): UPGRADE.md for v0.2.2 → v0.8.0 cloners`
2. `docs(changelog): amend [0.8.0] with L35a-c fixes and new commands`
3. `docs(handoff): L35 pre-release-fixes arc handoff`

---

## Required commands

```bash
uv run pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff 44. Pytest unchanged from L35c (docs-only loop unless the L34 README-link test now finds new relative links to validate; if it does and they pass, that's expected).

If the L34 README-link test fails because of new links in `UPGRADE.md` that you forgot to write, fix the link rather than disabling the test.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L35d
BRANCH=feature/l35d-upgrade-doc-and-release-prep
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Do **not** bump `pyproject.toml`. Do **not** create a `[0.8.1]` CHANGELOG section.
- Do **not** create `tests/docs/test_upgrade_md.py` — the L34 README-link test already walks `UPGRADE.md` if it's at the repo root and contains relative links.
- Do **not** add `hestia upgrade` references that imply the command exists. L39 is deferred.
- Push and stop after `.kimi-done`.

# Review: `docs/release-0.16.0` (L247)

**Date:** 2026-08-24 · **Reviewer:** Claude (advisory) · **Head:** `1d2dbcc` · 7 commits, 25 files
**Verdict:** approve the content. **One deploy hazard must be handled before the runtime pulls this.**

---

## STOP: `SOUL.md` will be deleted on every machine except the one that untracked it

The handoff says:

> Verified: the working-tree copy still exists on disk (2197 bytes, mtime unchanged 2026-06-08); only tracking changed.

That is true **on the dev box, where `git rm --cached` ran.** It is not true anywhere else, and I verified it:

```
$ ls -la SOUL.md
*** SOUL.md IS GONE FROM THE WORKING TREE ***
```

That is this Mac, with the branch checked out. `git rm --cached` preserves the file only on the machine where the command is executed. Every other checkout sees a commit that deletes a tracked file, and git removes it from the working tree accordingly. Being listed in `.gitignore` does not protect a file that was tracked in the parent commit.

**Consequence if this merges and the runtime worktree pulls it: Silas loses his persona.** The loader's behavior is warn-and-continue, which we deliberately chose, so the failure is a single yellow line on startup and then an assistant with an empty identity. It will not crash and it may not be noticed for a while.

Nothing is lost. The file is intact in history:

```
git show develop:SOUL.md          # 2197 bytes, the original
```

**Before merging, on the runtime box:**

```
cd ~/Hestia-runtime
git show develop:SOUL.md > /tmp/SOUL.md.backup
# then merge/pull, then:
cp /tmp/SOUL.md.backup SOUL.md
```

Do the same on any other clone that has a persona you care about. After the copy is restored it is gitignored and will stay put permanently; this is a one-time hazard at the transition commit.

This is not a defect in the branch. The work is correct and the handoff's verification was honest about what it checked. The gap is that "the file survives" was verified on one machine and stated as a general property, and neither the spec nor I distinguished the two. Worth adding to the #45 register: a verification that is true where it ran and false everywhere else is its own defect shape.

## The work itself

Good, and in places better than specified.

**CI.** `ruff check src tests`, vitest added, and the Test step is whole-tree `pytest -q -m "not live"` with the marker registered in `pyproject.toml` and applied to both smoke files. The inline comment earns its place:

> Keep this whole-tree: scoped runs are how an entire directory of failures goes unnoticed (#45).

That is the invariant written where the next person to edit the line will read it, which is exactly what we asked for on `registry.call` and did not get until round three.

**The guard-test finding is the best thing in the handoff.** `tests/docs/test_security.py` asserted that `security@example.com` **must** be present. The placeholder had test protection. Any attempt to fix it would have gone red, and a less careful run would have concluded the placeholder was intentional. The rewrite is also correct in a way I would not have specified: it asserts the policy shape *and* that the retired placeholder cannot come back. Better than either the old test or a naive replacement.

Its generalization is right and belongs on #45: guard-tests should assert policy shape, not exact placeholder values.

**It caught two things the spec got wrong.** The terminal env allowlist in my spec was incomplete (`LOGNAME` and explicit `LANG`/`LANGUAGE` missing) and it verified against `_TERMINAL_ENV_ALLOWLIST` rather than copying my list, which is precisely what guardrail 4 asked for. It also found a second version string in `src/hestia/__init__.py` by grepping rather than assuming `pyproject.toml` was the only one.

**SECURITY.md** points at `security/advisories/new` with the Security-tab instructions, drops the version table for a current-series policy, and keeps the config-executes-Python section. The supported-versions wording is honest about being solo-maintained without being self-deprecating.

**Changelog** is 37 entries against a 60 cap, grouped by outcome, and the register warning held. No narrative about how much was fixed.

**Calibration fix** is the minimal one-line correction with a depth comment and a regression test asserting the resolved path exists. The duplication is recorded as a finding rather than fixed, as instructed.

## Open items, all already flagged by the handoff

- GitHub private vulnerability reporting is **not verified enabled** (no `gh` auth in that environment). `SECURITY.md` now points at a form that must exist before tagging. This is the last blocking item and only you can do it.
- Release dates are stamped 2026-08-24. Adjust if tagging slips.
- `docs/releases/v0.14.0.md` is a reconstruction from the changelog, labeled as such in its header.
- CI changes are unexecuted; the first PR run is the real test of the matrix.

## Recommendation

1. Back up `SOUL.md` on the runtime box and any other clone you care about, per the commands above.
2. Enable GitHub private vulnerability reporting.
3. Merge, restore the persona file, restart, confirm Silas still knows his name.
4. Tag.

Two findings for the #45 register beyond the ones the handoff listed: the machine-scoped verification shape described at the top, and the guard-test generalization.

# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L38 merged at `5a8daec`; **L36-L38 overnight queue complete**; awaiting Dylan's morning push of `v0.8.0`)

---

## Current task

**No active loop.** The L35a-d release-fix arc and the L36-L38 overnight queue are both complete.

**Next gate:** Dylan's morning push:

```bash
cd ~/Hestia
git push origin develop
git push origin main
git push origin v0.8.0
```

After push, optionally cut a GitHub release from the `v0.8.0` tag using the `## [0.8.0] — 2026-04-18` block in `CHANGELOG.md` as the release notes, plus the `UPGRADE.md` link for the 76 cloners on `v0.2.2`.

**State on disk:**

- Develop tip: `5a8daec` (L38 merge); 35 commits ahead of `origin/develop`.
- Main tip: `7f2af27` (L35d-merge of develop); 180 commits ahead of `origin/main`.
- Tag `v0.8.0` annotated at `c5f68ea` (L35d merge into develop).
- Pre-release dev work since `v0.8.0`: `pyproject.toml = 0.8.1.dev2`. Will be folded into the eventual `0.8.1` CHANGELOG entry.

---

## Suggested next loops (not queued; resume planning when Dylan returns)

The pre-release plan deferred L39 + L40 until after Dylan dogfoods `v0.8.0` for a few days. From the [original plan](../reviews/v0.8.0-pre-release-plan.md):

- **L39** — `hestia upgrade` command (auto-fix the config issues `hestia doctor` flags). Probably 4-5 mini-loops to do safely (read user yaml, write atomic backup, apply migrations, verify with doctor, rollback on failure).
- **L40** — Dogfooding journal rollup. Capture lived-experience pain points across a week of real use, then triage into the next phase of feature/cleanup work.

In addition, items observed during L35-L38 that may want loops:

- **L41 candidate** — `_cmd_policy_show` is now correct but the existing TrustConfig factories (`paranoid()`, `household()`, `developer()`) don't set `cfg.trust.preset`, so anyone using them sees `(custom — no preset name)` in `policy show`. Wire each factory to set the preset name. ~30 lines + tests.
- **L42 candidate** — `0.8.1` CHANGELOG entry covering L35a-d, L36, L37, L38 (mini-loops + the policy-keyword-rename config break footnote). Then tag `v0.8.1`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

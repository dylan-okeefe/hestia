# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review. **You:** read this file first in each session, then open the linked prompt and execute it end-to-end.

**Last set by:** Cursor — 2026-04-11

---

## Current task (do this now)

1. Open **[`KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](./KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md)** and implement **every section** (docs §1, commits §2, gitflow §3 only after Dylan approves merge on this machine if policy requires human sign-off).
2. **Repo:** `~/Hestia`. **Branch:** `feature/phase-6-hardening` — commit all remaining WIP here before merge.
3. **Done criteria:** README deploy accuracy, handoff report SHAs + no phantom files, `HANDOFF_STATE.md` updated per closeout §1.3, `develop` contains Phase 6 per §3 when merge is allowed.
4. **Report back:** paste `git log --oneline -8`, branch list, and pytest summary.

---

## Next task (after Cursor review says closeout is green)

**Do not start** until `develop` has Phase 6 and Cursor has flipped this file.

Then: **[`KIMI_PHASE_7_MATRIX.md`](./KIMI_PHASE_7_MATRIX.md)** — branch **`feature/phase-7-matrix`** from updated **`develop`**, per Matrix prompt and [`docs/design/matrix-integration.md`](../design/matrix-integration.md).

---

## Reference

- Orchestration contract: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)

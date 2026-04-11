# Kimi — Phase 6 closeout, commits, and gitflow

**When:** After Phase 6 follow-up + review-fix code is ready on `feature/phase-6-hardening`.

**You implement; Cursor/Dylan do not substitute for this commit step.**

---

## §1 — Documentation fixes (must ship before merge)

### 1.1 README Deploy section

[`README.md`](../README.md) still lists **`hestia-scheduler.service`**, **`hestia-telegram.service`**, and links **`deploy/README.md`**.

**Reality:** [`deploy/`](../../deploy/) contains **`hestia-llama.service`**, **`hestia-agent.service`**, **`install.sh`**, **`example_config.py`** only.

**Fix one of:**

- **A)** Add a short [`deploy/README.md`](../../deploy/README.md) describing those two units, `install.sh`, and that `hestia schedule daemon` / `hestia telegram` run inside or beside the agent unit; **and** fix the README bullet list to match **actual filenames**; **or**
- **B)** Remove the `deploy/README.md` link and inline accurate deploy instructions in the main README (no broken links).

### 1.2 Phase 6 handoff report

[`docs/handoffs/HESTIA_PHASE_6_REPORT_20260410.md`](../handoffs/HESTIA_PHASE_6_REPORT_20260410.md):

- Remove any reference to nonexistent **`src/hestia/tools/decorators.py`**.
- Deduplicate “new vs modified” file lists if `metadata.py` appears twice inconsistently.
- Replace **`[SHA]`** placeholders with **real commit hashes** after you commit (same session).

### 1.3 `docs/HANDOFF_STATE.md`

- Set test count to match **`uv run pytest tests/unit/ tests/integration/ -q`**.
- Set **Last updated** date and **last updated by: Kimi** when you finish closeout.
- State clearly: **Phase 6 ready to merge** after commits land.

**Commit:** `docs: fix deploy README accuracy and Phase 6 handoff`

---

## §2 — Commit discipline (before merge)

Split into logical commits if possible, for example:

1. `feat(cli): observability — logging, version, status, failures` (+ new `logging_config.py`, store query helpers, tests).
2. `docs: README, CHANGELOG, HANDOFF for Phase 6 follow-up`
3. `style: ruff format` (if large formatting-only diff remains — optional squash with (1) if Dylan prefers fewer commits).

Ensure **all** new files are added: `logging_config.py`, `test_cli_commands.py`, `test_logging_config.py`, `test_status_queries.py`, handoff report.

---

## §3 — Gitflow (Dylan executes or approves)

From repo root, after commits are on `feature/phase-6-hardening`:

```bash
git checkout feature/phase-6-hardening
git pull origin feature/phase-6-hardening   # if using remote
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/ tests/
# merge latest develop if needed:
git fetch origin develop
git merge origin/develop   # resolve conflicts if any
uv run pytest tests/unit/ tests/integration/ -q

git checkout develop
git merge feature/phase-6-hardening
git push origin develop
```

Optional: delete remote feature branch after merge, or keep for history.

**Do not merge** until README deploy + handoff SHA sections are fixed.

---

## §4 — Next step after merge

Start **[`KIMI_PHASE_7_MATRIX.md`](./KIMI_PHASE_7_MATRIX.md)** from a **new** branch **`feature/phase-7-matrix`** cut from **updated `develop`**.

---

**End of prompt**

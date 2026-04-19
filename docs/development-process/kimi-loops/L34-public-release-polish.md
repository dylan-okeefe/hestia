# Kimi loop L34 — public-release polish (README, deployment, model recommendations)

## Review carry-forward

From L33c (merged at `8b5228c`, closing the L33 arc):

- Test baseline: **741 passed, 6 skipped**.
- Mypy 0. Ruff 44 — must not regress.
- New env vars / config that need to be documented in the README updates: `HESTIA_EXPERIMENTAL_SKILLS=1` (L33c), `SecurityConfig.injection_entropy_threshold` and `SecurityConfig.injection_skip_filters_for_structured` (L33a), `EmailAdapter.imap_session()` and the new `email_search_and_read` tool (L33b).
- L32 closed the context-builder rework (ADR-0021); L33 closed the perf-and-polish arc (ADR-0022). Both ADRs are reference-worthy from the README architecture section.

From **external public-release evaluation (2026-04-18)**:

- README has no demo/screenshot. Single biggest conversion gap for a public repo.
- README never recommends specific models, parameter counts, or quantizations. Stated audience is "consumer GPU"; users need a concrete starting point (Llama-3.1-8B-Instruct Q4_K_M, Qwen 2.5 7B Instruct Q4_K_M, etc.).
- README does not reference `deploy/` systemd unit files. Self-hosting story is incomplete.
- Email setup guide should be rewritten around the env-var workflow shipped in L29.
- CHANGELOG needs curating for the 0.7→0.8 jump (L35 release).

**Branch:** `feature/l34-public-release-polish` from **`develop`** (post-L33c merge tip `8b5228c`).

**Target version:** **0.7.12** (patch — docs only, but a meaningful one).

## Hard step budget

≤ **7 commits** (one per section), ≤ **1 new test module** (the optional README-links walker). Docs-only — do **not** chase production-code cleanups even if you spot them. Do **not** generate any image/asciicast assets; the spec wants placeholders only.

---

## Goal

Make the README and deployment docs match the bones of the project. No code changes (or only tiny doc-driving changes).

---

## Scope

### §-1 — Merge prep

Branch from `develop` post-L33. `git status` clean.

### §0 — Cleanup carry-forward

(Cursor populates from L33 review.)

### §1 — README model recommendations

New "Recommended models" subsection under "Quickstart" (or wherever the user picks a model). Format as a table:

| Model | Parameters | Quantization | VRAM | Strengths | Notes |
|-------|-----------|--------------|------|-----------|-------|
| Llama-3.1-8B-Instruct | 8B | Q4_K_M | ~6GB | Tool calling, general | Default recommendation |
| Qwen 2.5 7B Instruct | 7B | Q4_K_M | ~5GB | Tool calling, structured output | Solid alternative |
| Llama-3.2-3B-Instruct | 3B | Q5_K_M | ~3GB | Speed | Light identity-check workload |
| Qwen 2.5 14B Instruct | 14B | Q4_K_M | ~10GB | Quality | Needs ≥12GB VRAM |

Include a sentence that says: "Static K-quants (Q4_K_M, Q6_K_M) work well; avoid imatrix (I-) quants, which can corrupt tool-calling. The same project-wide guidance from `~/AGENTS.md` applies."

Pull this list **only** from common open-source models that ship in GGUF on HF; do not invent quants.

### §2 — README deployment section

New "Running Hestia as a daemon" section pointing at `deploy/`:

- List the unit files Cursor finds in `deploy/` (`ls deploy/`); document each one in one or two lines.
- Include the systemd-user enable/start sequence (`systemctl --user daemon-reload && systemctl --user enable --now hestia.service`).
- Cross-link to the env-var pattern (especially `HESTIA_SOUL_PATH`, `HESTIA_CALIBRATION_PATH`, `HESTIA_EXPERIMENTAL_SKILLS`, email `password_env`) so daemon users know how to configure secrets without putting them in source.

### §3 — README demo placeholder

Add a "Demo" subsection near the top with:

- A placeholder for an asciinema recording: a code-block markdown link `[![asciicast](https://asciinema.org/a/PLACEHOLDER.svg)](https://asciinema.org/a/PLACEHOLDER)`. Mark it `<!-- TODO(dylan): record asciicast and replace PLACEHOLDER -->`.
- A static screenshot path placeholder `docs/assets/hestia-chat.png` (do not generate the image; just refer to the path with a TODO).
- Include a small text transcript (3-5 lines) showing a `hestia chat` interaction with one tool call so the section is not empty until the asciicast lands.

### §4 — Email setup guide rewrite

Update `docs/guides/email-setup.md` to:

- Lead with the **env-var** workflow (`password_env: "EMAIL_APP_PASSWORD"` + `export EMAIL_APP_PASSWORD=...`).
- Demote the plaintext `password=` example to a "for ephemeral testing only" callout.
- Reference the ADR consolidation (L29) and the L25 email handoff for design rationale.

### §5 — CHANGELOG curation for 0.7 → 0.8

Add a curated `## [0.7.12] — 2026-04-18` entry for the docs work. **Also** add an unreleased "Towards 0.8.0" preface block explaining what the upcoming `v0.8.0` release rolls up (L20–L34 highlights, including the L32 context-builder rework, the L33 perf-and-polish arc, the cli-decomposition in L30, the orchestrator engine cleanup in L31, and the security/email/style/reflection foundations from L20–L27). L35 will move that preface into the actual `## [0.8.0]` section.

### §6 — Tests / lint pass

- `uv run pytest tests/unit/ tests/integration/ -q` — unchanged (docs-only loop).
- Add a `tests/docs/test_readme_links.py` (optional; only if it's quick): walk all relative links in README.md and assert files exist. This catches the next time someone moves an ADR.

### §7 — Version bump + handoff

- `pyproject.toml` → `0.7.12`.
- `uv lock`.
- `docs/handoffs/L34-public-release-polish-handoff.md`.

**Commits:**

- `docs(readme): model recommendations table`
- `docs(readme): running Hestia as a systemd daemon`
- `docs(readme): demo placeholder + transcript`
- `docs(email): env-var-first setup guide`
- `docs(changelog): curate 0.7.12 + 0.8.0 preface`
- `chore(release): bump to 0.7.12`
- `docs(handoff): L34 public-release polish report`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/hestia tests
ls deploy/
```

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L34
BRANCH=feature/l34-public-release-polish
COMMIT=<sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

---

## Critical Rules Recap

- Docs-only. No production code changes.
- Do not generate images / asciicasts; placeholders only.
- One commit per section.
- Push and stop.

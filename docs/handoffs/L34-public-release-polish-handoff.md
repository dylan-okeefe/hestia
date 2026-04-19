# L34 Public-Release Polish — Handoff

## Scope

Docs-only loop. No production code changes. README, deployment documentation, email setup guide, and CHANGELOG curation for the v0.7.12 patch.

## Spec

- `docs/development-process/kimi-loops/L34-public-release-polish.md`

## Files changed

| Section | File | Change |
|---------|------|--------|
| §3 | `README.md` | New "Demo" placeholder subsection with asciinema link placeholder, screenshot path placeholder, and text transcript |
| §1 | `README.md` | New "Recommended models" table (Llama-3.1-8B, Qwen 2.5 7B, Llama-3.2-3B, Qwen 2.5 14B) with quantization guidance |
| §2 | `README.md` | Expanded "Running Hestia as a daemon" section documenting all `deploy/` unit files, systemd enable/start sequences, and env-var cross-links |
| §4 | `docs/guides/email-setup.md` | Rewritten env-var-first; plaintext `password=` demoted to "ephemeral testing only" callout; added L25/L29 design-rationale references |
| §5 | `CHANGELOG.md` | Curated `[0.7.12]` entry + unreleased "Towards 0.8.0" preface block summarizing L20–L34 arc |
| §6 | `tests/docs/test_readme_links.py` | Optional regression test: walks relative links in README.md and asserts targets exist |
| §6 | `docs/assets/hestia-chat.png` | Zero-byte placeholder for future screenshot (spec: no image generation) |
| §7 | `pyproject.toml` | Version bumped to `0.7.12` |
| §7 | `uv.lock` | Synced to `0.7.12` |

## User-visible behavior changes

1. **README now recommends specific models** (§1). New users get concrete starting points instead of vague "consumer GPU" guidance.
2. **Deployment docs are discoverable from README** (§2). The `deploy/` unit files, install script, and systemd sequences are summarized without leaving the main page.
3. **Email setup prioritizes secrets hygiene** (§4). The env-var pattern (`password_env`) is the primary path; plaintext examples carry a warning.
4. **CHANGELOG previews the 0.8.0 release** (§5). Operators can see what the upcoming tag rolls up before it ships.

## Final gate

```
Tests:    741 passed, 6 skipped (+1 new docs test)
Mypy:     0 errors
Ruff:     44 errors (no regression)
Version:  0.7.12
Branch:   feature/l34-public-release-polish
```

## Design notes for future loops

- The README demo section contains two placeholders (`PLACEHOLDER` asciinema ID, `docs/assets/hestia-chat.png` screenshot). L35 or a manual pass should record real assets and replace them.
- The "Towards 0.8.0" CHANGELOG preface will be moved into the actual `## [0.8.0]` section by L35.
- The README links test (`tests/docs/test_readme_links.py`) should be updated if the project switches to absolute URLs for internal documentation.

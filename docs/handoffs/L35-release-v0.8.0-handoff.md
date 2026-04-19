# L35 handoff — v0.8.0 release

**Date:** 2026-04-18
**Author:** Cursor (release loop, no Kimi)
**Tag:** `v0.8.0`
**Released by:** Dylan (push commands at the bottom)

---

## What this release contains

`v0.8.0` is the first major release on `main` since `v0.2.2` (April 11). It rolls up the entire L20 → L34 arc — 15 Kimi loops, 6 ADRs, ~500 net new tests, and a complete platform/security/email/style/reflection foundation.

Final stats on the `develop` tip going into the merge:

| Metric | v0.2.2 | v0.8.0 |
|--------|--------|--------|
| Tests passing | 250-ish | **741** |
| Mypy errors | uncapped | **0** |
| Ruff errors in `src/` | uncapped | **44** (baseline) |
| ADRs | 13 | **22** |
| Public CLI surface | `chat`, `version` | `chat`, `audit`, `email`, `health`, `memory`, `reflection`, `schedule`, `slot`, `style`, `telegram`, `matrix`, `version`, `(skills experimental)` |

Full feature catalog in `CHANGELOG.md` under `## [0.8.0] — 2026-04-18`.

## Loop manifest (L20 → L34)

| Loop | Merge | Theme |
|------|-------|-------|
| L20 | (pre-window — see kimi-loop-log) | Trust profiles + web_search |
| L21 | (pre-window) | Context resilience + handoff summaries |
| L22 | (pre-window) | Mypy 44 → 0 |
| L23 | (pre-window) | Platform confirmation callbacks |
| L24 | (pre-window) | Injection detection + egress audit |
| L25 | (pre-window) | Email adapter |
| L26 | (pre-window) | Reflection loop |
| L27 | (pre-window) | Style profile |
| L28 | `dcc54c5` | Critical bug fixes (nh3, read_artifact, IMAP injection, Message-ID) |
| L29 | `bbed167` | Reliability + secrets + ADR consolidation |
| L30 | `30a224f` | CLI decomposition (cli.py 2569 → 588 lines + app.py + runners.py); ADR-0020 |
| L31 | `2f20850` | Orchestrator engine cleanup (failure bundles, confirmation, artifact accumulation) |
| L32a | `7ea4a53` | Delete dead `TurnState`/`ToolResult` |
| L32b | `e74ed46` | `ContextBuilder` prefix-layer registry |
| L32c | `6b6fb36` | `ContextBuilder` tokenize cache; ADR-0021 |
| L33a | `d28cdad` | `InjectionScanner` threshold tuning + structured-content filters |
| L33b | `f7dcd91` | `EmailAdapter` IMAP session reuse + `email_search_and_read` |
| L33c | `8b5228c` | Skills experimental flag; ADR-0022; L33-arc handoff |
| L34 | `d51d816` | README polish + deployment docs + email-guide rewrite + CHANGELOG curation |
| L35 | (this handoff) | Release v0.8.0 to main |

## Process notes

This release validates the **mini-loop chunking strategy** introduced after L31:

- L29, L30, L31 each hit the Kimi `--max-steps-per-turn=100` ceiling and required Cursor to manually verify, write `.kimi-done`, and merge.
- L32a, L32b, L32c, L33a, L33b, L33c, L34 — **all clean Kimi runs** (one tiny missed-commit fix on L33b that Cursor caught in the post-merge gate). Each loop ≤ 5 commits, single theme, ≤ 2 new test modules.
- The launcher's `--max-steps-per-turn` was bumped to 250 as belt-and-braces, but no mini-loop has come close to using it.

## What Cursor did locally for L35

1. Bumped `pyproject.toml` from `0.7.12` to `0.8.0`.
2. Bumped `src/hestia/__init__.py` `__version__` from `0.7.0` (stale since pre-window!) to `0.8.0`.
3. `uv lock` synced the lockfile.
4. Promoted the "Towards 0.8.0" CHANGELOG preface into a full `## [0.8.0]` section grouped by theme.
5. Wrote this handoff.
6. Committed everything as a single `chore(release): v0.8.0` commit on `develop`.
7. Created annotated tag `v0.8.0` on the release commit.
8. Merged `develop` into `main` locally with a `--no-ff` merge commit.
9. **STOPPED.** Did not push to origin — that's Dylan's job per `.cursorrules`.

## What Dylan needs to run

```bash
cd ~/Hestia

# Push develop with the release commit
git push origin develop

# Push main with the merge commit
git push origin main

# Push the tag
git push origin v0.8.0
```

After that, optionally cut a GitHub release from the tag and paste in the `[0.8.0]` CHANGELOG section as the release notes. The README's demo placeholder still has a `<!-- TODO(dylan): record asciicast -->` marker — recording one would be a good post-release task but is not blocking.

## What's next (post-release)

The original brainstorm doc had several items still unaddressed:

- Event system / filesystem watcher (proactive intelligence — Hestia notices things without being asked).
- Multi-model routing (small model for trivial work, big model for hard work).
- Temporal knowledge graph (MemPalace-style time-indexed memories).
- Cross-invocation IMAP connection pool (intentionally deferred from L33b).
- Skills framework activation: gate is in place; the framework is invoked nowhere during a turn. Wiring it into `process_turn` is its own design loop.

The honest recommendation from the April-18 reconnaissance still stands: **spend a week using v0.8.0 hard before queueing more loops**. The best backlog prioritization comes from real annoyances, not retrospective audits.
